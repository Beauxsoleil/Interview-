import SwiftData
import SwiftUI

struct InterviewDetailView: View {
    @Bindable var interview: Interview

    @Environment(\.modelContext) private var context
    @Environment(PipelineCoordinator.self) private var pipeline

    @Query(sort: \TagLabel.name) private var allLabels: [TagLabel]

    @State private var player = AudioPlayer()
    @State private var showSpeakerEditor = false
    @State private var busy: String?
    @State private var errorText: String?
    @State private var newLabelName = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                header
                if interview.isProcessing { processingCard }
                if let note = interview.jobError, !interview.isProcessing { noticeCard(note) }

                if interview.hasTranscript {
                    SummarySection(interview: interview, busy: $busy, errorText: $errorText)
                    ProfileSection(interview: interview, busy: $busy, errorText: $errorText)
                    TranscriptSection(
                        interview: interview,
                        player: player,
                        showSpeakerEditor: $showSpeakerEditor
                    )
                } else if !interview.isProcessing {
                    ContentUnavailableView(
                        "No transcript yet",
                        systemImage: "waveform.slash",
                        description: Text("Run transcription to generate a diarized transcript.")
                    )
                    .frame(height: 200)
                }
            }
            .padding(20)
        }
        .navigationTitle(interview.applicant?.name ?? "Interview")
        .sheet(isPresented: $showSpeakerEditor) {
            SpeakerEditorSheet(interview: interview) { showSpeakerEditor = false }
        }
        .sheet(item: Binding(
            get: { errorText.map(ErrorMessage.init) },
            set: { if $0 == nil { errorText = nil } }
        )) { message in
            ErrorSheet(message: message.text) { errorText = nil }
        }
        .onAppear { player.load(AudioStore.url(for: interview.audioStoredName)) }
        .onDisappear { player.stop() }
    }

    // MARK: - Header

    private var header: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 4) {
                    TextField("Applicant name", text: Binding(
                        get: { interview.applicant?.name ?? "" },
                        set: { interview.applicant?.name = $0; try? context.save() }
                    ))
                    .textFieldStyle(.plain)
                    .font(.largeTitle.weight(.semibold))

                    HStack(spacing: 6) {
                        TextField("Add a title", text: Binding(
                            get: { interview.title ?? "" },
                            set: { interview.title = $0.isEmpty ? nil : $0; try? context.save() }
                        ))
                        .textFieldStyle(.plain)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: 260)

                        DatePicker("", selection: Binding(
                            get: { interview.interviewDate },
                            set: { interview.interviewDate = $0; try? context.save() }
                        ), displayedComponents: .date)
                        .labelsHidden()
                        .datePickerStyle(.compact)

                        if let file = interview.audioFilename {
                            Text(file).font(.caption).foregroundStyle(.tertiary).lineLimit(1)
                        }
                    }
                }
                Spacer()
                Picker("Status", selection: Binding(
                    get: { interview.status },
                    set: { interview.status = $0; try? context.save() }
                )) {
                    ForEach(InterviewStatus.allCases) { status in
                        Label(status.rawValue, systemImage: status.symbolName).tag(status)
                    }
                }
                .pickerStyle(.menu)
                .frame(width: 190)
            }

            labelRow

            HStack(spacing: 10) {
                Button {
                    pipeline.process(interview, in: context)
                } label: {
                    Label(interview.hasTranscript ? "Re-run transcription" : "Transcribe",
                          systemImage: "waveform")
                }
                .disabled(interview.isProcessing)

                if let busy {
                    ProgressView().controlSize(.small)
                    Text(busy).font(.caption).foregroundStyle(.secondary)
                }

                Spacer()

                Button(role: .destructive) {
                    AudioStore.delete(interview.audioStoredName)
                    context.delete(interview)
                    try? context.save()
                } label: {
                    Label("Delete", systemImage: "trash")
                }
            }
        }
    }

    private var labelRow: some View {
        HStack(spacing: 6) {
            ForEach(interview.labels) { label in
                HStack(spacing: 3) {
                    Text(label.name).font(.caption)
                    Button {
                        interview.labels.removeAll { $0.persistentModelID == label.persistentModelID }
                        try? context.save()
                    } label: {
                        Image(systemName: "xmark.circle.fill").font(.caption2)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(Color(hex: label.colorHex).opacity(0.22), in: Capsule())
            }

            Menu {
                ForEach(allLabels.filter { existing in
                    !interview.labels.contains { $0.persistentModelID == existing.persistentModelID }
                }) { label in
                    Button(label.name) {
                        interview.labels.append(label)
                        try? context.save()
                    }
                }
                Divider()
                Button("New label…") { addLabel() }
            } label: {
                Label("Label", systemImage: "tag")
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
        }
    }

    /// Creates a uniquely-named label, cycling the palette so consecutive
    /// labels are visually distinct. Rename it inline in the sidebar.
    private func addLabel() {
        var index = allLabels.count + 1
        var name = "Label \(index)"
        while allLabels.contains(where: { $0.name == name }) {
            index += 1
            name = "Label \(index)"
        }
        let hex = LabelPalette.all[allLabels.count % LabelPalette.all.count]
        let label = TagLabel(name: name, colorHex: hex)
        context.insert(label)
        interview.labels.append(label)
        try? context.save()
    }

    // MARK: - Cards

    private var processingCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(interview.jobStage ?? "Processing").font(.callout.weight(.medium))
                Spacer()
                Text("\(Int(interview.jobProgress * 100))%").foregroundStyle(.secondary).font(.caption)
            }
            ProgressView(value: interview.jobProgress)
        }
        .padding(14)
        .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 10))
    }

    private func noticeCard(_ text: String) -> some View {
        Label(text, systemImage: "info.circle")
            .font(.callout)
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 10))
    }
}

enum LabelPalette {
    static let all = ["#0EA5E9", "#8B5CF6", "#EC4899", "#F59E0B", "#10B981", "#EF4444"]
}
