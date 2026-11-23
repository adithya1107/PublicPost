import SwiftUI

// Small helpers that hide the differences between iPhone, iPad and Mac, so the rest of the
// views can stay platform-neutral. (The Apple Watch app has its own views.)

// MARK: - Colors

extension Color {
    /// The main screen background (white in light mode, black in dark mode on iPhone / iPad).
    static var appBackground: Color {
        #if os(macOS)
        Color(nsColor: .windowBackgroundColor)
        #else
        Color(.systemBackground)
        #endif
    }

    /// A slightly different background for chips, buttons and text fields sitting on `appBackground`.
    static var appSecondaryBackground: Color {
        #if os(macOS)
        Color.primary.opacity(0.08)   // a soft tint that stays visible in both light and dark mode
        #else
        Color(.secondarySystemBackground)
        #endif
    }

    /// A thin divider line.
    static var appSeparator: Color {
        #if os(macOS)
        Color(nsColor: .separatorColor)
        #else
        Color(.separator)
        #endif
    }
}

// MARK: - Modifiers that only exist on some platforms

extension View {
    /// Small inline navigation title (iPhone / iPad). On Mac the window title is used as is.
    func inlineNavigationTitle() -> some View {
        #if os(iOS)
        return navigationBarTitleDisplayMode(.inline)
        #else
        return self
        #endif
    }

    /// Email field behaviour: email keyboard, no auto-capitalisation or auto-correction.
    func emailFieldBehavior() -> some View {
        #if os(iOS)
        return textContentType(.emailAddress)
            .keyboardType(.emailAddress)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
        #else
        return autocorrectionDisabled()
        #endif
    }

    /// Display-name field behaviour (the "nickname" autofill hint is iOS only).
    func displayNameFieldBehavior() -> some View {
        #if os(iOS)
        return textContentType(.nickname)
        #else
        return self
        #endif
    }

    /// Lets the keyboard be dragged away by scrolling. Only iPhone / iPad have a software keyboard.
    func dismissKeyboardOnScroll() -> some View {
        #if os(iOS)
        return scrollDismissesKeyboard(.interactively)
        #else
        return self
        #endif
    }

    /// A sensible minimum size for sheets on Mac, where they would otherwise be tiny.
    /// No effect on iPhone / iPad, where sheets size themselves.
    func macSheetSize(minWidth: CGFloat = 480, minHeight: CGFloat = 560) -> some View {
        #if os(macOS)
        return frame(minWidth: minWidth, minHeight: minHeight)
        #else
        return self
        #endif
    }
}
