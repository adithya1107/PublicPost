import Foundation

/// Saves the last successfully loaded page 1 of the feed (one file per category) in the
/// Caches directory, so the app can show stories instantly on launch and keep showing real
/// (if slightly old) news when the server can't be reached. iOS may delete Caches files
/// when storage is low, which is fine: this is only a convenience copy.
nonisolated struct FeedCache: Sendable {

    let directory: URL

    /// The app's cache. Tests create their own with a temporary folder.
    static let shared = FeedCache(
        directory: URL.cachesDirectory.appending(path: "FeedCache", directoryHint: .isDirectory)
    )

    private func file(for category: NewsCategory?) -> URL {
        directory.appending(path: "feed-\(category?.rawValue.lowercased() ?? "all").json")
    }

    /// The saved articles for this category (`nil` = All), or `nil` if nothing usable is saved.
    func load(category: NewsCategory?) -> [Article]? {
        guard let data = try? Data(contentsOf: file(for: category)),
              let articles = try? JSONCoding.makeDecoder().decode([Article].self, from: data),
              !articles.isEmpty else { return nil }
        return articles
    }

    /// Replaces the saved articles for this category. Failures are ignored: a missing cache
    /// is not an error.
    func save(_ articles: [Article], category: NewsCategory?) {
        guard !articles.isEmpty,
              let data = try? JSONCoding.makeEncoder().encode(articles) else { return }
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try? data.write(to: file(for: category), options: .atomic)
    }

    /// Deletes everything. Called on logout, because saved articles contain that user's votes.
    func clear() {
        try? FileManager.default.removeItem(at: directory)
    }
}
