import Foundation

/// Errors the services throw. Every case has a friendly, user-facing description.
nonisolated enum ServiceError: LocalizedError, Equatable {
    case notFound
    case invalidResponse
    case bundledDataMissing(String)
    case server(statusCode: Int)
    case unauthorized
    /// The saved login was rejected (expired or revoked). The session has been cleared.
    case sessionExpired
    case network(String)
    case rateLimited
    case invalidCredentials
    case emailTaken
    /// A readable message sent by the server (FastAPI's `{"detail": "..."}`).
    case api(String)

    var errorDescription: String? {
        switch self {
        case .notFound: "That item could not be found. It may have been removed."
        case .invalidResponse: "We got an unexpected reply from the server. Please try again."
        case .bundledDataMissing(let file): "The bundled file \(file) is missing."
        case .server(let code) where code >= 500: "The server is having trouble right now. Please try again later."
        case .server(let code): "Something went wrong (error \(code)). Please try again."
        case .unauthorized: "Please log in to do that."
        case .sessionExpired: "Session expired, please log in again."
        case .network(let message): message
        case .rateLimited: "You're doing that too quickly. Please wait a moment and try again."
        case .invalidCredentials: "Incorrect email or password."
        case .emailTaken: "An account with that email already exists."
        case .api(let message): message
        }
    }
}

extension URLError {
    /// Plain-language text for common network failures.
    nonisolated var friendlyDescription: String {
        switch code {
        case .notConnectedToInternet, .dataNotAllowed:
            "You appear to be offline. Check your connection and try again."
        case .timedOut:
            "The server took too long to respond. Please try again."
        case .cannotConnectToHost, .cannotFindHost, .networkConnectionLost:
            "We can't reach the server right now. Please try again later."
        default:
            "A network problem occurred. Please try again."
        }
    }
}

extension Error {
    /// Friendly text to show in an alert, or `nil` when nothing should be shown:
    /// cancelled work, and session expiry (which `AuthManager` announces on its own).
    nonisolated var userMessage: String? {
        if self is CancellationError { return nil }
        if let serviceError = self as? ServiceError {
            return serviceError == .sessionExpired ? nil : serviceError.errorDescription
        }
        if let urlError = self as? URLError { return urlError.friendlyDescription }
        if let localized = self as? LocalizedError, let description = localized.errorDescription {
            return description
        }
        return "Something went wrong. Please try again."
    }

    /// Like `userMessage`, but always returns text (for full-screen error states).
    nonisolated var friendlyMessage: String {
        userMessage ?? "Something went wrong. Please try again."
    }
}

/// The updated counts the server returns after a vote.
nonisolated struct VoteResult: Codable, Sendable {
    let upvotes: Int
    let downvotes: Int
    let userVote: Vote
}

/// Everything the news feed needs. Implemented by `MockService` and `APIService`.
nonisolated protocol NewsService: Sendable {
    /// GET /articles?category=&page=   (pages start at 1; `nil` category means all)
    func fetchArticles(category: NewsCategory?, page: Int) async throws -> [Article]

    /// GET /articles/{id}
    func fetchArticle(id: String) async throws -> Article

    /// POST /articles/{id}/vote
    func vote(articleId: String, vote: Vote) async throws -> VoteResult

    /// Stories saved from the last successful load of page 1, to show instantly while the
    /// real load runs. Services without a cache return an empty list (see the default below).
    func cachedArticles(category: NewsCategory?) async -> [Article]

    /// `true` while the feed is showing saved or sample stories because the server can't be
    /// reached. Services that never fall back return `false`.
    func isOffline() async -> Bool
}

extension NewsService {
    nonisolated func cachedArticles(category: NewsCategory?) async -> [Article] { [] }
    nonisolated func isOffline() async -> Bool { false }
}

/// Everything the discussion screen needs.
nonisolated protocol DiscussionService: Sendable {
    /// GET /articles/{id}/comments
    func fetchComments(articleId: String) async throws -> [Comment]

    /// POST /articles/{id}/comments
    func postComment(articleId: String, text: String, parentId: String?) async throws -> Comment

    /// POST /comments/{id}/upvote  with body {"upvoted": true | false}.
    /// Returns the comment's new upvote count.
    func setCommentUpvote(articleId: String, commentId: String, upvoted: Bool) async throws -> Int

    /// GET /users/me/comments: the logged-in user's own comments, for the Profile tab.
    func fetchMyComments() async throws -> [Comment]

    /// POST /comments/{id}/report  with body {"reason": "spam" | "abuse" | "misinformation" | "other"}.
    /// (App Store guideline 1.2: users must be able to flag objectionable content.)
    func reportComment(commentId: String, reason: ReportReason) async throws

    /// POST /users/{id}/block. After this the server leaves that user's comments out of
    /// `fetchComments` for the caller. (App Store guideline 1.2: users must be able to block abusers.)
    func blockUser(userId: String) async throws
}
