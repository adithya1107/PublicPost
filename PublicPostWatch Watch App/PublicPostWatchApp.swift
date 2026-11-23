import SwiftUI

/// The Apple Watch app: a quick reader for headlines, summaries and discussions.
/// It reuses the iPhone app's models, services and view models; only the screens are different.
/// (Voting and commenting need an account, so they stay on iPhone, iPad and Mac.)
@main
struct PublicPostWatchApp: App {
    var body: some Scene {
        WindowGroup {
            WatchRootView()
        }
    }
}
