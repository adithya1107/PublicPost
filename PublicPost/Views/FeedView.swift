import SwiftUI

/// The main news feed: category chips on top, then one full-screen card per story
/// that the user swipes through vertically.
struct FeedView: View {
    @Environment(AuthManager.self) private var auth
    @State private var viewModel: FeedViewModel
    @State private var loginPrompt: LoginPrompt?
    @State private var safariDestination: SafariDestination?
    /// The article whose discussion sheet is open.
    @State private var discussionArticle: Article?

    init(viewModel: FeedViewModel = FeedViewModel()) {
        _viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        VStack(spacing: 0) {
            CategoryChipsBar(selection: $viewModel.selectedCategory)
            content
        }
        // Runs on first appearance and again whenever the category changes
        // (the previous load is cancelled automatically).
        .task(id: viewModel.selectedCategory) {
            await viewModel.reload(showSpinner: true)
        }
        .sheet(item: $safariDestination) { destination in
            SafariView(url: destination.url)
                .ignoresSafeArea()
        }
        .sheet(item: $discussionArticle) { article in
            DiscussionView(
                viewModel: DiscussionViewModel(article: article) { count in
                    viewModel.updateCommentCount(articleId: article.id, count: count)
                }
            )
        }
        .loginSheet(item: $loginPrompt)
        .alert("Couldn't refresh", isPresented: refreshErrorBinding) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(viewModel.refreshError ?? "")
        }
        .alert("Vote not saved", isPresented: voteErrorBinding) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(viewModel.voteError ?? "")
        }
    }

    // MARK: - Content for each state

    @ViewBuilder
    private var content: some View {
        switch viewModel.state {
        case .loading:
            LoadingStateView(message: "Loading stories…")
        case .empty:
            ScrollView {
                EmptyStateView(
                    title: "No stories yet",
                    message: "There's nothing in this category right now. Pull down to refresh."
                )
                .containerRelativeFrame(.vertical)
            }
            .refreshable { await viewModel.reload(showSpinner: false) }
        case .error(let message):
            ErrorStateView(message: message) {
                Task { await viewModel.reload(showSpinner: true) }
            }
        case .loaded:
            feed
        }
    }

    /// Vertical paging scroll view: each card fills the screen and snaps into place.
    private var feed: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                ForEach(viewModel.articles) { article in
                    ArticleCardView(article: article) { tapped in
                        // Guests can read, but must log in to vote.
                        guard auth.isLoggedIn else {
                            loginPrompt = LoginPrompt(reason: "Log in to vote on stories.")
                            return
                        }
                        Task { await viewModel.vote(on: article, tapped: tapped) }
                    } onOpenDiscussion: {
                        discussionArticle = article
                    } onReadFullArticle: {
                        safariDestination = SafariDestination(url: article.articleURL)
                    }
                    .containerRelativeFrame(.vertical)
                    .task { await viewModel.loadMoreIfNeeded(currentArticle: article) }
                }
            }
            .scrollTargetLayout()
        }
        .scrollTargetBehavior(.paging)
        .scrollIndicators(.hidden)
        .refreshable { await viewModel.reload(showSpinner: false) }
    }

    private var voteErrorBinding: Binding<Bool> {
        Binding(
            get: { viewModel.voteError != nil },
            set: { if !$0 { viewModel.voteError = nil } }
        )
    }

    private var refreshErrorBinding: Binding<Bool> {
        Binding(
            get: { viewModel.refreshError != nil },
            set: { if !$0 { viewModel.refreshError = nil } }
        )
    }
}

#Preview {
    FeedView(viewModel: FeedViewModel(service: MockService()))
        .environment(AuthManager.preview(signedIn: false))
}
