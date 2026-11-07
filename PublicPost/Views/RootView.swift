import SwiftUI

/// App root: the tab bar (Feed, Discussions, Profile).
struct RootView: View {
    var body: some View {
        TabView {
            FeedView()
                .tabItem { Label("Feed", systemImage: "newspaper") }

            DiscussionsListView()
                .tabItem { Label("Discussions", systemImage: "bubble.left.and.bubble.right") }

            ProfileView()
                .tabItem { Label("Profile", systemImage: "person.crop.circle") }
        }
    }
}

#Preview {
    RootView()
        .environment(AuthManager.preview(signedIn: false))
}
