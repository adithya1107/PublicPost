import SwiftUI

/// Headlines list: pick a category, tap a story to read its summary.
struct WatchRootView: View {
    @State private var viewModel: FeedViewModel

    init(viewModel: FeedViewModel = FeedViewModel()) {
        _viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        NavigationStack {
            content
                .navigationTitle("PublicPost")
                .navigationDestination(for: Article.self) { article in
                    WatchArticleView(article: article)
                }
        }
        // Runs on first appearance and whenever the category changes.
        .task(id: viewModel.selectedCategory) {
            await viewModel.reload(showSpinner: true)
        }
    }

    // MARK: - Content for each state

    @ViewBuilder
    private var content: some View {
        switch viewModel.state {
        case .loading:
            ProgressView("Loading…")
        case .empty:
            ContentUnavailableView("No stories", systemImage: "newspaper",
                                   description: Text("Nothing here right now."))
        case .error(let message):
            ScrollView {
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle")
                    Text(message).font(.footnote)
                    Button("Try again") {
                        Task { await viewModel.reload(showSpinner: true) }
                    }
                }
            }
        case .loaded:
            headlines
        }
    }

    private var headlines: some View {
        List {
            if let notice = viewModel.offlineNotice {
                Label(notice, systemImage: "wifi.slash")
                    .font(.footnote)
                    .listRowBackground(Color.yellow.opacity(0.25))
            }

            Picker("Category", selection: $viewModel.selectedCategory) {
                Text("All").tag(NewsCategory?.none)
                ForEach(NewsCategory.allCases) { category in
                    Text(category.rawValue).tag(NewsCategory?.some(category))
                }
            }

            ForEach(viewModel.articles) { article in
                NavigationLink(value: article) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(article.title)
                            .font(.headline)
                            .lineLimit(4)
                        Text("\(article.sourceName) · \(article.publishedAt.formatted(.relative(presentation: .named)))")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                .task { await viewModel.loadMoreIfNeeded(currentArticle: article) }
            }
        }
        .refreshable { await viewModel.reload(showSpinner: false) }
    }
}

#Preview {
    WatchRootView(viewModel: FeedViewModel(service: MockService()))
}
