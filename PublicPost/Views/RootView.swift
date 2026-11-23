import SwiftUI

/// App root: Feed, Discussions and Profile.
/// iPhone shows a bottom tab bar; on iPad and Mac the same tabs appear as a sidebar
/// (`.sidebarAdaptable`), which suits the larger screens.
struct RootView: View {
    var body: some View {
        TabView {
            Tab("Feed", systemImage: "newspaper") {
                FeedView()
            }
            Tab("Discussions", systemImage: "bubble.left.and.bubble.right") {
                DiscussionsListView()
            }
            Tab("Profile", systemImage: "person.crop.circle") {
                ProfileView()
            }
        }
        .tabViewStyle(.sidebarAdaptable)
        .sessionExpiredAlert()
    }
}

#Preview {
    RootView()
        .environment(AuthManager.preview(signedIn: false))
}
