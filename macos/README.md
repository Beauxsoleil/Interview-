# InterviewProfiler — macOS desktop app (Apple Intelligence)

A native SwiftUI/SwiftData rewrite of the interview transcription and applicant
profiling tool, built for an **iMac (M4, 24 GB) running macOS 26**.

Everything runs **on device**. There is no API key, no Python, no server, and
the app ships without the `network.client` sandbox entitlement — so an
accidental outbound call is blocked by the OS, not just by convention. That is
the point: this tool handles health, legal, and demographic information.

---

## What Apple Intelligence does here

| Stage | Framework | Runs on |
| --- | --- | --- |
| Transcription | `SpeechAnalyzer` / `SpeechTranscriber` (Speech) | Device (Neural Engine) |
| Speaker separation | Heuristic — see caveat below | Device |
| **Summary** | Foundation Models | Device (~3B model) |
| **Profile extraction** | Foundation Models, guided generation | Device (~3B model) |

### Structured extraction, not free-writing

The original rule was *extract into a schema first, then render* — never let the
model free-write a profile. Foundation Models enforces that at the type level
via `@Generable`:

```swift
@Generable
struct ProfileFacts {
    @Guide(description: "The applicant's age in years… Use \"not mentioned\" if absent.")
    var age: String
    …
}

let facts = try await session.respond(to: prompt, generating: ProfileFacts.self)
```

Guided generation constrains decoding to the schema, so the result is a typed
Swift value, not prose that has to be parsed. The summary card is a pure
rendering of that value.

### Three deliberate design decisions

**1. Map/reduce, because the context window is small.**
The on-device model has a context window measured in low thousands of tokens
covering prompt *and* output — nothing like a cloud model. A 40-minute interview
does not fit. `TranscriptChunker` splits the transcript on speaker-turn
boundaries into ~4,000-character chunks; each chunk is extracted independently;
the reducer keeps the first confident value per field. Notes are gathered per
chunk and condensed in a final pass.

**2. Extraction reads the applicant's turns only.**
`Interview.applicantOnlyText` filters to the speaker marked as the applicant.
This follows the product rule (profile the applicant, not the interviewer) and
roughly halves the token count as a side effect. Re-marking the applicant in the
speaker editor genuinely re-aims the next extraction.

**3. The model never writes the quotes.**
Small models paraphrase when asked to quote, which produces citations that look
verbatim but aren't. Instead the model returns values only, and
`EvidenceLocator` finds the best-matching real sentence in the source text by
token overlap. Every quote on the card is therefore a real sentence from the
transcript.

Fields the transcript doesn't cover stay `"not mentioned"` and render muted and
italic — never guessed.

---

## Build

Requires macOS 26+, Xcode 26+, and Apple Intelligence enabled
(System Settings → Apple Intelligence & Siri).

```bash
brew install xcodegen        # one time
cd macos
xcodegen generate
open InterviewProfiler.xcodeproj
```

Then set your signing team in **Signing & Capabilities** and press Run.

The project is generated from `project.yml` rather than a checked-in
`.pbxproj` — it stays readable and doesn't produce merge conflicts.

---

## Using it

1. **Import Recording** (toolbar) — pick an `.mp3`, `.wav`, or `.m4a`. The file
   is copied into Application Support, so moving the original won't break the
   library.
2. Transcription starts automatically; progress shows in the list and detail.
3. When the transcript lands, summary and profile extraction run automatically
   if Apple Intelligence is available.
4. **Rename speakers** — name each speaker and mark the applicant, then
   re-extract to re-aim the profile.
5. Click any transcript line to seek the audio there; the active line highlights
   as playback moves.
6. Set status, attach labels, filter from the sidebar, and search across
   transcripts, profiles, and summaries.

---

## Known caveats — read before trusting output

**Speaker diarization is a heuristic, not a model.** Apple ships no public
speaker-diarization API as of macOS 26. `HeuristicDiarizer` infers turns from
pauses and then guesses which side is the interviewer from conversational shape
(questions are short and end in "?"; answers are long and first-person). On a
structured two-person screening interview this is usually right; on crosstalk,
three-plus speakers, or an interviewer who monologues, it will be wrong.

Two things make that acceptable rather than dangerous: the speaker editor fixes
it in one click, and `DiarizationService` is a protocol — a real Core ML
diarizer (a converted pyannote segmentation + embedding pair, or the FluidAudio
Swift package) drops in behind it without touching the rest of the app. If you
need reliable multi-speaker separation, that is the change to make.

**The on-device model is ~3B parameters.** It is fast, free, and private, but it
is not Claude Opus. Expect it to miss nuance on long or rambling answers, and
treat the profile as a review aid rather than a finished assessment. The
evidence quotes exist so a reviewer can check any field against what was said.

**First transcription downloads a speech model.** The Speech framework fetches
its on-device asset on first use; that one-time download needs a network
connection and can take a few minutes.

---

## Relationship to the web version

The FastAPI + React version in `backend/` and `frontend/` still works and is
still the right choice for multi-user or non-Mac deployments — it uses
Whisper/pyannote and the Claude API, which are stronger but require a GPU, a
Python toolchain, and sending transcripts to a cloud API.

This macOS app trades some model quality for privacy, zero setup, and zero
running cost. The two share no code but implement the same data model and the
same product rules.

---

## Project layout

```
macos/
  project.yml                       XcodeGen spec
  InterviewProfiler/
    App/         InterviewProfilerApp.swift    SwiftData container (CloudKit off)
    Models/      Models.swift                  Applicant, Interview, Segment, …
                 ProfileSchema.swift           @Generable + stored profile
    Intelligence/AppleIntelligence.swift       availability, chunking, evidence
                 ProfileExtractor.swift        map/reduce guided extraction
                 Summarizer.swift              hierarchical summarization
    Speech/      TranscriptionService.swift    SpeechAnalyzer/SpeechTranscriber
                 Diarization.swift             protocol + heuristic + merge
                 PipelineCoordinator.swift     orchestration + progress
    Storage/     AudioStore.swift              local audio, sandbox-aware
    Views/       ContentView, InterviewListView, InterviewDetailView,
                 TranscriptSection, ProfileSection
    Resources/   Info.plist, entitlements
```
