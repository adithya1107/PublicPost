import SwiftUI

/// One story on the watch: title, summary, score and a link to its discussion.
struct WatchArticleView: View {
    let article: Article

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                Text(article.category.rawValue.uppercased())
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(.tint)

                Text(article.title)
                    .font(.headline)

                Text(article.summary)
                    .font(.footnote)
                    .foregroundStyle(.secondary)

                Text("\(article.sourceName) · \(article.publishedAt.formatted(.relative(presentation: .named)))")
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                // Voting needs an account, so the watch only shows the score.
                Label("Score \(article.score)", systemImage: "arrow.up.arrow.down")
                    .font(.footnote.weight(.semibold))
                    .accessibilityLabel("Score \(article.score)")

                NavigationLink {
                    WatchCommentsView(article: article)
                } label: {
                    Label("\(article.commentCount) \(article.commentCount == 1 ? "comment" : "comments")",
                          systemImage: "bubble.left")
                }

                Text("Open PublicPost on iPhone, iPad or Mac to vote, comment or read the full article.")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 4)
        }
        .navigationTitle(article.category.rawValue)
    }
}

#Preview {
    NavigationStack {
        WatchArticleView(article: .preview)
    }
}
