import SwiftUI

/// Upvote / net score / downvote control. It only reports taps through `onVote`;
/// the view model decides what the new vote is and updates the article.
struct VoteBarView: View {
    let score: Int
    let userVote: Vote
    let onVote: (Vote) -> Void

    var body: some View {
        HStack(spacing: 6) {
            voteButton(.up, symbol: "arrow.up", tint: .orange)

            Text(score, format: .number)
                .font(.headline.monospacedDigit())
                .frame(minWidth: 36)
                .contentTransition(.numericText(value: Double(score)))
                .accessibilityLabel("Score")
                .accessibilityValue("\(score)")

            voteButton(.down, symbol: "arrow.down", tint: .indigo)
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 4)
        .background(Color(.secondarySystemBackground), in: Capsule())
        .animation(.snappy, value: score)
        .animation(.snappy, value: userVote)
        // Haptics: a firmer tap when a vote is cast, a light tick when it is removed.
        .sensoryFeedback(trigger: userVote) { _, newVote in
            newVote == .none ? .selection : .impact(flexibility: .soft)
        }
    }

    /// One arrow button; filled and tinted when it is the user's current vote.
    private func voteButton(_ vote: Vote, symbol: String, tint: Color) -> some View {
        let isSelected = userVote == vote
        return Button {
            onVote(vote)
        } label: {
            Image(systemName: isSelected ? "\(symbol).circle.fill" : symbol)
                .font(.title3.weight(.semibold))
                .foregroundStyle(isSelected ? tint : Color.secondary)
                .frame(width: 36, height: 36)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(vote == .up ? "Upvote" : "Downvote")
        .accessibilityAddTraits(isSelected ? .isSelected : [])
        .accessibilityHint(isSelected ? "Double tap to remove your vote" : "")
    }
}

#Preview("Interactive") {
    @Previewable @State var article = Article.preview
    VoteBarView(score: article.score, userVote: article.userVote) { tapped in
        article.setVote(article.voteAfterTapping(tapped))
    }
    .padding()
}

#Preview("Upvoted") {
    VoteBarView(score: 42, userVote: .up) { _ in }
        .padding()
}

#Preview("Downvoted, negative score") {
    VoteBarView(score: -3, userVote: .down) { _ in }
        .padding()
}
