import Foundation
import Observation

/// App-wide login state. Injected into the SwiftUI environment at the root, so any
/// screen can ask `auth.isLoggedIn`. No user means the app is in guest mode.
@Observable
final class AuthManager {

    private(set) var currentUser: User?

    /// Set when the server rejected the saved login; the root view shows it in an alert.
    var sessionExpiredMessage: String?

    var isLoggedIn: Bool { currentUser != nil }

    private let service: any AuthService
    /// Listens for `APIService` reporting a 401 on a logged-in request.
    @ObservationIgnored private var sessionObserver: Task<Void, Never>?

    /// - Parameter restoreSession: when `true` (the app), a token saved in the Keychain
    ///   logs the user straight back in. Previews and tests pass `false`.
    init(service: any AuthService = Config.authService, restoreSession: Bool = true) {
        self.service = service
        if restoreSession {
            if SessionStore.token != nil, let user = SessionStore.user {
                currentUser = user
            } else {
                SessionStore.clear()   // half-saved session: start clean as a guest
            }
        }

        sessionObserver = Task { [weak self] in
            for await _ in NotificationCenter.default.notifications(named: .sessionExpired) {
                self?.handleSessionExpired()
            }
        }
    }

    isolated deinit {
        sessionObserver?.cancel()
    }

    func login(email: String, password: String) async throws {
        let session = try await service.login(email: email, password: password)
        try SessionStore.save(session)
        sessionExpiredMessage = nil
        currentUser = session.user
    }

    func register(displayName: String, email: String, password: String) async throws {
        let session = try await service.register(displayName: displayName, email: email, password: password)
        try SessionStore.save(session)
        sessionExpiredMessage = nil
        currentUser = session.user
    }

    func logout() {
        SessionStore.clear()
        currentUser = nil
    }

    /// The server said our token is no longer valid: forget the login, go back to guest
    /// mode and explain why. Safe to call several times (several requests may fail together).
    func handleSessionExpired() {
        guard isLoggedIn else { return }
        SessionStore.clear()
        currentUser = nil
        sessionExpiredMessage = ServiceError.sessionExpired.errorDescription
    }
}

extension AuthManager {
    /// Preview helper: a manager that is already logged in (or a guest). Does not touch the Keychain.
    static func preview(signedIn: Bool) -> AuthManager {
        let manager = AuthManager(service: MockAuthService(), restoreSession: false)
        manager.currentUser = signedIn ? .mockCurrent : nil
        return manager
    }
}
