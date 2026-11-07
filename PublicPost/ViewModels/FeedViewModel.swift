import Foundation
import Observation

/// Drives the news feed: loading, category filtering, pull-to-refresh and paging.
@Observable
final class FeedViewModel {

    /// What the feed screen should currently show.
    enum State: Equatable {
        case loading
        case loaded
        case empty
        case error(String)
    }

    // MARK: - State read by the view

    private(set) var articles: [Article] = []
    private(set) var state: State = .loading
    /// `nil` means "All".
    var selectedCategory: NewsCategory?
    /// Set when a refresh fails while articles are already on screen (shown as an alert).
    var refreshError: String?
    /// Set when sending a vote fails (the vote has already been rolled back).
    var voteError: String?

    // MARK: - Private

    private let service: any NewsService
    private var page = 1
    private var canLoadMore = true
    private var isLoadingMore = false
    /// Article ids whose vote request is still running.
    private var votesInFlight: Set<String> = []
    /// Incremented on every reload so late responses for an old category are ignored.
    private var generation = 0

    init(service: any NewsService = Config.newsService) {
        self.service = service
    }

    // MARK: - Loading

    /// Loads page 1 for the selected category.
    /// - Parameter showSpinner: `true` for first load / category change (full-screen spinner),
    ///   `false` for pull-to-refresh (the system refresh indicator is already visible).
    func reload(showSpinner: Bool) async {
        generation += 1
        let currentGeneration = generation
        page = 1
        canLoadMore = true
        isLoadingMore = false

        if showSpinner {
            articles = []
            state = .loading
        }

        do {
            let result = try await service.fetchArticles(category: selectedCategory, page: 1)
            guard currentGeneration == generation else { return }
            articles = result
            canLoadMore = result.count >= Config.pageSize
            state = result.isEmpty ? .empty : .loaded
        } catch {
            guard currentGeneration == generation, !isCancellation(error) else { return }
            if articles.isEmpty {
                state = .error(error.localizedDescription)
            } else {
                refreshError = error.localizedDescription   // keep what we already have
            }
        }
    }

    /// Call when a card appears; loads the next page when the user nears the end.
    func loadMoreIfNeeded(currentArticle: Article) async {
        guard canLoadMore, !isLoadingMore, state == .loaded else { return }
        let triggerIndex = max(articles.count - 3, 0)
        guard let index = articles.firstIndex(where: { $0.id == currentArticle.id }),
              index >= triggerIndex else { return }

        isLoadingMore = true
        let currentGeneration = generation
        let nextPage = page + 1
        defer { if currentGeneration == generation { isLoadingMore = false } }

        do {
            let result = try await service.fetchArticles(category: selectedCategory, page: nextPage)
            guard currentGeneration == generation else { return }
            // Skip anything we already have, in case the server's pages overlap.
            let known = Set(articles.map(\.id))
            articles.append(contentsOf: result.filter { !known.contains($0.id) })
            page = nextPage
            canLoadMore = result.count >= Config.pageSize
        } catch {
            // A failed "load more" is not fatal; the next appearance retries.
        }
    }

    // MARK: - Voting

    /// Handles a tap on the up or down arrow.
    /// 1. Update the article on screen immediately (optimistic UI).
    /// 2. Send the vote to the service.
    /// 3. On success, adopt the server's counts; on failure, roll back and tell the user.
    func vote(on article: Article, tapped: Vote) async {
        let id = article.id
        // Ignore extra taps while this article's previous vote is still being sent.
        guard !votesInFlight.contains(id),
              let index = articles.firstIndex(where: { $0.id == id }) else { return }

        let original = articles[index]                      // kept for rollback
        let newVote = original.voteAfterTapping(tapped)     // same vote again -> .none

        votesInFlight.insert(id)
        defer { votesInFlight.remove(id) }
        articles[index].setVote(newVote)

        do {
            let result = try await service.vote(articleId: id, vote: newVote)
            // Look the article up again: the list may have been reloaded while we waited.
            if let i = articles.firstIndex(where: { $0.id == id }) {
                articles[i].upvotes = result.upvotes
                articles[i].downvotes = result.downvotes
                articles[i].userVote = result.userVote
            }
        } catch {
            if let i = articles.firstIndex(where: { $0.id == id }) {
                articles[i].upvotes = original.upvotes
                articles[i].downvotes = original.downvotes
                articles[i].userVote = original.userVote
            }
            voteError = error.localizedDescription
        }
    }

    // MARK: - Comments

    /// Keeps a card's comment count in sync after the discussion screen loads or posts.
    func updateCommentCount(articleId: String, count: Int) {
        guard let index = articles.firstIndex(where: { $0.id == articleId }) else { return }
        articles[index].commentCount = count
    }

    private func isCancellation(_ error: Error) -> Bool {
        error is CancellationError || (error as? URLError)?.code == .cancelled
    }
}
