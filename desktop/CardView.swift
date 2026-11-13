import SwiftUI

struct CardView: View {
    @ObservedObject var model: CardModel
    @ObservedObject var activity: ActivityModel
    @StateObject private var history = HistoryModel()
    @StateObject private var wechat = WeChatConnectionModel()
    @State private var showWeChat = false
    @State private var expanded = false
    @State private var pinned = true
    @State private var promptedChoiceID: String?
    @State private var promptedQuestionID: String?
    @State private var presentedPrompt: PromptPresentation?
    let resize: (Bool) -> Void
    let pin: (Bool) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            if wechat.configured { connection }
            if showWeChat {
                WeChatConnectionView(model: wechat).frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                TaskDashboard(model: model, activity: activity, history: history, expanded: expanded)
            }
            if model.readError {
                Label("任务状态暂时不可读；当前为最后记录。", systemImage: "exclamationmark.circle")
                    .font(.caption).foregroundStyle(GlimmerTheme.warning)
            }
            footer
        }
        .padding(16)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(GlimmerTheme.canvas)
        .foregroundStyle(GlimmerTheme.ink)
        .tint(GlimmerTheme.accent)
        .sheet(item: $presentedPrompt) { prompt in
            switch prompt {
            case .choice(let choice): ChoicePromptView(choice: choice)
            case .question(let question): NativeQuestionSheet(question: question)
            }
        }
        .onReceive(activity.$feed) { feed in
            guard let feed, feed.error.isEmpty else {
                presentedPrompt = nil
                return
            }
            if let choice = feed.choice, choice.isValid,
               !(feed.choice_result?.choice_id == choice.id && feed.choice_result?.status != "retry") {
                if let source = choice.source_question_id { promptedQuestionID = "native:" + source }
                if promptedChoiceID != choice.id {
                    promptedChoiceID = choice.id
                    presentedPrompt = .choice(choice)
                }
                return
            }
            if case .choice = presentedPrompt { presentedPrompt = nil }
            if let question = feed.latest_question, question.isValid, !question.replayed, question.inactive != true,
               promptedQuestionID != question.id,
               Date().timeIntervalSince1970 - question.time < 86400 {
                promptedQuestionID = question.id
                presentedPrompt = .question(question)
            }
        }
    }

    private var header: some View {
        HStack(spacing: 8) {
            GlimmerIcon()
            VStack(alignment: .leading, spacing: 1) {
                Text("微光").font(.system(size: 18, weight: .semibold, design: .rounded))
                Text("AI 任务小看板").font(.system(size: 10))
                    .foregroundStyle(GlimmerTheme.secondary)
            }
            Spacer()
            Button {
                pinned.toggle()
                pin(pinned)
            } label: {
                Image(systemName: pinned ? "pin.fill" : "pin")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(pinned ? GlimmerTheme.accent : GlimmerTheme.secondary)
                    .frame(width: 30, height: 27)
                    .background(pinned ? GlimmerTheme.accentWash : GlimmerTheme.inset,
                                in: RoundedRectangle(cornerRadius: 8))
            }
            .buttonStyle(.plain)
            .help(pinned ? "取消置顶" : "置顶")
            .accessibilityLabel(pinned ? "取消置顶" : "置顶")
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    private var connection: some View {
        Button {
            showWeChat.toggle()
            if showWeChat && !expanded {
                expanded = true
                resize(true)
            }
        } label: {
            HStack(spacing: 7) {
                Image(systemName: wechat.connected ? "checkmark.message.fill" : "message")
                    .foregroundStyle(wechat.connected ? GlimmerTheme.success : GlimmerTheme.secondary)
                Text(wechat.label).lineLimit(2).multilineTextAlignment(.leading)
                Spacer(minLength: 4)
                Text(showWeChat ? "返回任务" : "设置").foregroundStyle(GlimmerTheme.secondary)
                Image(systemName: showWeChat ? "chevron.up" : "chevron.right")
                    .font(.system(size: 8, weight: .semibold))
            }
            .font(.system(size: 11, weight: .medium))
            .padding(.horizontal, 10).padding(.vertical, 7)
            .background(wechat.connected ? GlimmerTheme.successWash : GlimmerTheme.inset,
                        in: RoundedRectangle(cornerRadius: 9))
            .contentShape(RoundedRectangle(cornerRadius: 9))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(showWeChat ? "返回任务看板" : "查看微信连接设置")
    }

    private var footer: some View {
        HStack(spacing: 6) {
            Image(systemName: "internaldrive")
            Text("本地记录 · 最多 12 个任务")
            Spacer(minLength: 4)
            Button {
                expanded.toggle()
                if !expanded { showWeChat = false }
                resize(expanded)
            } label: {
                HStack(spacing: 4) {
                    Text(expanded ? "收起" : "展开")
                    Image(systemName: expanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 8, weight: .semibold))
                }
                .padding(.horizontal, 8).padding(.vertical, 5)
                .background(GlimmerTheme.inset, in: RoundedRectangle(cornerRadius: 7))
                .contentShape(RoundedRectangle(cornerRadius: 7))
            }
            .buttonStyle(.plain)
            .accessibilityLabel(expanded ? "收起任务看板" : "展开任务分类")
        }
        .font(.system(size: 10))
        .foregroundStyle(GlimmerTheme.secondary)
        .padding(.top, 8)
        .overlay(alignment: .top) { GlimmerTheme.border.frame(height: 0.5) }
        .fixedSize(horizontal: false, vertical: true)
        .layoutPriority(1)
    }
}
