import Foundation
import Combine

@MainActor
final class WeChatSetupModel: ObservableObject {
    @Published var enableApprovals = false
    @Published var issue = ""
    @Published var starting = false
    private var worker: Process?

    var boundThread: String? {
        guard let data = try? Data(contentsOf: CardPaths.directory.appendingPathComponent("activity-source.json")),
              data.count <= 16_384,
              let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let thread = value["thread_id"] as? String, UUID(uuidString: thread) != nil else { return nil }
        return thread
    }

    func start(completion: () -> Void) {
        guard !starting, let thread = boundThread else { return }
        starting = true
        issue = ""
        do {
            let process = try BundledPython.process(module: "agent_progress_wechat.relay", arguments: [
                "--state-dir", CardPaths.directory.appendingPathComponent("wechat").path,
                "--thread-id", thread, "--card-dir", CardPaths.directory.path,
                enableApprovals ? "--remote-approvals" : "--no-remote-approvals"
            ])
            try process.run()
            worker = process
            completion()
        } catch {
            starting = false
            issue = "未能启动连接，请检查运行组件后重试。"
        }
    }
}
