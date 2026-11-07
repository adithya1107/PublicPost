"""Checks the feed list. The live test reaches real sites: uv run pytest -m live"""

from collections import Counter

import feedparser
import httpx
import pytest

from app.enums import NewsCategory
from app.feeds import FEEDS, Feed
from app.ingestion import USER_AGENT, clean_summary


def test_every_category_has_at_least_two_feeds() -> None:
    counts = Counter(feed.category for feed in FEEDS)
    assert {category: counts[category] for category in NewsCategory if counts[category] < 2} == {}


def test_feed_urls_are_unique_https_with_terms_recorded() -> None:
    assert len({feed.url for feed in FEEDS}) == len(FEEDS)
    assert all(feed.url.startswith("https://") for feed in FEEDS)
    assert all(feed.terms and feed.source_name for feed in FEEDS)


@pytest.mark.live
@pytest.mark.parametrize("feed", FEEDS, ids=lambda f: f"{f.category}-{f.source_name}")
def test_feed_returns_usable_items(feed: Feed) -> None:
    response = httpx.get(
        feed.url, headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True
    )
    assert response.status_code == 200
    entries = feedparser.parse(response.content).entries
    assert entries, "feed has no items"

    usable = [e for e in entries if e.get("title") and e.get("link") and clean_summary(e.get("summary"))]
    assert len(usable) >= len(entries) / 2, "most items should have a title, link and summary"
