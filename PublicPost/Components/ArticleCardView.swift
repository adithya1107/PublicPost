import SwiftUI

/// One full-screen, Inshorts-style news card: image on top, then title, summary,
/// and a bottom bar with votes, comments, source / time ago and a "Read full article" button.
struct ArticleCardView: View {
    let article: Article
    let onVote: (Vote) -> Void
    let onOpenDiscussion: () -> Void
    let onReadFullArticle: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            image

            // The text scrolls only if it doesn't fit (very large Dynamic Type sizes),
            // so the vote bar and button below always stay on screen.
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Text(article.category.rawValue.uppercased())
                        .font(.caption.weight(.bold))
                        .foregroundStyle(Color.accentColor)

                    Text(article.title)
                        .font(.title2.weight(.bold))
                        .accessibilityAddTraits(.isHeader)

                    Text(article.summary)
                        .font(.body)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding([.horizontal, .top])
            }
            .scrollBounceBehavior(.basedOnSize)   // short text: swipes go to the feed instead

            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    VoteBarView(score: article.score, userVote: article.userVote, onVote: onVote)
                    Spacer()
                    commentsButton
                }

                // Source and relative time, e.g. "Daily Meridian · 2 hours ago".
                Text("\(article.sourceName) · \(article.publishedAt.formatted(.relative(presentation: .named)))")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)   // wrap instead of truncating

                Button(action: onReadFullArticle) {
                    Label("Read full article", systemImage: "safari")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .accessibilityHint("Opens the original article in the app")
            }
            .padding()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(Color(.systemBackground))
    }

    /// Opens the discussion thread for this story.
    private var commentsButton: some View {
        Button(action: onOpenDiscussion) {
            Label {
                Text(article.commentCount, format: .number)
                    .monospacedDigit()
            } icon: {
                Image(systemName: "bubble.left")
            }
            .font(.headline)
            .padding(.horizontal, 14)
            .frame(minHeight: 44)
            .background(Color(.secondarySystemBackground), in: Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(article.commentCount) \(article.commentCount == 1 ? "comment" : "comments")")
        .accessibilityHint("Opens the discussion")
    }

    /// Top ~35% of the card. Shows a placeholder when there is no URL or loading fails.
    private var image: some View {
        Color(.secondarySystemBackground)
            .overlay {
                AsyncImage(url: article.imageURL) { phase in
                    switch phase {
                    case .success(let loaded):
                        loaded.resizable().scaledToFill()
                    case .empty where article.imageURL != nil:
                        ProgressView()
                    default:
                        Image(systemName: "newspaper")
                            .font(.system(size: 48))
                            .foregroundStyle(.tertiary)
                    }
                }
            }
            .containerRelativeFrame(.vertical) { height, _ in height * 0.35 }
            .clipped()
            .accessibilityHidden(true)   // decorative: the title already says what the story is
    }
}

#Preview("With image (tap to vote)") {
    @Previewable @State var article = Article.preview
    ArticleCardView(article: article) { tapped in
        article.setVote(article.voteAfterTapping(tapped))
    } onOpenDiscussion: {} onReadFullArticle: {}
}

#Preview("No image") {
    let article = Article(
        id: "preview-2", title: Article.preview.title, summary: Article.preview.summary,
        sourceName: "Circuit Daily", articleURL: Article.preview.articleURL, imageURL: nil,
        category: .tech, publishedAt: Article.preview.publishedAt, upvotes: 5, downvotes: 9,
        commentCount: 0, userVote: .down
    )
    ArticleCardView(article: article) { _ in } onOpenDiscussion: {} onReadFullArticle: {}
}
