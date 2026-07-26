import SwiftData
import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @Environment(\.modelContext) private var context
    @Environment(PipelineCoordinator.self) private var pipeline

    @Query(sort: \Applicant.name) private var applicants: [Applicant]
    @Query(sort: \TagLabel.name) private var labels: [TagLabel]

    @State private var filter = InterviewFilter()
    @State private var selection: Interview?
    @State private var showImporter = false
    @State private var importError: String?

    var body: some View {
        NavigationSplitView {
            SidebarView(filter: $filter, applicants: applicants, labels: labels)
                .navigationSplitViewColumnWidth(min: 210, ideal: 240)
        } content: {
            InterviewListView(filter: $filter, selection: $selection)
                .navigationSplitViewColumnWidth(min: 300, ideal: 360)
        } detail: {
            if let selection {
                InterviewDetailView(interview: selection)
                    .id(selection.persistentModelID)
            } else {
                ContentUnavailableView(
                    "No interview selected",
                    systemImage: "waveform",
                    description: Text("Choose an interview, or import a recording to get started.")
                )
            }
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    showImporter = true
                } label: {
                    Label("Import Recording", systemImage: "plus")
                }
                .help("Import an mp3, wav, or m4a recording")
            }
        }
        .fileImporter(
            isPresented: $showImporter,
            allowedContentTypes: [.mp3, .wav, .mpeg4Audio, .audio],
            allowsMultipleSelection: false
        ) { result in
            handleImport(result)
        }
        .sheet(item: Binding(
            get: { importError.map(ErrorMessage.init) },
            set: { if $0 == nil { importError = nil } }
        )) { message in
            ErrorSheet(message: message.text) { importError = nil }
        }
        .safeAreaInset(edge: .bottom) { IntelligenceStatusBar() }
    }

    private func handleImport(_ result: Result<[URL], Error>) {
        switch result {
        case .failure(let error):
            importError = error.localizedDescription
        case .success(let urls):
            guard let url = urls.first else { return }
            do {
                let storedName = try AudioStore.importFile(from: url)
                let name = url.deletingPathExtension().lastPathComponent
                let applicant = findOrCreateApplicant(named: name)
                let interview = Interview(
                    applicant: applicant,
                    title: nil,
                    interviewDate: .now,
                    audioFilename: url.lastPathComponent,
                    audioStoredName: storedName
                )
                context.insert(interview)
                applicant.interviews.append(interview)
                try? context.save()
                selection = interview
                pipeline.process(interview, in: context)
            } catch {
                importError = error.localizedDescription
            }
        }
    }

    /// Imports name the applicant after the file; the reviewer renames from the
    /// detail pane. Reusing an existing applicant keeps repeat interviews grouped.
    private func findOrCreateApplicant(named raw: String) -> Applicant {
        let name = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        let resolved = name.isEmpty ? "Untitled applicant" : name
        if let existing = applicants.first(where: { $0.name.caseInsensitiveCompare(resolved) == .orderedSame }) {
            return existing
        }
        let applicant = Applicant(name: resolved)
        context.insert(applicant)
        return applicant
    }
}

// MARK: - Filter state

struct InterviewFilter: Equatable {
    var search: String = ""
    var status: InterviewStatus?
    var applicantName: String?
    var labelName: String?
    var sort: SortOption = .date
    var ascending: Bool = false

    enum SortOption: String, CaseIterable, Identifiable {
        case date = "Date"
        case applicant = "Applicant"
        case status = "Status"
        var id: String { rawValue }
    }

    var isActive: Bool {
        !search.isEmpty || status != nil || applicantName != nil || labelName != nil
    }
}

// MARK: - Sidebar

private struct SidebarView: View {
    @Binding var filter: InterviewFilter
    let applicants: [Applicant]
    let labels: [TagLabel]

    var body: some View {
        List {
            Section("Library") {
                Button {
                    filter.applicantName = nil
                    filter.status = nil
                    filter.labelName = nil
                } label: {
                    Label("All interviews", systemImage: "tray.full")
                }
                .buttonStyle(.plain)
            }

            Section("Status") {
                ForEach(InterviewStatus.allCases) { status in
                    Toggle(isOn: Binding(
                        get: { filter.status == status },
                        set: { filter.status = $0 ? status : nil }
                    )) {
                        Label(status.rawValue, systemImage: status.symbolName)
                    }
                    .toggleStyle(.button)
                    .buttonStyle(.plain)
                }
            }

            if !applicants.isEmpty {
                Section("Applicants") {
                    ForEach(applicants) { applicant in
                        Toggle(isOn: Binding(
                            get: { filter.applicantName == applicant.name },
                            set: { filter.applicantName = $0 ? applicant.name : nil }
                        )) {
                            HStack {
                                Text(applicant.name).lineLimit(1)
                                Spacer()
                                Text("\(applicant.interviews.count)")
                                    .foregroundStyle(.secondary)
                                    .font(.caption)
                            }
                        }
                        .toggleStyle(.button)
                        .buttonStyle(.plain)
                    }
                }
            }

            if !labels.isEmpty {
                Section("Labels") {
                    ForEach(labels) { label in
                        Toggle(isOn: Binding(
                            get: { filter.labelName == label.name },
                            set: { filter.labelName = $0 ? label.name : nil }
                        )) {
                            Label {
                                Text(label.name).lineLimit(1)
                            } icon: {
                                Circle().fill(Color(hex: label.colorHex)).frame(width: 9, height: 9)
                            }
                        }
                        .toggleStyle(.button)
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .listStyle(.sidebar)
    }
}

// MARK: - Status bar

private struct IntelligenceStatusBar: View {
    @Environment(PipelineCoordinator.self) private var pipeline
    private var availability: AppleIntelligence.Availability { AppleIntelligence.availability }

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: availability.isAvailable ? "apple.intelligence" : "exclamationmark.triangle")
                .foregroundStyle(availability.isAvailable ? Color.accentColor : .orange)
            Text(availability.isAvailable
                 ? "Apple Intelligence · on-device"
                 : availability.explanation)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)

            Spacer()

            Label("Speakers: \(pipeline.diarizerLabel)", systemImage: "person.2.wave.2")
                .font(.caption)
                .foregroundStyle(.secondary)

            Label("Local only", systemImage: "lock.fill")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 7)
        .background(.bar)
    }
}

// MARK: - Small shared pieces

struct ErrorMessage: Identifiable {
    let id = UUID()
    let text: String
    init(_ text: String) { self.text = text }
}

struct ErrorSheet: View {
    let message: String
    let dismiss: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("Something went wrong", systemImage: "exclamationmark.triangle.fill")
                .font(.headline)
                .foregroundStyle(.orange)
            Text(message).font(.callout).textSelection(.enabled)
            HStack {
                Spacer()
                Button("OK", action: dismiss).keyboardShortcut(.defaultAction)
            }
        }
        .padding(20)
        .frame(width: 420)
    }
}

extension InterviewStatus {
    var symbolName: String {
        switch self {
        case .pendingReview: return "clock"
        case .priority: return "flag.fill"
        case .approved: return "checkmark.seal.fill"
        case .rejected: return "xmark.seal.fill"
        }
    }

    var tint: Color {
        switch self {
        case .pendingReview: return .secondary
        case .priority: return .orange
        case .approved: return .green
        case .rejected: return .red
        }
    }
}

extension Color {
    init(hex: String) {
        var value = UInt64()
        let cleaned = hex.hasPrefix("#") ? String(hex.dropFirst()) : hex
        Scanner(string: cleaned).scanHexInt64(&value)
        self.init(
            .sRGB,
            red: Double((value >> 16) & 0xFF) / 255,
            green: Double((value >> 8) & 0xFF) / 255,
            blue: Double(value & 0xFF) / 255
        )
    }
}
