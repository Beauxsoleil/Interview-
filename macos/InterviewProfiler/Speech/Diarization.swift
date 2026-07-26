import Foundation

/// A stretch of audio attributed to one speaker.
struct SpeakerInterval: Equatable {
    var speaker: String
    var start: TimeInterval
    var end: TimeInterval
}

/// Anything that can say who spoke when.
///
/// Apple ships no public speaker-diarization API as of macOS 26, so this is a
/// seam rather than a wrapper: the bundled implementation is a heuristic, and a
/// Core ML model (e.g. a converted pyannote segmentation + embedding pair, or
/// the FluidAudio Swift package) can be dropped in behind the same protocol
/// without touching the rest of the app.
protocol DiarizationService {
    var label: String { get }
    func diarize(url: URL, items: [TimedText]) async throws -> [SpeakerInterval]
}

/// Turn-taking heuristic tuned for two-person interviews.
///
/// It does NOT use voice characteristics — it infers turns from pauses and then
/// decides which side is the interviewer from conversational shape (questions
/// are short and end in "?"; answers are longer and declarative).
///
/// This is deliberately conservative and always beatable by a real model. The
/// UI treats its output as a first draft: reviewers reassign speakers in one
/// click, and that correction is what the profile extraction actually uses.
struct HeuristicDiarizer: DiarizationService {

    let label = "Turn-taking heuristic"

    /// A silence at least this long is treated as a possible speaker change.
    var pauseThreshold: TimeInterval = 0.55

    func diarize(url: URL, items: [TimedText]) async throws -> [SpeakerInterval] {
        let turns = Self.groupIntoTurns(items, pauseThreshold: pauseThreshold)
        guard !turns.isEmpty else { return [] }

        // Score each turn: positive leans interviewer, negative leans applicant.
        let scores = turns.map { Self.interviewerScore(for: $0.text) }

        // Smooth: an isolated flip between two same-side neighbours is usually
        // a mis-scored short turn ("Right." / "Okay."), not a real handoff.
        var sides = scores.map { $0 >= 0 }
        for i in 1..<max(1, sides.count - 1) where sides.count >= 3 {
            if sides[i - 1] == sides[i + 1], sides[i] != sides[i - 1], abs(scores[i]) < 0.5 {
                sides[i] = sides[i - 1]
            }
        }

        // Whichever side talks less is the interviewer — interviewers ask,
        // applicants explain. This holds up well on screening interviews.
        let wordsWhenTrue = zip(sides, turns).filter { $0.0 }.reduce(0) { $0 + $1.1.text.split(separator: " ").count }
        let wordsWhenFalse = zip(sides, turns).filter { !$0.0 }.reduce(0) { $0 + $1.1.text.split(separator: " ").count }
        let trueIsInterviewer = wordsWhenTrue <= wordsWhenFalse

        return zip(sides, turns).map { side, turn in
            let isInterviewer = (side == trueIsInterviewer)
            return SpeakerInterval(
                speaker: isInterviewer ? "SPEAKER_INTERVIEWER" : "SPEAKER_APPLICANT",
                start: turn.start,
                end: turn.end
            )
        }
    }

    /// Merges recognized runs into turns separated by meaningful pauses.
    static func groupIntoTurns(_ items: [TimedText], pauseThreshold: TimeInterval) -> [TimedText] {
        let sorted = items.sorted { $0.start < $1.start }
        var turns: [TimedText] = []
        for item in sorted {
            if var last = turns.last, item.start - last.end < pauseThreshold {
                last.end = max(last.end, item.end)
                last.text = (last.text + " " + item.text).trimmingCharacters(in: .whitespaces)
                turns[turns.count - 1] = last
            } else {
                turns.append(item)
            }
        }
        return turns
    }

    /// > 0 means "looks like an interviewer turn".
    static func interviewerScore(for text: String) -> Double {
        let lower = text.lowercased()
        let words = lower.split(whereSeparator: { !$0.isLetter && !$0.isNumber })
        guard !words.isEmpty else { return 0 }

        var score = 0.0
        if text.contains("?") { score += 1.4 }

        let openers = ["can you", "tell me", "what", "how", "why", "do you", "have you",
                       "are you", "did you", "would you", "any ", "let's", "walk me"]
        if openers.contains(where: { lower.hasPrefix($0) }) { score += 0.9 }
        else if openers.contains(where: { lower.contains($0) }) { score += 0.35 }

        // Length: questions are short, answers run long.
        if words.count <= 12 { score += 0.5 }
        if words.count >= 35 { score -= 1.0 }

        // First-person disclosure is the applicant's register.
        let firstPerson = ["i ", "i'm", "im ", "my ", "i've", "ive ", "we "]
        let hits = firstPerson.reduce(0) { $0 + (lower.contains($1) ? 1 : 0) }
        score -= 0.45 * Double(hits)

        return score
    }
}

// MARK: - Merge

/// Combines "who spoke when" with "what was said", mirroring the merge step in
/// the web backend: every timed run is assigned to the speaker interval it
/// overlaps most, then consecutive same-speaker runs collapse into turns.
enum SpeakerMerge {

    struct Turn: Equatable {
        var speaker: String
        var start: TimeInterval
        var end: TimeInterval
        var text: String
    }

    static func merge(intervals: [SpeakerInterval], items: [TimedText]) -> [Turn] {
        guard !items.isEmpty else { return [] }
        let sortedItems = items.sorted { $0.start < $1.start }
        let fallback = intervals.first?.speaker ?? "SPEAKER_1"

        var turns: [Turn] = []
        for item in sortedItems {
            let text = item.text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty else { continue }
            let speaker = bestSpeaker(for: item, in: intervals) ?? fallback

            if var last = turns.last, last.speaker == speaker {
                last.text = (last.text + " " + text).trimmingCharacters(in: .whitespaces)
                last.end = max(last.end, item.end)
                turns[turns.count - 1] = last
            } else {
                turns.append(Turn(speaker: speaker, start: item.start, end: item.end, text: text))
            }
        }
        return turns
    }

    private static func bestSpeaker(for item: TimedText, in intervals: [SpeakerInterval]) -> String? {
        var best: (overlap: TimeInterval, speaker: String)?
        for interval in intervals {
            let overlap = min(item.end, interval.end) - max(item.start, interval.start)
            if overlap > 0, overlap > (best?.overlap ?? 0) {
                best = (overlap, interval.speaker)
            }
        }
        if let best { return best.speaker }

        // No overlap (a run landing in a gap): fall back to the nearest interval.
        let mid = (item.start + item.end) / 2
        return intervals.min {
            min(abs(mid - $0.start), abs(mid - $0.end)) < min(abs(mid - $1.start), abs(mid - $1.end))
        }?.speaker
    }

    /// Renames raw diarizer ids to "Speaker 1", "Speaker 2", … in order of first
    /// appearance, so the UI never shows internal labels.
    static func normalize(_ turns: [Turn]) -> (turns: [Turn], speakers: [String]) {
        var mapping: [String: String] = [:]
        var order: [String] = []
        var out: [Turn] = []

        for var turn in turns {
            if mapping[turn.speaker] == nil {
                let name = "Speaker \(mapping.count + 1)"
                mapping[turn.speaker] = name
                order.append(name)
            }
            turn.speaker = mapping[turn.speaker]!
            out.append(turn)
        }
        return (out, order)
    }
}
