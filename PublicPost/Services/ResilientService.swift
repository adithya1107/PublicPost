import Foundation

/// Wraps the real `APIService` and keeps the app useful when the backend can't be reached.
///
/// Where page 1 of the feed comes from, in order of preference:
///   1. the server (and the result is saved to the disk cache);
///   2. the disk cache: the last real stories we loaded;
///   3. the stories bundled in the app (samples), if there is nothing cached yet.
///
/// How it decides:
/// - Loading page 1 of the feed is the "health check". If it fails we use (2) or (3); if it
///   succeeds we are back on (1).
/// - While showing samples, article, comment and vote calls also go to the mock, because those
///   ids only exist in the bundle. While showing cached real stories they still go to the
///   server (they will fail with a friendly "offline" message rather than a confusing "not found").
/// - Paging beyond page 1 never falls back on its own, so server and bundled pages never mix.
actor ResilientService: NewsService, DiscussionService {

    private enum Source {
        case live       // the server answered
        case cache      // server unreachable; showing the last real stories
        case sample     // server unreachable and nothing cached; showing bundled samples
    }

    private let primary: APIService
    private let fallback: MockService
    private let cache: FeedCache
    private var source = Source.live

    init(primary: APIService, fallback: MockService, cache: FeedCache = .shared) {
        self.primary = primary
        self.fallback = fallback
        self.cache = cache
    }

    /// The service that article / comment calls should go to right now.
    private var current: any (NewsService & DiscussionService) {
        source == .sample ? fallback : primary
    }

    // MARK: - NewsService

    func fetchArticles(category: NewsCategory?, page: Int) async throws -> [Article] {
        guard page == 1 else {
            return try await current.fetchArticles(category: category, page: page)
        }
        do {
            let articles = try await primary.fetchArticles(category: category, page: 1)
            source = .live
            cache.save(articles, category: category)
            return articles
        } catch {
            if error is CancellationError { throw error }
            if let saved = cache.load(category: category) {
                source = .cache
                return saved
            }
            source = .sample
            return try await fallback.fetchArticles(category: category, page: 1)
        }
    }

    func cachedArticles(category: NewsCategory?) async -> [Article] {
        cache.load(category: category) ?? []
    }

    func isOffline() async -> Bool {
        source != .live
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

    func reportComment(commentId: String, reason: ReportReason) async throws {
        try await current.reportComment(commentId: commentId, reason: reason)
    }

    func blockUser(userId: String) async throws {
        try await current.blockUser(userId: userId)
    }
}
