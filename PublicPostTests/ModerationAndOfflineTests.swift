import Foundation
import Testing
@testable import PublicPost

/// Report / block requests, the feed cache and offline banner, and friendly error messages.
struct ModerationAndOfflineTests {

    // MARK: - Moderation requests (App Store guideline 1.2)

    @Test func reportingSendsTheReasonAndExpectsNoContent() async throws {
        let server = StubServer(.noContent)

        try await server.api.reportComment(commentId: "c1", reason: .misinformation)

        let request = try #require(server.requests.first)
        #expect(request.method == "POST")
        #expect(request.path == "/comments/c1/report")
        #expect(request.body == #"{"reason":"misinformation"}"#)
    }

    @Test func everyReportReasonMatchesTheBackendsValues() {
        #expect(ReportReason.allCases.map(\.rawValue) == ["spam", "abuse", "misinformation", "other"])
    }

    @Test func blockingCallsTheBlockRoute() async throws {
        let server = StubServer(.noContent)

        try await server.api.blockUser(userId: "u_abc123")

        let request = try #require(server.requests.first)
        #expect(request.method == "POST")
        #expect(request.path == "/users/u_abc123/block")
    }

    @Test func aReplyIsPostedWithItsParentAndATopLevelCommentWithout() async throws {
        let server = StubServer(.json(Fixtures.comment))

        _ = try await server.api.postComment(articleId: "a1", text: "Top", parentId: nil)
        _ = try await server.api.postComment(articleId: "a1", text: "Re", parentId: "c1")

        #expect(server.requests[0].body == #"{"text":"Top"}"#)          // parent_id left out
        #expect(server.requests[1].body.contains(#""parent_id":"c1""#))
    }

    @Test func commentUpvoteSendsTheDesiredState() async throws {
        let server = StubServer(.json(#"{"upvotes":9}"#))

        let count = try await server.api.setCommentUpvote(articleId: "a1", commentId: "c1", upvoted: true)

        #expect(count == 9)
        #expect(server.requests[0].path == "/comments/c1/upvote")
        #expect(server.requests[0].body == #"{"upvoted":true}"#)
    }

    @MainActor
    @Test func blockingHidesThatUsersCommentsImmediatelyAndRollsBackOnFailure() async throws {
        let comments = try [Fixtures.comment, Fixtures.reply].map {
            try JSONCoding.makeDecoder().decode(Comment.self, from: Data($0.utf8))
        }
        let server = StubServer { request in
            switch request.path {
            case "/articles/a1/comments": .json("[\(Fixtures.comment),\(Fixtures.reply)]")
            case "/users/u_abc123/block": .noContent
            default: .http(500, #"{"detail":"boom"}"#)
            }
        }
        let viewModel = DiscussionViewModel(article: makeArticle(id: "a1"), service: server.api)
        await viewModel.load()
        #expect(viewModel.threads.count == 2)   // the reply's parent is c1, but both are visible to start with

        // Success: Meera's comment disappears.
        await viewModel.block(comments[0])
        #expect(viewModel.threads.allSatisfy { $0.comment.authorId != "u_abc123" })
        #expect(viewModel.notice != nil)

        // Failure: Ravi's comment comes back.
        await viewModel.block(comments[1])
        #expect(viewModel.blockedAuthorIDs.contains("u_def456") == false)
        #expect(viewModel.actionError != nil)
    }

    // MARK: - Feed cache

    @Test func theCacheKeepsEverythingExceptTheSampleFlag() throws {
        let cache = makeTemporaryCache()
        let original = makeArticle(id: "a1", upvotes: 7, downvotes: 1, userVote: .down, isSample: true)

        cache.save([original], category: .sports)
        let loaded = try #require(cache.load(category: .sports)?.first)

        #expect(loaded.id == "a1")
        #expect(loaded.upvotes == 7)
        #expect(loaded.userVote == .down)
        #expect(loaded.articleURL == original.articleURL)
        #expect(loaded.publishedAt == original.publishedAt)
        #expect(loaded.isSample == false)       // saved stories are never "samples"
    }

    @Test func clearingTheCacheRemovesEverything() {
        let cache = makeTemporaryCache()
        cache.save([makeArticle()], category: nil)
        cache.save([makeArticle()], category: .tech)

        cache.clear()

        #expect(cache.load(category: nil) == nil)
        #expect(cache.load(category: .tech) == nil)
    }

    @Test func aCorruptCacheFileIsIgnored() throws {
        let cache = makeTemporaryCache()
        cache.save([makeArticle()], category: nil)
        let file = try #require(
            FileManager.default.contentsOfDirectory(at: cache.directory, includingPropertiesForKeys: nil).first
        )
        try Data("not json".utf8).write(to: file)

        #expect(cache.load(category: nil) == nil)
    }

    // MARK: - Feed view model: instant cache and offline banner

    @MainActor
    @Test func savedStoriesAppearInstantlyWhileTheRefreshRuns() async throws {
        let service = StubNewsService(
            articles: [makeArticle(id: "fresh")],
            cached: [makeArticle(id: "saved")],
            fetchDelay: .milliseconds(400)
        )
        let viewModel = FeedViewModel(service: service)

        let load = Task { await viewModel.reload(showSpinner: true) }
        try await Task.sleep(for: .milliseconds(150))

        // Refresh still running, but the saved stories are already on screen.
        #expect(viewModel.state == .loaded)
        #expect(viewModel.articles.map(\.id) == ["saved"])

        await load.value
        #expect(viewModel.articles.map(\.id) == ["fresh"])
    }

    @MainActor
    @Test func theBannerSaysSampleOrSavedDependingOnWhatIsShown() async {
        let sampleFeed = FeedViewModel(service: StubNewsService(articles: [makeArticle(isSample: true)], offline: true))
        await sampleFeed.reload(showSpinner: true)
        #expect(sampleFeed.offlineNotice == "Offline – showing sample stories")

        let savedFeed = FeedViewModel(service: StubNewsService(articles: [makeArticle()], offline: true))
        await savedFeed.reload(showSpinner: true)
        #expect(savedFeed.offlineNotice == "Offline – showing saved stories")

        let liveFeed = FeedViewModel(service: StubNewsService(articles: [makeArticle()], offline: false))
        await liveFeed.reload(showSpinner: true)
        #expect(liveFeed.offlineNotice == nil)
    }

    // MARK: - Friendly errors

    @Test func httpFailuresBecomeFriendlyMessages() async {
        let cases: [(StubReply, ServiceError)] = [
            (.http(404, #"{"detail":"Article not found"}"#), .notFound),
            (.http(429, #"{"detail":"Rate limit exceeded"}"#), .rateLimited),
            (.http(400, #"{"detail":"Please write something before posting."}"#), .api("Please write something before posting.")),
            (.http(422, #"{"detail":"Comments can be at most 1000 characters."}"#), .api("Comments can be at most 1000 characters.")),
            (.http(503, "<html>Bad gateway</html>"), .server(statusCode: 503)),
            (.http(200, "not json"), .invalidResponse),
        ]
        for (reply, expected) in cases {
            let server = StubServer(reply)
            await #expect(throws: expected) {
                try await server.api.fetchArticle(id: "a1")
            }
        }
    }

    @Test func networkFailuresBecomeFriendlyMessages() async {
        let server = StubServer(.network(.notConnectedToInternet))

        do {
            _ = try await server.api.fetchArticles(category: nil, page: 1)
            Issue.record("Expected a network error")
        } catch {
            #expect(error.userMessage == "You appear to be offline. Check your connection and try again.")
        }
    }

    @Test func messagesNeverExposeTechnicalDetails() {
        let messages = [
            ServiceError.server(statusCode: 500).userMessage,
            ServiceError.invalidResponse.userMessage,
            ServiceError.notFound.userMessage,
            ServiceError.rateLimited.userMessage,
            URLError(.timedOut).userMessage,
            URLError(.cannotConnectToHost).userMessage,
            DecodingError.dataCorrupted(.init(codingPath: [], debugDescription: "x")).userMessage,
        ].compactMap { $0 }

        #expect(messages.count == 7)
        for message in messages {
            #expect(!message.contains("500") && !message.contains("URLError") && !message.contains("Decoding"))
            #expect(message.hasSuffix(".") || message.hasSuffix("?"))
        }
    }

    @Test func cancellationAndSessionExpiryShowNoAlert() {
        #expect(CancellationError().userMessage == nil)
        #expect(ServiceError.sessionExpired.userMessage == nil)
        #expect(ServiceError.sessionExpired.errorDescription == "Session expired, please log in again.")
    }
}
