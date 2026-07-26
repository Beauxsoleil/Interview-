import Foundation

/// Produces a short, neutral interview summary using the on-device model.
///
/// Unlike profile extraction this reads the FULL transcript (both speakers) —
/// the interviewer's questions are context that makes the summary coherent.
/// Long interviews are summarized hierarchically: summarize each chunk, then
/// summarize the summaries.
struct Summarizer {

    struct Result: Equatable {
        var overview: String
        var keyPoints: [String]
    }

    private static let instructions = """
    You summarize a recorded job interview for a reviewer who has not heard it.

    Rules:
    - Use ONLY what the transcript says. Never speculate about the applicant.
    - Stay neutral and factual. Do not make a hiring recommendation.
    - Do not repeat the same fact in both the overview and the key points.
    """

    private static let mergeInstructions = """
    You combine partial summaries of one interview into a single coherent \
    summary. Use only the supplied material, stay neutral, and do not make a \
    hiring recommendation.
    """

    static func summarize(
        transcript: String,
        progress: @MainActor (Double, String) -> Void = { _, _ in }
    ) async throws -> Result {
        try AppleIntelligence.requireAvailable()

        let trimmed = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { throw AppleIntelligence.IntelligenceError.noTranscript }

        let chunks = TranscriptChunker.chunk(trimmed)
        guard !chunks.isEmpty else { throw AppleIntelligence.IntelligenceError.noTranscript }

        // Short interview: one pass is enough.
        if chunks.count == 1 {
            await progress(0.4, "Summarizing")
            let draft = try await AppleIntelligence.generate(
                instructions: instructions,
                prompt: "Interview transcript:\n\(chunks[0])",
                as: InterviewSummaryDraft.self,
                temperature: 0.3
            )
            await progress(1.0, "Done")
            return clean(draft)
        }

        // Long interview: summarize each part, then merge.
        var partials: [InterviewSummaryDraft] = []
        for (index, chunk) in chunks.enumerated() {
            await progress(Double(index) / Double(chunks.count + 1), "Summarizing part \(index + 1) of \(chunks.count)")
            if let draft = try? await AppleIntelligence.generate(
                instructions: instructions,
                prompt: "Part \(index + 1) of \(chunks.count) of an interview transcript:\n\(chunk)",
                as: InterviewSummaryDraft.self,
                temperature: 0.3
            ) {
                partials.append(draft)
            }
        }

        guard !partials.isEmpty else {
            throw AppleIntelligence.IntelligenceError.generationFailed("The model could not summarize this transcript.")
        }

        await progress(0.85, "Merging summary")
        let material = partials.enumerated().map { index, draft in
            let bullets = draft.keyPoints.map { "- \($0)" }.joined(separator: "\n")
            return "Part \(index + 1): \(draft.overview)\n\(bullets)"
        }.joined(separator: "\n\n")

        let merged = try await AppleIntelligence.generate(
            instructions: mergeInstructions,
            prompt: "Partial summaries:\n\(String(material.prefix(TranscriptChunker.defaultBudget)))",
            as: InterviewSummaryDraft.self,
            temperature: 0.3
        )

        await progress(1.0, "Done")
        return clean(merged)
    }

    private static func clean(_ draft: InterviewSummaryDraft) -> Result {
        Result(
            overview: draft.overview.trimmingCharacters(in: .whitespacesAndNewlines),
            keyPoints: draft.keyPoints
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines.union(CharacterSet(charactersIn: "-• "))) }
                .filter { !$0.isEmpty }
        )
    }
}
