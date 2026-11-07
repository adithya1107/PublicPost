import Foundation

/// Real backend client for the FastAPI server (base URL in `Config`).
///
/// Contract (all JSON, snake_case keys, ISO 8601 dates):
///   GET  /articles?category=&page=      -> [Article]
///   GET  /articles/{id}                 -> Article
///   POST /articles/{id}/vote            {"vote": "up"|"down"|"none"} -> {upvotes, downvotes, user_vote?}
///   GET  /articles/{id}/comments        -> [Comment]
///   POST /articles/{id}/comments        {"text", "parent_id"?} -> Comment
///   POST /auth/register                 {"display_name", "email", "password"} -> {token, user}
///   POST /auth/login                    {"email", "password"} -> {token, user}
/// Extra routes this app proposes (not in the original contract):
///   POST /comments/{id}/upvote          {"upvoted": bool} -> {"upvotes": Int}
///   GET  /users/me/comments             -> [Comment]
///   POST /comments/{id}/report          {"reason": "spam"|"abuse"|"misinformation"|"other"} -> 204
///   POST /users/{id}/block              -> 204
///   DELETE /users/me                    -> 204
/// Logged-in requests carry "Authorization: Bearer <token>" (token read from the Keychain).
nonisolated struct APIService: NewsService, DiscussionService, AuthService {

    let baseURL: URL
    let session: URLSession

    init(baseURL: URL = Config.baseURL, session: URLSession = APIService.makeSession()) {
        self.baseURL = baseURL
        self.session = session
    }

    /// Short timeouts so an unreachable server fails quickly and the bundled-news
    /// fallback appears without a long wait.
    static func makeSession() -> URLSession {
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 10
        configuration.waitsForConnectivity = false
        return URLSession(configuration: configuration)
    }

    // MARK: - NewsService

    func fetchArticles(category: NewsCategory?, page: Int) async throws -> [Article] {
        var query = [URLQueryItem(name: "page", value: String(page))]
        if let category {
            query.insert(URLQueryItem(name: "category", value: category.rawValue), at: 0)
        }
        return try await send(.get, "articles", query: query)
    }

    func fetchArticle(id: String) async throws -> Article {
        try await send(.get, "articles/\(id)")
    }

    func vote(articleId: String, vote: Vote) async throws -> VoteResult {
        let response: VoteResponse = try await send(.post, "articles/\(articleId)/vote", body: VoteBody(vote: vote))
        // If the server leaves out user_vote, the vote we just sent is what it recorded.
        return VoteResult(upvotes: response.upvotes, downvotes: response.downvotes, userVote: response.userVote ?? vote)
    }

    // MARK: - DiscussionService

    func fetchComments(articleId: String) async throws -> [Comment] {
        try await send(.get, "articles/\(articleId)/comments")
    }

    func postComment(articleId: String, text: String, parentId: String?) async throws -> Comment {
        try await send(.post, "articles/\(articleId)/comments", body: CommentBody(text: text, parentId: parentId))
    }

    func setCommentUpvote(articleId: String, commentId: String, upvoted: Bool) async throws -> Int {
        let response: UpvoteResponse = try await send(.post, "comments/\(commentId)/upvote", body: UpvoteBody(upvoted: upvoted))
        return response.upvotes
    }

    func fetchMyComments() async throws -> [Comment] {
        try await send(.get, "users/me/comments")
    }

    func reportComment(commentId: String, reason: ReportReason) async throws {
        try await sendExpectingNoContent(.post, "comments/\(commentId)/report", body: ReportBody(reason: reason))
    }

    func blockUser(userId: String) async throws {
        try await sendExpectingNoContent(.post, "users/\(userId)/block")
    }

    // MARK: - AuthService

    func register(displayName: String, email: String, password: String) async throws -> AuthSession {
        try await send(
            .post, "auth/register",
            body: RegisterBody(displayName: displayName, email: email, password: password),
            authenticated: false,
            errorOverrides: [409: .emailTaken]
        )
    }

    func login(email: String, password: String) async throws -> AuthSession {
        try await send(
            .post, "auth/login",
            body: LoginBody(email: email, password: password),
            authenticated: false,
            errorOverrides: [401: .invalidCredentials]
        )
    }

    func deleteAccount() async throws {
        try await sendExpectingNoContent(.delete, "users/me")
    }

    // MARK: - Request plumbing

    private enum Method: String {
        case get = "GET"
        case post = "POST"
        case delete = "DELETE"
    }

    /// Builds the request, sends it, turns failures into `ServiceError`, and decodes the reply.
    /// - Parameter errorOverrides: status codes that should map to a specific error
    ///   (e.g. 401 on login means "wrong password", not "not logged in").
    private func send<Response: Decodable>(
        _ method: Method,
        _ path: String,
        query: [URLQueryItem] = [],
        body: (any Encodable)? = nil,
        authenticated: Bool = true,
        errorOverrides: [Int: ServiceError] = [:]
    ) async throws -> Response {
        let request = try makeRequest(method, path, query: query, body: body, authenticated: authenticated)
        let data = try await perform(request, errorOverrides: errorOverrides)
        do {
            return try JSONCoding.makeDecoder().decode(Response.self, from: data)
        } catch {
            throw ServiceError.invalidResponse
        }
    }

    /// For routes that answer "204 No Content" (report, block, delete account).
    private func sendExpectingNoContent(
        _ method: Method,
        _ path: String,
        body: (any Encodable)? = nil
    ) async throws {
        let request = try makeRequest(method, path, query: [], body: body, authenticated: true)
        _ = try await perform(request, errorOverrides: [:])
    }

    /// Builds the URLRequest: URL, headers, bearer token and JSON body.
    private func makeRequest(
        _ method: Method,
        _ path: String,
        query: [URLQueryItem],
        body: (any Encodable)?,
        authenticated: Bool
    ) throws -> URLRequest {
        var components = URLComponents(url: baseURL.appending(path: path), resolvingAgainstBaseURL: false)
        if !query.isEmpty { components?.queryItems = query }
        guard let url = components?.url else { throw ServiceError.invalidResponse }

        var request = URLRequest(url: url)
        request.httpMethod = method.rawValue
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        // The token goes on EVERY request when logged in (GETs too), so the server can fill in
        // user_vote / user_upvoted and hide comments from users the caller has blocked.
        if authenticated, let token = SessionStore.token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONCoding.makeEncoder().encode(body)
        }
        return request
    }

    /// Sends the request and returns the body of a 2xx response; anything else throws.
    private func perform(_ request: URLRequest, errorOverrides: [Int: ServiceError]) async throws -> Data {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch let error as URLError {
            if error.code == .cancelled { throw CancellationError() }   // not a real failure
            throw ServiceError.network(error.friendlyDescription)
        }

        guard let http = response as? HTTPURLResponse else { throw ServiceError.invalidResponse }
        if (200..<300).contains(http.statusCode) { return data }

        if let overridden = errorOverrides[http.statusCode] { throw overridden }
        switch http.statusCode {
        case 401:
            // 401 on a request that carried our token means the token is expired or revoked.
            // Only react if it is still the CURRENT token (a late reply for an old token must
            // not sign out a newer login). Clear it and tell the app to return to guest mode.
            let sentToken = request.value(forHTTPHeaderField: "Authorization")?
                .replacingOccurrences(of: "Bearer ", with: "")
            if let sentToken, sentToken == SessionStore.token {
                SessionStore.clear()
                NotificationCenter.default.post(name: .sessionExpired, object: nil)
                throw ServiceError.sessionExpired
            }
            throw ServiceError.unauthorized
        case 404: throw ServiceError.notFound
        case 413: throw ServiceError.api("That's too long to send. Please shorten it and try again.")
        case 429: throw ServiceError.rateLimited
        case 400..<500:
            if let detail = Self.errorDetail(in: data) { throw ServiceError.api(detail) }
            throw ServiceError.server(statusCode: http.statusCode)
        default:
            throw ServiceError.server(statusCode: http.statusCode)
        }
    }

    /// Reads FastAPI's `{"detail": "message"}` error body, if present.
    private static func errorDetail(in data: Data) -> String? {
        (try? JSONDecoder().decode(ErrorBody.self, from: data))?.detail
    }

    // MARK: - Request / response bodies

    private nonisolated struct ErrorBody: Decodable { let detail: String }
    private nonisolated struct VoteBody: Encodable { let vote: Vote }
    private nonisolated struct VoteResponse: Decodable {
        let upvotes: Int
        let downvotes: Int
        let userVote: Vote?
    }
    private nonisolated struct CommentBody: Encodable {
        let text: String
        let parentId: String?          // nil is left out of the JSON
    }
    private nonisolated struct UpvoteBody: Encodable { let upvoted: Bool }
    private nonisolated struct ReportBody: Encodable { let reason: ReportReason }
    private nonisolated struct UpvoteResponse: Decodable { let upvotes: Int }
    private nonisolated struct RegisterBody: Encodable {
        let displayName: String
        let email: String
        let password: String
    }
    private nonisolated struct LoginBody: Encodable {
        let email: String
        let password: String
    }
}
