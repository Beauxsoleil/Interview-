import AVFoundation
import Observation
import SwiftData
import SwiftUI

/// Audio playback synced to the transcript.
@MainActor
@Observable
final class AudioPlayer {
    private var player: AVAudioPlayer?
    private var ticker: Timer?

    var currentTime: TimeInterval = 0
    var duration: TimeInterval = 0
    var isPlaying = false

    func load(_ url: URL?) {
        stop()
        guard let url else { player = nil; duration = 0; return }
        player = try? AVAudioPlayer(contentsOf: url)
        player?.prepareToPlay()
        duration = player?.duration ?? 0
        currentTime = 0
    }

    func togglePlay() {
        guard let player else { return }
        if player.isPlaying { pause() } else { play() }
    }

    func play() {
        guard let player else { return }
        player.play()
        isPlaying = true
        ticker?.invalidate()
        ticker = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self, let player = self.player else { return }
                self.currentTime = player.currentTime
                if !player.isPlaying { self.isPlaying = false }
            }
        }
    }

    func pause() {
        player?.pause()
        isPlaying = false
        ticker?.invalidate()
        ticker = nil
    }

    func stop() {
        player?.stop()
        isPlaying = false
        ticker?.invalidate()
        ticker = nil
    }

    /// Seek and start playing — used when a transcript line is clicked.
    func seek(to time: TimeInterval) {
        guard let player else { return }
        player.currentTime = max(0, min(time, player.duration))
        currentTime = player.currentTime
        play()
    }
}

struct TranscriptSection: View {
    @Bindable var interview: Interview
    let player: AudioPlayer
    @Binding var showSpeakerEditor: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Transcript").font(.title3.weight(.semibold))
                if let language = interview.language {
                    Pill(text: language)
                }
                Spacer()
                Button {
                    showSpeakerEditor = true
                } label: {
                    Label("Rename speakers", systemImage: "person.2.badge.gearshape")
                }
                .controlSize(.small)
            }

            playbackBar

            LazyVStack(alignment: .leading, spacing: 3) {
                ForEach(interview.orderedSegments, id: \.persistentModelID) { segment in
                    SegmentRow(
                        segment: segment,
                        displayName: interview.displayName(for: segment.speaker),
                        isApplicant: segment.speaker == interview.applicantSpeaker,
                        isActive: player.currentTime >= segment.start && player.currentTime < segment.end
                    ) {
                        player.seek(to: segment.start)
                    }
                }
            }
        }
        .padding(16)
        .background(.quaternary.opacity(0.25), in: RoundedRectangle(cornerRadius: 12))
    }

    private var playbackBar: some View {
        HStack(spacing: 10) {
            Button {
                player.togglePlay()
            } label: {
                Image(systemName: player.isPlaying ? "pause.circle.fill" : "play.circle.fill")
                    .font(.title2)
            }
            .buttonStyle(.plain)
            .disabled(player.duration == 0)

            Slider(
                value: Binding(
                    get: { player.currentTime },
                    set: { player.seek(to: $0) }
                ),
                in: 0...max(player.duration, 0.01)
            )
            .disabled(player.duration == 0)

            Text("\(Self.time(player.currentTime)) / \(Self.time(player.duration))")
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
        }
    }

    static func time(_ seconds: TimeInterval) -> String {
        guard seconds.isFinite, seconds >= 0 else { return "0:00" }
        let total = Int(seconds)
        return String(format: "%d:%02d", total / 60, total % 60)
    }
}

private struct SegmentRow: View {
    let segment: Segment
    let displayName: String
    let isApplicant: Bool
    let isActive: Bool
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(displayName)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(isApplicant ? Color.green : Color.secondary)
                    if isApplicant {
                        Text("applicant").font(.caption2).foregroundStyle(.tertiary)
                    }
                    Text(TranscriptSection.time(segment.start))
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.tertiary)
                }
                Text(segment.text)
                    .font(.body)
                    .foregroundStyle(.primary)
                    .fixedSize(horizontal: false, vertical: true)
                    .multilineTextAlignment(.leading)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 7)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                isActive ? Color.accentColor.opacity(0.16) : Color.clear,
                in: RoundedRectangle(cornerRadius: 8)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Speaker rename

/// Renames raw speakers to roles and marks which one is the applicant.
///
/// This matters beyond cosmetics: the applicant selection decides which turns
/// are fed to profile extraction, so correcting it here re-aims the extraction.
struct SpeakerEditorSheet: View {
    @Bindable var interview: Interview
    let dismiss: () -> Void

    @Environment(\.modelContext) private var context
    @State private var names: [String: String] = [:]
    @State private var applicant: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Speakers").font(.title3.weight(.semibold))
            Text("Name each speaker and mark the applicant. The applicant's turns are the only ones used for profile extraction.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            ForEach(interview.speakerIDs, id: \.self) { speaker in
                HStack(spacing: 10) {
                    Text(speaker)
                        .font(.callout.monospaced())
                        .foregroundStyle(.secondary)
                        .frame(width: 82, alignment: .leading)

                    TextField("e.g. Interviewer", text: Binding(
                        get: { names[speaker] ?? "" },
                        set: { names[speaker] = $0 }
                    ))
                    .textFieldStyle(.roundedBorder)

                    Toggle("Applicant", isOn: Binding(
                        get: { applicant == speaker },
                        set: { if $0 { applicant = speaker } }
                    ))
                    .toggleStyle(.checkbox)
                }
            }

            HStack {
                Spacer()
                Button("Cancel", action: dismiss)
                Button("Save") {
                    interview.speakerLabels = names.filter { !$0.value.trimmingCharacters(in: .whitespaces).isEmpty }
                    interview.applicantSpeaker = applicant
                    interview.updatedAt = .now
                    try? context.save()
                    dismiss()
                }
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding(20)
        .frame(width: 500)
        .onAppear {
            names = interview.speakerLabels
            applicant = interview.applicantSpeaker ?? interview.speakerIDs.first
        }
    }
}
