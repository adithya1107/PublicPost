import Foundation

/// A PublicPost account holder.
nonisolated struct User: Codable, Identifiable, Hashable, Sendable {
    let id: String
    let displayName: String
}

extension User {
    /// The user the mock service pretends is signed in.
    static let mockCurrent = User(id: "u_me", displayName: "Guest Reader")
}
