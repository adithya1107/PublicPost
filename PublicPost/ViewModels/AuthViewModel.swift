import Foundation
import Observation

/// Form state and validation for the login / register screen.
@Observable
final class AuthViewModel {

    enum Mode: String, CaseIterable, Identifiable {
        case login = "Log in"
        case register = "Register"

        var id: String { rawValue }
    }

    var mode: Mode = .login {
        didSet { errorMessage = nil }
    }
    var displayName = ""
    var email = ""
    var password = ""

    private(set) var isSubmitting = false
    var errorMessage: String?

    private let auth: AuthManager

    init(auth: AuthManager) {
        self.auth = auth
    }

    // MARK: - Validation

    private var trimmedName: String { displayName.trimmingCharacters(in: .whitespacesAndNewlines) }
    private var trimmedEmail: String { email.trimmingCharacters(in: .whitespacesAndNewlines) }

    /// A short hint explaining what is still missing, or `nil` when the form is valid.
    var validationHint: String? {
        // These limits mirror the backend's rules, so users get the hint before a round trip.
        if mode == .register && !(2...30).contains(trimmedName.count) { return "Display name must be 2 to 30 characters." }
        if !trimmedEmail.contains("@") || !trimmedEmail.contains(".") { return "Enter a valid email address." }
        if mode == .register && password.count < 8 { return "Password must be at least 8 characters." }
        if password.isEmpty { return "Enter your password." }
        return nil
    }

    var canSubmit: Bool { validationHint == nil && !isSubmitting }

    // MARK: - Submit

    /// Logs in or registers depending on `mode`. Returns `true` on success.
    func submit() async -> Bool {
        guard canSubmit else { return false }
        isSubmitting = true
        errorMessage = nil
        defer { isSubmitting = false }

        do {
            switch mode {
            case .login:
                try await auth.login(email: trimmedEmail, password: password)
            case .register:
                try await auth.register(displayName: trimmedName, email: trimmedEmail, password: password)
            }
            return true
        } catch {
            errorMessage = error.friendlyMessage
            return false
        }
    }
}
