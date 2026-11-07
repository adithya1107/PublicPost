from datetime import UTC, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import make_article

BASE = datetime(2026, 11, 7, 10, 0, tzinfo=UTC)


def seed(db: Session, count: int, category: str = "Tech", prefix: str = "a") -> None:
    for index in range(count):
        make_article(
            db, f"{prefix}{index:03d}", category=category, published_at=BASE - timedelta(hours=index)
        )


def test_article_has_exactly_the_contract_shape(client: TestClient, db: Session) -> None:
    make_article(db, "abc", image_url="https://example.com/i.jpg", upvotes=3, downvotes=1, comment_count=2)

    assert client.get("/articles/abc").json() == {
        "id": "abc",
        "title": "Title",
        "summary": "Summary",
        "source_name": "Source",
        "article_url": "https://example.com/a",
        "image_url": "https://example.com/i.jpg",
        "category": "Tech",
        "published_at": "2026-11-07T10:00:00Z",
        "upvotes": 3,
        "downvotes": 1,
        "comment_count": 2,
        "user_vote": "none",
    }


def test_missing_image_is_null(client: TestClient, db: Session) -> None:
    make_article(db, "abc", image_url=None)
    assert client.get("/articles/abc").json()["image_url"] is None


def test_dates_are_converted_to_utc_whole_seconds(client: TestClient, db: Session) -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    make_article(db, "abc", published_at=datetime(2026, 11, 7, 15, 30, 0, 123456, tzinfo=ist))
    assert client.get("/articles/abc").json()["published_at"] == "2026-11-07T10:00:00Z"


def test_unknown_article_is_404_with_string_detail(client: TestClient, db: Session) -> None:
    response = client.get("/articles/nope")
    assert response.status_code == 404
    assert response.json() == {"detail": "Article not found"}


def test_list_is_newest_first_with_ten_per_page(client: TestClient, db: Session) -> None:
    seed(db, 25)

    first = client.get("/articles").json()
    assert [a["id"] for a in first] == [f"a{i:03d}" for i in range(10)]

    second = client.get("/articles", params={"page": 2}).json()
    assert [a["id"] for a in second] == [f"a{i:03d}" for i in range(10, 20)]

    third = client.get("/articles", params={"page": 3}).json()
    assert [a["id"] for a in third] == [f"a{i:03d}" for i in range(20, 25)]


def test_page_past_the_end_is_an_empty_list(client: TestClient, db: Session) -> None:
    seed(db, 3)
    response = client.get("/articles", params={"page": 2})
    assert response.status_code == 200
    assert response.json() == []


def test_empty_database_is_an_empty_list(client: TestClient, db: Session) -> None:
    assert client.get("/articles").json() == []


def test_same_timestamp_pages_are_stable_with_no_repeats(client: TestClient, db: Session) -> None:
    for index in range(15):
        make_article(db, f"a{index:03d}", published_at=BASE)

    pages = [client.get("/articles", params={"page": p}).json() for p in (1, 2)]
    ids = [article["id"] for page in pages for article in page]
    assert len(ids) == 15
    assert len(set(ids)) == 15


def test_category_filter(client: TestClient, db: Session) -> None:
    seed(db, 2, "Tech", "t")
    seed(db, 3, "Sports", "s")

    response = client.get("/articles", params={"category": "Sports"}).json()
    assert {a["category"] for a in response} == {"Sports"}
    assert len(response) == 3


def test_blank_category_means_all(client: TestClient, db: Session) -> None:
    seed(db, 2, "Tech", "t")
    seed(db, 1, "Sports", "s")
    assert len(client.get("/articles?category=").json()) == 3


@pytest.mark.parametrize("category", ["India", "World", "Tech", "Sports", "Business", "Science"])
def test_all_six_categories_are_accepted(client: TestClient, db: Session, category: str) -> None:
    assert client.get("/articles", params={"category": category}).status_code == 200


@pytest.mark.parametrize(
    "params",
    [
        {"category": "Politics"},
        {"category": "tech"},
        {"page": 0},
        {"page": -1},
        {"page": "abc"},
        {"page": 10**30},
    ],
)
def test_bad_parameters_are_422_with_string_detail(client: TestClient, params: dict) -> None:
    response = client.get("/articles", params=params)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
