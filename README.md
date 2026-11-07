# PublicPost

An Inshorts-style news feed with Reddit-style discussion. Swipe through ~60-word news summaries, open the
original article, vote on stories, and read, write, report and block in the discussion, so you can see
*different public perspectives* on the same story instead of being told which one is right.

- **iOS app:** Swift + SwiftUI (iOS only), `@Observable` + MVVM, `URLSession` + `async/await` + `Codable`.
  No third-party packages.
- **Backend:** FastAPI in [`backend/`](backend/README.md) (news ingestion, voting, comments, accounts, moderation).

## Run the app and the backend together

1. **Start the backend** (needs [uv](https://docs.astral.sh/uv/)). Full details are in
   [`backend/README.md`](backend/README.md); in short:

   ```bash
   cd backend
   uv sync
   cp .env.example .env            # then put a secret after JWT_SECRET= (see backend README)
   uv run alembic upgrade head
   uv run uvicorn app.main:app --reload
   curl http://127.0.0.1:8000/health      # {"status":"ok"}
   ```

   Articles appear a few seconds after the first start, while the server fetches the news feeds.

2. **Run the app:** open `PublicPost.xcodeproj`, choose an **iPhone simulator**, and press Run.
   In Debug the app talks to `http://127.0.0.1:8000`, which the simulator can reach on your Mac.

3. **No backend?** The app still works. If the server can't be reached it shows saved stories (or the
   bundled sample stories on a first launch) under an "Offline" banner. To run completely offline with
   sample data, set `Config.useMockService = true`.

### Testing on a real iPhone

A phone can't reach `127.0.0.1` (that is the phone itself), so point the app at your Mac instead:

1. Start the backend listening on your network: `uv run uvicorn app.main:app --host 0.0.0.0`
2. Find your Mac's address: *System Settings > Wi-Fi > Details > IP address*, or run `ipconfig getifaddr en0`
   (for example `192.168.1.23`).
3. In `PublicPost/App/Config.swift`, change the **Debug** `baseURL` to `http://192.168.1.23:8000`.
4. Put the phone and the Mac on the same Wi-Fi, then run on the device.

Plain HTTP is allowed only for local network addresses (`NSAllowsLocalNetworking` in the app's Info.plist).
Arbitrary HTTP loads are **not** enabled, so a real server must use HTTPS.

### Before releasing

The **Release** `baseURL` in `Config.swift` is a placeholder (`http://127.0.0.1:8000`). Replace it with
the production **HTTPS** URL after the backend is deployed. Also read the backend README's notes on
publisher terms and moderation: App Store guideline 1.2 expects timely action on reports.

## Architecture (MVVM)

```
View  ──►  ViewModel (@Observable)  ──►  Service protocol  ──►  MockService / APIService
 UI        state + logic                  NewsService             bundled JSON    FastAPI backend
                                          DiscussionService
                                          AuthService                  ▲
                                                                       │ wraps APIService
                                                                 ResilientService
                                                       (server → saved stories → bundled samples)
```

| Folder | What lives there |
|---|---|
| `App` | `MyApp` (entry point) and `Config` (backend URL, mock switch, image cache size) |
| `Models` | `Article`, `Comment`, `ReportReason`, `User`: plain `Codable` structs |
| `Services` | Service protocols, `APIService`, `MockService`, `ResilientService`, `FeedCache`, Keychain and session storage |
| `ViewModels` | `FeedViewModel`, `DiscussionViewModel`, `AuthManager`, `AuthViewModel`, `ProfileViewModel` |
| `Views` | Screens: feed, discussions list, discussion thread, profile, login |
| `Components` | Reusable pieces: article card, vote bar, comment row, composer, banners, state views, Safari wrapper |
| `Resources` | `news.json` (25 sample articles) and `comments.json`, used by the mock and as the offline fallback |
| `PublicPostTests` | Unit tests (Swift Testing) |

### Key ideas

- **Views never know where data comes from.** View models talk to protocols; `Config` decides which
  implementation they get. SwiftUI previews always use the mock, so they never touch the network.
- **Optimistic UI.** Votes and comment upvotes update the screen immediately, then the server confirms
  them, or the change is rolled back with a friendly message.
- **Guest mode.** Anyone can read. Voting, upvoting, replying, commenting, reporting and blocking ask a
  guest to log in.
- **Sessions.** The token and user live in the Keychain (`SessionStore`). `APIService` sends
  `Authorization: Bearer <token>` on **every** request when logged in (GETs too, so `user_vote` and
  `user_upvoted` come back correctly and blocked users' comments are left out). A 401 on a logged-in
  request clears the session, returns to guest mode and shows "Session expired, please log in again."
- **Offline.** `ResilientService` saves each category's page 1 to disk (`FeedCache`) and shows it instantly
  on launch while refreshing. If the server is unreachable it shows those saved stories, or the bundled
  samples if nothing is saved, with an "Offline" banner. Sample stories hide "Read full article"
  (their links are placeholders). Images use an enlarged `URLCache` (50 MB memory, 300 MB disk).
- **Moderation (App Store guideline 1.2).** Every comment has a Report (spam, abuse, misinformation, other)
  and Block menu (the "…" button or long-press). Blocking hides that user's comments immediately and tells
  the server. The Profile tab has **Delete account**.
- **Friendly errors.** Services throw `ServiceError`; `error.userMessage` turns any error into plain
  language. Technical details and status codes are never shown to users.
- Every screen has loading, empty and error states, and every view has a `#Preview`.

## Backend API used by the app

JSON, snake_case keys, ISO 8601 dates. Full details: [`backend/README.md`](backend/README.md).

| Method and path | Auth | Purpose |
|---|---|---|
| `GET /articles?category=&page=` | optional | Feed page (10 per page, newest first) |
| `GET /articles/{id}` | optional | One article |
| `POST /articles/{id}/vote` | required | `{"vote": "up" \| "down" \| "none"}` |
| `GET /articles/{id}/comments` | optional | Comments (blocked users left out when logged in) |
| `POST /articles/{id}/comments` | required | `{"text", "parent_id"?}` |
| `POST /comments/{id}/upvote` | required | `{"upvoted": bool}` |
| `POST /comments/{id}/report` | required | `{"reason": ...}` |
| `GET /users/me/comments` | required | Profile tab |
| `POST /users/{id}/block` | required | Block a user |
| `DELETE /users/me` | required | Delete account |
| `POST /auth/register`, `POST /auth/login` | none | Returns `{token, user}` |

## Tests

Run the **PublicPostTests** scheme (*Product > Scheme > PublicPostTests*, then Cmd-U), or from a terminal:

```bash
xcodebuild test -project PublicPost.xcodeproj -scheme PublicPostTests \
  -destination 'platform=iOS Simulator,name=iPhone 17'
```

The tests use a fake HTTP server (`URLProtocol`), so they need neither the backend nor a network. They cover:

- decoding the backend's real response shapes (articles, comments, auth, votes, dates);
- vote toggling, optimistic updates and rollback;
- the 401 flow: Keychain cleared, back to guest mode, message shown, no false sign-outs;
- bearer tokens on GET requests;
- `ResilientService`: server → saved stories → bundled samples, recovery, and no mixing across pages;
- report, block and delete-account requests, the disk cache, the offline banner and friendly error text.

Backend tests: `cd backend && uv run pytest`.

## Known limits

- Mock votes, comments and accounts (used by previews and `useMockService = true`) live in memory and
  reset on relaunch. Mock votes are global, not per account.
- There is no screen to unblock a user: the backend has a route to block but none to list blocked users.
- The app icon is a generated placeholder. It only appears once the target's *App Icon* is set to
  `AppIcon` (target > General > App Icons and Launch Screen).
- No password reset or email verification (the backend doesn't offer them yet).
