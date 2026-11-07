import Foundation
import Observation

/// App-wide login state. Injected into the SwiftUI environment at the root, so any
/// screen can ask `auth.isLoggedIn`. No user means the app is in guest mode.
@Observable
final class AuthManager {

    private(set) var currentUser: User?

    var isLoggedIn: Bool { currentUser != nil }

    private let service: any AuthService

    /// - Parameter restoreSession: when `true` (the app), a token saved in the Keychain
    ///   logs the user straight back in. Previews pass `false`.
    init(service: any AuthService = Config.authService, restoreSession: Bool = true) {
        self.service = service
        if restoreSession {
            if SessionStore.token != nil, let user = SessionStore.user {
                currentUser = user
            } else {
                SessionStore.clear()   // half-saved session: start clean as a guest
            }
        }
    }

    func login(email: String, password: String) async throws {
        let session = try await service.login(email: email, password: password)
        try SessionStore.save(session)
        currentUser = session.user
    }

    func register(displayName: String, email: String, password: String) async throws {
        let session = try await service.register(displayName: displayName, email: email, password: password)
        try SessionStore.save(session)
        currentUser = session.user
    }

    func logout() {
        SessionStore.clear()
        currentUser = nil
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
