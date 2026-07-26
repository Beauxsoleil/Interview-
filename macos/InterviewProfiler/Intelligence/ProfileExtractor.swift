import Foundation

/// Extracts a structured applicant profile from a transcript using the
/// on-device Apple Intelligence model.
///
/// Strategy — map/reduce, because the on-device context window is small:
///
///   map    each transcript chunk -> `ProfileFacts` + `ChunkNotes`
///   reduce first confident value per field wins; notes are concatenated and,
///          if long, condensed by a final generation
///
/// Only the APPLICANT's turns are fed in (per the product rule: profile the
/// applicant, not the interviewer). That also roughly halves the token count.
struct ProfileExtractor {

    private static let factsInstructions = """
    You extract facts about a job applicant from part of an interview transcript.

    Rules:
    - Use ONLY what this excerpt states or clearly implies. Never guess.
    - If the excerpt does not cover a field, set it to exactly "not mentioned".
    - Do not carry information between fields. Answer each independently.
    - Keep every value under 20 words.
    """

    private static let notesInstructions = """
    You note an applicant's stated goals, motivations, and any other relevant \
    flags from part of an interview transcript.

    Rules:
    - Use ONLY what this excerpt states. Never guess or embellish.
    - If the excerpt contains nothing notable, return an empty string.
    - Be concise: at most 3 sentences.
    """

    private static let condenseInstructions = """
    You condense rough interview notes into a single short paragraph covering \
    the applicant's goals, motivations, and any relevant flags. Use only the \
    supplied notes. At most 4 sentences.
    """

    /// - Parameters:
    ///   - applicantText: transcript limited to the applicant's turns.
    ///   - progress: called on the main actor with 0...1 and a stage label.
    static func extract(
        from applicantText: String,
        progress: @MainActor (Double, String) -> Void = { _, _ in }
    ) async throws -> ExtractedProfile {
        try AppleIntelligence.requireAvailable()

        let trimmed = applicantText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { throw AppleIntelligence.IntelligenceError.noTranscript }

        let chunks = TranscriptChunker.chunk(trimmed)
        guard !chunks.isEmpty else { throw AppleIntelligence.IntelligenceError.noTranscript }

        var profile = ExtractedProfile()
        var noteFragments: [String] = []

        for (index, chunk) in chunks.enumerated() {
            let base = Double(index) / Double(chunks.count)
            await progress(base, "Reading part \(index + 1) of \(chunks.count)")

            // --- map: facts ---
            // A chunk that fails outright shouldn't lose the whole interview;
            // fall back to "nothing found here" and keep going.
            let facts: ProfileFacts
            do {
                facts = try await AppleIntelligence.generate(
                    instructions: factsInstructions,
                    prompt: "Interview excerpt:\n\(chunk)",
                    as: ProfileFacts.self
                )
            } catch {
                facts = .empty
            }
            merge(facts, into: &profile, source: chunk)

            // --- map: notes ---
            if let notes = try? await AppleIntelligence.generate(
                instructions: notesInstructions,
                prompt: "Interview excerpt:\n\(chunk)",
                as: ChunkNotes.self
            ) {
                let cleaned = notes.notes.trimmingCharacters(in: .whitespacesAndNewlines)
                if !cleaned.isEmpty, cleaned.caseInsensitiveCompare(kNotMentioned) != .orderedSame {
                    noteFragments.append(cleaned)
                }
            }
        }

        // --- reduce: notes ---
        await progress(0.9, "Summarizing notes")
        profile.freeTextNotes = try await condense(noteFragments)

        await progress(1.0, "Done")
        return profile
    }

    /// First confident value wins; later chunks only fill gaps. Evidence is
    /// located in the chunk the value actually came from.
    private static func merge(_ facts: ProfileFacts, into profile: inout ExtractedProfile, source: String) {
        for (target, factKey) in ExtractedProfile.factMapping {
            guard !profile[keyPath: target].isPresent else { continue }

            let raw = facts[keyPath: factKey].trimmingCharacters(in: .whitespacesAndNewlines)
            let candidate = ProfileField(value: raw.isEmpty ? kNotMentioned : raw, evidence: nil)
            guard candidate.isPresent else { continue }

            profile[keyPath: target] = ProfileField(
                value: candidate.value,
                evidence: EvidenceLocator.evidence(for: candidate.value, in: source)
            )
        }
    }

    private static func condense(_ fragments: [String]) async throws -> String {
        let joined = fragments.joined(separator: " ")
        guard !joined.isEmpty else { return "" }
        // Short enough to stand on its own — no extra model round trip.
        guard joined.count > 600 else { return joined }

        let clipped = String(joined.prefix(TranscriptChunker.defaultBudget))
        let condensed = try? await AppleIntelligence.generate(
            instructions: condenseInstructions,
            prompt: "Notes:\n\(clipped)",
            as: ChunkNotes.self
        )
        let result = condensed?.notes.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return result.isEmpty ? String(joined.prefix(600)) : result
    }
}
