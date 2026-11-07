import Foundation
import Testing
@testable import PublicPost

/// The app must decode exactly what the backend sends (snake_case keys, ISO 8601 dates).
struct DecodingTests {

    private let decoder = JSONCoding.makeDecoder()

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try decoder.decode(type, from: Data(json.utf8))
    }

    @Test func decodesARealArticle() throws {
        let article = try decode(Article.self, Fixtures.article)

        #expect(article.id == "ff021b187b202cb4")
        #expect(article.sourceName == "The Hindu")
        #expect(article.category == .tech)
        #expect(article.articleURL.host == "www.thehindu.com")
        #expect(article.imageURL != nil)
        #expect(article.userVote == .none)
        #expect(article.isSample == false)
        #expect(article.publishedAt == ISO8601DateFormatter().date(from: "2026-11-07T07:44:22Z"))
    }

    @Test func decodesNullImageAndUserVote() throws {
        let article = try decode(Article.self, Fixtures.articleNoImage)

        #expect(article.imageURL == nil)
        #expect(article.userVote == .up)
        #expect(article.score == 2)
        #expect(article.commentCount == 2)
    }

    @Test func missingUserVoteDefaultsToNone() throws {
        let json = Fixtures.articleNoImage.replacingOccurrences(of: ",\"user_vote\":\"up\"", with: "")
        #expect(try decode(Article.self, json).userVote == .none)
    }

    @Test func decodesAList() throws {
        #expect(try decode([Article].self, Fixtures.articleList).count == 1)
        #expect(try decode([Article].self, "[]").isEmpty)
    }

    @Test func decodesATopLevelCommentAndAReply() throws {
        let top = try decode(Comment.self, Fixtures.comment)
        #expect(top.authorId == "u_abc123")
        #expect(top.authorName == "Meera")
        #expect(top.parentId == nil)
        #expect(top.isReply == false)
        #expect(top.userUpvoted == true)

        let reply = try decode(Comment.self, Fixtures.reply)
        #expect(reply.parentId == "c1")
        #expect(reply.isReply)
        #expect(reply.userUpvoted == false)
    }

    @Test func commentWithoutAuthorIdIsRejected() {
        let json = Fixtures.comment.replacingOccurrences(of: "\"author_id\":\"u_abc123\",", with: "")
        #expect(throws: DecodingError.self) { try decode(Comment.self, json) }
    }

    @Test func decodesTheLoginResponse() throws {
        let session = try decode(AuthSession.self, Fixtures.auth)
        #expect(session.token == "tok-123")
        #expect(session.user.id == "u_abc123")
        #expect(session.user.displayName == "Meera")
    }

    @Test func decodesTheVoteResponse() throws {
        let result = try decode(VoteResult.self, Fixtures.voteResponse)
        #expect(result.upvotes == 5)
        #expect(result.downvotes == 1)
        #expect(result.userVote == .up)
    }

    @Test func acceptsDatesWithFractionalSeconds() throws {
        let json = Fixtures.articleNoImage.replacingOccurrences(of: "06:30:00Z", with: "06:30:00.123Z")
        #expect(try decode(Article.self, json).publishedAt > Date(timeIntervalSince1970: 0))
    }

    @Test func rejectsAnUnknownCategory() {
        let json = Fixtures.articleNoImage.replacingOccurrences(of: "\"World\"", with: "\"Cooking\"")
        #expect(throws: DecodingError.self) { try decode(Article.self, json) }
    }

    @Test func bundledSampleDataStillDecodes() throws {
        let articles = try BundledData.loadArticles()
        let comments = try BundledData.loadComments()

        #expect(articles.count == 25)
        #expect(articles.allSatisfy(\.isSample))
        #expect(comments.allSatisfy { !$0.authorId.isEmpty })
    }
}
