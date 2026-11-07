import Foundation
import Testing
@testable import PublicPost

/// Vote arithmetic and the feed's optimistic update / rollback.
struct VotingTests {

    // MARK: - Pure vote logic

    @Test func tappingTheSameVoteRemovesIt() {
        var article = makeArticle(upvotes: 10, downvotes: 2)

        article.setVote(article.voteAfterTapping(.up))
        #expect(article.userVote == .up)
        #expect(article.upvotes == 11)

        article.setVote(article.voteAfterTapping(.up))      // same again: removed
        #expect(article.userVote == Vote.none)
        #expect(article.upvotes == 10)
    }

    @Test func switchingVoteMovesTheCount() {
        var article = makeArticle(upvotes: 10, downvotes: 2, userVote: .up)
        article.upvotes = 11   // the user's own upvote is already counted

        article.setVote(article.voteAfterTapping(.down))
        #expect(article.userVote == .down)
        #expect(article.upvotes == 10)
        #expect(article.downvotes == 3)
        #expect(article.score == 7)
    }

    @Test func downvoteThenRemove() {
        var article = makeArticle(upvotes: 10, downvotes: 2)
        article.setVote(article.voteAfterTapping(.down))
        article.setVote(article.voteAfterTapping(.down))
        #expect(article.downvotes == 2)
        #expect(article.userVote == Vote.none)
    }

    // MARK: - Feed view model

    @MainActor
    private func loadedViewModel(voteResult: Result<VoteResult, Error>) async -> FeedViewModel {
        let service = StubNewsService(articles: [makeArticle()], voteResult: voteResult)
        let viewModel = FeedViewModel(service: service)
        await viewModel.reload(showSpinner: true)
        return viewModel
    }

    @MainActor
    @Test func voteIsConfirmedWithTheServersCounts() async {
        // The server's numbers win over our local arithmetic (e.g. other people voted meanwhile).
        let viewModel = await loadedViewModel(
            voteResult: .success(VoteResult(upvotes: 50, downvotes: 4, userVote: .up))
        )

        await viewModel.vote(on: viewModel.articles[0], tapped: .up)

        #expect(viewModel.articles[0].upvotes == 50)
        #expect(viewModel.articles[0].downvotes == 4)
        #expect(viewModel.articles[0].userVote == .up)
        #expect(viewModel.voteError == nil)
    }

    @MainActor
    @Test func failedVoteRollsBackAndExplainsWhy() async {
        let viewModel = await loadedViewModel(voteResult: .failure(ServiceError.network("You appear to be offline.")))
        let before = viewModel.articles[0]

        await viewModel.vote(on: before, tapped: .up)

        #expect(viewModel.articles[0].upvotes == before.upvotes)
        #expect(viewModel.articles[0].userVote == before.userVote)
        #expect(viewModel.voteError == "You appear to be offline.")
    }

    @MainActor
    @Test func expiredSessionRollsBackWithoutASecondAlert() async {
        // AuthManager shows the "Session expired" message, so the vote alert must stay quiet.
        let viewModel = await loadedViewModel(voteResult: .failure(ServiceError.sessionExpired))
        let before = viewModel.articles[0]

        await viewModel.vote(on: before, tapped: .down)

        #expect(viewModel.articles[0].downvotes == before.downvotes)
        #expect(viewModel.articles[0].userVote == before.userVote)
        #expect(viewModel.voteError == nil)
    }
}
