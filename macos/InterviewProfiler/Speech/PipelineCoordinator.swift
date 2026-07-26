import Foundation
import SwiftData

/// Drives the full processing pipeline for one interview:
///
///   transcribe (Speech) → diarize → merge → save
///                        → summarize (Apple Intelligence)
///                        → extract profile (Apple Intelligence)
///
/// Heavy work happens off the main actor; every SwiftData mutation is applied
/// back on the main actor, which is where the model container lives.
@MainActor
@Observable
final class PipelineCoordinator {

    private(set) var activeInterviewID: PersistentIdentifier?
    private(set) var lastError: String?

    private let transcriber = TranscriptionService()
    private let diarizer: DiarizationService = HeuristicDiarizer()

    var diarizerLabel: String { diarizer.label }

    func process(_ interview: Interview, in context: ModelContext) {
        guard interview.jobState != .running else { return }
        guard let audioURL = AudioStore.url(for: interview.audioStoredName) else {
            fail(interview, "The audio file for this interview is missing.")
            return
        }

        activeInterviewID = interview.persistentModelID
        interview.jobState = .running
        interview.jobProgress = 0
        interview.jobStage = "Starting"
        interview.jobError = nil
        try? context.save()

        Task { [weak self] in
            guard let self else { return }
            do {
                // ---- Transcription (off-main, on-device) ----
                let (language, items) = try await self.transcriber.transcribe(url: audioURL) { fraction, stage in
                    interview.jobProgress = fraction * 0.55
                    interview.jobStage = stage
                }

                // ---- Diarization + merge ----
                interview.jobStage = "Separating speakers"
                interview.jobProgress = 0.6

                let intervals = try await self.diarizer.diarize(url: audioURL, items: items)
                let merged = SpeakerMerge.merge(intervals: intervals, items: items)
                let (turns, speakers) = SpeakerMerge.normalize(merged)

                self.applyTranscript(turns: turns, speakers: speakers, language: language, to: interview, in: context)

                // ---- Apple Intelligence passes ----
                // A failure here must not discard the transcript, which is
                // valuable on its own; it surfaces as a non-fatal note instead.
                var softFailure: String?

                if AppleIntelligence.availability.isAvailable {
                    interview.jobStage = "Summarizing"
                    interview.jobProgress = 0.7
                    do {
                        try await self.runSummary(for: interview, in: context) { fraction, _ in
                            interview.jobProgress = 0.7 + fraction * 0.1
                        }
                    } catch {
                        softFailure = error.localizedDescription
                    }

                    interview.jobStage = "Extracting profile"
                    interview.jobProgress = 0.8
                    do {
                        try await self.runProfile(for: interview, in: context) { fraction, stage in
                            interview.jobProgress = 0.8 + fraction * 0.2
                            interview.jobStage = stage
                        }
                    } catch {
                        softFailure = error.localizedDescription
                    }
                } else {
                    softFailure = AppleIntelligence.availability.explanation
                }

                interview.jobState = .done
                interview.jobProgress = 1
                interview.jobStage = "Done"
                interview.jobError = softFailure
                interview.updatedAt = .now
                try? context.save()
                self.activeInterviewID = nil

            } catch {
                self.fail(interview, error.localizedDescription, in: context)
            }
        }
    }

    // MARK: - Individual passes (also callable from the UI)

    func runSummary(
        for interview: Interview,
        in context: ModelContext,
        progress: @MainActor (Double, String) -> Void = { _, _ in }
    ) async throws {
        let transcript = interview.transcriptText
        let result = try await Summarizer.summarize(transcript: transcript, progress: progress)

        if let existing = interview.summary {
            existing.overview = result.overview
            existing.keyPoints = result.keyPoints
            existing.engine = AppleIntelligence.engineName
        } else {
            let record = SummaryRecord(
                overview: result.overview,
                keyPoints: result.keyPoints,
                engine: AppleIntelligence.engineName
            )
            record.interview = interview
            context.insert(record)
            interview.summary = record
        }
        interview.updatedAt = .now
        try? context.save()
    }

    func runProfile(
        for interview: Interview,
        in context: ModelContext,
        progress: @MainActor (Double, String) -> Void = { _, _ in }
    ) async throws {
        // Applicant turns only — the interviewer's words are not the profile.
        let text = interview.applicantOnlyText
        let profile = try await ProfileExtractor.extract(from: text, progress: progress)
        let encoded = try JSONEncoder().encode(profile)

        if let existing = interview.profile {
            existing.dataJSON = encoded
            existing.engine = AppleIntelligence.engineName
        } else {
            let record = ProfileRecord(dataJSON: encoded, engine: AppleIntelligence.engineName)
            record.interview = interview
            context.insert(record)
            interview.profile = record
        }
        interview.updatedAt = .now
        try? context.save()
    }

    // MARK: - Helpers

    private func applyTranscript(
        turns: [SpeakerMerge.Turn],
        speakers: [String],
        language: String,
        to interview: Interview,
        in context: ModelContext
    ) {
        for old in interview.segments { context.delete(old) }
        interview.segments = []

        for turn in turns {
            let segment = Segment(speaker: turn.speaker, start: turn.start, end: turn.end, text: turn.text)
            segment.interview = interview
            context.insert(segment)
            interview.segments.append(segment)
        }

        interview.language = language

        // Seed friendly names from the interview shape. The heuristic diarizer
        // emits the interviewer first, so speaker 1 is the interviewer by
        // default — reviewers can flip this in one click.
        if interview.speakerLabels.isEmpty, speakers.count >= 2 {
            interview.speakerLabels = [speakers[0]: "Interviewer", speakers[1]: "Applicant"]
        }
        if interview.applicantSpeaker == nil {
            interview.applicantSpeaker = speakers.count > 1 ? speakers[1] : speakers.first
        }
        interview.updatedAt = .now
        try? context.save()
    }

    private func fail(_ interview: Interview, _ message: String, in context: ModelContext? = nil) {
        interview.jobState = .error
        interview.jobError = message
        interview.jobStage = "Failed"
        lastError = message
        activeInterviewID = nil
        try? context?.save()
    }
}
