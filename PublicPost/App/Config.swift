import Foundation

/// App-wide configuration. This is the ONE place to change the backend URL or to
/// switch between the mock data and the real FastAPI backend.
nonisolated enum Config {

    // MARK: - Backend URL  (the ONE place to change it)

    /// Backend URL (ngrok tunnel to the local FastAPI server).
    #if DEBUG
    static let baseURL = URL(string: "https://empower-obtrusive-cultural.ngrok-free.dev")!
    #else
    static let baseURL = URL(string: "https://empower-obtrusive-cultural.ngrok-free.dev")!
    #endif

    // MARK: - Mock / real switch

    /// `false` -> use the FastAPI backend, with automatic fallback to the bundled news.
    /// `true`  -> run fully offline with bundled JSON + in-memory votes and comments.
    static let useMockService = false

    /// What the services below actually follow: the switch above, or always mock inside
    /// SwiftUI previews so previews never touch the network.
    static var usesMockData: Bool {
        useMockService || ProcessInfo.processInfo.environment["XCODE_RUNNING_FOR_PREVIEWS"] == "1"
    }

    // MARK: - Image cache

    /// Story images are loaded by `AsyncImage`, which uses the shared `URLCache`. The system
    /// default (about 10 MB on disk) is small for photo thumbnails, so enlarge it: images
    /// then stay in memory (fast scrolling) and on disk (survive relaunch, work offline).
    /// Called once when the app starts.
    static func configureImageCache() {
        URLCache.shared = URLCache(
            memoryCapacity: 50 * 1024 * 1024,    // 50 MB in memory
            diskCapacity: 300 * 1024 * 1024      // 300 MB on disk (iOS trims it if space is low)
        )
    }

    // MARK: - Other settings

    /// Number of articles per page (the backend returns 10; the mock mimics it).
    static let pageSize = 10

    // One shared instance of each, so every screen sees the same data.
    private static let mock = MockService()
    private static let mockAuth = MockAuthService()
    private static let api = APIService(baseURL: baseURL)
    /// The API, with bundled news as the safety net when it can't be reached.
    private static let resilient = ResilientService(primary: api, fallback: mock)

    /// The service the view models should use for news. Views never see which one it is.
    static var newsService: any NewsService {
        usesMockData ? mock : resilient
    }

    /// The service the view models should use for discussions.
    static var discussionService: any DiscussionService {
        usesMockData ? mock : resilient
    }

    /// The service used for login and registration. There is deliberately no mock fallback
    /// when the real API is selected: a down server must not let anyone "log in".
    static var authService: any AuthService {
        usesMockData ? mockAuth : api
    }
}
