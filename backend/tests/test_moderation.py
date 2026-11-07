import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Article, ArticleVote, Block, Comment, CommentReport, CommentUpvote, User
from tests.factories import auth_headers, make_article, make_comment, make_user

needs_postgres = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Needs PostgreSQL row locks; SQLite doesn't handle concurrent writers",
)


@pytest.fixture
def author(db: Session) -> User:
    return make_user(db, "author@example.com")


@pytest.fixture
def article(db: Session) -> Article:
    return make_article(db, "a1")


@pytest.fixture
def comment(db: Session, author: User, article: Article) -> Comment:
    created = make_comment(db, author)
    article.comment_count = 1
    db.commit()
    return created


def report(client: TestClient, user, comment_id: str, reason: str = "spam"):
    return client.post(f"/comments/{comment_id}/report", json={"reason": reason}, headers=auth_headers(user))


def reporters(db: Session, count: int) -> list[User]:
    return [make_user(db, f"reporter{i}@example.com") for i in range(count)]


def count_rows(db: Session, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def thread_ids(client: TestClient, headers: dict | None = None, article_id: str = "a1") -> list[str]:
    response = client.get(f"/articles/{article_id}/comments", headers=headers or {})
    return [item["id"] for item in response.json()]


def fresh(db: Session, model, key):
    db.expire_all()
    return db.get(model, key)


# --- Reporting ----------------------------------------------------------------------------


@pytest.mark.parametrize("reason", ["spam", "abuse", "misinformation", "other"])
def test_report_returns_204_with_no_body(client: TestClient, db: Session, comment, reason: str) -> None:
    response = report(client, make_user(db), comment.id, reason)
    assert response.status_code == 204
    assert response.content == b""
    assert db.scalar(select(CommentReport.reason)) == reason


def test_reporting_requires_login(client: TestClient, comment) -> None:
    response = client.post(f"/comments/{comment.id}/report", json={"reason": "spam"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Please log in to do that."}


def test_reporting_an_unknown_comment_is_404(client: TestClient, db: Session) -> None:
    response = report(client, make_user(db), "c_missing")
    assert response.status_code == 404
    assert response.json() == {"detail": "Comment not found"}


@pytest.mark.parametrize("body", [{}, {"reason": "boring"}, {"reason": "SPAM"}, {"reason": None}])
def test_invalid_reason_is_422_with_string_detail(client: TestClient, db: Session, comment, body: dict) -> None:
    response = client.post(f"/comments/{comment.id}/report", json=body, headers=auth_headers(make_user(db)))
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    assert count_rows(db, CommentReport) == 0


def test_two_reports_keep_the_comment_visible(client: TestClient, db: Session, comment) -> None:
    for user in reporters(db, 2):
        report(client, user, comment.id)
    assert thread_ids(client) == [comment.id]
    assert fresh(db, Comment, comment.id).is_hidden is False


def test_third_report_hides_the_comment_and_lowers_the_count(client: TestClient, db: Session, comment) -> None:
    for user in reporters(db, 3):
        assert report(client, user, comment.id).status_code == 204

    assert thread_ids(client) == []
    hidden = fresh(db, Comment, comment.id)
    assert hidden.is_hidden is True
    assert hidden.hidden_at is not None
    assert client.get("/articles/a1").json()["comment_count"] == 0


def test_different_reasons_still_count_toward_hiding(client: TestClient, db: Session, comment) -> None:
    for user, reason in zip(reporters(db, 3), ["spam", "abuse", "other"]):
        report(client, user, comment.id, reason)
    assert fresh(db, Comment, comment.id).is_hidden is True


def test_repeat_reports_from_one_user_count_once(client: TestClient, db: Session, comment) -> None:
    user = make_user(db)
    for _ in range(5):
        assert report(client, user, comment.id).status_code == 204

    assert count_rows(db, CommentReport) == 1
    assert fresh(db, Comment, comment.id).is_hidden is False


def test_first_reason_is_kept_on_a_repeat_report(client: TestClient, db: Session, comment) -> None:
    user = make_user(db)
    report(client, user, comment.id, "spam")
    report(client, user, comment.id, "abuse")
    assert db.scalar(select(CommentReport.reason)) == "spam"


def test_reporting_your_own_comment_does_not_count(client: TestClient, db: Session, author, comment) -> None:
    assert report(client, author, comment.id).status_code == 204
    assert count_rows(db, CommentReport) == 0


def test_more_reports_after_hiding_do_not_lower_the_count_again(client: TestClient, db: Session, comment) -> None:
    for user in reporters(db, 6):
        assert report(client, user, comment.id).status_code == 204

    assert count_rows(db, CommentReport) == 6
    assert fresh(db, Article, "a1").comment_count == 0


def test_hiding_one_comment_leaves_others_alone(client: TestClient, db: Session, author, comment, article) -> None:
    other = make_comment(db, author)
    article.comment_count = 2
    db.commit()
    for user in reporters(db, 3):
        report(client, user, comment.id)

    assert thread_ids(client) == [other.id]
    assert fresh(db, Article, "a1").comment_count == 1


def test_hiding_a_parent_leaves_its_replies_visible(client: TestClient, db: Session, author, comment) -> None:
    reply = make_comment(db, author, parent_id=comment.id)
    for user in reporters(db, 3):
        report(client, user, comment.id)
    assert thread_ids(client) == [reply.id]


def test_hidden_comment_stays_in_its_authors_profile(client: TestClient, db: Session, author, comment) -> None:
    for user in reporters(db, 3):
        report(client, user, comment.id)
    mine = client.get("/users/me/comments", headers=auth_headers(author)).json()
    assert [item["id"] for item in mine] == [comment.id]


def test_null_character_in_a_reported_id_is_404(client: TestClient, db: Session) -> None:
    assert report(client, make_user(db), "%00").status_code == 404


# --- Blocking -----------------------------------------------------------------------------


def block(client: TestClient, user, target_id: str):
    return client.post(f"/users/{target_id}/block", headers=auth_headers(user))


def unblock(client: TestClient, user, target_id: str):
    return client.delete(f"/users/{target_id}/block", headers=auth_headers(user))


def test_block_returns_204_and_hides_their_comments_at_once(client: TestClient, db: Session, author, comment) -> None:
    viewer = make_user(db)
    assert thread_ids(client, auth_headers(viewer)) == [comment.id]

    response = block(client, viewer, author.id)

    assert response.status_code == 204
    assert response.content == b""
    assert thread_ids(client, auth_headers(viewer)) == []


def test_unblock_returns_204_and_brings_their_comments_back(client: TestClient, db: Session, author, comment) -> None:
    viewer = make_user(db)
    block(client, viewer, author.id)

    response = unblock(client, viewer, author.id)

    assert response.status_code == 204
    assert thread_ids(client, auth_headers(viewer)) == [comment.id]


def test_block_affects_only_the_person_blocking(client: TestClient, db: Session, author, comment) -> None:
    viewer = make_user(db)
    bystander = make_user(db, "bystander@example.com")
    block(client, viewer, author.id)

    assert thread_ids(client, auth_headers(bystander)) == [comment.id]
    assert thread_ids(client) == [comment.id]
    assert fresh(db, Article, "a1").comment_count == 1


def test_blocking_twice_is_fine_and_stores_one_row(client: TestClient, db: Session, author) -> None:
    viewer = make_user(db)
    assert block(client, viewer, author.id).status_code == 204
    assert block(client, viewer, author.id).status_code == 204
    assert count_rows(db, Block) == 1


def test_concurrent_duplicate_block_is_not_an_error(client: TestClient, db: Session, author, monkeypatch) -> None:
    viewer = make_user(db)
    block(client, viewer, author.id)
    # Simulates losing the race: the existence check saw nothing, but the insert then conflicts.
    real_get = Session.get

    def blind_get(self, entity, ident, **kwargs):
        return None if entity is Block else real_get(self, entity, ident, **kwargs)

    monkeypatch.setattr(Session, "get", blind_get)
    assert block(client, viewer, author.id).status_code == 204


def test_unblocking_someone_not_blocked_is_fine(client: TestClient, db: Session, author) -> None:
    assert unblock(client, make_user(db), author.id).status_code == 204


def test_unblocking_an_unknown_user_is_fine(client: TestClient, db: Session) -> None:
    assert unblock(client, make_user(db), "u_missing").status_code == 204
    assert unblock(client, make_user(db, "b@example.com"), "%00").status_code == 204


def test_blocking_yourself_is_400(client: TestClient, db: Session) -> None:
    user = make_user(db)
    response = block(client, user, user.id)
    assert response.status_code == 400
    assert response.json() == {"detail": "You can't block yourself."}


@pytest.mark.parametrize("target", ["u_missing", "%00"])
def test_blocking_an_unknown_user_is_404(client: TestClient, db: Session, target: str) -> None:
    response = block(client, make_user(db), target)
    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}


def test_block_and_unblock_require_login(client: TestClient, author) -> None:
    assert client.post(f"/users/{author.id}/block").status_code == 401
    assert client.delete(f"/users/{author.id}/block").status_code == 401


def test_a_block_does_not_affect_voting_or_upvoting(client: TestClient, db: Session, author, comment) -> None:
    viewer = make_user(db)
    block(client, viewer, author.id)
    response = client.post(f"/comments/{comment.id}/upvote", json={"upvoted": True}, headers=auth_headers(viewer))
    assert response.status_code == 200


# --- Deleting an account ------------------------------------------------------------------


CREDENTIALS = {"email": "leaver@example.com", "password": "password123"}


@pytest.fixture
def leaver(client: TestClient) -> dict:
    """A real account, so logging in afterwards can be tested properly."""
    body = {"display_name": "Leaver"} | CREDENTIALS
    return client.post("/auth/register", json=body).json()


def bearer(account: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {account['token']}"}


def test_delete_returns_204_with_no_body(client: TestClient, leaver) -> None:
    response = client.delete("/users/me", headers=bearer(leaver))
    assert response.status_code == 204
    assert response.content == b""


def test_delete_requires_login(client: TestClient) -> None:
    response = client.delete("/users/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "Please log in to do that."}


def test_personal_details_are_erased(client: TestClient, db: Session, leaver) -> None:
    client.delete("/users/me", headers=bearer(leaver))

    row = fresh(db, User, leaver["user"]["id"])
    assert row.email is None
    assert row.password_hash is None
    assert row.display_name == "[deleted]"
    assert row.deleted_at is not None


def test_old_token_stops_working_everywhere(client: TestClient, db: Session, leaver, article) -> None:
    client.delete("/users/me", headers=bearer(leaver))

    assert client.delete("/users/me", headers=bearer(leaver)).status_code == 401
    assert client.get("/users/me/comments", headers=bearer(leaver)).status_code == 401
    assert client.post("/articles/a1/vote", json={"vote": "up"}, headers=bearer(leaver)).status_code == 401
    assert client.post("/articles/a1/comments", json={"text": "Hi"}, headers=bearer(leaver)).status_code == 401


def test_old_token_on_public_routes_means_guest(client: TestClient, db: Session, leaver, article) -> None:
    client.delete("/users/me", headers=bearer(leaver))
    response = client.get("/articles", headers=bearer(leaver))
    assert response.status_code == 200
    assert response.json()[0]["user_vote"] == "none"


def test_old_password_stops_working(client: TestClient, leaver) -> None:
    client.delete("/users/me", headers=bearer(leaver))
    assert client.post("/auth/login", json=CREDENTIALS).status_code == 401


def test_comments_stay_with_the_author_shown_as_deleted(client: TestClient, db: Session, leaver, article) -> None:
    posted = client.post("/articles/a1/comments", json={"text": "My words"}, headers=bearer(leaver)).json()
    client.delete("/users/me", headers=bearer(leaver))

    comment = client.get("/articles/a1/comments").json()[0]
    assert comment["id"] == posted["id"]
    assert comment["text"] == "My words"
    assert comment["author_name"] == "[deleted]"
    assert comment["author_id"] == leaver["user"]["id"]
    assert client.get("/articles/a1").json()["comment_count"] == 1


def test_others_replies_and_upvotes_on_their_comment_survive(client: TestClient, db: Session, leaver, article) -> None:
    other = make_user(db)
    posted = client.post("/articles/a1/comments", json={"text": "Hi"}, headers=bearer(leaver)).json()
    client.post(f"/comments/{posted['id']}/upvote", json={"upvoted": True}, headers=auth_headers(other))
    reply = client.post("/articles/a1/comments", json={"text": "Yo", "parent_id": posted["id"]}, headers=auth_headers(other))
    client.delete("/users/me", headers=bearer(leaver))

    thread = client.get("/articles/a1/comments").json()
    assert {item["id"] for item in thread} == {posted["id"], reply.json()["id"]}
    assert next(item for item in thread if item["id"] == posted["id"])["upvotes"] == 1


def test_votes_are_removed_and_counts_corrected(client: TestClient, db: Session, leaver) -> None:
    make_article(db, "up1", upvotes=5, downvotes=1)
    make_article(db, "down1", upvotes=2, downvotes=4)
    make_article(db, "plain1", upvotes=3, downvotes=3)
    client.post("/articles/up1/vote", json={"vote": "up"}, headers=bearer(leaver))
    client.post("/articles/down1/vote", json={"vote": "down"}, headers=bearer(leaver))

    client.delete("/users/me", headers=bearer(leaver))

    db.expire_all()
    assert (db.get(Article, "up1").upvotes, db.get(Article, "up1").downvotes) == (5, 1)
    assert (db.get(Article, "down1").upvotes, db.get(Article, "down1").downvotes) == (2, 4)
    assert (db.get(Article, "plain1").upvotes, db.get(Article, "plain1").downvotes) == (3, 3)
    assert count_rows(db, ArticleVote) == 0


def test_other_peoples_votes_are_untouched(client: TestClient, db: Session, leaver, article) -> None:
    other = make_user(db)
    client.post("/articles/a1/vote", json={"vote": "up"}, headers=auth_headers(other))
    client.post("/articles/a1/vote", json={"vote": "up"}, headers=bearer(leaver))

    client.delete("/users/me", headers=bearer(leaver))

    assert fresh(db, Article, "a1").upvotes == 1
    assert client.get("/articles/a1", headers=auth_headers(other)).json()["user_vote"] == "up"


def test_comment_upvotes_are_removed_and_counts_corrected(client: TestClient, db: Session, leaver, author, comment) -> None:
    other = make_user(db)
    client.post(f"/comments/{comment.id}/upvote", json={"upvoted": True}, headers=auth_headers(other))
    client.post(f"/comments/{comment.id}/upvote", json={"upvoted": True}, headers=bearer(leaver))

    client.delete("/users/me", headers=bearer(leaver))

    assert fresh(db, Comment, comment.id).upvotes == 1
    assert count_rows(db, CommentUpvote) == 1


def test_email_can_register_again_as_a_new_person(client: TestClient, leaver, article) -> None:
    client.post("/articles/a1/comments", json={"text": "Old"}, headers=bearer(leaver))
    client.delete("/users/me", headers=bearer(leaver))

    again = client.post("/auth/register", json={"display_name": "Back Again"} | CREDENTIALS)

    assert again.status_code == 200
    assert again.json()["user"]["id"] != leaver["user"]["id"]
    assert client.get("/users/me/comments", headers=bearer(again.json())).json() == []
    assert client.get("/articles/a1/comments").json()[0]["author_name"] == "[deleted]"


def test_blocks_they_made_are_removed(client: TestClient, db: Session, leaver, author) -> None:
    client.post(f"/users/{author.id}/block", headers=bearer(leaver))
    client.delete("/users/me", headers=bearer(leaver))
    assert count_rows(db, Block) == 0


def test_blocks_on_them_are_kept_so_they_cannot_reappear(client: TestClient, db: Session, leaver, article) -> None:
    viewer = make_user(db)
    posted = client.post("/articles/a1/comments", json={"text": "Rude"}, headers=bearer(leaver)).json()
    client.post(f"/users/{leaver['user']['id']}/block", headers=auth_headers(viewer))

    client.delete("/users/me", headers=bearer(leaver))

    assert thread_ids(client, auth_headers(viewer)) == []
    assert thread_ids(client) == [posted["id"]]


def test_reports_they_filed_keep_a_comment_hidden(client: TestClient, db: Session, leaver, comment) -> None:
    client.post(f"/comments/{comment.id}/report", json={"reason": "spam"}, headers=bearer(leaver))
    for user in reporters(db, 2):
        report(client, user, comment.id)

    client.delete("/users/me", headers=bearer(leaver))

    assert fresh(db, Comment, comment.id).is_hidden is True
    assert count_rows(db, CommentReport) == 3


def test_a_report_after_deletion_counts_toward_hiding_their_comment(client: TestClient, db: Session, leaver, article) -> None:
    posted = client.post("/articles/a1/comments", json={"text": "Hi"}, headers=bearer(leaver)).json()
    client.delete("/users/me", headers=bearer(leaver))
    for user in reporters(db, 3):
        report(client, user, posted["id"])
    assert thread_ids(client) == []


# --- Concurrency --------------------------------------------------------------------------


@needs_postgres
def test_simultaneous_reports_hide_once_and_lower_the_count_once(client: TestClient, db: Session, comment) -> None:
    users = reporters(db, 12)

    with ThreadPoolExecutor(8) as pool:
        codes = list(pool.map(lambda user: report(client, user, comment.id).status_code, users))

    assert set(codes) == {204}
    assert fresh(db, Article, "a1").comment_count == 0
    assert fresh(db, Comment, comment.id).is_hidden is True
    assert count_rows(db, CommentReport) == 12


@needs_postgres
def test_simultaneous_deletes_subtract_votes_only_once(client: TestClient, db: Session, leaver, article) -> None:
    make_article(db, "a2", upvotes=5)
    client.post("/articles/a2/vote", json={"vote": "up"}, headers=bearer(leaver))
    assert fresh(db, Article, "a2").upvotes == 6

    with ThreadPoolExecutor(6) as pool:
        codes = list(pool.map(lambda _: client.delete("/users/me", headers=bearer(leaver)).status_code, range(6)))

    assert set(codes) <= {204, 401}
    assert 204 in codes
    assert fresh(db, Article, "a2").upvotes == 5


@needs_postgres
def test_deleting_accounts_while_others_report_does_not_deadlock(client: TestClient, db: Session, author, article) -> None:
    comments = [make_comment(db, author) for _ in range(4)]
    article.comment_count = len(comments)
    db.commit()
    leavers = []
    for index in range(6):
        user = make_user(db, f"leaver{index}@example.com")
        leavers.append(user)
        for target in comments:
            client.post(f"/comments/{target.id}/upvote", json={"upvoted": True}, headers=auth_headers(user))
        client.post("/articles/a1/vote", json={"vote": "up"}, headers=auth_headers(user))
    people = reporters(db, 12)

    def act(index: int) -> int:
        if index < len(leavers):
            return client.delete("/users/me", headers=auth_headers(leavers[index])).status_code
        target = comments[index % len(comments)]
        return report(client, people[index - len(leavers)], target.id).status_code

    with ThreadPoolExecutor(8) as pool:
        codes = list(pool.map(act, range(len(leavers) + len(people))))

    assert set(codes) == {204}
    db.expire_all()
    assert db.get(Article, "a1").upvotes == 0
    assert all(db.get(Comment, target.id).upvotes == 0 for target in comments)
    visible = db.scalar(select(func.count()).select_from(Comment).where(Comment.is_hidden.is_(False)))
    assert db.get(Article, "a1").comment_count == visible
