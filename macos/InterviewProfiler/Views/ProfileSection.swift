import SwiftData
import SwiftUI

/// Readable summary card rendered from the structured profile.
///
/// The model never free-writes this card — it fills the schema, and the card is
/// a pure rendering of that JSON. Fields the transcript didn't cover render as
/// "not mentioned" in a muted style rather than being guessed at.
struct ProfileSection: View {
    @Bindable var interview: Interview
    @Binding var busy: String?
    @Binding var errorText: String?

    @Environment(\.modelContext) private var context
    @Environment(PipelineCoordinator.self) private var pipeline

    private var profile: ExtractedProfile? { interview.profile?.decoded }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Applicant profile").font(.title3.weight(.semibold))
                if let profile {
                    Pill(text: "\(profile.completedFieldCount)/\(ExtractedProfile.fieldOrder.count) fields")
                }
                Spacer()
                Button {
                    extract()
                } label: {
                    Label(profile == nil ? "Extract profile" : "Re-extract",
                          systemImage: "apple.intelligence")
                }
                .controlSize(.small)
                .disabled(busy != nil || !AppleIntelligence.availability.isAvailable)
                .help(AppleIntelligence.availability.isAvailable
                      ? "Extract on device with Apple Intelligence"
                      : AppleIntelligence.availability.explanation)
            }

            if let profile {
                LazyVGrid(
                    columns: [GridItem(.flexible(), alignment: .topLeading),
                              GridItem(.flexible(), alignment: .topLeading)],
                    alignment: .leading,
                    spacing: 14
                ) {
                    ForEach(ExtractedProfile.fieldOrder, id: \.0) { label, keyPath in
                        ProfileFieldView(label: label, field: profile[keyPath: keyPath])
                    }
                }

                if !profile.freeTextNotes.isEmpty {
                    Divider()
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Notes")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.tertiary)
                            .textCase(.uppercase)
                        Text(profile.freeTextNotes)
                            .font(.callout)
                            .fixedSize(horizontal: false, vertical: true)
                            .textSelection(.enabled)
                    }
                }

                if let engine = interview.profile?.engine {
                    Text(engine).font(.caption2).foregroundStyle(.tertiary)
                }
            } else {
                Text("No profile extracted yet.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.quaternary.opacity(0.25), in: RoundedRectangle(cornerRadius: 12))
    }

    private func extract() {
        busy = "Extracting profile…"
        Task {
            do {
                try await pipeline.runProfile(for: interview, in: context) { _, stage in
                    busy = stage
                }
            } catch {
                errorText = error.localizedDescription
            }
            busy = nil
        }
    }
}

private struct ProfileFieldView: View {
    let label: String
    let field: ProfileField

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.tertiary)
                .textCase(.uppercase)

            Text(field.isPresent ? field.value : kNotMentioned)
                .font(.callout)
                .foregroundStyle(field.isPresent ? .primary : .tertiary)
                .italic(!field.isPresent)
                .fixedSize(horizontal: false, vertical: true)
                .textSelection(.enabled)

            if field.isPresent, let evidence = field.evidence {
                Text("“\(evidence)”")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

// MARK: - Summary

struct SummarySection: View {
    @Bindable var interview: Interview
    @Binding var busy: String?
    @Binding var errorText: String?

    @Environment(\.modelContext) private var context
    @Environment(PipelineCoordinator.self) private var pipeline

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Summary").font(.title3.weight(.semibold))
                Spacer()
                Button {
                    summarize()
                } label: {
                    Label(interview.summary == nil ? "Summarize" : "Re-summarize",
                          systemImage: "apple.intelligence")
                }
                .controlSize(.small)
                .disabled(busy != nil || !AppleIntelligence.availability.isAvailable)
                .help(AppleIntelligence.availability.isAvailable
                      ? "Summarize on device with Apple Intelligence"
                      : AppleIntelligence.availability.explanation)
            }

            if let summary = interview.summary {
                Text(summary.overview)
                    .font(.callout)
                    .fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)

                if !summary.keyPoints.isEmpty {
                    VStack(alignment: .leading, spacing: 3) {
                        ForEach(Array(summary.keyPoints.enumerated()), id: \.offset) { _, point in
                            HStack(alignment: .top, spacing: 6) {
                                Text("•").foregroundStyle(.tertiary)
                                Text(point).font(.callout).fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                }
                Text(summary.engine).font(.caption2).foregroundStyle(.tertiary)
            } else {
                Text("No summary yet.").font(.callout).foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.quaternary.opacity(0.25), in: RoundedRectangle(cornerRadius: 12))
    }

    private func summarize() {
        busy = "Summarizing…"
        Task {
            do {
                try await pipeline.runSummary(for: interview, in: context) { _, stage in
                    busy = stage
                }
            } catch {
                errorText = error.localizedDescription
            }
            busy = nil
        }
    }
}
