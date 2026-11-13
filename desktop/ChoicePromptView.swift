import SwiftUI

struct ChoicePromptView: View {
    let choice: CardChoice
    @Environment(\.dismiss) private var dismiss
    @State private var issue = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 8) {
                GlimmerIcon(size: 30)
                Text("需要你确认").font(.headline)
                Spacer()
                Text("微光").font(.caption).foregroundStyle(GlimmerTheme.secondary)
            }
            GlimmerQuestionScroll {
                VStack(alignment: .leading, spacing: 10) {
                    Text(choice.question).font(.callout.weight(.medium)).textSelection(.enabled)
                    if choice.options.isEmpty && choice.fields != nil { ChoiceFormView(choice: choice) }
                    ForEach(Array(choice.options.enumerated()), id: \.offset) { index, option in
                        Button {
                            do {
                                try choice.submit(index + 1)
                                dismiss()
                            } catch { issue = "提交失败，请在小看板中重试" }
                        } label: { GlimmerChoiceLabel(number: index + 1, title: option) }
                        .buttonStyle(GlimmerChoiceStyle())
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            Text("也可以在绑定的微信机器人会话回复编号；没收到通知时发送“选项”获取当前问题。")
                .font(.caption).foregroundStyle(GlimmerTheme.secondary)
            if !issue.isEmpty { Text(issue).font(.caption).foregroundStyle(GlimmerTheme.warning) }
            Button("稍后选择") { dismiss() }.buttonStyle(.bordered)
        }
        .padding(20)
        .frame(width: 340)
        .background(GlimmerTheme.canvas)
        .foregroundStyle(GlimmerTheme.ink)
        .tint(GlimmerTheme.accent)
    }
}
