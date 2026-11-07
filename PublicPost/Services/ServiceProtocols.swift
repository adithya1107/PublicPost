import Foundation

/// Errors the view models can show to the user.
nonisolated enum ServiceError: LocalizedError {
    case notFound
    case invalidResponse
    case bundledDataMissing(String)
    case server(statusCode: Int)
    case unauthorized
    case network(String)
    case invalidCredentials
    case emailTaken
    /// A readable message sent by the server (FastAPI's `{"detail": "..."}`).
    case api(String)

    var errorDescription: String? {
        switch self {
        case .notFound: "That item could not be found."
        case .invalidResponse: "The server sent a response we couldn't understand."
        case .bundledDataMissing(let file): "The bundled file \(file) is missing."
        case .server(let code): "The server returned an error (\(code))."
        case .unauthorized: "Please log in to do that."
        case .network(let message): "Network problem: \(message)"
        case .invalidCredentials: "Incorrect email or password."
        case .emailTaken: "An account with that email already exists."
        case .api(let message): message
        }
    }
}

/// The updated counts the server returns after a vote.
nonisolated struct VoteResult: Codable, Sendable {
    let upvotes: Int
    let downvotes: Int
    let userVote: Vote
}

/// Everything the news feed needs. Implemented by `MockService` and (Phase 6) `APIService`.
nonisolated protocol NewsService: Sendable {
    /// GET /articles?category=&page=   (pages start at 1; `nil` category means all)
    func fetchArticles(category: NewsCategory?, page: Int) async throws -> [Article]

    /// GET /articles/{id}
    func fetchArticle(id: String) async throws -> Article

    /// POST /articles/{id}/vote
    func vote(articleId: String, vote: Vote) async throws -> VoteResult
}

/// Everything the discussion screen needs.
nonisolated protocol DiscussionService: Sendable {
    /// GET /articles/{id}/comments
    func fetchComments(articleId: String) async throws -> [Comment]

    /// POST /articles/{id}/comments
    func postComment(articleId: String, text: String, parentId: String?) async throws -> Comment

    /// Upvote (or take back an upvote on) a comment; returns the comment's new upvote count.
    /// NOTE: this is not in the original API contract. Proposed backend route:
    /// POST /comments/{id}/upvote  with body {"upvoted": true | false}.
    func setCommentUpvote(articleId: String, commentId: String, upvoted: Bool) async throws -> Int

    /// The logged-in user's own comments, for the Profile tab.
    /// NOTE: not in the original API contract. Proposed backend route: GET /users/me/comments
    func fetchMyComments() async throws -> [Comment]
}
