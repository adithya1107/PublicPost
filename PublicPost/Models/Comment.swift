import Foundation

/// A comment in an article's discussion thread. Only one level of replies is
/// supported: a reply has a `parentId`, and replies never have replies of their own.
nonisolated struct Comment: Codable, Identifiable, Hashable, Sendable {
    let id: String
    let articleId: String
    let authorName: String
    let text: String
    let createdAt: Date
    var upvotes: Int
    let parentId: String?          // nil for top-level comments
    var userUpvoted: Bool = false  // whether the current user has upvoted it

    var isReply: Bool { parentId != nil }

    enum CodingKeys: String, CodingKey {
        case id, articleId, authorName, text, createdAt, upvotes, parentId, userUpvoted
    }
}

extension Comment {
    /// Custom decoding so `user_upvoted` may be missing (e.g. guests) and defaults to `false`.
    /// Declared in an extension so the memberwise initializer is kept.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        articleId = try c.decode(String.self, forKey: .articleId)
        authorName = try c.decode(String.self, forKey: .authorName)
        text = try c.decode(String.self, forKey: .text)
        createdAt = try c.decode(Date.self, forKey: .createdAt)
        upvotes = try c.decodeIfPresent(Int.self, forKey: .upvotes) ?? 0
        parentId = try c.decodeIfPresent(String.self, forKey: .parentId)
        userUpvoted = try c.decodeIfPresent(Bool.self, forKey: .userUpvoted) ?? false
    }
}

extension Comment {
    /// Sample comment for SwiftUI previews.
    static let preview = Comment(
        id: "preview-c1",
        articleId: "preview-1",
        authorName: "Asha",
        text: "Good idea in principle, but I want to see how they plan to pay for it.",
        createdAt: Date().addingTimeInterval(-1_800),
        upvotes: 12,
        parentId: nil
    )
}
