import SwiftUI

struct WeChatSetupView: View {
    @StateObject private var setup = WeChatSetupModel()
    @Environment(\.dismiss) private var dismiss
    let onStarted: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label("连接本人微信", systemImage: "message").font(.headline)
            Text("这是可选功能。电脑、Codex 对话与网络保持可用时，可在手机查进度、发文字和回复受支持的选择。")
                .font(.callout)
            Text("连接后显示二维码，由你本人扫码。需要账号支持 iLink / ClawBot；不会读取个人聊天列表或群聊。")
                .font(.caption).foregroundStyle(GlimmerTheme.secondary)
            if setup.boundThread == nil {
                Text("请先用标题旁的连接按钮设置一个 Codex 会话，再回来扫码。")
                    .font(.callout).foregroundStyle(GlimmerTheme.warning)
            }
            Toggle("在微信处理已支持的一次性请求", isOn: $setup.enableApprovals)
                .font(.callout)
            Text("默认关闭。开启后仍需你阅读完整请求并明确选择，不放开长期权限，也不代答身份验证。")
                .font(.caption).foregroundStyle(GlimmerTheme.secondary)
            Text("此操作启动普通连接，不安装登录自启动项。关闭窗口不会停止微信同步；可在连接设置中停止。")
                .font(.caption).foregroundStyle(GlimmerTheme.secondary)
            if !setup.issue.isEmpty { Text(setup.issue).font(.caption).foregroundStyle(GlimmerTheme.warning) }
            Spacer()
            HStack {
                Button("稍后再说") { dismiss() }
                Spacer()
                Button("开始扫码连接") { setup.start(completion: onStarted) }
                    .buttonStyle(.borderedProminent)
                    .disabled(setup.boundThread == nil || setup.starting || !BundledPython.available)
            }
        }
        .padding(20).frame(width: 340, height: 370)
        .background(GlimmerTheme.canvas).foregroundStyle(GlimmerTheme.ink).tint(GlimmerTheme.accent)
    }
}
