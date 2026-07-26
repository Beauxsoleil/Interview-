import AVFoundation
import Foundation
import Speech

/// A timed piece of recognized text, before speaker attribution.
struct TimedText: Equatable {
    var start: TimeInterval
    var end: TimeInterval
    var text: String
}

/// On-device speech-to-text using the `SpeechAnalyzer` / `SpeechTranscriber`
/// stack introduced in macOS 26.
///
/// This replaces Whisper entirely: it is on-device, needs no Python or GPU
/// toolchain, handles long-form audio, and reports per-run time ranges, which
/// is exactly what speaker attribution needs.
struct TranscriptionService {

    enum TranscriptionError: LocalizedError {
        case localeUnsupported(String)
        case assetInstallFailed(String)
        case audioUnreadable(String)
        case noSpeechFound

        var errorDescription: String? {
            switch self {
            case .localeUnsupported(let id):
                return "Speech recognition isn't available for \(id) on this Mac."
            case .assetInstallFailed(let reason):
                return "Couldn't prepare the on-device speech model: \(reason)"
            case .audioUnreadable(let reason):
                return "Couldn't read the audio file: \(reason)"
            case .noSpeechFound:
                return "No speech was found in this recording."
            }
        }
    }

    var locale: Locale = .current

    /// Transcribes `url`, reporting 0...1 progress.
    func transcribe(
        url: URL,
        progress: @MainActor (Double, String) -> Void = { _, _ in }
    ) async throws -> (language: String, items: [TimedText]) {

        await progress(0.05, "Preparing speech model")

        let resolved = try await resolveLocale()
        let transcriber = SpeechTranscriber(
            locale: resolved,
            transcriptionOptions: [],
            reportingOptions: [],
            attributeOptions: [.audioTimeRange]   // gives us per-run timing
        )

        try await installAssetsIfNeeded(for: transcriber)

        let audioFile: AVAudioFile
        do {
            audioFile = try AVAudioFile(forReading: url)
        } catch {
            throw TranscriptionError.audioUnreadable(error.localizedDescription)
        }

        let duration = Double(audioFile.length) / audioFile.fileFormat.sampleRate
        let analyzer = SpeechAnalyzer(modules: [transcriber])

        await progress(0.1, "Transcribing")

        // Collect finalized results while the analyzer walks the file.
        let collector = Task { () -> [TimedText] in
            var collected: [TimedText] = []
            for try await result in transcriber.results where result.isFinal {
                collected.append(contentsOf: Self.timedText(from: result.text))
                if duration > 0, let last = collected.last {
                    let fraction = min(0.95, 0.1 + 0.85 * (last.end / duration))
                    await progress(fraction, "Transcribing")
                }
            }
            return collected
        }

        do {
            try await analyzer.analyzeSequence(from: audioFile)
            try await analyzer.finalizeAndFinishThroughEndOfInput()
        } catch {
            collector.cancel()
            throw TranscriptionError.audioUnreadable(error.localizedDescription)
        }

        let items = try await collector.value
        guard !items.isEmpty else { throw TranscriptionError.noSpeechFound }

        await progress(1.0, "Transcribed")
        return (resolved.identifier, items)
    }

    // MARK: - Locale + assets

    private func resolveLocale() async throws -> Locale {
        let supported = await SpeechTranscriber.supportedLocales
        // Match on language code so en_US audio still works under an en_GB Mac.
        if let exact = supported.first(where: { $0.identifier == locale.identifier }) {
            return exact
        }
        if let code = locale.language.languageCode?.identifier,
           let sameLanguage = supported.first(where: { $0.language.languageCode?.identifier == code }) {
            return sameLanguage
        }
        if let english = supported.first(where: { $0.language.languageCode?.identifier == "en" }) {
            return english
        }
        guard let fallback = supported.first else {
            throw TranscriptionError.localeUnsupported(locale.identifier)
        }
        return fallback
    }

    private func installAssetsIfNeeded(for transcriber: SpeechTranscriber) async throws {
        do {
            if let request = try await AssetInventory.assetInstallationRequest(supporting: [transcriber]) {
                try await request.downloadAndInstall()
            }
        } catch {
            throw TranscriptionError.assetInstallFailed(error.localizedDescription)
        }
    }

    // MARK: - Attributed string -> timed text

    /// Pulls `.audioTimeRange` off each run so downstream speaker attribution
    /// has real timings to work with.
    static func timedText(from attributed: AttributedString) -> [TimedText] {
        var items: [TimedText] = []
        for run in attributed.runs {
            let piece = String(attributed[run.range].characters)
            let trimmed = piece.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else { continue }

            guard let range = run.audioTimeRange else {
                // No timing on this run: extend the previous item rather than
                // dropping recognized words on the floor.
                if var last = items.popLast() {
                    last.text += " " + trimmed
                    items.append(last)
                }
                continue
            }
            items.append(
                TimedText(
                    start: range.start.seconds,
                    end: range.end.seconds,
                    text: trimmed
                )
            )
        }
        return items
    }
}
