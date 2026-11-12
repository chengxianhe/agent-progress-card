import AppKit
import CoreImage
import SwiftUI

struct WeChatConnectionState: Decodable {
    let status: String
    let message: String
    let mode: String?
    let thread_id: String?
    let qr: String?
    let unsent: Int?
    let send_paused: Bool?

    static func read(_ url: URL) throws -> Self {
        let file = try FileHandle(forReadingFrom: url)
        defer { try? file.close() }
        let data = try file.read(upToCount: 262_145) ?? Data()
        guard data.count <= 262_144 else { throw CocoaError(.fileReadCorruptFile) }
        let state = try JSONDecoder().decode(Self.self, from: data)
        guard state.message.count <= 4_000, (state.qr?.count ?? 0) <= 8_192,
              ["loading", "wait", "scaned", "need_verifycode", "connected", "retrying", "error", "expired", "stopped"].contains(state.status)
        else { throw CocoaError(.fileReadCorruptFile) }
        return state
    }
}

@MainActor
final class WeChatConnectionModel: ObservableObject {
    @Published var state: WeChatConnectionState?
    @Published var issue = ""
    @Published var configured = false
    private var directory: URL?
    private var timer: Timer?
    private let binding = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Application Support/AgentProgressCard/wechat-source.json")

    var connected: Bool { state?.status == "connected" && state?.send_paused != true && issue.isEmpty }
    var label: String {
        if connected { return "微信已连接" }
        if !issue.isEmpty { return "微信连接待检查" }
        if state?.status == "expired" { return "微信登录已失效" }
        if state?.status == "stopped" { return "微信同步已停止" }
        if state?.send_paused == true { return "微信推送已暂停 · 等待新消息" }
        if state?.status == "retrying" {
            if let pending = state?.unsent, pending > 0 { return "微信有 \(pending) 条待送达 · 查看原因" }
            return "微信同步待处理 · 查看原因"
        }
        return "微信连接"
    }

    init() {
        reload()
        timer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.reload() }
        }
    }

    func reload() {
        guard FileManager.default.fileExists(atPath: binding.path) else {
            configured = false
            state = nil
            directory = nil
            return
        }
        configured = true
        do {
            let data = try Data(contentsOf: binding)
            guard data.count <= 16_384,
                  let value = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  value["version"] as? Int == 1, let path = value["directory"] as? String,
                  path.hasPrefix("/") else { throw CocoaError(.fileReadCorruptFile) }
            let location = URL(fileURLWithPath: path, isDirectory: true).resolvingSymlinksInPath()
            let file = location.appendingPathComponent("connection.json")
            let latest = try WeChatConnectionState.read(file)
            directory = location
            state = latest
            let attributes = try FileManager.default.attributesOfItem(atPath: file.path)
            let modified = attributes[.modificationDate] as? Date ?? .distantPast
            issue = latest.status == "connected" && Date().timeIntervalSince(modified) > 30
                ? "微信服务状态已超过 30 秒没有更新。" : ""
        } catch {
            directory = nil
            state = nil
            issue = "微信连接状态暂时不可读。"
        }
    }

    func submitCode(_ code: String) {
        guard state?.status == "need_verifycode",
              code.range(of: "^[0-9]{4,12}$", options: .regularExpression) != nil else { return }
        write("verify-code.json", data: (try? JSONSerialization.data(withJSONObject: ["code": code])) ?? Data())
    }

    func stop() { write("stop-request", data: Data()) }

    var canReconnect: Bool {
        guard state?.mode == "current_session", let thread = state?.thread_id,
              UUID(uuidString: thread) != nil else { return false }
        return !["loading", "wait", "scaned", "need_verifycode"].contains(state?.status ?? "")
    }

    func reconnect() {
        guard canReconnect, let directory, let thread = state?.thread_id else { return }
        do {
            let cardDirectory = FileManager.default.homeDirectoryForCurrentUser
                .appendingPathComponent("Library/Application Support/AgentProgressCard")
            let data = try Data(contentsOf: cardDirectory.appendingPathComponent("activity-source.json"))
            guard data.count <= 16_384,
                  let source = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  source["thread_id"] as? String == thread else {
                issue = "小看板已切换会话，请先切回原会话。"
                return
            }
            guard let resources = Bundle.main.resourceURL else { throw CocoaError(.fileNoSuchFile) }
            guard write("reconnect-request", data: Data()), write("stop-request", data: Data()) else { return }
            let worker = Process()
            worker.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
            worker.arguments = ["-m", "agent_progress_wechat.relay", "--state-dir", directory.path,
                                "--thread-id", thread, "--card-dir", cardDirectory.path, "--reconnect"]
            var environment = ProcessInfo.processInfo.environment
            environment["PYTHONPATH"] = resources.path
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            environment["SSL_CERT_FILE"] = "/etc/ssl/cert.pem"
            worker.environment = environment
            worker.standardOutput = FileHandle.nullDevice
            worker.standardError = FileHandle.nullDevice
            try worker.run()
            issue = "正在停止旧连接并获取新二维码…"
        } catch { issue = "无法启动重新扫码，请检查本机权限。" }
    }

    @discardableResult
    private func write(_ filename: String, data: Data) -> Bool {
        guard let directory else { return false }
        do {
            let file = directory.appendingPathComponent(filename)
            try data.write(to: file, options: .atomic)
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file.path)
            return true
        } catch {
            issue = "无法更新微信连接，请检查本机权限。"
            return false
        }
    }
}

struct WeChatConnectionView: View {
    @ObservedObject var model: WeChatConnectionModel
    @State private var verificationCode = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Label(model.label, systemImage: model.connected ? "checkmark.message.fill" : "message")
                    .font(.headline)
                if !model.issue.isEmpty {
                    Text(model.issue).foregroundStyle(.orange).font(.callout)
                }
                Text(model.state?.message ?? "等待连接状态").font(.callout).textSelection(.enabled)
                if let text = model.state?.qr, let qr = qrImage(text) {
                    Image(nsImage: qr).interpolation(.none).resizable()
                        .frame(width: 210, height: 210)
                        .accessibilityLabel("请使用微信扫描连接二维码")
                }
                if model.state?.status == "need_verifycode" {
                    HStack {
                        TextField("手机微信显示的配对码", text: $verificationCode)
                            .textFieldStyle(.roundedBorder)
                        Button("确认") {
                            model.submitCode(verificationCode.trimmingCharacters(in: .whitespacesAndNewlines))
                            verificationCode = ""
                        }.buttonStyle(.bordered)
                    }
                }
                if model.state?.mode == "current_session" {
                    Text("连接当前对话，保留任务上下文。\n微信发来的文字会交给当前助手，进度和回复同步回微信。")
                        .font(.callout).foregroundStyle(.secondary)
                }
                if let pending = model.state?.unsent, pending > 0 {
                    Text("还有 \(pending) 条回复等待送达").font(.caption).foregroundStyle(.orange)
                }
                if model.canReconnect {
                    Button("重新扫码连接") { model.reconnect() }.buttonStyle(.borderedProminent)
                }
                Text("关闭小看板不会停止微信同步。停止同步不会中断正在执行的任务。")
                    .font(.caption).foregroundStyle(.secondary)
                if let status = model.state?.status, status != "stopped" {
                    Button("停止微信同步") { model.stop() }.buttonStyle(.bordered)
                }
            }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 2)
        }
    }

    private func qrImage(_ text: String) -> NSImage? {
        guard let filter = CIFilter(name: "CIQRCodeGenerator") else { return nil }
        filter.setValue(Data(text.utf8), forKey: "inputMessage")
        filter.setValue("M", forKey: "inputCorrectionLevel")
        guard let output = filter.outputImage?.transformed(by: CGAffineTransform(scaleX: 8, y: 8)) else { return nil }
        let padded = output.composited(over: CIImage(color: .white).cropped(to: output.extent.insetBy(dx: -32, dy: -32)))
        guard let cg = CIContext().createCGImage(padded, from: padded.extent) else { return nil }
        return NSImage(cgImage: cg, size: NSSize(width: 210, height: 210))
    }
}
