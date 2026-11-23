import SwiftUI

/// A story's discussion, read-only: comments with their replies indented underneath.
struct WatchCommentsView: View {
    @State private var viewModel: DiscussionViewModel

    init(article: Article, service: any DiscussionService = Config.discussionService) {
        _viewModel = State(initialValue: DiscussionViewModel(article: article, service: service))
    }

    var body: some View {
        content
            .navigationTitle("Comments")
            .task { await viewModel.load() }
    }

    @ViewBuilder
    private var content: some View {
        switch viewModel.state {
        case .loading:
            ProgressView("Loading…")
        case .empty:
            ContentUnavailableView("No comments yet", systemImage: "bubble.left.and.bubble.right",
                                   description: Text("Be the first on iPhone, iPad or Mac."))
        case .error(let message):
            ScrollView {
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle")
                    Text(message).font(.footnote)
                    Button("Try again") { Task { await viewModel.load() } }
                }
            }
        case .loaded:
            List {
                ForEach(viewModel.threads) { thread in
                    row(thread.comment)
                    ForEach(thread.replies) { reply in
                        row(reply).padding(.leading, 12)
                    }
                }
            }
            .refreshable { await viewModel.load(showSpinner: false) }
        }
    }

    private func row(_ comment: Comment) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text("\(comment.authorName) · \(comment.createdAt.formatted(.relative(presentation: .named)))")
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(comment.text)
                .font(.footnote)
            Label("\(comment.upvotes)", systemImage: "arrow.up")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .accessibilityLabel("\(comment.upvotes) upvotes")
        }
    }
}

#Preview {
    NavigationStack {
        WatchCommentsView(article: .preview, service: MockService())
    }
}
