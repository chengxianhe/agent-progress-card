import SwiftUI

struct ChoicePromptView: View {
    let choice: CardChoice
    @Environment(\.dismiss) private var dismiss
    @State private var issue = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("需要你选择", systemImage: "list.number").font(.headline)
            Text(choice.question).font(.callout)
            ForEach(Array(choice.options.enumerated()), id: \.offset) { index, option in
                Button("\(index + 1). \(option)") {
                    do {
                        try choice.submit(index + 1)
                        dismiss()
                    } catch { issue = "提交失败，请在小看板中重试" }
                }
                .buttonStyle(.borderedProminent)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            Text("也可以在绑定的微信机器人会话回复编号；没收到通知时发送“选项”获取当前问题。")
                .font(.caption).foregroundStyle(.secondary)
            if !issue.isEmpty { Text(issue).font(.caption).foregroundStyle(.orange) }
            Button("稍后选择") { dismiss() }.buttonStyle(.bordered)
        }
        .padding(20)
        .frame(width: 340)
    }
}
