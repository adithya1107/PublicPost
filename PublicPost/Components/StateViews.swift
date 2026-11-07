import SwiftUI

/// Full-screen spinner shown while content loads.
struct LoadingStateView: View {
    var message: String = "Loading…"

    var body: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text(message)
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// Shown when a request succeeded but there is nothing to display.
struct EmptyStateView: View {
    let title: String
    let message: String
    var systemImage: String = "newspaper"

    var body: some View {
        ContentUnavailableView(title, systemImage: systemImage, description: Text(message))
    }
}

/// Shown when loading failed, with a retry button.
struct ErrorStateView: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        ContentUnavailableView {
            Label("Something went wrong", systemImage: "exclamationmark.triangle")
        } description: {
            Text(message)
        } actions: {
            Button("Try again", action: retry)
                .buttonStyle(.borderedProminent)
        }
    }
}

#Preview("Loading") {
    LoadingStateView()
}

#Preview("Empty") {
    EmptyStateView(title: "No stories yet", message: "Nothing here for this category. Pull down to refresh.")
}

#Preview("Error") {
    ErrorStateView(message: "The server returned an error (500).") {}
}
