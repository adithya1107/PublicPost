import SwiftUI

/// Horizontal row of category filter chips. "All" is represented by `nil`.
struct CategoryChipsBar: View {
    @Binding var selection: NewsCategory?

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                chip(title: "All", isSelected: selection == nil) {
                    selection = nil
                }
                ForEach(NewsCategory.allCases) { category in
                    chip(title: category.rawValue, isSelected: selection == category) {
                        selection = category
                    }
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
        }
    }

    private func chip(title: String, isSelected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.subheadline.weight(.semibold))
                .padding(.horizontal, 14)
                .padding(.vertical, 7)
                .foregroundStyle(isSelected ? Color.white : Color.primary)
                .background(isSelected ? Color.accentColor : Color(.secondarySystemBackground), in: Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }
}

#Preview {
    @Previewable @State var selection: NewsCategory? = .tech
    CategoryChipsBar(selection: $selection)
}
