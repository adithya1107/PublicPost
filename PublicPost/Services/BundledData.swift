import Foundation

/// Loads the JSON files shipped inside the app. Used by `MockService`, and by
/// `APIService` as the automatic fallback when the backend can't be reached.
nonisolated enum BundledData {

    /// The bundled sample stories, each marked `isSample` so the UI can tell them apart.
    static func loadArticles() throws -> [Article] {
        try load("news", as: [Article].self).map { article in
            var sample = article
            sample.isSample = true
            return sample
        }
    }

    static func loadComments() throws -> [Comment] {
        try load("comments", as: [Comment].self)
    }

    private static func load<T: Decodable>(_ name: String, as type: T.Type) throws -> T {
        guard let url = Bundle.main.url(forResource: name, withExtension: "json") else {
            throw ServiceError.bundledDataMissing("\(name).json")
        }
        let data = try Data(contentsOf: url)
        return try JSONCoding.makeDecoder().decode(T.self, from: data)
    }
}
