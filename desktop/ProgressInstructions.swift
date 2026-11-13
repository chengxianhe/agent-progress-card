import AppKit

enum ProgressInstructions {
    static func copyToClipboard() {
        let executable = Bundle.main.bundleURL.appendingPathComponent("Contents/MacOS/weiguang-cli").path
        let quoted = "'" + executable.replacingOccurrences(of: "'", with: "'\\''") + "'"
        let directory = "'" + CardPaths.directory.path.replacingOccurrences(of: "'", with: "'\\''") + "'"
        let cli = quoted + " --state-dir " + directory
        let state = try? ProgressState.read(from: CardPaths.directory.appendingPathComponent("state.json"))
        let command = state.map {
            cli + " update --task-id " + $0.task_id + " --status running --action '正在处理当前任务'"
        } ?? (cli + " begin --title '当前任务' --action '开始处理'")
        let text = """
        请用本机微光同步当前任务进度。下面的 CLI 自带运行环境，无需仓库或系统 Python：
        \(command)
        后续保留 task_id，用 update 发布阶段；进行中用 running，需要我确认时用 waiting，
        当前工作完成用 succeeded，失败用 failed。显示完成不等于人工验收。
        只发布公开状态，不记录凭据或内部推理，不替我作权限选择。
        """
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }
}
