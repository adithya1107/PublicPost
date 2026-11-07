import Foundation
import Testing
@testable import PublicPost

/// Token handling and the "401 means signed out" flow. These tests share the real Keychain,
/// so they run one at a time and always clean up.
@Suite(.serialized)
struct SessionTests {

    init() { SessionStore.clear() }

    private func signIn(token: String = "tok-123") throws {
        try SessionStore.save(AuthSession(token: token, user: User(id: "u1", displayName: "Meera")))
    }

    // MARK: - Bearer token

    @Test func getRequestsCarryTheBearerToken() async throws {
        defer { SessionStore.clear() }
        try signIn()
        let server = StubServer { request in
            request.path.hasSuffix("/comments") ? .json("[\(Fixtures.comment)]") : .json(Fixtures.articleList)
        }

        _ = try await server.api.fetchArticles(category: nil, page: 1)
        _ = try await server.api.fetchComments(articleId: "a1")

        #expect(server.requests.map(\.method) == ["GET", "GET"])
        #expect(server.requests.allSatisfy { $0.authorization == "Bearer tok-123" })
    }

    @Test func guestRequestsHaveNoAuthorizationHeader() async throws {
        let server = StubServer(.json(Fixtures.articleList))

        _ = try await server.api.fetchArticles(category: .tech, page: 2)

        #expect(server.requests[0].authorization == nil)
        #expect(server.requests[0].path == "/articles")
        #expect(server.requests[0].query?.contains("category=Tech") == true)
        #expect(server.requests[0].query?.contains("page=2") == true)
    }

    @Test func loginAndRegisterNeverSendAnOldToken() async throws {
        defer { SessionStore.clear() }
        try signIn(token: "old-token")
        let server = StubServer(.json(Fixtures.auth))

        _ = try await server.api.login(email: "a@b.com", password: "password1")
        _ = try await server.api.register(displayName: "Meera", email: "a@b.com", password: "password1")

        #expect(server.requests.allSatisfy { $0.authorization == nil })
        #expect(server.requests[0].body.contains("\"email\":\"a@b.com\""))
        #expect(server.requests[1].body.contains("\"display_name\":\"Meera\""))
    }

    // MARK: - 401 handling

    @Test func a401OnALoggedInRequestClearsTheSession() async throws {
        defer { SessionStore.clear() }
        try signIn()
        let server = StubServer(.http(401, #"{"detail":"Could not validate credentials"}"#))

        await #expect(throws: ServiceError.sessionExpired) {
            try await server.api.vote(articleId: "a1", vote: .up)
        }

        #expect(SessionStore.token == nil)
        #expect(SessionStore.user == nil)
    }

    @Test func a401ForAGuestIsJustUnauthorized() async {
        let server = StubServer(.http(401, #"{"detail":"Not authenticated"}"#))

        await #expect(throws: ServiceError.unauthorized) {
            try await server.api.vote(articleId: "a1", vote: .up)
        }
    }

    @Test func wrongPasswordIsNotASessionExpiry() async throws {
        defer { SessionStore.clear() }
        try signIn()
        let server = StubServer(.http(401, #"{"detail":"Incorrect email or password"}"#))

        await #expect(throws: ServiceError.invalidCredentials) {
            try await server.api.login(email: "a@b.com", password: "wrong")
        }
        #expect(SessionStore.token == "tok-123")   // the existing login is left alone
    }

    @Test func aLateReplyForAnOldTokenDoesNotSignOutANewLogin() async throws {
        defer { SessionStore.clear() }
        try signIn(token: "old-token")
        // While the request is "in flight" the user logs in again; then the old request fails.
        let server = StubServer { _ in
            try? SessionStore.save(AuthSession(token: "new-token", user: User(id: "u2", displayName: "Ravi")))
            return .http(401, #"{"detail":"expired"}"#)
        }

        await #expect(throws: ServiceError.unauthorized) {
            try await server.api.vote(articleId: "a1", vote: .up)
        }
        #expect(SessionStore.token == "new-token")
    }

    // MARK: - Full flow with AuthManager

    @MainActor
    @Test func aRejectedTokenReturnsTheAppToGuestModeWithAMessage() async throws {
        defer { SessionStore.clear() }
        let server = StubServer { request in
            request.method == "POST" && request.path == "/auth/login"
                ? .json(Fixtures.auth)
                : .http(401, #"{"detail":"Token expired"}"#)
        }
        let manager = AuthManager(service: server.api, restoreSession: false)
        try await manager.login(email: "a@b.com", password: "password1")
        #expect(manager.isLoggedIn)
        #expect(SessionStore.token == "tok-123")

        // Any logged-in request now gets a 401.
        _ = try? await server.api.fetchMyComments()

        // AuthManager hears about it through a notification, so give it a moment.
        for _ in 0..<100 where manager.isLoggedIn {
            try await Task.sleep(for: .milliseconds(20))
        }

        #expect(manager.isLoggedIn == false)
        #expect(manager.currentUser == nil)
        #expect(manager.sessionExpiredMessage == "Session expired, please log in again.")
        #expect(SessionStore.token == nil)
    }

    @MainActor
    @Test func loggingInAgainClearsTheExpiredMessage() async throws {
        defer { SessionStore.clear() }
        let server = StubServer(.json(Fixtures.auth))
        let manager = AuthManager(service: server.api, restoreSession: false)
        manager.sessionExpiredMessage = "Session expired, please log in again."

        try await manager.login(email: "a@b.com", password: "password1")

        #expect(manager.sessionExpiredMessage == nil)
    }

    @MainActor
    @Test func deletingTheAccountCallsTheServerThenLogsOut() async throws {
        defer { SessionStore.clear() }
        let server = StubServer { request in
            request.path == "/auth/login" ? .json(Fixtures.auth) : .noContent
        }
        let manager = AuthManager(service: server.api, restoreSession: false)
        try await manager.login(email: "a@b.com", password: "password1")

        try await manager.deleteAccount()

        let delete = try #require(server.requests.last)
        #expect(delete.method == "DELETE")
        #expect(delete.path == "/users/me")
        #expect(delete.authorization == "Bearer tok-123")
        #expect(manager.isLoggedIn == false)
        #expect(SessionStore.token == nil)
    }

    @MainActor
    @Test func aFailedAccountDeletionKeepsTheUserLoggedIn() async throws {
        defer { SessionStore.clear() }
        let server = StubServer { request in
            request.path == "/auth/login" ? .json(Fixtures.auth) : .http(500, #"{"detail":"boom"}"#)
        }
        let manager = AuthManager(service: server.api, restoreSession: false)
        try await manager.login(email: "a@b.com", password: "password1")

        await #expect(throws: ServiceError.server(statusCode: 500)) {
            try await manager.deleteAccount()
        }
        #expect(manager.isLoggedIn)
        #expect(SessionStore.token == "tok-123")
    }
}
