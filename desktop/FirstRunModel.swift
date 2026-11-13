import AppKit
import Combine
import UniformTypeIdentifiers

struct SetupReply: Decodable {
    struct Value: Decodable {
        let thread_id: String
        let path: String?
        let task_id: String?
    }
    let ok: Bool
    let value: Value?
    let message: String?
}

@MainActor
final class FirstRunModel: ObservableObject {
    @Published var title = "我的 Codex 任务"
    @Published var selection: URL?
    @Published var threadID = ""
    @Published var issue = ""
    @Published var busy = false
    @Published var confirmReplacement = false
    let hasExistingData = FileManager.default.fileExists(atPath: CardPaths.directory.appendingPathComponent("state.json").path)
        || FileManager.default.fileExists(atPath: CardPaths.directory.appendingPathComponent("activity-source.json").path)

    var canConnect: Bool {
        BundledPython.available && selection != nil && UUID(uuidString: threadID) != nil && !busy
            && !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && title.count <= 80
            && (!hasExistingData || confirmReplacement)
    }

    func chooseRecord() {
        let panel = NSOpenPanel()
        panel.title = "选择这个 Codex 对话的记录"
        panel.prompt = "检查这份记录"
        panel.allowedContentTypes = [.json, UTType(filenameExtension: "jsonl") ?? .plainText]
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.directoryURL = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".codex/sessions")
        panel.begin { [weak self] response in
            guard response == .OK, let file = panel.url else { return }
            self?.inspect(file)
        }
    }

    func inspect(_ file: URL) {
        selection = file
        threadID = ""
        issue = ""
        busy = true
        SetupWorker.run(["inspect", "--transcript", file.path]) { [weak self] data in
            guard let self else { return }
            self.busy = false
            guard let data, let reply = try? JSONDecoder().decode(SetupReply.self, from: data), reply.ok,
                  let value = reply.value, UUID(uuidString: value.thread_id) != nil else {
                self.issue = Self.message(data)
                return
            }
            self.threadID = value.thread_id
        }
    }

    func connect(completion: @escaping (String) -> Void) {
        guard canConnect, let selection else { return }
        busy = true
        issue = ""
        var arguments = ["connect", "--transcript", selection.path, "--thread-id", threadID,
                         "--title", title.trimmingCharacters(in: .whitespacesAndNewlines)]
        if confirmReplacement { arguments.append("--replace") }
        SetupWorker.run(arguments) { [weak self] data in
            guard let self else { return }
            self.busy = false
            guard let data, let reply = try? JSONDecoder().decode(SetupReply.self, from: data), reply.ok,
                  let value = reply.value else {
                self.issue = Self.message(data)
                return
            }
            completion(value.thread_id)
        }
    }

    private static func message(_ data: Data?) -> String {
        guard let data, let reply = try? JSONDecoder().decode(SetupReply.self, from: data) else {
            return "配置未完成，请重试。若问题持续，请重新下载完整应用。"
        }
        return reply.message ?? "无法连接所选记录，请检查后重试。"
    }
}
