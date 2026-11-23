import SwiftUI

@main struct MyApp: App {
    /// One login state for the whole app, shared through the environment.
    @State private var auth = AuthManager()

    init() {
        Config.configureImageCache()
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(auth)
                #if os(macOS)
                .frame(minWidth: 520, minHeight: 640)   // keep the Mac window usable when resized
                #endif
        }
        #if os(macOS)
        .defaultSize(width: 900, height: 820)
        #endif
    }
}
