import Foundation

/// Local-only audio storage.
///
/// Imported recordings are copied into the app's Application Support directory
/// so the library keeps working if the user moves or deletes the original.
/// Nothing is uploaded anywhere.
enum AudioStore {

    static let allowedExtensions: Set<String> = ["mp3", "wav", "m4a"]

    static var directory: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("InterviewProfiler", isDirectory: true)
            .appendingPathComponent("Audio", isDirectory: true)
        try? FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        return base
    }

    enum StoreError: LocalizedError {
        case unsupportedType(String)
        case copyFailed(String)

        var errorDescription: String? {
            switch self {
            case .unsupportedType(let ext):
                return "Unsupported audio type \".\(ext)\". Use mp3, wav, or m4a."
            case .copyFailed(let reason):
                return "Couldn't import the audio file: \(reason)"
            }
        }
    }

    /// Copies `source` into the store, returning the generated filename.
    static func importFile(from source: URL) throws -> String {
        let ext = source.pathExtension.lowercased()
        guard allowedExtensions.contains(ext) else {
            throw StoreError.unsupportedType(ext)
        }

        let storedName = "\(UUID().uuidString).\(ext)"
        let destination = directory.appendingPathComponent(storedName)

        // Security-scoped access is required for files chosen via the open panel
        // while the app is sandboxed.
        let scoped = source.startAccessingSecurityScopedResource()
        defer { if scoped { source.stopAccessingSecurityScopedResource() } }

        do {
            try FileManager.default.copyItem(at: source, to: destination)
        } catch {
            throw StoreError.copyFailed(error.localizedDescription)
        }
        return storedName
    }

    static func url(for storedName: String?) -> URL? {
        guard let storedName, !storedName.isEmpty else { return nil }
        let url = directory.appendingPathComponent(storedName)
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }

    static func delete(_ storedName: String?) {
        guard let url = url(for: storedName) else { return }
        try? FileManager.default.removeItem(at: url)
    }
}
