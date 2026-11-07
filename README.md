# PublicPost

An Inshorts-style news feed with Reddit-style discussion. Swipe through ~60-word news summaries, open the
original article, vote on stories, and read or write comments, so you can see *different public
perspectives* on the same story instead of being told which one is right.

Swift + SwiftUI, iOS only, no third-party packages. Networking is `URLSession` + `async/await` + `Codable`.

## Running it

Open `PublicPost.xcodeproj`, pick an **iPhone simulator**, and run. The app works fully offline with
bundled data. Demo login: `demo@publicpost.app` / `password123` (or browse as a guest).

## Architecture (MVVM)

```
View  ──►  ViewModel (@Observable)  ──►  Service protocol  ──►  MockService / APIService
 UI        state + logic                  NewsService             bundled JSON   FastAPI backend
                                          DiscussionService
                                          AuthService
```

| Folder | What lives there |
|---|---|
| `App` | `MyApp` (entry point) and `Config` (the mock/API switch and backend URL) |
| `Models` | `Article`, `Comment`, `User`: plain `Codable` structs |
| `Services` | Service protocols, `MockService`, `APIService`, `ResilientService`, Keychain and session storage |
| `ViewModels` | `FeedViewModel`, `DiscussionViewModel`, `AuthManager`, `AuthViewModel`, `ProfileViewModel` |
| `Views` | Screens: feed, discussions, discussion thread, profile, login |
| `Components` | Reusable pieces: article card, vote bar, comment row, composer, state views, Safari wrapper |
| `Resources` | `news.json` (25 sample articles) and `comments.json` |

Key ideas:

- **Views never know where data comes from.** View models talk to protocols; `Config` decides which
  implementation they get. This is a single switch: `Config.useMockService`.
- **Optimistic UI.** Votes and comment upvotes update the screen immediately, then the service call
  confirms them, or the change is rolled back and an alert is shown.
- **Automatic fallback.** With the real API selected, `ResilientService` serves the bundled news if
  loading the feed fails, and goes back to the API once it works again.
- **Guest mode.** Anyone can read. Voting, upvoting, replying and commenting ask the guest to log in.
- **Token in the Keychain.** `SessionStore` keeps the login token; `APIService` sends it as
  `Authorization: Bearer <token>`.
- Every screen has loading, empty and error states, and every view has a `#Preview` using mock data.

## Switching to the real backend

1. Set `Config.useMockService = false` and, if needed, change `Config.baseURL`
   (default `http://127.0.0.1:8000`; a real iPhone needs your Mac's LAN IP and `uvicorn --host 0.0.0.0`).
2. The backend contract (JSON, snake_case keys, ISO 8601 dates):

| Method and path | Body | Returns |
|---|---|---|
| `GET /articles?category=&page=` | | `[Article]` |
| `GET /articles/{id}` | | `Article` |
| `POST /articles/{id}/vote` | `{"vote": "up" \| "down" \| "none"}` | `{upvotes, downvotes, user_vote?}` |
| `GET /articles/{id}/comments` | | `[Comment]` |
| `POST /articles/{id}/comments` | `{"text", "parent_id"?}` | `Comment` |
| `POST /auth/register` | `{"display_name", "email", "password"}` | `{token, user: {id, display_name}}` |
| `POST /auth/login` | `{"email", "password"}` | `{token, user: {id, display_name}}` |
| `POST /comments/{id}/upvote` *(extra)* | `{"upvoted": bool}` | `{upvotes}` |
| `GET /users/me/comments` *(extra)* | | `[Comment]` |

The two *extra* routes are not in the original contract; the app needs them for comment upvotes and
the Profile tab.

## Known limits

- Mock votes, comments and accounts live in memory and reset on relaunch (the saved login survives).
- Mock votes are global, not per account.
- The app icon is a generated placeholder.
