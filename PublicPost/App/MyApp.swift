import SwiftUI

@main struct MyApp: App {
    /// One login state for the whole app, shared through the environment.
    @State private var auth = AuthManager()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(auth)
        }
    }
}
