import SwiftUI

struct FirstRunView: View {
    @StateObject private var setup = FirstRunModel()
    @Environment(\.dismiss) private var dismiss
    @State private var connectedThread: String?
    @State private var copied = false
    let onConnected: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                GlimmerIcon(size: 40)
                VStack(alignment: .leading, spacing: 3) {
                    Text("让微光连接你的任务").font(.headline)
                    Text("只需设置一次，无需输入命令").font(.caption).foregroundStyle(GlimmerTheme.secondary)
                }
            }
            if let connectedThread {
                VStack(alignment: .leading, spacing: 16) {
                    Label("会话已连接，首个任务已创建", systemImage: "checkmark.circle")
                        .font(.callout.weight(.semibold)).foregroundStyle(GlimmerTheme.success)
                    Text("公开说明、工具记录和最近回复会自动刷新。任务阶段与完成状态由助手发布。")
                        .font(.callout)
                    Text("把接入说明复制给当前 Codex 对话，助手便能使用 App 自带的 CLI 更新进度，无需安装 Python 或打开仓库。")
                        .font(.caption).foregroundStyle(GlimmerTheme.secondary)
                    Button(copied ? "已复制，粘贴到当前对话即可" : "复制给助手的进度接入说明") {
                        ProgressInstructions.copyToClipboard()
                        copied = true
                    }.buttonStyle(.bordered)
                    Spacer()
                    Button("进入看板") { onConnected(connectedThread) }.buttonStyle(.borderedProminent)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            } else {
                form
            }
        }
        .padding(20).frame(width: 340, height: 470)
        .background(GlimmerTheme.canvas).foregroundStyle(GlimmerTheme.ink).tint(GlimmerTheme.accent)
    }

    private var form: some View {
        VStack(alignment: .leading, spacing: 14) {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Label(BundledPython.available ? "运行组件已内置" : "运行组件缺失，请下载完整应用",
                          systemImage: BundledPython.available ? "checkmark.circle" : "exclamationmark.circle")
                        .font(.caption).foregroundStyle(BundledPython.available ? GlimmerTheme.success : GlimmerTheme.warning)
                    VStack(alignment: .leading, spacing: 7) {
                        Text("1 · 打开目标 Codex 对话").font(.callout.weight(.semibold))
                        Text("先在这个对话发一条消息。下一步只选择它对应的记录，微光不会读取其它对话。")
                            .font(.caption).foregroundStyle(GlimmerTheme.secondary)
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        Text("2 · 选择一份会话记录").font(.callout.weight(.semibold))
                        Text("文件选择器会打开 Codex 的 sessions 目录，可按日期找到 rollout 记录。会话编号会自动读取。")
                            .font(.caption).foregroundStyle(GlimmerTheme.secondary)
                        Button("选择会话记录…") { setup.chooseRecord() }
                            .buttonStyle(.bordered).disabled(setup.busy)
                        if let file = setup.selection {
                            Text(file.lastPathComponent).font(.caption).textSelection(.enabled).lineLimit(2)
                        }
                        if !setup.threadID.isEmpty {
                            Label("已识别会话 " + String(setup.threadID.prefix(8)), systemImage: "checkmark.circle")
                                .font(.caption).foregroundStyle(GlimmerTheme.success)
                        }
                    }.glimmerSurface()
                    VStack(alignment: .leading, spacing: 8) {
                        Text("3 · 给当前任务取个名字").font(.callout.weight(.semibold))
                        TextField("任务名称", text: $setup.title).textFieldStyle(.roundedBorder)
                        Text("连接后会创建首个看板任务，并开始收集这份记录的公开说明、工具和回复。")
                            .font(.caption).foregroundStyle(GlimmerTheme.secondary)
                    }
                    if setup.hasExistingData {
                        Toggle("我确认切换当前看板，保留旧任务记录", isOn: $setup.confirmReplacement)
                            .font(.caption)
                        Text("已绑定的微信通道会在会话改变后停止；需要时由你重新连接。不会取消 Codex 中的工作。")
                            .font(.caption).foregroundStyle(GlimmerTheme.warning)
                    }
                    if !setup.issue.isEmpty {
                        Text(setup.issue).font(.caption).foregroundStyle(GlimmerTheme.warning)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
            HStack {
                Button("稍后设置") { dismiss() }.buttonStyle(.bordered)
                Spacer()
                if setup.busy { ProgressView().controlSize(.small) }
                Button("连接并开始记录") { setup.connect { connectedThread = $0 } }
                    .buttonStyle(.borderedProminent).disabled(!setup.canConnect)
            }
        }
    }
}
