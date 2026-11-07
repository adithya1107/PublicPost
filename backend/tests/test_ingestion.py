"""Ingestion against fake feeds. No real network: httpx uses a mock transport."""

import socket
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from xml.sax.saxutils import escape

import feedparser
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ingestion
from app.config import get_settings
from app.enums import NewsCategory
from app.feeds import Feed
from app.ingestion import (
    clean_summary,
    extract_image,
    fetch_og_image,
    ingest,
    run_ingestion,
    strip_html,
    trim_to_words,
)
from app.main import create_app
from app.models import Article, ArticleVote, Comment
from app.url_utils import article_id
from tests.factories import make_article, make_user

MEDIA_NS = 'xmlns:media="http://search.yahoo.com/mrss/"'
TECH_FEED = Feed("https://feeds.test/tech", "Tech Source", NewsCategory.TECH, "test")
WORLD_FEED = Feed("https://feeds.test/world", "World Source", NewsCategory.WORLD, "test")


def item(
    slug: str = "story",
    title: str | None = "A title",
    summary: str = "A summary.",
    published: datetime | None = None,
    extra: str = "",
    link: str | None = None,
) -> str:
    published = published or datetime.now(UTC) - timedelta(hours=1)
    url = link if link is not None else f"https://news.test/{slug}"
    parts = [
        f"<title>{escape(title)}</title>" if title is not None else "",
        f"<link>{escape(url)}</link>" if url else "",
        f"<description>{escape(summary)}</description>",
        f"<pubDate>{format_datetime(published)}</pubDate>",
        extra,
    ]
    return f"<item>{''.join(parts)}</item>"


def rss(*items: str) -> str:
    return f'<?xml version="1.0"?><rss version="2.0" {MEDIA_NS}><channel><title>T</title>{"".join(items)}</channel></rss>'


def entry_with(extra: str):
    return feedparser.parse(rss(item(extra=extra))).entries[0]


Handler = Callable[[httpx.Request], httpx.Response]


def client_for(routes: dict[str, str | Handler]) -> httpx.Client:
    """Feed URLs map to RSS text or a handler. Unknown URLs are 404s, like a page with no image."""

    def handle(request: httpx.Request) -> httpx.Response:
        route = routes.get(str(request.url))
        if route is None:
            return httpx.Response(404)
        return route(request) if callable(route) else httpx.Response(200, text=route)

    return httpx.Client(transport=httpx.MockTransport(handle))


@pytest.fixture(autouse=True)
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(0, 0, 0, "", ("93.184.216.34", 0))])


def stored(db: Session) -> list[Article]:
    db.expire_all()
    return list(db.scalars(select(Article).order_by(Article.title)))


# --- Text ---------------------------------------------------------------------------------


def test_html_is_stripped_and_whitespace_collapsed() -> None:
    assert strip_html("<p>One  &amp;\n two</p><p>three &#039;four&#039;</p>") == "One & two three 'four'"


def test_double_escaped_entities_are_decoded() -> None:
    assert strip_html("A retail expansion.&amp;nbsp;") == "A retail expansion."


def test_script_and_style_content_is_dropped() -> None:
    assert strip_html("Hi<script>alert(1)</script><style>p{}</style> there") == "Hi there"


@pytest.mark.parametrize(
    "tail",
    [
        '<a href="https://x.test">Continue reading...</a>',
        "Read more",
        "[…]",
        "[...]",
        "The post A story appeared first on Some Site.",
    ],
)
def test_feed_boilerplate_is_removed(tail: str) -> None:
    assert clean_summary(f"<p>A real summary.</p> {tail}") == "A real summary."


def test_short_summary_is_unchanged() -> None:
    text = " ".join(["word"] * 60)
    assert trim_to_words(text) == text


def test_long_summary_is_trimmed_at_a_word_boundary_with_an_ellipsis() -> None:
    trimmed = trim_to_words(" ".join(f"w{i}" for i in range(200)))
    assert trimmed.endswith("w59…")
    assert len(trimmed.split()) == 60


def test_long_summary_ends_on_a_nearby_sentence_when_it_can() -> None:
    words = [f"w{i}" for i in range(200)]
    words[54] = "end."
    trimmed = trim_to_words(" ".join(words))
    assert trimmed.endswith("end.")
    assert len(trimmed.split()) == 55


def test_trim_drops_dangling_punctuation() -> None:
    words = [f"w{i}" for i in range(200)]
    words[59] = "dangling,"
    assert trim_to_words(" ".join(words)).endswith("dangling…")


# --- Images -------------------------------------------------------------------------------


def test_media_content_prefers_the_widest_image() -> None:
    entry = entry_with(
        '<media:content url="https://i.test/small.jpg" width="140"/>'
        '<media:content url="https://i.test/large.jpg" width="1200"/>'
    )
    assert extract_image(entry) == "https://i.test/large.jpg"


def test_video_media_content_is_skipped_for_a_thumbnail() -> None:
    entry = entry_with(
        '<media:content url="https://i.test/clip.mp4" type="video/mp4"/>'
        '<media:thumbnail url="https://i.test/thumb.jpg"/>'
    )
    assert extract_image(entry) == "https://i.test/thumb.jpg"


def test_image_enclosure_is_used() -> None:
    entry = entry_with('<enclosure url="http://i.test/e.jpg" type="image/jpeg" length="1"/>')
    assert extract_image(entry) == "https://i.test/e.jpg"


def test_audio_enclosure_is_ignored() -> None:
    entry = entry_with('<enclosure url="https://i.test/e.mp3" type="audio/mpeg" length="1"/>')
    assert extract_image(entry) is None


def test_unreadable_image_width_is_treated_as_unknown() -> None:
    entry = entry_with(
        '<media:content url="https://i.test/odd.jpg" width="wide"/>'
        '<media:content url="https://i.test/large.jpg" width="800"/>'
    )
    assert extract_image(entry) == "https://i.test/large.jpg"


def test_og_lookup_reads_only_the_start_of_a_huge_page() -> None:
    late_tag = b'<meta property="og:image" content="https://i.test/late.jpg">'
    body = b"x" * ingestion.MAX_PAGE_BYTES + late_tag
    client = client_for(
        {"https://news.test/a": lambda _: httpx.Response(200, content=body, headers={"content-type": "text/html"})}
    )
    assert fetch_og_image(client, "https://news.test/a") is None


PAGE = '<html><head><meta property="og:image" content="/img/og.jpg"></head><body>Secret text</body></html>'


def html_response(body: str, status: int = 200) -> Handler:
    return lambda _: httpx.Response(status, text=body, headers={"content-type": "text/html; charset=utf-8"})


def test_og_image_is_found_and_made_absolute() -> None:
    client = client_for({"https://news.test/a": html_response(PAGE)})
    assert fetch_og_image(client, "https://news.test/a") == "https://news.test/img/og.jpg"


def test_og_image_works_with_attributes_in_either_order() -> None:
    page = '<meta content="https://i.test/x.jpg" name="og:image">'
    client = client_for({"https://news.test/a": html_response(page)})
    assert fetch_og_image(client, "https://news.test/a") == "https://i.test/x.jpg"


@pytest.mark.parametrize(
    "handler",
    [
        html_response("<html><head></head></html>"),
        html_response(PAGE, status=403),
        lambda _: httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"}),
    ],
)
def test_og_image_is_none_when_unavailable(handler: Handler) -> None:
    client = client_for({"https://news.test/a": handler})
    assert fetch_og_image(client, "https://news.test/a") is None


def test_og_image_is_none_on_network_error() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("too slow", request=request)

    assert fetch_og_image(client_for({"https://news.test/a": fail}), "https://news.test/a") is None


def test_og_lookup_follows_public_redirects() -> None:
    client = client_for(
        {
            "https://news.test/a": lambda _: httpx.Response(302, headers={"location": "/b"}),
            "https://news.test/b": html_response(PAGE),
        }
    )
    assert fetch_og_image(client, "https://news.test/a") == "https://news.test/img/og.jpg"


def test_og_lookup_refuses_a_redirect_to_a_private_address(monkeypatch: pytest.MonkeyPatch) -> None:
    def resolve(host, *args, **kwargs):
        address = "10.0.0.5" if host == "internal.test" else "93.184.216.34"
        return [(0, 0, 0, "", (address, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    requested: list[str] = []

    def internal(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, text=PAGE, headers={"content-type": "text/html"})

    client = client_for(
        {
            "https://news.test/a": lambda _: httpx.Response(302, headers={"location": "https://internal.test/x"}),
            "https://internal.test/x": internal,
        }
    )
    assert fetch_og_image(client, "https://news.test/a") is None
    assert requested == []


def test_og_lookup_gives_up_on_a_redirect_loop() -> None:
    client = client_for({"https://news.test/a": lambda _: httpx.Response(302, headers={"location": "/a"})})
    assert fetch_og_image(client, "https://news.test/a") is None


# --- Ingest -------------------------------------------------------------------------------


def test_items_are_stored_with_every_field(db: Session) -> None:
    published = datetime.now(UTC) - timedelta(hours=1)
    body = rss(
        item(
            title="A <b>bold</b> title",
            summary="<p>Some <b>summary</b></p>",
            published=published,
            link="https://news.test/s?utm_source=rss",
            extra='<media:content url="http://i.test/a.jpg" medium="image"/>',
        )
    )
    result = ingest([TECH_FEED], client_for({TECH_FEED.url: body}))

    assert (result.feeds_ok, result.feeds_failed, result.articles_added) == (1, 0, 1)
    article = stored(db)[0]
    assert article.id == article_id("https://news.test/s")
    assert article.title == "A bold title"
    assert article.summary == "Some summary"
    assert article.source_name == "Tech Source"
    assert article.article_url == "https://news.test/s"
    assert article.image_url == "https://i.test/a.jpg"
    assert article.category == "Tech"
    assert article.published_at == published.replace(microsecond=0)


def test_refetching_never_duplicates(db: Session) -> None:
    client = client_for({TECH_FEED.url: rss(item("a"), item("b"))})
    assert ingest([TECH_FEED], client).articles_added == 2
    assert ingest([TECH_FEED], client).articles_added == 0
    assert len(stored(db)) == 2


def test_tracking_variants_of_a_link_are_one_article(db: Session) -> None:
    body = rss(
        item(link="https://news.test/s?utm_source=rss"),
        item(link="https://news.test/s/?utm_source=twitter#top"),
    )
    assert ingest([TECH_FEED], client_for({TECH_FEED.url: body})).articles_added == 1


def test_refetching_keeps_counts_and_original_text(db: Session) -> None:
    client = client_for({TECH_FEED.url: rss(item("a", title="Original"))})
    ingest([TECH_FEED], client)
    article = stored(db)[0]
    article.upvotes = 5
    article.comment_count = 2
    db.commit()

    ingest([TECH_FEED], client_for({TECH_FEED.url: rss(item("a", title="Edited"))}))

    article = stored(db)[0]
    assert (article.upvotes, article.comment_count, article.title) == (5, 2, "Original")


def test_first_feed_decides_the_category_of_a_shared_story(db: Session) -> None:
    routes = {TECH_FEED.url: rss(item("shared")), WORLD_FEED.url: rss(item("shared"))}
    ingest([TECH_FEED, WORLD_FEED], client_for(routes))
    assert [a.category for a in stored(db)] == ["Tech"]


def test_unusable_items_are_skipped(db: Session) -> None:
    body = rss(
        item("no-title", title=None),
        item("blank-title", title="   "),
        item(link=""),
        item(link="ftp://news.test/file"),
        item("no-summary", summary=""),
        item("old", published=datetime.now(UTC) - timedelta(days=15)),
        item("good", title="Good"),
    )
    ingest([TECH_FEED], client_for({TECH_FEED.url: body}))
    assert [a.title for a in stored(db)] == ["Good"]


def test_future_dates_are_clamped_to_now(db: Session) -> None:
    body = rss(item(published=datetime.now(UTC) + timedelta(days=3)))
    ingest([TECH_FEED], client_for({TECH_FEED.url: body}))
    assert stored(db)[0].published_at <= datetime.now(UTC)


def test_missing_date_uses_now(db: Session) -> None:
    body = rss("<item><title>T</title><link>https://news.test/x</link><description>S</description></item>")
    before = datetime.now(UTC) - timedelta(seconds=5)
    ingest([TECH_FEED], client_for({TECH_FEED.url: body}))
    assert stored(db)[0].published_at >= before


def test_feed_item_limit_is_applied(db: Session) -> None:
    body = rss(*[item(f"s{i}") for i in range(ingestion.MAX_ITEMS_PER_FEED + 5)])
    result = ingest([TECH_FEED], client_for({TECH_FEED.url: body}))
    assert result.articles_added == ingestion.MAX_ITEMS_PER_FEED


def test_long_description_is_never_stored_in_full(db: Session) -> None:
    body = rss(item(summary=" ".join(f"word{i}" for i in range(5000))))
    ingest([TECH_FEED], client_for({TECH_FEED.url: body}))
    assert len(stored(db)[0].summary.split()) <= ingestion.SUMMARY_WORDS


def timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectTimeout("too slow", request=request)


@pytest.mark.parametrize(
    "bad_feed",
    [
        lambda _: httpx.Response(500),
        lambda _: httpx.Response(404),
        lambda _: httpx.Response(200, text="<html>This is not a feed</html>"),
        lambda _: httpx.Response(200, text=rss()),
        timeout,
    ],
)
def test_one_failing_feed_does_not_stop_the_others(
    db: Session, bad_feed: Handler, caplog: pytest.LogCaptureFixture
) -> None:
    routes = {TECH_FEED.url: bad_feed, WORLD_FEED.url: rss(item("good", title="Good"))}
    result = ingest([TECH_FEED, WORLD_FEED], client_for(routes))

    assert (result.feeds_ok, result.feeds_failed, result.articles_added) == (1, 1, 1)
    assert [a.title for a in stored(db)] == ["Good"]
    assert any(r.message == "Feed failed" and r.levelname == "WARNING" for r in caplog.records)


def test_one_malformed_item_does_not_lose_the_rest_of_the_feed(
    db: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    real_parse = ingestion.parse_entry

    def flaky_parse(entry, *args):
        if entry.get("title") == "Broken":
            raise KeyError("unexpected item shape")
        return real_parse(entry, *args)

    monkeypatch.setattr(ingestion, "parse_entry", flaky_parse)
    body = rss(item("a", title="Broken"), item("b", title="Good"))
    result = ingest([TECH_FEED], client_for({TECH_FEED.url: body}))

    assert result.feeds_ok == 1
    assert [a.title for a in stored(db)] == ["Good"]
    assert "Skipped a malformed item" in caplog.text


def test_ingest_creates_and_closes_its_own_client(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    client = client_for({TECH_FEED.url: rss(item("a"))})
    monkeypatch.setattr(ingestion, "make_client", lambda: client)

    assert ingest([TECH_FEED]).articles_added == 1
    assert client.is_closed


def test_real_client_identifies_itself_without_personal_details() -> None:
    with ingestion.make_client() as client:
        assert client.headers["user-agent"] == "PublicPostBot/1.0"


def test_og_image_is_looked_up_for_new_articles_only(db: Session) -> None:
    calls: list[str] = []

    def page(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text=PAGE, headers={"content-type": "text/html"})

    client = client_for({TECH_FEED.url: rss(item("a")), "https://news.test/a": page})
    ingest([TECH_FEED], client)
    ingest([TECH_FEED], client)

    assert calls == ["https://news.test/a"]
    assert stored(db)[0].image_url == "https://news.test/img/og.jpg"


def test_og_page_text_is_never_stored(db: Session) -> None:
    client = client_for(
        {TECH_FEED.url: rss(item("a")), "https://news.test/a": html_response(PAGE)}
    )
    ingest([TECH_FEED], client)
    article = stored(db)[0]
    assert "Secret text" not in article.summary
    assert article.image_url == "https://news.test/img/og.jpg"


def test_failed_og_lookup_leaves_the_image_null(db: Session) -> None:
    ingest([TECH_FEED], client_for({TECH_FEED.url: rss(item("a"))}))
    assert stored(db)[0].image_url is None


# --- Retention ----------------------------------------------------------------------------


def test_pruning_follows_the_retention_rules(db: Session) -> None:
    author = make_user(db)
    old = datetime.now(UTC) - timedelta(days=15)
    make_article(db, "recent", published_at=datetime.now(UTC) - timedelta(days=13))
    make_article(db, "old-plain", published_at=old)
    make_article(db, "old-commented", published_at=old)
    make_article(db, "old-hidden", published_at=old)
    make_article(db, "old-voted", published_at=old)
    db.add(Comment(article_id="old-commented", author_id=author.id, text="Keep"))
    db.add(Comment(article_id="old-hidden", author_id=author.id, text="Keep", is_hidden=True))
    db.add(ArticleVote(user_id=author.id, article_id="old-voted", value="up"))
    db.commit()

    result = ingest([], client_for({}))

    assert result.articles_pruned == 2
    db.expire_all()
    remaining = set(db.scalars(select(Article.id)))
    assert remaining == {"recent", "old-commented", "old-hidden"}
    assert db.scalars(select(ArticleVote)).all() == []


# --- Scheduling ---------------------------------------------------------------------------


def test_a_failed_run_is_logged_and_does_not_raise(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def explode() -> None:
        raise RuntimeError("database is down")

    monkeypatch.setattr(ingestion, "ingest", explode)
    run_ingestion()
    assert "Ingestion run failed" in caplog.text


def test_scheduler_runs_at_startup_then_on_the_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    import threading

    from app import scheduler as scheduler_module

    ran = threading.Event()
    monkeypatch.setattr(scheduler_module, "run_ingestion", ran.set)

    scheduler = scheduler_module.start_scheduler(20)
    try:
        assert ran.wait(timeout=5), "the job should run once at startup"
        job = scheduler.get_job("ingest_news")
        assert job.trigger.interval == timedelta(minutes=20)
        assert job.max_instances == 1
    finally:
        scheduler.shutdown(wait=False)


def test_app_starts_and_stops_the_scheduler_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import main as main_module

    events: list[object] = []

    class FakeScheduler:
        def shutdown(self, wait: bool) -> None:
            events.append("stopped")

    def fake_start(interval: int) -> FakeScheduler:
        events.append(interval)
        return FakeScheduler()

    monkeypatch.setattr(main_module, "start_scheduler", fake_start)
    monkeypatch.setenv("INGESTION_ENABLED", "true")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            assert client.get("/health").status_code == 200
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()

    assert events == [20, "stopped"]
