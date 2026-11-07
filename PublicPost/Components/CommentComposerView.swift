import SwiftUI

/// Text field and send button pinned to the bottom of the discussion screen.
/// Shows a "Replying to …" banner while a reply is in progress.
struct CommentComposerView: View {
    @Binding var text: String
    let replyingToName: String?
    let isPosting: Bool
    let canSend: Bool
    var isFocused: FocusState<Bool>.Binding
    let onCancelReply: () -> Void
    let onSend: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            Divider()

            if let replyingToName {
                HStack {
                    Text("Replying to \(replyingToName)")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    Spacer()
                    Button("Cancel reply", systemImage: "xmark.circle.fill", action: onCancelReply)
                        .labelStyle(.iconOnly)
                        .foregroundStyle(.secondary)
                }
                .padding(.horizontal)
                .padding(.top, 8)
            }

            HStack(alignment: .bottom, spacing: 8) {
                TextField(
                    replyingToName == nil ? "Add a comment…" : "Write a reply…",
                    text: $text,
                    axis: .vertical
                )
                .lineLimit(1...4)
                .focused(isFocused)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 18))

                Button(action: onSend) {
                    if isPosting {
                        ProgressView()
                            .frame(width: 32, height: 32)
                    } else {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.system(size: 32))
                    }
                }
                .disabled(!canSend)
                .accessibilityLabel("Send comment")
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
        }
        .background(.bar)
    }
}

#Preview("Composer") {
    @Previewable @State var text = ""
    @Previewable @FocusState var focused: Bool
    VStack {
        Spacer()
        CommentComposerView(
            text: $text, replyingToName: nil, isPosting: false,
            canSend: !text.isEmpty, isFocused: $focused,
            onCancelReply: {}, onSend: {}
        )
    }
}

#Preview("Replying") {
    @Previewable @State var text = "I agree with this"
    @Previewable @FocusState var focused: Bool
    VStack {
        Spacer()
        CommentComposerView(
            text: $text, replyingToName: "Asha", isPosting: false,
            canSend: true, isFocused: $focused,
            onCancelReply: {}, onSend: {}
        )
    }
}
