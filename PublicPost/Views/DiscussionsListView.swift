import SwiftUI

/// Discussions tab: a list of stories (with category filter) to jump straight into a
/// discussion. It reuses `FeedViewModel` for loading, paging and filtering.
struct DiscussionsListView: View {
    @State private var viewModel: FeedViewModel
    /// The article whose discussion sheet is open.
    @State private var discussionArticle: Article?

    init(viewModel: FeedViewModel = FeedViewModel()) {
        _viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                CategoryChipsBar(selection: $viewModel.selectedCategory)
                content
            }
            .navigationTitle("Discussions")
            .navigationBarTitleDisplayMode(.inline)
            // Runs on first appearance and whenever the category changes.
            .task(id: viewModel.selectedCategory) {
                await viewModel.reload(showSpinner: true)
            }
            .sheet(item: $discussionArticle) { article in
                DiscussionView(
                    viewModel: DiscussionViewModel(article: article) { count in
                        viewModel.updateCommentCount(articleId: article.id, count: count)
                    }
                )
            }
            .alert("Couldn't refresh", isPresented: refreshErrorBinding) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(viewModel.refreshError ?? "")
            }
        }
    }

    // MARK: - Content for each state

    @ViewBuilder
    private var content: some View {
        switch viewModel.state {
        case .loading:
            LoadingStateView(message: "Loading discussions…")
        case .empty:
            ScrollView {
                EmptyStateView(
                    title: "No discussions yet",
                    message: "There are no stories in this category right now. Pull down to refresh.",
                    systemImage: "bubble.left.and.bubble.right"
                )
                .containerRelativeFrame(.vertical)
            }
            .refreshable { await viewModel.reload(showSpinner: false) }
        case .error(let message):
            ErrorStateView(message: message) {
                Task { await viewModel.reload(showSpinner: true) }
            }
        case .loaded:
            List(viewModel.articles) { article in
                Button {
                    discussionArticle = article
                } label: {
                    row(article)
                }
                .buttonStyle(.plain)
                .accessibilityHint("Opens the discussion")
                .task { await viewModel.loadMoreIfNeeded(currentArticle: article) }
            }
            .listStyle(.plain)
            .refreshable { await viewModel.reload(showSpinner: false) }
        }
    }

    private func row(_ article: Article) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(article.category.rawValue.uppercased())
                .font(.caption.weight(.bold))
                .foregroundStyle(Color.accentColor)

            Text(article.title)
                .font(.headline)

            HStack(spacing: 6) {
                Label("\(article.commentCount)", systemImage: "bubble.left")
                    .accessibilityLabel("\(article.commentCount) \(article.commentCount == 1 ? "comment" : "comments")")
                Text("· \(article.sourceName) · \(article.publishedAt.formatted(.relative(presentation: .named)))")
            }
            .font(.footnote)
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    private var refreshErrorBinding: Binding<Bool> {
        Binding(
            get: { viewModel.refreshError != nil },
            set: { if !$0 { viewModel.refreshError = nil } }
        )
    }
}

#Preview {
    DiscussionsListView(viewModel: FeedViewModel(service: MockService()))
        .environment(AuthManager.preview(signedIn: false))
}
