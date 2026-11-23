import SwiftUI

/// Small `Identifiable` wrapper so a URL can drive `.sheet(item:)`.
struct SafariDestination: Identifiable {
    let url: URL
    var id: URL { url }
}

#if os(iOS)
import SafariServices

/// Wraps `SFSafariViewController` so the original article opens inside the app (iPhone / iPad).
/// On Mac there is no in-app Safari view, so `FeedView` opens the default browser instead.
struct SafariView: UIViewControllerRepresentable {
    let url: URL

    func makeUIViewController(context: Context) -> SFSafariViewController {
        SFSafariViewController(url: url)
    }

    func updateUIViewController(_ controller: SFSafariViewController, context: Context) {}
}

#Preview {
    SafariView(url: URL(string: "https://www.apple.com")!)
        .ignoresSafeArea()
}
#endif
