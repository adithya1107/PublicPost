import SwiftUI

/// Describes a request to show the login screen. `reason` is shown at the top of the form.
struct LoginPrompt: Identifiable {
    let id = UUID()
    let reason: String?
}

/// Presents `AuthView` as a sheet whenever `item` is set. Each screen that can ask a guest
/// to log in applies this itself, because a sheet can only be shown from the topmost view
/// (the discussion sheet, for example, sits on top of the feed).
private struct LoginSheetModifier: ViewModifier {
    @Environment(AuthManager.self) private var auth
    @Binding var item: LoginPrompt?

    func body(content: Content) -> some View {
        content.sheet(item: $item) { prompt in
            AuthView(auth: auth, reason: prompt.reason)
        }
    }
}

extension View {
    /// Shows the login sheet when `item` becomes non-nil.
    func loginSheet(item: Binding<LoginPrompt?>) -> some View {
        modifier(LoginSheetModifier(item: item))
    }
}
