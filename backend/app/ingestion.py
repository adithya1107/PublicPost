"""Fetches the RSS feeds and stores new articles. Run once with: python -m app.ingestion

Only titles, short summaries, links and image links are stored, never full article text.
"""

import calendar
import html
import logging
import re
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

import feedparser
import httpx
from sqlalchemy import delete, exists, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, utcnow
from app.feeds import FEEDS, Feed
from app.logging_config import configure_logging
from app.models import Article, Comment
from app.url_utils import article_id, clean_article_url, clean_image_url, is_public_url

logger = logging.getLogger(__name__)

USER_AGENT = "PublicPostBot/1.0"
SUMMARY_WORDS = 60
MAX_ITEMS_PER_FEED = 50
MAX_FEED_BYTES = 5_000_000
MAX_PAGE_BYTES = 512_000
FEED_TIMEOUT_SECONDS = 15
PAGE_TIMEOUT_SECONDS = 5
MAX_REDIRECTS = 3
WORKERS = 8

_TRAILERS = re.compile(
    r"\s*(continue reading\W*|read more\W*|\[(…|\.\.\.)\]|the post .{0,200} appeared first on .{0,100})$",
    re.IGNORECASE,
)
_VIDEO_OR_AUDIO = (".mp4", ".m3u8", ".mov", ".webm", ".mp3")


# --- Text ---------------------------------------------------------------------------------


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip_depth += 1
        self.parts.append(" ")  # so "<p>one</p><p>two</p>" doesn't become "onetwo"

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1
        self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)


def strip_html(value: str | None) -> str:
    """Plain text with entities decoded and whitespace collapsed."""
    extractor = _TextExtractor()
    extractor.feed(value or "")
    extractor.close()
    # Some feeds escape entities twice, which would leave a literal "&nbsp;" in the text.
    return " ".join(html.unescape("".join(extractor.parts)).split())


def trim_to_words(text: str, limit: int = SUMMARY_WORDS) -> str:
    """Trims at a word boundary, ending on a full sentence if one finishes close to the limit."""
    words = text.split()
    if len(words) <= limit:
        return text
    kept = words[:limit]
    for index in range(limit - 1, limit - 16, -1):
        if kept[index].endswith((".", "!", "?")):
            return " ".join(kept[: index + 1])
    return " ".join(kept).rstrip(",;:-–—") + "…"


def clean_summary(value: str | None) -> str:
    text = strip_html(value)
    while True:
        shorter = _TRAILERS.sub("", text)
        if shorter == text:
            return trim_to_words(text)
        text = shorter


# --- Images -------------------------------------------------------------------------------


def _width(item: dict[str, Any]) -> int:
    try:
        return int(item.get("width") or 0)
    except (TypeError, ValueError):
        return 0


def _is_image(item: dict[str, Any], url: str) -> bool:
    mime = (item.get("type") or "").lower()
    medium = (item.get("medium") or "").lower()
    if (mime and not mime.startswith("image/")) or (medium and medium != "image"):
        return False
    return not url.split("?")[0].lower().endswith(_VIDEO_OR_AUDIO)


def extract_image(entry: Any) -> str | None:
    """media:content, then media:thumbnail, then an image enclosure. Prefers the widest."""
    for key in ("media_content", "media_thumbnail"):
        for item in sorted(entry.get(key) or [], key=_width, reverse=True):
            url = item.get("url") or ""
            cleaned = clean_image_url(url)
            if cleaned and _is_image(item, url):
                return cleaned
    for enclosure in entry.get("enclosures") or []:
        if (enclosure.get("type") or "").lower().startswith("image/"):
            cleaned = clean_image_url(enclosure.get("href"))
            if cleaned:
                return cleaned
    return None


class _OpenGraphParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.image: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta" or self.image:
            return
        values = dict(attrs)
        if (values.get("property") or values.get("name")) == "og:image":
            self.image = values.get("content")


def _read_capped(response: httpx.Response, limit: int) -> bytes:
    data = bytearray()
    for chunk in response.iter_bytes():
        data.extend(chunk)
        if len(data) >= limit:
            break
    return bytes(data[:limit])


def fetch_og_image(client: httpx.Client, page_url: str) -> str | None:
    """The page's og:image, or None. Every redirect hop is checked, and only the start of the
    page is read and only that one tag is kept, so article text is never stored."""
    url = page_url
    try:
        for _ in range(MAX_REDIRECTS + 1):
            if not is_public_url(url):
                return None
            with client.stream("GET", url, timeout=PAGE_TIMEOUT_SECONDS, follow_redirects=False) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                content_type = response.headers.get("content-type", "")
                if response.status_code != 200 or "html" not in content_type.lower():
                    return None
                page = _read_capped(response, MAX_PAGE_BYTES)
            parser = _OpenGraphParser()
            parser.feed(page.decode("utf-8", errors="ignore"))
            parser.close()
            return clean_image_url(urljoin(url, parser.image)) if parser.image else None
    except httpx.HTTPError as error:
        logger.debug("og:image lookup failed for %s: %s", page_url, error)
    return None


# --- Feeds --------------------------------------------------------------------------------


def fetch_entries(client: httpx.Client, feed: Feed) -> list[Any]:
    """The feed's newest entries. Raises on any HTTP failure or unusable feed."""
    with client.stream("GET", feed.url, timeout=FEED_TIMEOUT_SECONDS, follow_redirects=True) as response:
        response.raise_for_status()
        body = _read_capped(response, MAX_FEED_BYTES)
    parsed = feedparser.parse(body)
    if not parsed.entries:
        raise ValueError(f"No entries in feed (parser said: {parsed.get('bozo_exception', 'empty')})")
    return parsed.entries[:MAX_ITEMS_PER_FEED]


def _published_at(entry: Any, now: datetime) -> datetime:
    """The item's date in UTC. Missing dates become now, and future dates are clamped to now."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return now
    return min(datetime.fromtimestamp(calendar.timegm(parsed), UTC), now)


def parse_entry(entry: Any, feed: Feed, now: datetime, cutoff: datetime) -> dict[str, Any] | None:
    """Article column values, or None if the item should be skipped."""
    title = strip_html(entry.get("title"))
    url = clean_article_url(entry.get("link"))
    summary = clean_summary(entry.get("summary"))
    published_at = _published_at(entry, now)
    # A card with no summary would be blank. Items past retention would be deleted and
    # re-added on every run, so they're skipped too.
    if not title or not url or not summary or published_at < cutoff:
        return None
    return {
        "id": article_id(url),
        "title": title,
        "summary": summary,
        "source_name": feed.source_name,
        "article_url": url,
        "image_url": extract_image(entry),
        "category": feed.category.value,
        "published_at": published_at,
        "fetched_at": now,
    }


def _fetch_feed_rows(client: httpx.Client, feed: Feed, now: datetime, cutoff: datetime) -> list[dict[str, Any]] | None:
    """Parsed rows for one feed, or None if the feed failed. Never raises."""
    try:
        entries = fetch_entries(client, feed)
    except Exception as error:  # one bad feed must never stop the others
        logger.warning(
            "Feed failed",
            extra={"fields": {"feed": feed.url, "source": feed.source_name, "error": repr(error)}},
        )
        return None

    rows = []
    for entry in entries:
        try:
            row = parse_entry(entry, feed, now, cutoff)
        except Exception:
            logger.warning("Skipped a malformed item in %s", feed.url, exc_info=True)
            continue
        if row:
            rows.append(row)
    return rows


# --- Storage ------------------------------------------------------------------------------


def _insert_new(session: Session, rows: list[dict[str, Any]]) -> int:
    """Inserts rows and ignores any another process added first, so IDs never conflict."""
    if not rows:
        return 0
    insert = postgresql_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    statement = insert(Article).values(rows).on_conflict_do_nothing(index_elements=["id"])
    return len(session.execute(statement.returning(Article.id)).all())


def prune_old_articles(session: Session, cutoff: datetime) -> int:
    """Deletes articles past retention, except any that have comments (even hidden ones)."""
    has_comments = exists().where(Comment.article_id == Article.id)
    statement = delete(Article).where(Article.published_at < cutoff, ~has_comments)
    return session.execute(statement.execution_options(synchronize_session=False)).rowcount


@dataclass(frozen=True)
class IngestionResult:
    feeds_ok: int
    feeds_failed: int
    articles_added: int
    articles_pruned: int


def make_client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT})


def ingest(
    feeds: Iterable[Feed] = FEEDS,
    client: httpx.Client | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
) -> IngestionResult:
    feeds = list(feeds)
    now = utcnow()
    cutoff = now - timedelta(days=get_settings().article_retention_days)
    owns_client = client is None
    http = client or make_client()

    try:
        with ThreadPoolExecutor(WORKERS) as pool:
            results = list(pool.map(lambda feed: _fetch_feed_rows(http, feed, now, cutoff), feeds))

        # If two feeds carry the same story, the earlier feed in the list decides its category.
        candidates: dict[str, dict[str, Any]] = {}
        for rows in results:
            for row in rows or []:
                candidates.setdefault(row["id"], row)

        with session_factory() as session:
            known = set(session.scalars(select(Article.id).where(Article.id.in_(candidates))))
            # Existing articles are left alone, so re-fetching can't touch votes or comment counts.
            new_rows = [row for row in candidates.values() if row["id"] not in known]

            needs_image = [row for row in new_rows if not row["image_url"]]
            with ThreadPoolExecutor(WORKERS) as pool:
                images = pool.map(lambda row: fetch_og_image(http, row["article_url"]), needs_image)
                for row, image in zip(needs_image, images):
                    row["image_url"] = image

            added = _insert_new(session, new_rows)
            pruned = prune_old_articles(session, cutoff)
            session.commit()
    finally:
        if owns_client:
            http.close()

    result = IngestionResult(
        feeds_ok=sum(rows is not None for rows in results),
        feeds_failed=sum(rows is None for rows in results),
        articles_added=added,
        articles_pruned=pruned,
    )
    logger.info("Ingestion finished", extra={"fields": vars(result)})
    return result


def run_ingestion() -> None:
    """Scheduler entry point. A failed run is logged and the next run tries again."""
    try:
        ingest()
    except Exception:
        logger.exception("Ingestion run failed")


if __name__ == "__main__":
    configure_logging(get_settings().log_level)
    print(ingest())
