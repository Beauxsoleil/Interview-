import Foundation
import FoundationModels

/// Wraps the on-device Apple Intelligence model: availability, chunking, and
/// small guarded generations.
///
/// Everything here runs **on device**. No transcript text leaves the Mac, which
/// is what makes this appropriate for health / legal / demographic content.
enum AppleIntelligence {

    // MARK: - Availability

    enum Availability: Equatable {
        case available
        case deviceNotEligible
        case notEnabled
        case modelNotReady
        case unavailable(String)

        var isAvailable: Bool { self == .available }

        /// Human-readable reason plus the action the user can take.
        var explanation: String {
            switch self {
            case .available:
                return "Apple Intelligence is ready."
            case .deviceNotEligible:
                return "This Mac isn't eligible for Apple Intelligence."
            case .notEnabled:
                return "Turn on Apple Intelligence in System Settings → Apple Intelligence & Siri."
            case .modelNotReady:
                return "The on-device model is still downloading. Try again shortly."
            case .unavailable(let reason):
                return reason
            }
        }
    }

    static var availability: Availability {
        let model = SystemLanguageModel.default
        switch model.availability {
        case .available:
            return .available
        case .unavailable(let reason):
            switch reason {
            case .deviceNotEligible:
                return .deviceNotEligible
            case .appleIntelligenceNotEnabled:
                return .notEnabled
            case .modelNotReady:
                return .modelNotReady
            @unknown default:
                return .unavailable("Apple Intelligence is unavailable on this Mac.")
            }
        @unknown default:
            return .unavailable("Apple Intelligence is unavailable on this Mac.")
        }
    }

    static let engineName = "Apple Intelligence (on-device)"

    // MARK: - Errors

    enum IntelligenceError: LocalizedError {
        case unavailable(String)
        case generationFailed(String)
        case noTranscript

        var errorDescription: String? {
            switch self {
            case .unavailable(let reason): return reason
            case .generationFailed(let reason): return "On-device generation failed: \(reason)"
            case .noTranscript: return "This interview has no transcript yet."
            }
        }
    }

    static func requireAvailable() throws {
        let state = availability
        guard state.isAvailable else {
            throw IntelligenceError.unavailable(state.explanation)
        }
    }

    // MARK: - Guarded generation
    //
    // The on-device context window is small (a few thousand tokens covering
    // prompt AND output). Rather than matching on specific error cases — which
    // couples us to the exact enum shape — any failure is retried once with a
    // halved input. That covers context overflow, which is the failure we
    // actually expect, without brittle error introspection.

    /// Runs one guided generation, retrying with a shortened prompt on failure.
    static func generate<T: Generable>(
        instructions: String,
        prompt: String,
        as type: T.Type,
        temperature: Double = 0.1
    ) async throws -> T {
        do {
            return try await runOnce(instructions: instructions, prompt: prompt, as: type, temperature: temperature)
        } catch {
            // Most likely cause: the prompt plus schema overflowed the context
            // window. Halve the input and try one more time before giving up.
            let shortened = String(prompt.prefix(max(400, prompt.count / 2)))
            guard shortened.count < prompt.count else {
                throw IntelligenceError.generationFailed(error.localizedDescription)
            }
            do {
                return try await runOnce(instructions: instructions, prompt: shortened, as: type, temperature: temperature)
            } catch {
                throw IntelligenceError.generationFailed(error.localizedDescription)
            }
        }
    }

    private static func runOnce<T: Generable>(
        instructions: String,
        prompt: String,
        as type: T.Type,
        temperature: Double
    ) async throws -> T {
        // A fresh session per generation keeps each call's context minimal —
        // transcript chunks are independent, so there is nothing to carry over.
        let session = LanguageModelSession(instructions: instructions)
        let options = GenerationOptions(temperature: temperature)
        let response = try await session.respond(to: prompt, generating: type, options: options)
        return response.content
    }
}

// MARK: - Chunking

enum TranscriptChunker {
    /// Conservative character budget per generation.
    ///
    /// The on-device window covers prompt + schema + output. ~3.5 characters per
    /// token puts 4,000 characters near 1,100 tokens, leaving comfortable room
    /// for the instructions and the generated object.
    static let defaultBudget = 4_000

    /// Splits on line boundaries so a speaker turn is never cut mid-sentence.
    static func chunk(_ text: String, budget: Int = defaultBudget) -> [String] {
        let lines = text.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
        var chunks: [String] = []
        var current = ""

        for line in lines {
            // A single oversized line is hard-split rather than dropped.
            if line.count > budget {
                if !current.isEmpty { chunks.append(current); current = "" }
                chunks.append(contentsOf: hardSplit(line, budget: budget))
                continue
            }
            if current.count + line.count + 1 > budget {
                chunks.append(current)
                current = line
            } else {
                current = current.isEmpty ? line : current + "\n" + line
            }
        }
        if !current.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            chunks.append(current)
        }
        return chunks.isEmpty ? [] : chunks
    }

    private static func hardSplit(_ line: String, budget: Int) -> [String] {
        var pieces: [String] = []
        var remaining = Substring(line)
        while !remaining.isEmpty {
            let piece = remaining.prefix(budget)
            pieces.append(String(piece))
            remaining = remaining.dropFirst(piece.count)
        }
        return pieces
    }
}

// MARK: - Evidence

/// Finds a real sentence from the source transcript that best supports an
/// extracted value. The model never invents quotes — this locates them.
enum EvidenceLocator {
    static func evidence(for value: String, in source: String) -> String? {
        guard !value.isEmpty,
              value.caseInsensitiveCompare(kNotMentioned) != .orderedSame else { return nil }

        let sentences = split(source)
        guard !sentences.isEmpty else { return nil }

        let needle = tokens(value)
        guard !needle.isEmpty else { return nil }

        var best: (score: Double, text: String)?
        for sentence in sentences {
            let hay = tokens(sentence)
            guard !hay.isEmpty else { continue }
            let overlap = needle.intersection(hay).count
            guard overlap > 0 else { continue }
            // Favour sentences that cover the value without being padded out.
            let score = Double(overlap) / Double(needle.count)
                - 0.0015 * Double(max(0, sentence.count - 160))
            if best == nil || score > best!.score {
                best = (score, sentence)
            }
        }
        guard let best, best.score > 0.34 else { return nil }
        return best.text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func split(_ text: String) -> [String] {
        text
            .replacingOccurrences(of: "\n", with: " ")
            .split(whereSeparator: { ".?!".contains($0) })
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { $0.count > 8 }
    }

    /// Lowercased content words, with speaker prefixes and filler removed.
    private static func tokens(_ text: String) -> Set<String> {
        let stop: Set<String> = [
            "the", "and", "a", "an", "of", "to", "in", "is", "was", "for", "with",
            "on", "at", "it", "that", "this", "i", "im", "ive", "my", "me", "he",
            "she", "they", "we", "you", "not", "no", "yes", "but", "so", "as",
            "interviewer", "applicant", "speaker",
        ]
        return Set(
            text.lowercased()
                .split(whereSeparator: { !$0.isLetter && !$0.isNumber })
                .map(String.init)
                .filter { $0.count > 2 && !stop.contains($0) }
        )
    }
}
