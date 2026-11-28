"""The RSS feeds to ingest. Edit this list to add or remove sources."""

from dataclasses import dataclass

from app.enums import NewsCategory


@dataclass(frozen=True)
class Feed:
    url: str
    source_name: str
    category: NewsCategory


FEEDS: tuple[Feed, ...] = (
    # India
    Feed("https://www.thehindu.com/news/national/feeder/default.rss", "The Hindu", NewsCategory.INDIA),
    Feed("https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml", "Hindustan Times", NewsCategory.INDIA),
    Feed("https://feeds.feedburner.com/ndtvnews-india-news", "NDTV", NewsCategory.INDIA),
    # World
    Feed("https://www.theguardian.com/world/rss", "The Guardian", NewsCategory.WORLD),
    Feed("https://www.aljazeera.com/xml/rss/all.xml", "Al Jazeera", NewsCategory.WORLD),
    Feed("https://www.thehindu.com/news/international/feeder/default.rss", "The Hindu", NewsCategory.WORLD),
    # Tech
    Feed("https://techcrunch.com/feed/", "TechCrunch", NewsCategory.TECH),
    Feed("https://feeds.arstechnica.com/arstechnica/index", "Ars Technica", NewsCategory.TECH),
    Feed("https://www.thehindu.com/sci-tech/technology/feeder/default.rss", "The Hindu", NewsCategory.TECH),
    # Sports
    Feed("https://www.espncricinfo.com/rss/content/story/feeds/0.xml", "ESPNcricinfo", NewsCategory.SPORTS),
    Feed("https://www.theguardian.com/uk/sport/rss", "The Guardian", NewsCategory.SPORTS),
    Feed("https://www.thehindu.com/sport/feeder/default.rss", "The Hindu", NewsCategory.SPORTS),
    # Business
    Feed("https://www.livemint.com/rss/companies", "Mint", NewsCategory.BUSINESS),
    Feed("https://www.theguardian.com/uk/business/rss", "The Guardian", NewsCategory.BUSINESS),
    Feed("https://www.thehindu.com/business/feeder/default.rss", "The Hindu", NewsCategory.BUSINESS),
    # Science
    Feed("https://www.sciencedaily.com/rss/all.xml", "ScienceDaily", NewsCategory.SCIENCE),
    Feed("https://www.theguardian.com/science/rss", "The Guardian", NewsCategory.SCIENCE),
    Feed("https://www.thehindu.com/sci-tech/science/feeder/default.rss", "The Hindu", NewsCategory.SCIENCE),
)
