import SwiftUI
import SafariServices

/// Wraps `SFSafariViewController` so the original article opens inside the app.
struct SafariView: UIViewControllerRepresentable {
    let url: URL

    func makeUIViewController(context: Context) -> SFSafariViewController {
        SFSafariViewController(url: url)
    }

    func updateUIViewController(_ controller: SFSafariViewController, context: Context) {}
}

/// Small `Identifiable` wrapper so a URL can drive `.sheet(item:)`.
struct SafariDestination: Identifiable {
    let url: URL
    var id: URL { url }
}

#Preview {
    SafariView(url: URL(string: "https://www.apple.com")!)
        .ignoresSafeArea()
}
