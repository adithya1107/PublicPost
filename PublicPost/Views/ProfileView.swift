import SwiftUI

/// Profile tab. Guests see a prompt to log in; logged-in users see their name,
/// a log out button and a list of their own comments.
struct ProfileView: View {
    @Environment(AuthManager.self) private var auth
    @State private var viewModel: ProfileViewModel
    @State private var loginPrompt: LoginPrompt?
    @State private var isConfirmingLogout = false

    init(viewModel: ProfileViewModel = ProfileViewModel()) {
        _viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        NavigationStack {
            Group {
                if let user = auth.currentUser {
                    commentsList(for: user)
                } else {
                    guestPlaceholder
                }
            }
            .navigationTitle("Profile")
            .toolbar {
                if auth.isLoggedIn {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("Log out") { isConfirmingLogout = true }
                    }
                }
            }
            .confirmationDialog("Log out of PublicPost?", isPresented: $isConfirmingLogout, titleVisibility: .visible) {
                Button("Log out", role: .destructive) {
                    auth.logout()
                    viewModel.reset()
                }
            }
        }
        // Reload whenever the logged-in user changes (login, logout, switching accounts).
        .task(id: auth.currentUser?.id) {
            if auth.isLoggedIn { await viewModel.load() }
        }
        .loginSheet(item: $loginPrompt)
    }

    // MARK: - Guest

    private var guestPlaceholder: some View {
        ContentUnavailableView {
            Label("You're browsing as a guest", systemImage: "person.crop.circle")
        } description: {
            Text("Log in to vote, join discussions and see your own comments here.")
        } actions: {
            Button("Log in or register") {
                loginPrompt = LoginPrompt(reason: nil)
            }
            .buttonStyle(.borderedProminent)
        }
    }

    // MARK: - Logged in

    private func commentsList(for user: User) -> some View {
        List {
            Section {
                HStack(spacing: 14) {
                    Text(String(user.displayName.prefix(1)).uppercased())
                        .font(.title2.weight(.bold))
                        .foregroundStyle(.white)
                        .frame(width: 52, height: 52)
                        .background(Color.accentColor.gradient, in: Circle())
                        .accessibilityHidden(true)
                    VStack(alignment: .leading) {
                        Text(user.displayName).font(.title3.weight(.semibold))
                        Text("Signed in").font(.footnote).foregroundStyle(.secondary)
                    }
                }
                .padding(.vertical, 4)
            }

            Section("My comments") {
                switch viewModel.state {
                case .loading:
                    HStack { Spacer(); ProgressView(); Spacer() }
                case .empty:
                    Text("You haven't commented yet. Join a discussion from the feed.")
                        .foregroundStyle(.secondary)
                case .error(let message):
                    VStack(alignment: .leading, spacing: 8) {
                        Text(message).foregroundStyle(.secondary)
                        Button("Try again") { Task { await viewModel.load() } }
                    }
                case .loaded:
                    ForEach(viewModel.items) { item in
                        row(item)
                    }
                }
            }
        }
        .refreshable { await viewModel.load(showSpinner: false) }
    }

    private func row(_ item: ProfileComment) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if let title = item.articleTitle {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Color.accentColor)
                    .lineLimit(2)
            }
            Text(item.comment.text)
            Text("\(item.comment.upvotes) upvotes · \(item.comment.createdAt.formatted(.relative(presentation: .named)))")
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 2)
    }
}

#Preview("Guest") {
    ProfileView()
        .environment(AuthManager.preview(signedIn: false))
}

#Preview("Logged in") {
    ProfileView(viewModel: ProfileViewModel(discussionService: PreviewProfileService(), newsService: MockService()))
        .environment(AuthManager.preview(signedIn: true))
}

/// Preview-only service returning a couple of "my comments" (the real mock needs a saved login).
private struct PreviewProfileService: DiscussionService {
    func fetchComments(articleId: String) async throws -> [Comment] { [] }
    func postComment(articleId: String, text: String, parentId: String?) async throws -> Comment { .preview }
    func setCommentUpvote(articleId: String, commentId: String, upvoted: Bool) async throws -> Int { 0 }

    func fetchMyComments() async throws -> [Comment] {
        [
            Comment(id: "m1", articleId: "n04", authorName: "Guest Reader",
                    text: "Start small with unplugged logic puzzles. You don't need a computer to teach thinking.",
                    createdAt: Date().addingTimeInterval(-7_200), upvotes: 6, parentId: nil),
            Comment(id: "m2", articleId: "n10", authorName: "Guest Reader",
                    text: "Cycle life is the real test for any fast-charging claim.",
                    createdAt: Date().addingTimeInterval(-86_400), upvotes: 2, parentId: nil)
        ]
    }
}
