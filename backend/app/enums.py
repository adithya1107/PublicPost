"""Fixed values shared by the database and the API. The iOS app depends on these exact strings."""

from enum import StrEnum


class NewsCategory(StrEnum):
    INDIA = "India"
    WORLD = "World"
    TECH = "Tech"
    SPORTS = "Sports"
    BUSINESS = "Business"
    SCIENCE = "Science"


class VoteValue(StrEnum):
    """What the API accepts and returns. "none" is never stored: it means no vote row exists."""

    UP = "up"
    DOWN = "down"
    NONE = "none"


class ReportReason(StrEnum):
    SPAM = "spam"
    ABUSE = "abuse"
    MISINFORMATION = "misinformation"
    OTHER = "other"
