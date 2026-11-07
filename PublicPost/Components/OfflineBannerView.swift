import SwiftUI

/// A slim banner telling the user the app can't reach the server.
struct OfflineBannerView: View {
    let message: String

    var body: some View {
        Label(message, systemImage: "wifi.slash")
            .font(.footnote.weight(.semibold))
            .foregroundStyle(.primary)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 6)
            .background(Color.yellow.opacity(0.25))
            .accessibilityElement(children: .combine)
    }
}

#Preview {
    VStack(spacing: 0) {
        OfflineBannerView(message: "Offline – showing sample stories")
        Spacer()
    }
}
