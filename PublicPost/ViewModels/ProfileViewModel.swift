import Foundation
import Observation

/// One of my comments, plus the title of the article it was posted on.
struct ProfileComment: Identifiable {
    let comment: Comment
    let articleTitle: String?

    var id: String { comment.id }
}

/// Loads the logged-in user's comments for the Profile tab.
@Observable
final class ProfileViewModel {

    enum State: Equatable {
        case loading
        case loaded
        case empty
        case error(String)
    }

    private(set) var items: [ProfileComment] = []
    private(set) var state: State = .loading

    private let discussionService: any DiscussionService
    private let newsService: any NewsService

    init(
        discussionService: any DiscussionService = Config.discussionService,
        newsService: any NewsService = Config.newsService
    ) {
        self.discussionService = discussionService
        self.newsService = newsService
    }

    func load(showSpinner: Bool = true) async {
        if showSpinner { state = .loading }
        do {
            let comments = try await discussionService.fetchMyComments()
                .sorted { $0.createdAt > $1.createdAt }

            // Look up each article's title once, so every row can say where it was posted.
            var titles: [String: String] = [:]
            for id in Set(comments.map(\.articleId)) {
                if let article = try? await newsService.fetchArticle(id: id) {
                    titles[id] = article.title
                }
            }

            items = comments.map { ProfileComment(comment: $0, articleTitle: titles[$0.articleId]) }
            state = items.isEmpty ? .empty : .loaded
        } catch {
            if error is CancellationError || (error as? URLError)?.code == .cancelled { return }
            state = .error(error.localizedDescription)
        }
    }

    /// Clears everything (used on logout so the next user doesn't see stale data).
    func reset() {
        items = []
        state = .loading
    }
}
