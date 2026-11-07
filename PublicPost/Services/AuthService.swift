import Foundation

/// What the server returns after a successful login or registration.
/// ASSUMED response shape: { "token": "...", "user": { "id": "...", "display_name": "..." } }
nonisolated struct AuthSession: Codable, Sendable {
    let token: String
    let user: User
}

/// Account operations. Implemented by `MockAuthService` and (Phase 6) `APIService`.
nonisolated protocol AuthService: Sendable {
    /// POST /auth/register
    func register(displayName: String, email: String, password: String) async throws -> AuthSession

    /// POST /auth/login
    func login(email: String, password: String) async throws -> AuthSession
}

/// The saved login: the token goes in the Keychain, and so does the user's name
/// (so the profile can be shown instantly on launch). Services read the token from
/// here to build the `Authorization: Bearer <token>` header.
nonisolated enum SessionStore {
    private static let tokenAccount = "auth-token"
    private static let userAccount = "auth-user"

    static var token: String? {
        KeychainStore.read(account: tokenAccount).flatMap { String(data: $0, encoding: .utf8) }
    }

    static var user: User? {
        KeychainStore.read(account: userAccount)
            .flatMap { try? JSONCoding.makeDecoder().decode(User.self, from: $0) }
    }

    static func save(_ session: AuthSession) throws {
        try KeychainStore.save(Data(session.token.utf8), account: tokenAccount)
        try KeychainStore.save(JSONCoding.makeEncoder().encode(session.user), account: userAccount)
    }

    static func clear() {
        KeychainStore.delete(account: tokenAccount)
        KeychainStore.delete(account: userAccount)
    }
}

/// Offline accounts for development. Accounts live in memory only (they are gone after
/// a relaunch), but one demo account is always available.
actor MockAuthService: AuthService {
    /// Demo account: demo@publicpost.app / password123
    private struct Account {
        let user: User
        let password: String
    }

    private var accounts: [String: Account] = [
        "demo@publicpost.app": Account(
            user: User(id: "u_demo", displayName: "Demo Reader"),
            password: "password123"
        )
    ]

    func register(displayName: String, email: String, password: String) async throws -> AuthSession {
        let key = email.lowercased()
        guard accounts[key] == nil else { throw ServiceError.emailTaken }
        let user = User(id: "u_" + UUID().uuidString.prefix(8).lowercased(), displayName: displayName)
        accounts[key] = Account(user: user, password: password)
        return AuthSession(token: "mock-token-\(user.id)", user: user)
    }

    func login(email: String, password: String) async throws -> AuthSession {
        guard let account = accounts[email.lowercased()], account.password == password else {
            throw ServiceError.invalidCredentials
        }
        return AuthSession(token: "mock-token-\(account.user.id)", user: account.user)
    }
}
