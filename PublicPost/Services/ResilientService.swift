import Foundation

/// Wraps the real `APIService` and falls back to the bundled data (`MockService`)
/// when the backend can't be reached, so the app always has something to show.
///
/// How it decides:
/// - Loading page 1 of the feed is the "health check". If it fails, we switch to the bundled
///   news; if it succeeds, we switch back to the API.
/// - While on the bundled news, every article, comment and vote call also goes to the mock,
///   because those article ids only exist in the bundle (the server wouldn't know them).
/// - Paging beyond page 1 never falls back on its own, so server and bundled pages never mix.
actor ResilientService: NewsService, DiscussionService {

    private let primary: APIService
    private let fallback: MockService
    private var usingFallback = false

    init(primary: APIService, fallback: MockService) {
        self.primary = primary
        self.fallback = fallback
    }

    /// The service that article / comment calls should go to right now.
    private var current: any (NewsService & DiscussionService) {
        usingFallback ? fallback : primary
    }

    // MARK: - NewsService

    func fetchArticles(category: NewsCategory?, page: Int) async throws -> [Article] {
        guard page == 1 else {
            return try await current.fetchArticles(category: category, page: page)
        }
        do {
            let articles = try await primary.fetchArticles(category: category, page: 1)
            usingFallback = false
            return articles
        } catch {
            if error is CancellationError { throw error }
            usingFallback = true
            return try await fallback.fetchArticles(category: category, page: 1)
        }
    }

    func fetchArticle(id: String) async throws -> Article {
        try await current.fetchArticle(id: id)
    }

    func vote(articleId: String, vote: Vote) async throws -> VoteResult {
        try await current.vote(articleId: articleId, vote: vote)
    }

    // MARK: - DiscussionService

    func fetchComments(articleId: String) async throws -> [Comment] {
        try await current.fetchComments(articleId: articleId)
    }

    func postComment(articleId: String, text: String, parentId: String?) async throws -> Comment {
        try await current.postComment(articleId: articleId, text: text, parentId: parentId)
    }

    func setCommentUpvote(articleId: String, commentId: String, upvoted: Bool) async throws -> Int {
        try await current.setCommentUpvote(articleId: articleId, commentId: commentId, upvoted: upvoted)
    }

    func fetchMyComments() async throws -> [Comment] {
        try await current.fetchMyComments()
    }
}
