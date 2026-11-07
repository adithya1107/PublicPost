import Foundation
import Testing
@testable import PublicPost

/// Where page 1 of the feed comes from: server, then disk cache, then bundled samples.
struct ResilientServiceTests {

    private func makeService(server: StubServer, cache: FeedCache = makeTemporaryCache()) -> ResilientService {
        ResilientService(primary: server.api, fallback: MockService(), cache: cache)
    }

    // MARK: - Server is healthy

    @Test func liveFeedIsReturnedAndSavedToTheCache() async throws {
        let cache = makeTemporaryCache()
        let service = makeService(server: StubServer(.json(Fixtures.articleList)), cache: cache)

        let articles = try await service.fetchArticles(category: .tech, page: 1)

        #expect(articles.map(\.id) == ["ff021b187b202cb4"])
        #expect(await service.isOffline() == false)
        #expect(cache.load(category: .tech)?.map(\.id) == ["ff021b187b202cb4"])
        #expect(cache.load(category: .world) == nil)   // each category has its own file
    }

    @Test func cachedStoriesAreAvailableInstantlyOnTheNextLaunch() async throws {
        let cache = makeTemporaryCache()
        _ = try await makeService(server: StubServer(.json(Fixtures.articleList)), cache: cache)
            .fetchArticles(category: nil, page: 1)

        // A "new launch": a fresh service object sharing only the cache folder.
        let nextLaunch = makeService(server: StubServer(.network(.notConnectedToInternet)), cache: cache)

        #expect(await nextLaunch.cachedArticles(category: nil).map(\.id) == ["ff021b187b202cb4"])
    }

    // MARK: - Server is down

    @Test func withNothingCachedItFallsBackToTheBundledSamples() async throws {
        let service = makeService(server: StubServer(.network(.cannotConnectToHost)))

        let articles = try await service.fetchArticles(category: nil, page: 1)

        #expect(articles.count == Config.pageSize)
        #expect(articles.allSatisfy { $0.isSample })
        #expect(await service.isOffline())
    }

    @Test func aServerErrorAlsoTriggersTheFallback() async throws {
        let service = makeService(server: StubServer(.http(500, #"{"detail":"boom"}"#)))

        let articles = try await service.fetchArticles(category: nil, page: 1)

        #expect(articles.allSatisfy { $0.isSample })
        #expect(await service.isOffline())
    }

    @Test func savedRealStoriesAreShownInsteadOfSamplesWhenOffline() async throws {
        let cache = makeTemporaryCache()
        let server = StubServer(.json(Fixtures.articleList))
        let service = makeService(server: server, cache: cache)
        _ = try await service.fetchArticles(category: nil, page: 1)

        server.respond(with: .network(.notConnectedToInternet))
        let articles = try await service.fetchArticles(category: nil, page: 1)

        #expect(articles.map(\.id) == ["ff021b187b202cb4"])
        #expect(articles.allSatisfy { !$0.isSample })      // real stories, so "Read full article" stays
        #expect(await service.isOffline())
    }

    @Test func sampleStoriesStayFullyUsableOffline() async throws {
        let service = makeService(server: StubServer(.network(.cannotConnectToHost)))
        _ = try await service.fetchArticles(category: nil, page: 1)

        // Votes and comments on sample ids go to the bundled data, not the (down) server.
        let vote = try await service.vote(articleId: "n01", vote: .up)
        let comments = try await service.fetchComments(articleId: "n01")

        #expect(vote.userVote == .up)
        #expect(comments.isEmpty == false)
    }

    @Test func callsForCachedRealStoriesStillGoToTheServer() async throws {
        let server = StubServer(.json(Fixtures.articleList))
        let service = makeService(server: server)
        _ = try await service.fetchArticles(category: nil, page: 1)
        server.respond(with: .network(.notConnectedToInternet))
        _ = try await service.fetchArticles(category: nil, page: 1)   // now showing the cache

        // The real server owns these ids, so the vote must fail with a friendly offline message
        // instead of silently succeeding against the bundled mock.
        await #expect(throws: ServiceError.self) {
            try await service.vote(articleId: "ff021b187b202cb4", vote: .up)
        }
    }

    // MARK: - Recovery and paging

    @Test func theAppGoesBackOnlineWhenTheServerReturns() async throws {
        let server = StubServer(.network(.cannotConnectToHost))
        let service = makeService(server: server)
        _ = try await service.fetchArticles(category: nil, page: 1)
        #expect(await service.isOffline())

        server.respond(with: .json(Fixtures.articleList))
        let articles = try await service.fetchArticles(category: nil, page: 1)

        #expect(articles.map(\.id) == ["ff021b187b202cb4"])
        #expect(await service.isOffline() == false)
    }

    @Test func laterPagesNeverFallBackSoStoriesDontMix() async throws {
        let server = StubServer(.json(Fixtures.articleList))
        let service = makeService(server: server)
        _ = try await service.fetchArticles(category: nil, page: 1)

        server.respond(with: .http(500, "{}"))

        await #expect(throws: ServiceError.server(statusCode: 500)) {
            try await service.fetchArticles(category: nil, page: 2)
        }
        #expect(await service.isOffline() == false)
    }

    @Test func aCancelledLoadIsNotTreatedAsAnOutage() async {
        let service = makeService(server: StubServer(.network(.cancelled)))

        await #expect(throws: CancellationError.self) {
            try await service.fetchArticles(category: nil, page: 1)
        }
        #expect(await service.isOffline() == false)
    }
}
