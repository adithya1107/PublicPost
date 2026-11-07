import SwiftUI

/// The discussion thread for one article, shown as a sheet from the feed:
/// sort picker, comments with one level of replies, upvotes, and a composer.
struct DiscussionView: View {
    @Environment(AuthManager.self) private var auth
    @State private var viewModel: DiscussionViewModel
    @State private var loginPrompt: LoginPrompt?
    @FocusState private var isComposerFocused: Bool
    @Environment(\.dismiss) private var dismiss

    init(viewModel: DiscussionViewModel) {
        _viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        NavigationStack {
            content
                .navigationTitle("Discussion")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Done") { dismiss() }
                    }
                }
                .safeAreaInset(edge: .bottom, spacing: 0) {
                    if auth.isLoggedIn {
                        CommentComposerView(
                            text: $viewModel.draft,
                            replyingToName: viewModel.replyingTo?.authorName,
                            isPosting: viewModel.isPosting,
                            canSend: viewModel.canSend,
                            isFocused: $isComposerFocused,
                            onCancelReply: { viewModel.cancelReply() },
                            onSend: {
                                Task {
                                    await viewModel.post()
                                    // Close the keyboard once the comment was accepted.
                                    if viewModel.draft.isEmpty { isComposerFocused = false }
                                }
                            }
                        )
                    } else {
                        guestComposerBar
                    }
                }
        }
        .task { await viewModel.load() }
        .loginSheet(item: $loginPrompt)
        .alert("Something went wrong", isPresented: actionErrorBinding) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(viewModel.actionError ?? "")
        }
    }

    // MARK: - Content for each state

    @ViewBuilder
    private var content: some View {
        switch viewModel.state {
        case .loading:
            LoadingStateView(message: "Loading comments…")
        case .error(let message):
            ErrorStateView(message: message) {
                Task { await viewModel.load() }
            }
        case .empty:
            ScrollView {
                EmptyStateView(
                    title: "No comments yet",
                    message: "Be the first to share your view on this story.",
                    systemImage: "bubble.left.and.bubble.right"
                )
                .containerRelativeFrame(.vertical)
            }
            .refreshable { await viewModel.load(showSpinner: false) }
        case .loaded:
            commentList
        }
    }

    private var commentList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0) {
                    header

                    ForEach(viewModel.threads) { thread in
                        threadView(thread)
                    }
                }
                .padding(.horizontal)
            }
            .refreshable { await viewModel.load(showSpinner: false) }
            .scrollDismissesKeyboard(.interactively)
            // After posting, jump to the new comment (it may be low in the "Top" order).
            .onChange(of: viewModel.lastPostedCommentID) { _, newID in
                guard let newID else { return }
                withAnimation { proxy.scrollTo(newID, anchor: .center) }
            }
        }
    }

    /// Article title and the Top / New picker.
    private var header: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(viewModel.article.title)
                .font(.headline)

            Picker("Sort comments", selection: $viewModel.sort.animation()) {
                ForEach(CommentSort.allCases) { sort in
                    Text(sort.rawValue).tag(sort)
                }
            }
            .pickerStyle(.segmented)
        }
        .padding(.vertical, 12)
    }

    /// A top-level comment followed by its indented replies.
    private func threadView(_ thread: CommentThread) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            CommentRowView(
                comment: thread.comment,
                onUpvote: { upvote(thread.comment) },
                onReply: {
                    guard auth.isLoggedIn else {
                        loginPrompt = LoginPrompt(reason: "Log in to reply to comments.")
                        return
                    }
                    viewModel.startReply(to: thread.comment)
                    isComposerFocused = true
                }
            )
            .id(thread.comment.id)

            ForEach(thread.replies) { reply in
                CommentRowView(
                    comment: reply,
                    onUpvote: { upvote(reply) },
                    onReply: nil
                )
                .id(reply.id)
                .padding(.leading, 28)
                .overlay(alignment: .leading) {
                    // Thin line marking the reply as part of the thread.
                    Rectangle()
                        .fill(Color(.separator))
                        .frame(width: 2)
                        .padding(.leading, 14)
                }
            }

            Divider()
        }
    }

    /// Upvoting needs an account; guests are asked to log in instead.
    private func upvote(_ comment: Comment) {
        guard auth.isLoggedIn else {
            loginPrompt = LoginPrompt(reason: "Log in to upvote comments.")
            return
        }
        Task { await viewModel.toggleUpvote(comment) }
    }

    /// Replaces the composer for guests with a button that opens the login screen.
    private var guestComposerBar: some View {
        VStack(spacing: 0) {
            Divider()
            Button {
                loginPrompt = LoginPrompt(reason: "Log in to join the discussion.")
            } label: {
                Label("Log in to join the discussion", systemImage: "person.crop.circle")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .padding()
        }
        .background(.bar)
    }

    private var actionErrorBinding: Binding<Bool> {
        Binding(
            get: { viewModel.actionError != nil },
            set: { if !$0 { viewModel.actionError = nil } }
        )
    }
}

#Preview("Logged in") {
    DiscussionView(
        viewModel: DiscussionViewModel(article: .preview, service: PreviewDiscussionService())
    )
    .environment(AuthManager.preview(signedIn: true))
}

#Preview("Guest") {
    DiscussionView(
        viewModel: DiscussionViewModel(article: .preview, service: PreviewDiscussionService())
    )
    .environment(AuthManager.preview(signedIn: false))
}

/// Preview-only service with a few comments for `Article.preview`.
private struct PreviewDiscussionService: DiscussionService {
    func fetchComments(articleId: String) async throws -> [Comment] {
        let now = Date()
        return [
            Comment(id: "p1", articleId: articleId, authorName: "Asha",
                    text: "Good idea in principle, but I want to see how they plan to pay for it.",
                    createdAt: now.addingTimeInterval(-3_600), upvotes: 24, parentId: nil),
            Comment(id: "p2", articleId: articleId, authorName: "Ravi",
                    text: "The pilot is only six months, so the cost is limited. Let's see the numbers first.",
                    createdAt: now.addingTimeInterval(-3_000), upvotes: 9, parentId: "p1"),
            Comment(id: "p3", articleId: articleId, authorName: "Meera",
                    text: "Free buses on weekends would help our family a lot.",
                    createdAt: now.addingTimeInterval(-1_200), upvotes: 31, parentId: nil)
        ]
    }

    func postComment(articleId: String, text: String, parentId: String?) async throws -> Comment {
        Comment(id: UUID().uuidString, articleId: articleId, authorName: "Guest Reader",
                text: text, createdAt: Date(), upvotes: 0, parentId: parentId)
    }

    func setCommentUpvote(articleId: String, commentId: String, upvoted: Bool) async throws -> Int {
        upvoted ? 25 : 24
    }

    func fetchMyComments() async throws -> [Comment] { [] }
}
