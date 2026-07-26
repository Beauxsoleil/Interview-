import Foundation
import FoundationModels

/// Sentinel used everywhere a field is absent from the transcript.
/// The rule from the spec: flag "not mentioned" rather than guessing.
let kNotMentioned = "not mentioned"

// MARK: - Guided-generation types (what the on-device model produces)
//
// Design notes for the ~3B on-device model:
//
// 1. Extraction is split into two SMALL generations (facts, then notes) instead
//    of one large nested object. The Foundation Models context window is a few
//    thousand tokens total (prompt + output), so keeping each generation small
//    is what makes long interviews work at all.
// 2. The model is NOT asked to produce verbatim quotes. Small models paraphrase
//    when asked to quote, which reads as a fabricated citation. Evidence is
//    instead located deterministically in the source text afterwards by
//    `EvidenceLocator`. That keeps every quote real.

@Generable
struct ProfileFacts: Equatable {
    @Guide(description: "The applicant's age in years, digits only (e.g. \"26\"). Use \"not mentioned\" if absent.")
    var age: String

    @Guide(description: "Physical health: injuries, conditions, surgeries, fitness. Use \"not mentioned\" if absent.")
    var physicalHealth: String

    @Guide(description: "Prior military or uniformed service: branch, years, role, discharge type. Use \"not mentioned\" if absent.")
    var priorServiceHistory: String

    @Guide(description: "Legal status and history: arrests, charges, convictions, citations, and any current standing such as pending charges, probation, or parole. Use \"not mentioned\" if absent.")
    var legalHistory: String

    @Guide(description: "Highest level of education completed, plus field of study if stated. Use \"not mentioned\" if absent.")
    var educationLevel: String

    @Guide(description: "Marital status: single, married, divorced, separated, widowed. Use \"not mentioned\" if absent.")
    var maritalStatus: String

    @Guide(description: "Number of dependents or children. Use \"not mentioned\" if absent.")
    var numberOfDependents: String

    @Guide(description: "Tattoos, brandings, or piercings, including body location. Use \"not mentioned\" if absent.")
    var tattoosBrandingsPiercings: String

    /// Every field set to the "not mentioned" sentinel.
    static var empty: ProfileFacts {
        ProfileFacts(
            age: kNotMentioned,
            physicalHealth: kNotMentioned,
            priorServiceHistory: kNotMentioned,
            legalHistory: kNotMentioned,
            educationLevel: kNotMentioned,
            maritalStatus: kNotMentioned,
            numberOfDependents: kNotMentioned,
            tattoosBrandingsPiercings: kNotMentioned
        )
    }
}

@Generable
struct ChunkNotes: Equatable {
    @Guide(description: "The applicant's stated goals, motivations, and any other notable flags, in 1-3 sentences. Empty string if nothing notable was said.")
    var notes: String
}

@Generable
struct InterviewSummaryDraft: Equatable {
    @Guide(description: "A neutral 2-4 sentence summary of what the applicant conveyed in this interview.")
    var overview: String

    @Guide(description: "Between 2 and 5 short bullet points capturing the most decision-relevant facts.")
    var keyPoints: [String]
}

// MARK: - Stored profile (merged result)

struct ProfileField: Codable, Equatable, Hashable {
    var value: String = kNotMentioned
    /// A real sentence from the transcript supporting `value`, located locally.
    var evidence: String?

    var isPresent: Bool {
        !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && value.caseInsensitiveCompare(kNotMentioned) != .orderedSame
    }

    static let absent = ProfileField(value: kNotMentioned, evidence: nil)
}

struct ExtractedProfile: Codable, Equatable {
    var age: ProfileField = .absent
    var physicalHealth: ProfileField = .absent
    var priorServiceHistory: ProfileField = .absent
    var legalHistory: ProfileField = .absent
    var educationLevel: ProfileField = .absent
    var maritalStatus: ProfileField = .absent
    var numberOfDependents: ProfileField = .absent
    var tattoosBrandingsPiercings: ProfileField = .absent
    var freeTextNotes: String = ""

    /// Display order and labels for the summary card.
    static let fieldOrder: [(String, KeyPath<ExtractedProfile, ProfileField>)] = [
        ("Age", \.age),
        ("Physical health", \.physicalHealth),
        ("Prior service history", \.priorServiceHistory),
        ("Legal status & history", \.legalHistory),
        ("Education level", \.educationLevel),
        ("Marital status", \.maritalStatus),
        ("Dependents", \.numberOfDependents),
        ("Tattoos / brandings / piercings", \.tattoosBrandingsPiercings),
    ]

    var completedFieldCount: Int {
        Self.fieldOrder.reduce(0) { $0 + (self[keyPath: $1.1].isPresent ? 1 : 0) }
    }

    /// Flat text used for search indexing.
    var searchBlob: String {
        Self.fieldOrder.map { self[keyPath: $0.1].value }.joined(separator: " ") + " " + freeTextNotes
    }
}

// MARK: - Facts -> stored profile

extension ExtractedProfile {
    /// Writable key paths paired with the matching `ProfileFacts` field, so the
    /// merge step can iterate instead of repeating eight near-identical blocks.
    static let factMapping: [(WritableKeyPath<ExtractedProfile, ProfileField>, KeyPath<ProfileFacts, String>)] = [
        (\.age, \.age),
        (\.physicalHealth, \.physicalHealth),
        (\.priorServiceHistory, \.priorServiceHistory),
        (\.legalHistory, \.legalHistory),
        (\.educationLevel, \.educationLevel),
        (\.maritalStatus, \.maritalStatus),
        (\.numberOfDependents, \.numberOfDependents),
        (\.tattoosBrandingsPiercings, \.tattoosBrandingsPiercings),
    ]
}
