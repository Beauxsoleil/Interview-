import SwiftData
import SwiftUI

/// Sortable, filterable, searchable list of interviews.
///
/// Search covers applicant name, title, transcript text, and extracted profile
/// fields. Transcript and profile matching is done in memory rather than in a
/// SwiftData predicate because both live in child records / encoded JSON.
struct InterviewListView: View {
    @Binding var filter: InterviewFilter
    @Binding var selection: Interview?

    @Query(sort: \Interview.interviewDate, order: .reverse)
    private var interviews: [Interview]

    private var visible: [Interview] {
        var rows = interviews

        if let status = filter.status {
            rows = rows.filter { $0.status == status }
        }
        if let applicant = filter.applicantName {
            rows = rows.filter { $0.applicant?.name == applicant }
        }
        if let label = filter.labelName {
            rows = rows.filter { iv in iv.labels.contains { $0.name == label } }
        }

        let needle = filter.search.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if !needle.isEmpty {
            rows = rows.filter { iv in
                if iv.applicant?.name.lowercased().contains(needle) == true { return true }
                if iv.title?.lowercased().contains(needle) == true { return true }
                if iv.transcriptText.lowercased().contains(needle) { return true }
                if let profile = iv.profile?.decoded,
                   profile.searchBlob.lowercased().contains(needle) { return true }
                if let summary = iv.summary,
                   summary.overview.lowercased().contains(needle) { return true }
                return false
            }
        }

        rows.sort { lhs, rhs in
            let result: Bool
            switch filter.sort {
            case .date:
                result = lhs.interviewDate < rhs.interviewDate
            case .applicant:
                result = (lhs.applicant?.name ?? "").localizedCaseInsensitiveCompare(rhs.applicant?.name ?? "") == .orderedAscending
            case .status:
                result = lhs.statusRaw < rhs.statusRaw
            }
            return filter.ascending ? result : !result
        }
        return rows
    }

    var body: some View {
        List(visible, id: \.persistentModelID, selection: Binding(
            get: { selection?.persistentModelID },
            set: { id in selection = visible.first { $0.persistentModelID == id } }
        )) { interview in
            InterviewRow(interview: interview).tag(interview.persistentModelID)
        }
        .searchable(text: $filter.search, prompt: "Search transcripts, profiles, applicants")
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Menu {
                    Picker("Sort by", selection: $filter.sort) {
                        ForEach(InterviewFilter.SortOption.allCases) { option in
                            Text(option.rawValue).tag(option)
                        }
                    }
                    Divider()
                    Toggle("Ascending", isOn: $filter.ascending)
                } label: {
                    Label("Sort", systemImage: "arrow.up.arrow.down")
                }
            }
        }
        .overlay {
            if visible.isEmpty {
                ContentUnavailableView(
                    filter.isActive ? "No matches" : "No interviews yet",
                    systemImage: filter.isActive ? "magnifyingglass" : "waveform.badge.plus",
                    description: Text(filter.isActive
                                      ? "Try clearing a filter or searching for something else."
                                      : "Import a recording to create your first interview.")
                )
            }
        }
    }
}

private struct InterviewRow: View {
    let interview: Interview

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 6) {
                Text(interview.applicant?.name ?? "Unknown applicant")
                    .font(.headline)
                    .lineLimit(1)
                if let title = interview.title, !title.isEmpty {
                    Text("· \(title)")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                Spacer()
                Image(systemName: interview.status.symbolName)
                    .foregroundStyle(interview.status.tint)
                    .help(interview.status.rawValue)
            }

            HStack(spacing: 8) {
                Text(interview.interviewDate, style: .date)
                    .font(.caption)
                    .foregroundStyle(.secondary)

                if interview.isProcessing {
                    ProgressView(value: interview.jobProgress)
                        .progressViewStyle(.linear)
                        .frame(width: 70)
                    Text(interview.jobStage ?? "Processing")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                } else {
                    if interview.hasTranscript { Pill(text: "transcript") }
                    if interview.summary != nil { Pill(text: "summary") }
                    if interview.profile != nil { Pill(text: "profile") }
                    if interview.jobState == .error { Pill(text: "failed", tint: .red) }
                }
                Spacer()
            }

            if !interview.labels.isEmpty {
                HStack(spacing: 4) {
                    ForEach(interview.labels) { label in
                        Text(label.name)
                            .font(.caption2)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color(hex: label.colorHex).opacity(0.22), in: Capsule())
                    }
                }
            }
        }
        .padding(.vertical, 3)
    }
}

struct Pill: View {
    let text: String
    var tint: Color = .secondary

    var body: some View {
        Text(text)
            .font(.caption2)
            .foregroundStyle(tint)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(tint.opacity(0.14), in: Capsule())
    }
}
