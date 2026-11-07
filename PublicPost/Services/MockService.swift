import Foundation

/// Offline implementation of both service protocols.
/// Articles and comments come from the bundled JSON; votes and new comments are
/// kept in memory only, so they reset when the app is relaunched.
/// It is an `actor` so the in-memory state is safe to touch from async code.
actor MockService: NewsService, DiscussionService {

    private var articles: [Article] = []
    private var comments: [Comment] = []
    private var isLoaded = false

    // MARK: - Loading

    /// Loads the bundled files once, on first use.
    private func loadIfNeeded() throws {
        guard !isLoaded else { return }
        articles = try BundledData.loadArticles().sorted { $0.publishedAt > $1.publishedAt }
        comments = try BundledData.loadComments()
        // Make each article's comment count match the sample comments we actually have.
        for index in articles.indices {
            let id = articles[index].id
            articles[index].commentCount = comments.filter { $0.articleId == id }.count
        }
        isLoaded = true
    }

    // MARK: - NewsService

    func fetchArticles(category: NewsCategory?, page: Int) async throws -> [Article] {
        try loadIfNeeded()
        let filtered = articles.filter { category == nil || $0.category == category }
        // Mimic server pagination (pages start at 1).
        let start = (max(page, 1) - 1) * Config.pageSize
        guard start < filtered.count else { return [] }
        return Array(filtered[start..<min(start + Config.pageSize, filtered.count)])
    }

    func fetchArticle(id: String) async throws -> Article {
        try loadIfNeeded()
        guard let article = articles.first(where: { $0.id == id }) else {
            throw ServiceError.notFound
        }
        return article
    }

    func vote(articleId: String, vote: Vote) async throws -> VoteResult {
        try loadIfNeeded()
        guard let index = articles.firstIndex(where: { $0.id == articleId }) else {
            throw ServiceError.notFound
        }
        var article = articles[index]

        // Undo the previous vote and apply the new one (shared logic in the model).
        article.setVote(vote)
        articles[index] = article

        return VoteResult(upvotes: article.upvotes, downvotes: article.downvotes, userVote: vote)
    }

    // MARK: - DiscussionService

    func fetchComments(articleId: String) async throws -> [Comment] {
        try loadIfNeeded()
        return comments.filter { $0.articleId == articleId }
    }

    func postComment(articleId: String, text: String, parentId: String?) async throws -> Comment {
        try loadIfNeeded()
        guard let index = articles.firstIndex(where: { $0.id == articleId }) else {
            throw ServiceError.notFound
        }

        // Only one level of replies: if the parent is itself a reply, attach to its parent.
        var resolvedParent = parentId
        if let parentId, let parent = comments.first(where: { $0.id == parentId }) {
            resolvedParent = parent.parentId ?? parent.id
        }

        let comment = Comment(
            id: UUID().uuidString,
            articleId: articleId,
            authorName: SessionStore.user?.displayName ?? User.mockCurrent.displayName,
            text: text,
            createdAt: Date(),
            upvotes: 0,
            parentId: resolvedParent
        )
        comments.append(comment)
        articles[index].commentCount += 1
        return comment
    }

    func setCommentUpvote(articleId: String, commentId: String, upvoted: Bool) async throws -> Int {
        try loadIfNeeded()
        guard let index = comments.firstIndex(where: { $0.id == commentId && $0.articleId == articleId }) else {
            throw ServiceError.notFound
        }
        // Only change the count when the state really changes, so repeats can't double count.
        if upvoted != comments[index].userUpvoted {
            comments[index].upvotes += upvoted ? 1 : -1
            comments[index].userUpvoted = upvoted
        }
        return comments[index].upvotes
    }

    func fetchMyComments() async throws -> [Comment] {
        try loadIfNeeded()
        // The mock matches by display name; a real backend would use the user id from the token.
        guard let name = SessionStore.user?.displayName else { throw ServiceError.unauthorized }
        return comments.filter { $0.authorName == name }
    }
}
