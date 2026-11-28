# PublicPost

PublicPost is an Inshorts-style news app with Reddit-style voting and discussion. Each story
is cut down to a summary of about 60 words. You can open the original article, vote on the
story and join the discussion thread. The backend pulls in 18 RSS feeds across 6 categories
and refreshes them every 20 minutes.

**iOS:** Swift, SwiftUI, MVVM, no third-party packages.
**Backend:** FastAPI, SQLAlchemy, Alembic, APScheduler, SQLite.

## Run the backend

Requires [uv](https://docs.astral.sh/uv/).

```bash
cd backend
uv sync
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # paste after JWT_SECRET= in .env
uv run alembic upgrade head
uv run uvicorn app.main:app --port 8000
```

## Expose it with ngrok

```bash
ngrok http --url=https://empower-obtrusive-cultural.ngrok-free.dev 8000
```

## Run the app

1. Open `PublicPost.xcodeproj` in Xcode.
2. Under Signing & Capabilities, choose your signing team.
3. Run the app on an iPhone with iOS 27.2 or later.

The backend URL is set in `PublicPost/App/Config.swift`. If the backend is unreachable, the
app falls back to stories it saved earlier, or to sample stories bundled with the app.

## Tests

```bash
cd backend && uv run pytest
```

```bash
xcodebuild test -project PublicPost.xcodeproj -scheme PublicPostTests \
  -destination 'platform=iOS Simulator,name=iPhone 17'
```

## Authors

- Harkaran Singh Anand (230905406)
- Adithya M Adiga (230905008)
