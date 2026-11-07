import Foundation

/// App-wide configuration. This is the ONE place to change the backend URL or to
/// switch between the mock data and the real FastAPI backend.
nonisolated enum Config {
    /// `true`  -> use bundled JSON + in-memory votes/comments (no backend needed).
    /// `false` -> use the FastAPI backend, with automatic fallback to the bundled news.
    static let useMockService = true

    /// Base URL of the FastAPI backend.
    /// (The simulator can reach 127.0.0.1 on your Mac; a real iPhone needs your Mac's LAN IP.)
    static let baseURL = URL(string: "http://127.0.0.1:8000")!

    /// Number of articles per page (used by the mock service to mimic `?page=`).
    static let pageSize = 10

    // One shared instance of each, so every screen sees the same data.
    private static let mock = MockService()
    private static let mockAuth = MockAuthService()
    private static let api = APIService(baseURL: baseURL)
    /// The API, with bundled news as the safety net when it can't be reached.
    private static let resilient = ResilientService(primary: api, fallback: mock)

    /// The service the view models should use for news. Views never see which one it is.
    static var newsService: any NewsService {
        useMockService ? mock : resilient
    }

    /// The service the view models should use for discussions.
    static var discussionService: any DiscussionService {
        useMockService ? mock : resilient
    }

    /// The service used for login and registration. There is deliberately no mock fallback
    /// when the real API is selected: a down server must not let anyone "log in".
    static var authService: any AuthService {
        useMockService ? mockAuth : api
    }
}
