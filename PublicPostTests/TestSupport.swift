import Foundation
@testable import PublicPost

/// The Testing framework also defines a `Comment` type; this makes plain `Comment` mean ours
/// in every test file.
typealias Comment = PublicPost.Comment

// MARK: - Fake HTTP server

/// What the app sent, as recorded by the stub.
struct RecordedRequest: Sendable {
    let method: String
    let url: URL
    let authorization: String?
    let body: String

    var path: String { url.path }
    var query: String? { url.query }
}

/// What the stub should answer.
enum StubReply: Sendable {
    case http(Int, String)
    case network(URLError.Code)

    static func json(_ body: String) -> StubReply { .http(200, body) }
    static let noContent = StubReply.http(204, "")
}

/// A `URLProtocol` that answers requests from a handler instead of using the network.
/// Handlers are registered per host, so every test gets its own fake server and tests can
/// run in parallel without interfering.
final class StubURLProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) private static var handlers: [String: @Sendable (RecordedRequest) -> StubReply] = [:]
    nonisolated(unsafe) private static var recorded: [String: [RecordedRequest]] = [:]
    private static let lock = NSLock()

    static func setHandler(_ handler: @escaping @Sendable (RecordedRequest) -> StubReply, for host: String) {
        lock.withLock { handlers[host] = handler }
    }

    static func removeHandler(for host: String) {
        lock.withLock {
            handlers[host] = nil
            recorded[host] = nil
        }
    }

    static func requests(for host: String) -> [RecordedRequest] {
        lock.withLock { recorded[host] ?? [] }
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let url = request.url, let host = url.host else { return }
        let entry = RecordedRequest(
            method: request.httpMethod ?? "GET",
            url: url,
            authorization: request.value(forHTTPHeaderField: "Authorization"),
            body: Self.body(of: request)
        )
        let handler = Self.lock.withLock { () -> (@Sendable (RecordedRequest) -> StubReply)? in
            Self.recorded[host, default: []].append(entry)
            return Self.handlers[host]
        }

        switch handler?(entry) ?? .http(500, "{}") {
        case .http(let status, let text):
            let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: nil)!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(text.utf8))
            client?.urlProtocolDidFinishLoading(self)
        case .network(let code):
            client?.urlProtocol(self, didFailWithError: URLError(code))
        }
    }

    override func stopLoading() {}

    /// URLSession hands protocols the body as a stream, so read it out.
    private static func body(of request: URLRequest) -> String {
        if let data = request.httpBody { return String(decoding: data, as: UTF8.self) }
        guard let stream = request.httpBodyStream else { return "" }
        stream.open()
        defer { stream.close() }
        var data = Data()
        let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: 1024)
        defer { buffer.deallocate() }
        while stream.hasBytesAvailable {
            let count = stream.read(buffer, maxLength: 1024)
            if count <= 0 { break }
            data.append(buffer, count: count)
        }
        return String(decoding: data, as: UTF8.self)
    }
}

/// One fake backend. Create it with a handler, then use `api` to talk to it.
final class StubServer: @unchecked Sendable {
    let host = "stub-\(UUID().uuidString.lowercased()).local"
    let session: URLSession

    init(_ handler: @escaping @Sendable (RecordedRequest) -> StubReply) {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [StubURLProtocol.self]
        session = URLSession(configuration: configuration)
        StubURLProtocol.setHandler(handler, for: host)
    }

    /// A server that always gives the same answer.
    convenience init(_ reply: StubReply) {
        self.init { _ in reply }
    }

    // No cleanup in deinit on purpose: `api` outlives the server object (tests often write
    // `makeService(server: StubServer(...))`), and each test uses its own unique host anyway.

    var api: APIService { APIService(baseURL: URL(string: "http://\(host)")!, session: session) }
    var requests: [RecordedRequest] { StubURLProtocol.requests(for: host) }

    /// Changes the answer mid-test (e.g. "the server goes down now").
    func respond(with reply: StubReply) {
        StubURLProtocol.setHandler({ _ in reply }, for: host)
    }
}

// MARK: - Real response shapes

/// JSON copied from the backend's actual responses (see backend/README.md and app/schemas.py).
enum Fixtures {
    static let article = """
    {"id":"ff021b187b202cb4","title":"U.S. FBI and regulators issue warning about cyber-attacks targeting industrial refrigerators",\
    "summary":"The U.S. regulators warned organisations about ongoing cyber threat activity.","source_name":"The Hindu",\
    "article_url":"https://www.thehindu.com/sci-tech/technology/article71677605.ece",\
    "image_url":"https://th-i.thgim.com/public/incoming/6wg3aq/article71677598.ece/alternates/LANDSCAPE_1200/photo.JPG",\
    "category":"Tech","published_at":"2026-11-07T07:44:22Z","upvotes":0,"downvotes":0,"comment_count":0,"user_vote":"none"}
    """

    static let articleNoImage = """
    {"id":"a2","title":"T","summary":"S","source_name":"Src","article_url":"https://example.com/a","image_url":null,\
    "category":"World","published_at":"2026-11-07T06:30:00Z","upvotes":3,"downvotes":1,"comment_count":2,"user_vote":"up"}
    """

    static let comment = """
    {"id":"c1","article_id":"ff021b187b202cb4","author_id":"u_abc123","author_name":"Meera","text":"Quiet and cheap to run.",\
    "created_at":"2026-11-07T07:10:00Z","upvotes":4,"parent_id":null,"user_upvoted":true}
    """

    static let reply = """
    {"id":"c2","article_id":"ff021b187b202cb4","author_id":"u_def456","author_name":"Ravi","text":"Agreed.",\
    "created_at":"2026-11-07T07:20:00Z","upvotes":0,"parent_id":"c1","user_upvoted":false}
    """

    static let auth = """
    {"token":"tok-123","user":{"id":"u_abc123","display_name":"Meera"}}
    """

    static let voteResponse = #"{"upvotes":5,"downvotes":1,"user_vote":"up"}"#
    static let articleList = "[\(article)]"
}

// MARK: - Helpers

/// Builds an article with sensible defaults for tests.
func makeArticle(
    id: String = "a1",
    upvotes: Int = 10,
    downvotes: Int = 2,
    userVote: Vote = .none,
    isSample: Bool = false
) -> Article {
    Article(
        id: id, title: "Title \(id)", summary: "Summary", sourceName: "Source",
        articleURL: URL(string: "https://example.com/\(id)")!, imageURL: nil, category: .tech,
        publishedAt: Date(timeIntervalSince1970: 1_800_000_000),
        upvotes: upvotes, downvotes: downvotes, commentCount: 0, userVote: userVote,
        isSample: isSample
    )
}

/// A fresh, empty cache in a temporary folder.
func makeTemporaryCache() -> FeedCache {
    FeedCache(directory: FileManager.default.temporaryDirectory
        .appending(path: "PublicPostTests-\(UUID().uuidString)", directoryHint: .isDirectory))
}

/// A news service whose answers the test controls.
actor StubNewsService: NewsService {
    var articles: [Article]
    var cached: [Article]
    var offline: Bool
    var voteResult: Result<VoteResult, Error>
    var fetchDelay: Duration

    init(
        articles: [Article] = [],
        cached: [Article] = [],
        offline: Bool = false,
        voteResult: Result<VoteResult, Error> = .success(VoteResult(upvotes: 0, downvotes: 0, userVote: .none)),
        fetchDelay: Duration = .zero
    ) {
        self.articles = articles
        self.cached = cached
        self.offline = offline
        self.voteResult = voteResult
        self.fetchDelay = fetchDelay
    }

    func fetchArticles(category: NewsCategory?, page: Int) async throws -> [Article] {
        try await Task.sleep(for: fetchDelay)
        return page == 1 ? articles : []
    }

    func fetchArticle(id: String) async throws -> Article {
        guard let article = articles.first(where: { $0.id == id }) else { throw ServiceError.notFound }
        return article
    }

    func vote(articleId: String, vote: Vote) async throws -> VoteResult {
        try voteResult.get()
    }

    func cachedArticles(category: NewsCategory?) async -> [Article] { cached }
    func isOffline() async -> Bool { offline }
}
