import SwiftUI

/// Shows "Session expired, please log in again." when `AuthManager` signs the user out
/// because the server rejected their token. Applied to the root view AND to sheets, because
/// an alert can only appear on the topmost presented screen.
private struct SessionExpiredAlertModifier: ViewModifier {
    @Environment(AuthManager.self) private var auth

    func body(content: Content) -> some View {
        content.alert(
            "Signed out",
            isPresented: Binding(
                get: { auth.sessionExpiredMessage != nil },
                set: { if !$0 { auth.sessionExpiredMessage = nil } }
            )
        ) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(auth.sessionExpiredMessage ?? "")
        }
    }
}

extension View {
    func sessionExpiredAlert() -> some View {
        modifier(SessionExpiredAlertModifier())
    }
}
