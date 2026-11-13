import Foundation

struct CardChoice: Decodable, Identifiable {
    let id: String
    let thread_id: String
    let created_at: Double
    let question: String
    let options: [String]
    let fields: [ChatField]?
    let source_question_id: String?

    var isValid: Bool {
        !id.isEmpty && id.count <= 64 && !thread_id.isEmpty &&
        created_at.isFinite && created_at > 0 && question.count <= 300 &&
        ((2...5).contains(options.count) || (options.isEmpty && !(fields ?? []).isEmpty)) &&
        options.allSatisfy { !$0.isEmpty && $0.count <= 180 } &&
        (fields == nil || ((1...3).contains(fields!.count) && fields!.allSatisfy { $0.isValid } &&
                          Set(fields!.map(\.id)).count == fields!.count))
    }

    func submit(_ index: Int) throws {
        guard isValid, options.indices.contains(index - 1) else { throw CocoaError(.fileReadCorruptFile) }
        try submitPayload(["index": index])
    }

    func submitForm(_ answers: [String: String]) throws {
        guard isValid, let fields, Set(answers.keys) == Set(fields.map(\.id)),
              fields.allSatisfy({ field in
                  guard let value = answers[field.id] else { return false }
                  return !value.isEmpty && value.count <= 2000 &&
                      (field.options.isEmpty || field.options.contains(value))
              }) else { throw CocoaError(.fileReadCorruptFile) }
        try submitPayload(["answers": answers])
    }

    private func submitPayload(_ values: [String: Any]) throws {
        let directory = CardPaths.directory
        let file = directory.appendingPathComponent("choice-selection.json")
        let payload = values.merging(["choice_id": id, "thread_id": thread_id,
                                      "created_at": Date().timeIntervalSince1970]) { _, new in new }
        let data = try JSONSerialization.data(withJSONObject: payload)
        try data.write(to: file, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file.path)
        let worker = try BundledPython.process(module: "agent_progress_wechat.card_choice")
        try worker.run()
    }
}

struct CardChoiceResult: Decodable {
    let choice_id: String
    let thread_id: String?
    let status: String
    let index: Int?
    let created_at: Double?
    let message: String
    var isValid: Bool {
        !choice_id.isEmpty && choice_id.count <= 64 && ["sent", "uncertain", "retry"].contains(status) &&
        message.count <= 180 && (index == nil || (1...5).contains(index!)) &&
        (created_at == nil || (created_at!.isFinite && created_at! > 0))
    }
}
