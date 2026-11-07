import Foundation
import Security

/// Thin wrapper around the Keychain for storing small secrets (the auth token).
/// Generic-password items are keyed by `account` under one service name.
nonisolated enum KeychainStore {

    enum KeychainError: LocalizedError {
        case unexpectedStatus(OSStatus)

        var errorDescription: String? {
            "Couldn't save your login securely on this device."
        }
    }

    private static let service = "PublicPost"

    /// Saves `data`, replacing any existing value for `account`.
    static func save(_ data: Data, account: String) throws {
        let query = baseQuery(account: account)
        SecItemDelete(query as CFDictionary)   // remove the old value, if any

        var attributes = query
        attributes[kSecValueData as String] = data
        // Readable after the first unlock, and never copied to another device.
        attributes[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly

        let status = SecItemAdd(attributes as CFDictionary, nil)
        guard status == errSecSuccess else { throw KeychainError.unexpectedStatus(status) }
    }

    /// Returns the stored data, or `nil` if there is none.
    static func read(account: String) -> Data? {
        var query = baseQuery(account: account)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        return status == errSecSuccess ? result as? Data : nil
    }

    static func delete(account: String) {
        SecItemDelete(baseQuery(account: account) as CFDictionary)
    }

    private static func baseQuery(account: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
    }
}
