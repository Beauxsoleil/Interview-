import Foundation
import SwiftData

// MARK: - Workflow vocabulary

enum InterviewStatus: String, CaseIterable, Codable, Identifiable {
    case pendingReview = "Pending Review"
    case priority = "Priority"
    case approved = "Approved"
    case rejected = "Rejected"

    var id: String { rawValue }
}

enum JobState: String, Codable {
    case idle, running, done, error
}

// MARK: - SwiftData models
//
// Applicant 1--* Interview 1--* Segment
//                Interview 1--1 ProfileRecord
//                Interview *--* TagLabel

@Model
final class Applicant {
    @Attribute(.unique) var name: String
    var notes: String?
    var createdAt: Date

    @Relationship(deleteRule: .cascade, inverse: \Interview.applicant)
    var interviews: [Interview] = []

    init(name: String, notes: String? = nil) {
        self.name = name
        self.notes = notes
        self.createdAt = .now
    }
}

@Model
final class TagLabel {
    @Attribute(.unique) var name: String
    /// Stored as a hex string so it survives SwiftData without a transformer.
    var colorHex: String
    var createdAt: Date

    @Relationship(inverse: \Interview.labels)
    var interviews: [Interview] = []

    init(name: String, colorHex: String = "#64748B") {
        self.name = name
        self.colorHex = colorHex
        self.createdAt = .now
    }
}

@Model
final class Interview {
    var title: String?
    var interviewDate: Date
    var statusRaw: String

    /// Filename the user imported, for display.
    var audioFilename: String?
    /// Filename inside the app's Application Support audio store.
    var audioStoredName: String?

    var language: String?
    /// Raw speaker id -> friendly role, e.g. ["Speaker 1": "Interviewer"].
    var speakerLabels: [String: String]
    /// Which raw speaker id is the applicant (drives profile extraction).
    var applicantSpeaker: String?

    // Processing state, surfaced in the UI.
    var jobStateRaw: String
    var jobProgress: Double
    var jobStage: String?
    var jobError: String?

    var createdAt: Date
    var updatedAt: Date

    var applicant: Applicant?
    var labels: [TagLabel] = []

    @Relationship(deleteRule: .cascade, inverse: \Segment.interview)
    var segments: [Segment] = []

    @Relationship(deleteRule: .cascade, inverse: \ProfileRecord.interview)
    var profile: ProfileRecord?

    @Relationship(deleteRule: .cascade, inverse: \SummaryRecord.interview)
    var summary: SummaryRecord?

    init(
        applicant: Applicant,
        title: String? = nil,
        interviewDate: Date = .now,
        audioFilename: String? = nil,
        audioStoredName: String? = nil
    ) {
        self.applicant = applicant
        self.title = title
        self.interviewDate = interviewDate
        self.audioFilename = audioFilename
        self.audioStoredName = audioStoredName
        self.statusRaw = InterviewStatus.pendingReview.rawValue
        self.speakerLabels = [:]
        self.jobStateRaw = JobState.idle.rawValue
        self.jobProgress = 0
        self.createdAt = .now
        self.updatedAt = .now
    }

    var status: InterviewStatus {
        get { InterviewStatus(rawValue: statusRaw) ?? .pendingReview }
        set { statusRaw = newValue.rawValue; updatedAt = .now }
    }

    var jobState: JobState {
        get { JobState(rawValue: jobStateRaw) ?? .idle }
        set { jobStateRaw = newValue.rawValue }
    }

    var isProcessing: Bool { jobState == .running }
    var hasTranscript: Bool { !segments.isEmpty }

    /// Segments in chronological order.
    var orderedSegments: [Segment] {
        segments.sorted { $0.start < $1.start }
    }

    /// Distinct raw speaker ids, in order of first appearance.
    var speakerIDs: [String] {
        var seen: [String] = []
        for s in orderedSegments where !seen.contains(s.speaker) {
            seen.append(s.speaker)
        }
        return seen
    }

    func displayName(for speaker: String) -> String {
        let mapped = speakerLabels[speaker]
        return (mapped?.isEmpty == false ? mapped! : speaker)
    }

    /// Full labeled transcript, e.g. "Interviewer: …\nApplicant: …".
    var transcriptText: String {
        orderedSegments
            .map { "\(displayName(for: $0.speaker)): \($0.text)" }
            .joined(separator: "\n")
    }

    /// Only the applicant's turns — what profile extraction is allowed to see.
    var applicantOnlyText: String {
        guard let applicantSpeaker else { return transcriptText }
        let role = displayName(for: applicantSpeaker)
        return orderedSegments
            .filter { $0.speaker == applicantSpeaker }
            .map { "\(role): \($0.text)" }
            .joined(separator: "\n")
    }
}

@Model
final class Segment {
    /// Raw normalized speaker id, e.g. "Speaker 1".
    var speaker: String
    var start: TimeInterval
    var end: TimeInterval
    var text: String

    var interview: Interview?

    init(speaker: String, start: TimeInterval, end: TimeInterval, text: String) {
        self.speaker = speaker
        self.start = start
        self.end = end
        self.text = text
    }
}

@Model
final class ProfileRecord {
    /// JSON encoding of `ExtractedProfile`.
    var dataJSON: Data
    /// Which engine produced it, e.g. "Apple Intelligence (on-device)".
    var engine: String
    var createdAt: Date

    var interview: Interview?

    init(dataJSON: Data, engine: String) {
        self.dataJSON = dataJSON
        self.engine = engine
        self.createdAt = .now
    }

    var decoded: ExtractedProfile? {
        try? JSONDecoder().decode(ExtractedProfile.self, from: dataJSON)
    }
}

@Model
final class SummaryRecord {
    var overview: String
    var keyPoints: [String]
    var engine: String
    var createdAt: Date

    var interview: Interview?

    init(overview: String, keyPoints: [String], engine: String) {
        self.overview = overview
        self.keyPoints = keyPoints
        self.engine = engine
        self.createdAt = .now
    }
}
