import SwiftUI

/// One comment (or reply) in the thread: avatar initial, author, time, text,
/// an upvote button and, for top-level comments only, a Reply button.
struct CommentRowView: View {
    let comment: Comment
    let onUpvote: () -> Void
    /// `nil` hides the Reply button (replies can't have replies).
    let onReply: (() -> Void)?

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            avatar

            VStack(alignment: .leading, spacing: 6) {
                Text("\(Text(comment.authorName).fontWeight(.semibold)) · \(comment.createdAt.formatted(.relative(presentation: .named)))")
                    .font(.footnote)
                    .foregroundStyle(.secondary)

                Text(comment.text)
                    .font(.body)

                HStack(spacing: 16) {
                    Button(action: onUpvote) {
                        Label {
                            Text(comment.upvotes, format: .number)
                                .monospacedDigit()
                                .contentTransition(.numericText(value: Double(comment.upvotes)))
                        } icon: {
                            Image(systemName: comment.userUpvoted ? "arrow.up.circle.fill" : "arrow.up")
                        }
                        .foregroundStyle(comment.userUpvoted ? Color.orange : Color.secondary)
                    }
                    .accessibilityLabel("Upvote")
                    .accessibilityValue("\(comment.upvotes) upvotes")
                    .accessibilityAddTraits(comment.userUpvoted ? .isSelected : [])

                    if let onReply {
                        Button("Reply", systemImage: "arrowshape.turn.up.left", action: onReply)
                            .foregroundStyle(.secondary)
                            .accessibilityLabel("Reply to \(comment.authorName)")
                    }
                }
                .font(.footnote.weight(.medium))
                .buttonStyle(.plain)
                .animation(.snappy, value: comment.upvotes)
                .sensoryFeedback(.selection, trigger: comment.userUpvoted)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 10)
    }

    /// Circle with the author's first letter.
    private var avatar: some View {
        Text(String(comment.authorName.prefix(1)).uppercased())
            .font(.footnote.weight(.bold))
            .foregroundStyle(.white)
            .frame(width: 30, height: 30)
            .background(Color.accentColor.gradient, in: Circle())
            .accessibilityHidden(true)   // the author's name is read in the text next to it
    }
}

#Preview("Comment with Reply") {
    CommentRowView(comment: .preview, onUpvote: {}, onReply: {})
        .padding()
}

#Preview("Upvoted, no Reply (a reply)") {
    var comment = Comment.preview
    comment.userUpvoted = true
    comment.upvotes = 13
    return CommentRowView(comment: comment, onUpvote: {}, onReply: nil)
        .padding()
}
