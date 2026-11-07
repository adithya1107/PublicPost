import Foundation

/// Shared JSON coders that follow the backend contract:
/// snake_case keys and ISO 8601 dates.
nonisolated enum JSONCoding {

    static func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        // ISO 8601 with or without fractional seconds (servers differ).
        decoder.dateDecodingStrategy = .custom { decoder in
            let string = try decoder.singleValueContainer().decode(String.self)
            let withFraction = Date.ISO8601FormatStyle(includingFractionalSeconds: true)
            if let date = try? withFraction.parse(string) { return date }
            if let date = try? Date.ISO8601FormatStyle().parse(string) { return date }
            throw DecodingError.dataCorrupted(
                .init(codingPath: decoder.codingPath, debugDescription: "Invalid ISO 8601 date: \(string)")
            )
        }
        return decoder
    }

    static func makeEncoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }
}
