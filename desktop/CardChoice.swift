import Foundation

struct CardChoice: Decodable {
    let id: String
    let thread_id: String
    let created_at: Double
    let question: String
    let options: [String]

    var isValid: Bool {
        !id.isEmpty && id.count <= 64 && !thread_id.isEmpty &&
        created_at.isFinite && created_at > 0 && question.count <= 300 &&
        (2...5).contains(options.count) && options.allSatisfy { !$0.isEmpty && $0.count <= 180 }
    }

    func submit(_ index: Int) throws {
        guard isValid, options.indices.contains(index - 1) else { throw CocoaError(.fileReadCorruptFile) }
        let directory = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/AgentProgressCard")
        let file = directory.appendingPathComponent("choice-selection.json")
        let data = try JSONSerialization.data(withJSONObject: ["choice_id": id, "thread_id": thread_id,
                                                                 "index": index, "created_at": Date().timeIntervalSince1970])
        try data.write(to: file, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file.path)
        guard let resources = Bundle.main.resourceURL else { throw CocoaError(.fileNoSuchFile) }
        let worker = Process()
        worker.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        worker.arguments = ["-m", "agent_progress_wechat.card_choice"]
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONPATH"] = resources.path
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        worker.environment = environment
        worker.standardOutput = FileHandle.nullDevice
        worker.standardError = FileHandle.nullDevice
        try worker.run()
    }
}

struct CardChoiceResult: Decodable {
    let choice_id: String
    let status: String
    let message: String
    var isValid: Bool { ["sent", "uncertain", "retry"].contains(status) && message.count <= 180 }
}
