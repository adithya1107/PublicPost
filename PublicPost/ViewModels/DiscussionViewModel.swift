import Foundation
import Observation

/// How comments are ordered.
enum CommentSort: String, CaseIterable, Identifiable {
    case top = "Top"
    case new = "New"

    var id: String { rawValue }
}

/// A top-level comment together with its replies (one level only).
struct CommentThread: Identifiable {
    let comment: Comment
    let replies: [Comment]

    var id: String { comment.id }
}

/// Drives the discussion screen for one article.
@Observable
final class DiscussionViewModel {

    enum State: Equatable {
        case loading
        case loaded
        case empty
        case error(String)
    }

    // MARK: - State read by the view

    let article: Article
    private(set) var comments: [Comment] = []
    private(set) var state: State = .loading
    var sort: CommentSort = .top

    /// Text in the composer.
    var draft = ""
    /// The comment being replied to, or `nil` when writing a top-level comment.
    private(set) var replyingTo: Comment?
    private(set) var isPosting = false
    /// Id of the comment just posted, so the view can scroll to it.
    private(set) var lastPostedCommentID: String?
    /// Set when posting or upvoting fails (shown as an alert).
    var actionError: String?

    // MARK: - Private

    private let service: any DiscussionService
    /// Reports the real comment count back so the feed card stays in sync.
    private let onCommentCountChange: (Int) -> Void
    private var upvotesInFlight: Set<String> = []

    init(
        article: Article,
        service: any DiscussionService = Config.discussionService,
        onCommentCountChange: @escaping (Int) -> Void = { _ in }
    ) {
        self.article = article
        self.service = service
        self.onCommentCountChange = onCommentCountChange
    }

    // MARK: - Derived data

    /// Top-level comments in the chosen order, each with its replies (oldest reply first,
    /// so a conversation reads top to bottom).
    var threads: [CommentThread] {
        let ids = Set(comments.map(\.id))
        // A reply whose parent is missing is shown as a normal comment rather than hidden.
        let topLevel = comments.filter { $0.parentId == nil || !ids.contains($0.parentId ?? "") }
        let repliesByParent = Dictionary(grouping: comments.filter { $0.parentId != nil }, by: { $0.parentId! })

        let sorted: [Comment]
        switch sort {
        case .top:
            sorted = topLevel.sorted {
                $0.upvotes != $1.upvotes ? $0.upvotes > $1.upvotes : $0.createdAt > $1.createdAt
            }
        case .new:
            sorted = topLevel.sorted { $0.createdAt > $1.createdAt }
        }

        return sorted.map { comment in
            let replies = (repliesByParent[comment.id] ?? []).sorted { $0.createdAt < $1.createdAt }
            return CommentThread(comment: comment, replies: replies)
        }
    }

    /// `true` when the composer has something worth sending.
    var canSend: Bool {
        !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !isPosting
    }

    // MARK: - Loading

    func load(showSpinner: Bool = true) async {
        if showSpinner { state = .loading }
        do {
            comments = try await service.fetchComments(articleId: article.id)
            state = comments.isEmpty ? .empty : .loaded
            onCommentCountChange(comments.count)
        } catch {
            if error is CancellationError || (error as? URLError)?.code == .cancelled { return }
            if comments.isEmpty {
                state = .error(error.localizedDescription)
            } else {
                actionError = error.localizedDescription   // keep showing what we have
            }
        }
    }

    // MARK: - Writing

    func startReply(to comment: Comment) {
        // One level of replies only: replying to a reply targets its parent.
        replyingTo = comments.first(where: { $0.id == comment.parentId }) ?? comment
    }

    func cancelReply() {
        replyingTo = nil
    }

    /// Sends the draft. Not optimistic: the comment appears once the server confirms it.
    func post() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard canSend else { return }

        isPosting = true
        defer { isPosting = false }

        do {
            let created = try await service.postComment(
                articleId: article.id, text: text, parentId: replyingTo?.id
            )
            comments.append(created)
            draft = ""
            replyingTo = nil
            state = .loaded
            lastPostedCommentID = created.id
            onCommentCountChange(comments.count)
        } catch {
            actionError = error.localizedDescription   // draft is kept so nothing is lost
        }
    }

    // MARK: - Upvoting comments

    /// Optimistically toggles the upvote, then confirms with the service (rolls back on failure).
    func toggleUpvote(_ comment: Comment) async {
        let id = comment.id
        guard !upvotesInFlight.contains(id),
              let index = comments.firstIndex(where: { $0.id == id }) else { return }

        let original = comments[index]          // kept for rollback
        let newState = !original.userUpvoted
        upvotesInFlight.insert(id)
        defer { upvotesInFlight.remove(id) }

        // Optimistic update.
        comments[index].userUpvoted = newState
        comments[index].upvotes += newState ? 1 : -1

        do {
            let count = try await service.setCommentUpvote(
                articleId: article.id, commentId: id, upvoted: newState
            )
            if let i = comments.firstIndex(where: { $0.id == id }) {
                comments[i].upvotes = count
            }
        } catch {
            if let i = comments.firstIndex(where: { $0.id == id }) {
                comments[i].userUpvoted = original.userUpvoted
                comments[i].upvotes = original.upvotes
            }
            actionError = error.localizedDescription
        }
    }
}
