import Foundation

/// The signed-in user's vote on an article. Raw values match the backend contract
/// (`{"vote": "up" | "down" | "none"}`).
nonisolated enum Vote: String, Codable, Sendable {
    case up
    case down
    case none
}

/// News categories shown as filter chips. Raw values are sent as `?category=`.
nonisolated enum NewsCategory: String, Codable, CaseIterable, Identifiable, Sendable {
    case india = "India"
    case world = "World"
    case tech = "Tech"
    case sports = "Sports"
    case business = "Business"
    case science = "Science"

    var id: String { rawValue }
}

/// One short news story (about 60 words) plus its voting state.
nonisolated struct Article: Codable, Identifiable, Hashable, Sendable {
    let id: String                 // stable across launches and servers
    let title: String
    let summary: String
    let sourceName: String
    let articleURL: URL            // original article at the publisher
    let imageURL: URL?
    let category: NewsCategory
    let publishedAt: Date
    var upvotes: Int
    var downvotes: Int
    var commentCount: Int
    var userVote: Vote             // the current user's vote
    /// `true` for the stories bundled in the app (offline samples). Never sent by or saved
    /// from the server; their links are placeholders, so the UI hides "Read full article".
    var isSample: Bool = false

    /// Net score shown in the UI (upvotes minus downvotes).
    var score: Int { upvotes - downvotes }

    // The JSON decoder converts snake_case keys to camelCase first ("article_url"
    // becomes "articleUrl"), so the URL properties map to those converted names.
    enum CodingKeys: String, CodingKey {
        case id, title, summary, sourceName
        case articleURL = "articleUrl"
        case imageURL = "imageUrl"
        case category, publishedAt, upvotes, downvotes, commentCount, userVote
    }
}

nonisolated extension Article {
    /// The vote that results from tapping `tapped`: tapping the vote you already
    /// have removes it, otherwise the tapped vote replaces the current one.
    func voteAfterTapping(_ tapped: Vote) -> Vote {
        userVote == tapped ? .none : tapped
    }

    /// Switches to `newVote`: takes back the previous vote's count, then adds the new one.
    /// Used for optimistic UI updates and by `MockService`.
    mutating func setVote(_ newVote: Vote) {
        switch userVote {
        case .up: upvotes -= 1
        case .down: downvotes -= 1
        case .none: break
        }
        switch newVote {
        case .up: upvotes += 1
        case .down: downvotes += 1
        case .none: break
        }
        userVote = newVote
    }
}

nonisolated extension Article {
    /// Custom decoding so `user_vote` may be missing (e.g. guests) and defaults to `.none`.
    /// Declared in an extension so the memberwise initializer is kept.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        title = try c.decode(String.self, forKey: .title)
        summary = try c.decode(String.self, forKey: .summary)
        sourceName = try c.decode(String.self, forKey: .sourceName)
        articleURL = try c.decode(URL.self, forKey: .articleURL)
        imageURL = try c.decodeIfPresent(URL.self, forKey: .imageURL)
        category = try c.decode(NewsCategory.self, forKey: .category)
        publishedAt = try c.decode(Date.self, forKey: .publishedAt)
        upvotes = try c.decodeIfPresent(Int.self, forKey: .upvotes) ?? 0
        downvotes = try c.decodeIfPresent(Int.self, forKey: .downvotes) ?? 0
        commentCount = try c.decodeIfPresent(Int.self, forKey: .commentCount) ?? 0
        userVote = try c.decodeIfPresent(Vote.self, forKey: .userVote) ?? .none
    }
}

nonisolated extension Article {
    /// Sample article for SwiftUI previews.
    static let preview = Article(
        id: "preview-1",
        title: "City launches free bus rides on weekends",
        summary: "The city council has approved a six-month pilot that makes all municipal bus routes free on Saturdays and Sundays. Officials hope the move will cut traffic and help families save money. Critics say the programme could strain the transport budget, and the council will review ridership figures before deciding whether to extend it.",
        sourceName: "Daily Meridian",
        articleURL: URL(string: "https://example.com/news/free-weekend-buses")!,
        imageURL: URL(string: "https://picsum.photos/seed/publicpost1/800/1200"),
        category: .india,
        publishedAt: Date().addingTimeInterval(-3_600),
        upvotes: 128,
        downvotes: 14,
        commentCount: 3,
        userVote: .none
    )
}
