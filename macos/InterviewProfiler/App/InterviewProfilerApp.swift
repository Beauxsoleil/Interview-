import SwiftData
import SwiftUI

@main
struct InterviewProfilerApp: App {

    /// Local-only store. No CloudKit, no sync, no analytics — this database
    /// holds health, legal, and demographic information and stays on this Mac.
    let container: ModelContainer = {
        let schema = Schema([
            Applicant.self,
            Interview.self,
            Segment.self,
            ProfileRecord.self,
            SummaryRecord.self,
            TagLabel.self,
        ])
        let config = ModelConfiguration(
            schema: schema,
            isStoredInMemoryOnly: false,
            cloudKitDatabase: .none
        )
        do {
            return try ModelContainer(for: schema, configurations: [config])
        } catch {
            fatalError("Could not create the local store: \(error)")
        }
    }()

    @State private var pipeline = PipelineCoordinator()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(pipeline)
                .frame(minWidth: 1_040, minHeight: 640)
        }
        .modelContainer(container)
        .commands {
            CommandGroup(replacing: .newItem) {}
        }
    }
}
