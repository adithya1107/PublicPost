# PublicPost backend

The API and news ingestion behind the PublicPost iOS app: a short-news feed with voting and
discussion. Built with FastAPI, SQLAlchemy 2, Alembic and Pydantic v2. It uses SQLite for local
development and PostgreSQL in production.

## Run it locally

You need [uv](https://docs.astral.sh/uv/getting-started/installation/), which also installs
Python 3.12 if you don't have it.

```bash
cd backend
uv sync
cp .env.example .env
```

Generate a secret and paste it after `JWT_SECRET=` in `.env`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Then create the database and start the server:

```bash
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

The server fetches news in the background at startup, so articles appear within a few seconds.

```bash
curl http://127.0.0.1:8000/health
curl "http://127.0.0.1:8000/articles?category=Tech"
```

Interactive API docs are at <http://127.0.0.1:8000/docs> (turned off in production).

To fetch news once without starting the server:

```bash
uv run python -m app.ingestion
```

### Connecting the iOS app

The simulator can reach `http://127.0.0.1:8000` directly. A real iPhone needs your Mac's LAN IP,
with the server started using `--host 0.0.0.0`. The app's base URL is `Config.baseURL`.

## Configuration

Everything is set through environment variables, or `backend/.env` locally.

| Variable | Default | Purpose |
|---|---|---|
| `JWT_SECRET` | none, **required** | Signs login tokens. At least 32 characters. |
| `DATABASE_URL` | `sqlite:///./publicpost.db` | Database. `postgres://` and `postgresql://` URLs both work. |
| `APP_ENV` | `development` | `production` turns off the `/docs` pages. |
| `JWT_EXPIRE_DAYS` | `30` | How long login tokens last. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. |
| `INGESTION_ENABLED` | `true` | Background RSS fetching. |
| `INGESTION_INTERVAL_MINUTES` | `20` | Time between fetches. |
| `ARTICLE_RETENTION_DAYS` | `14` | Older articles are deleted, unless they have comments. |
| `RATE_LIMITS_ENABLED` | `true` | Keep this on in production. |

## API

All JSON, with snake_case keys, string IDs and UTC dates like `2026-11-07T10:00:00Z`. Errors look
like `{"detail": "message"}`, and `detail` is always a string.

| Method and path | Auth | Body | Returns |
|---|---|---|---|
| `GET /health` | | | `{"status": "ok"}`, or 503 if the database is unreachable |
| `GET /articles?category=&page=` | optional | | `[Article]`, newest first, 10 per page |
| `GET /articles/{id}` | optional | | `Article` |
| `POST /articles/{id}/vote` | required | `{"vote": "up"\|"down"\|"none"}` | `{"upvotes", "downvotes", "user_vote"}` |
| `GET /articles/{id}/comments` | optional | | `[Comment]`, oldest first |
| `POST /articles/{id}/comments` | required | `{"text", "parent_id"?}` | `Comment` |
| `POST /comments/{id}/upvote` | required | `{"upvoted": bool}` | `{"upvotes"}` |
| `POST /comments/{id}/report` | required | `{"reason": "spam"\|"abuse"\|"misinformation"\|"other"}` | 204 |
| `GET /users/me/comments` | required | | `[Comment]`, newest first |
| `POST /users/{id}/block` | required | | 204 |
| `DELETE /users/{id}/block` | required | | 204 |
| `DELETE /users/me` | required | | 204 |
| `POST /auth/register` | | `{"display_name", "email", "password"}` | `{"token", "user"}` |
| `POST /auth/login` | | `{"email", "password"}` | `{"token", "user"}` |

Authenticated requests send `Authorization: Bearer <token>`. Protected routes return 401 for a
missing, invalid or expired token. On "optional" routes a bad token is treated as a guest, not an
error.

**Article:** `id`, `title`, `summary`, `source_name`, `article_url`, `image_url` (nullable),
`category`, `published_at`, `upvotes`, `downvotes`, `comment_count`, `user_vote`.

**Comment:** `id`, `article_id`, `author_id`, `author_name`, `text`, `created_at`, `upvotes`,
`parent_id` (nullable), `user_upvoted`.

**User:** `id`, `display_name`.

**Categories:** `India`, `World`, `Tech`, `Sports`, `Business`, `Science`.

### Limits

| What | Limit | Counted per |
|---|---|---|
| `POST /auth/login` | 10 a minute | IP address |
| `POST /auth/register` | 5 a minute | IP address |
| `POST /articles/{id}/comments` | 10 a minute, across all articles | user |
| `POST /articles/{id}/vote` | 60 a minute, across all articles | user |
| `POST /comments/{id}/upvote` | 60 a minute, across all comments | user |
| Any request body | 64 KB | request |

Going over a rate limit returns 429 with a `Retry-After` header. An oversized body returns 413.

Limits are held in memory, so they reset on restart and assume **one server process**. The
scheduled news fetch assumes the same, so run uvicorn with a single worker.

Behind a hosting proxy, uvicorn must be told to trust the forwarded address. Otherwise every user
appears to share the proxy's IP, and the login and registration limits apply to everyone at once.

## News ingestion

`app/feeds.py` holds the feed list, along with what each publisher's terms said when checked.
A background job fetches all feeds at startup and then every 20 minutes:

- **IDs:** the first 16 hex characters of the SHA-256 of the normalised URL, so re-fetching never
  creates duplicates. Normalising removes tracking parameters and fragments.
- **Summaries:** the feed's description with HTML removed, trimmed to about 60 words. Full article
  text is never stored.
- **Images:** from `media:content`, `media:thumbnail` or an image enclosure. Otherwise the start of
  the article page is read for its `og:image` tag, and if that fails the image is `null`.
- **Skipped items:** no title, no usable link, no summary, or older than the retention period.
- **Existing articles:** never updated by later fetches, so publisher corrections don't appear.
- **Failures:** a failing feed is logged and the others carry on.

**Publisher terms:** most publishers limit how their feeds can be reused. Review the notes in
`app/feeds.py` and get permission or legal advice before launching publicly.

## Tests

```bash
uv run pytest                                     # everything offline, on SQLite
uv run pytest --cov=app --cov-report=term-missing # with coverage
uv run pytest -m live                             # checks the real feeds still work
```

Some tests need real PostgreSQL row locks and are skipped on SQLite. Your production database is
PostgreSQL, so run these before deploying. Both databases must be empty and separate, because the
tests erase their contents:

```bash
createdb publicpost_test
createdb publicpost_migrations
TEST_DATABASE_URL=postgresql://localhost/publicpost_test \
TEST_POSTGRES_URL=postgresql://localhost/publicpost_migrations \
uv run pytest
```

## Database changes

Change `app/models.py`, then generate and review a migration:

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
```

Always read the generated file and run it on PostgreSQL. Alembic can generate defaults that only
work on SQLite.

## Moderating comments

A comment is hidden automatically after reports from 3 different users. There's no admin screen,
so review happens directly in the database. **Check reports regularly:** App Store guideline 1.2
expects timely action on them.

See what's been reported, most reported first:

```sql
SELECT c.id, c.is_hidden, COUNT(*) AS reports,
       STRING_AGG(DISTINCT r.reason, ', ') AS reasons, LEFT(c.text, 100) AS text
FROM comments c
JOIN comment_reports r ON r.comment_id = c.id
GROUP BY c.id
ORDER BY reports DESC, c.created_at DESC;
```

Restore a comment that was hidden unfairly. Replace `COMMENT_ID` in both places. Its reports are
cleared too, otherwise the next report would hide it again:

```sql
BEGIN;
WITH restored AS (
    UPDATE comments SET is_hidden = false, hidden_at = NULL
    WHERE id = 'COMMENT_ID' AND is_hidden
    RETURNING article_id
)
UPDATE articles SET comment_count = comment_count + 1
WHERE id IN (SELECT article_id FROM restored);
DELETE FROM comment_reports WHERE comment_id = 'COMMENT_ID';
COMMIT;
```

## Account deletion

`DELETE /users/me` erases the email and password hash, renames the account `[deleted]`, and removes
its votes, comment upvotes and the blocks it made. Comment text stays, shown under `[deleted]`, so
your privacy policy should say so. Reports the user filed and blocks others placed on them are
kept, so hidden comments stay hidden and blocked users can't reappear.

## Project layout

```
app/
  main.py            app setup: middleware, routers, scheduler
  config.py          settings from the environment
  database.py        engine, sessions, UTC datetime column
  models.py          database tables
  schemas.py         request and response shapes
  auth.py            identifying the caller from the token
  security.py        password hashing and JWTs
  rate_limit.py      rate limits
  request_size.py    request body limit
  errors.py          turns every error into {"detail": "message"}
  logging_config.py  JSON logs and per-request logging
  lookups.py         finding rows from IDs in URLs
  feeds.py           RSS feed list
  ingestion.py       fetching and storing articles
  url_utils.py       URL cleaning and article IDs
  scheduler.py       background fetch job
  routers/           one file per group of endpoints
migrations/          Alembic migrations
tests/               pytest suite
```

## Known limitations

- **One process only:** rate limits and the news job assume a single server process.
- **No password reset or email verification.**
- **Logging out can't revoke a token:** the app forgets it, but a copied token works until it
  expires, unless the account is deleted.
- **No comment paging:** a thread is returned as one list.
- **No moderation tools:** review is by SQL, as above.
