"""The RSS feeds to ingest. Edit this list to add or remove sources.

Every URL returned a valid feed with summaries when checked on 2026-11-07. Re-check them with:
    uv run pytest -m live

`terms` records what the publisher's terms page said on that date. It is a pointer for your
own review, not legal advice. Most publishers limit reuse, so get permission or legal advice
before launch.

Deliberately left out:
- BBC: its terms say business use of its RSS feeds needs permission, and there may be a fee.
- NPR: its feeds are marked "For Personal Use Only".
- The Indian Express, The Economic Times: few or no summaries in the feed.
- NASA news releases: the summaries contain page navigation text.
"""

from dataclasses import dataclass

from app.enums import NewsCategory


@dataclass(frozen=True)
class Feed:
    url: str
    source_name: str
    category: NewsCategory
    terms: str


THE_HINDU = "https://www.thehindu.com/termsofuse/ - found no wording about reusing RSS; needs review"
HT_MEDIA = "https://www.livemint.com/terms-of-use - covers RSS feeds; personal, non-commercial use"
NDTV = "Terms not checked; needs review"
GUARDIAN = "https://www.theguardian.com/help/terms-of-service - personal, non-commercial use"
AL_JAZEERA = "https://www.aljazeera.com/terms-and-conditions - personal, non-commercial use"
TECHCRUNCH = "https://techcrunch.com/terms-of-service/ - personal, non-commercial use"
CONDE_NAST = "https://www.condenast.com/user-agreement - personal, non-commercial use"
CRICINFO = "Terms page could not be read automatically; needs review"
SCIENCE_DAILY = (
    "https://www.sciencedaily.com/terms.htm - RSS reuse allowed with attribution, but text may "
    "not be edited, and our 60-word trim shortens some summaries"
)

FEEDS: tuple[Feed, ...] = (
    # India
    Feed("https://www.thehindu.com/news/national/feeder/default.rss", "The Hindu", NewsCategory.INDIA, THE_HINDU),
    Feed("https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml", "Hindustan Times", NewsCategory.INDIA, HT_MEDIA),
    Feed("https://feeds.feedburner.com/ndtvnews-india-news", "NDTV", NewsCategory.INDIA, NDTV),
    # World
    Feed("https://www.theguardian.com/world/rss", "The Guardian", NewsCategory.WORLD, GUARDIAN),
    Feed("https://www.aljazeera.com/xml/rss/all.xml", "Al Jazeera", NewsCategory.WORLD, AL_JAZEERA),
    Feed("https://www.thehindu.com/news/international/feeder/default.rss", "The Hindu", NewsCategory.WORLD, THE_HINDU),
    # Tech
    Feed("https://techcrunch.com/feed/", "TechCrunch", NewsCategory.TECH, TECHCRUNCH),
    Feed("https://feeds.arstechnica.com/arstechnica/index", "Ars Technica", NewsCategory.TECH, CONDE_NAST),
    Feed("https://www.thehindu.com/sci-tech/technology/feeder/default.rss", "The Hindu", NewsCategory.TECH, THE_HINDU),
    # Sports
    Feed("https://www.espncricinfo.com/rss/content/story/feeds/0.xml", "ESPNcricinfo", NewsCategory.SPORTS, CRICINFO),
    Feed("https://www.theguardian.com/uk/sport/rss", "The Guardian", NewsCategory.SPORTS, GUARDIAN),
    Feed("https://www.thehindu.com/sport/feeder/default.rss", "The Hindu", NewsCategory.SPORTS, THE_HINDU),
    # Business
    Feed("https://www.livemint.com/rss/companies", "Mint", NewsCategory.BUSINESS, HT_MEDIA),
    Feed("https://www.theguardian.com/uk/business/rss", "The Guardian", NewsCategory.BUSINESS, GUARDIAN),
    Feed("https://www.thehindu.com/business/feeder/default.rss", "The Hindu", NewsCategory.BUSINESS, THE_HINDU),
    # Science
    Feed("https://www.sciencedaily.com/rss/all.xml", "ScienceDaily", NewsCategory.SCIENCE, SCIENCE_DAILY),
    Feed("https://www.theguardian.com/science/rss", "The Guardian", NewsCategory.SCIENCE, GUARDIAN),
    Feed("https://www.thehindu.com/sci-tech/science/feeder/default.rss", "The Hindu", NewsCategory.SCIENCE, THE_HINDU),
)
