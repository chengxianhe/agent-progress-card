import SwiftUI

struct TaskDashboard: View {
    @ObservedObject var model: CardModel
    @ObservedObject var activity: ActivityModel
    @ObservedObject var history: HistoryModel
    let expanded: Bool
    @State private var selection: String?
    @State private var section = "概览"
    @State private var category = "全部"
    @State private var failuresOnly = false
    @State private var submittedChoiceID: String?
    @State private var choiceIssue = ""

    private var task: HistoryTask? {
        let id = expanded ? (selection ?? model.state?.task_id) : model.state?.task_id
        return history.tasks.first { $0.id == id } ?? history.tasks.last
    }
    private var isCurrent: Bool { task?.id == model.state?.task_id }
    private var filtered: [ToolActivity] {
        filteredCalls(task?.calls ?? [], category: category, failuresOnly: failuresOnly)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if expanded && !history.tasks.isEmpty {
                HStack {
                    Text(isCurrent ? "当前任务" : "历史任务")
                        .font(.system(size: 10, weight: .medium)).foregroundStyle(GlimmerTheme.secondary)
                    Spacer()
                    Menu {
                        Picker("任务", selection: Binding(get: { task?.id ?? "" }, set: { selection = $0 })) {
                            ForEach(history.tasks.reversed()) { item in
                                Text((item.id == model.state?.task_id ? "当前 · " : "历史 · ") + item.title).tag(item.id)
                            }
                        }
                    } label: {
                        Label("切换任务", systemImage: "clock.arrow.circlepath").font(.system(size: 10))
                    }
                    .menuStyle(.borderlessButton).fixedSize()
                    .accessibilityLabel("选择当前或历史任务")
                }
                .onChange(of: task?.id) { _ in category = "全部"; failuresOnly = false }
            }
            if let task {
                HStack(alignment: .top) {
                    Text(task.title).font(.system(size: 19, weight: .semibold, design: .rounded))
                        .lineLimit(2).frame(maxWidth: .infinity, alignment: .leading)
                    GlimmerStatusBadge(status: task.status, historical: !isCurrent)
                }
                if expanded {
                    Picker("内容分类", selection: $section) {
                        ForEach(["概览", "过程", "工具", "结果"], id: \.self) { Text($0).tag($0) }
                    }.pickerStyle(.segmented).labelsHidden().accessibilityLabel("内容分类")
                }
                if !history.issue.isEmpty { notice(history.issue) }
                if isCurrent && !activity.issue.isEmpty { notice(activity.issue) }
                if isCurrent, activity.issue.isEmpty, activity.feed?.thread_id == task.thread_id,
                   let rate = activity.feed?.output_rate {
                    Text(String(format: "本轮平均输出 %.1f token/秒", rate))
                        .font(.system(size: 10).monospacedDigit()).foregroundStyle(GlimmerTheme.secondary)
                }
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        if isCurrent, activity.issue.isEmpty, activity.feed?.thread_id == task.thread_id,
                           let question = activity.feed?.latest_question,
                           question.id != "native:" + (activity.feed?.choice?.source_question_id ?? "") {
                            NativeQuestionView(question: question)
                        }
                        if isCurrent, activity.issue.isEmpty, activity.feed?.thread_id == task.thread_id,
                           let choice = activity.feed?.choice, choice.isValid {
                            VStack(alignment: .leading, spacing: 8) {
                                Label("需要你确认", systemImage: "exclamationmark.circle")
                                    .font(.caption.weight(.semibold)).foregroundStyle(GlimmerTheme.warning)
                                Text(choice.question).font(.callout.weight(.medium))
                                if choice.options.isEmpty && choice.fields != nil { ChoiceFormView(choice: choice) }
                                ForEach(Array(choice.options.enumerated()), id: \.offset) { index, option in
                                    Button {
                                        do {
                                            try choice.submit(index + 1)
                                            submittedChoiceID = choice.id
                                            choiceIssue = "已提交，等待当前会话接收"
                                        } catch { choiceIssue = "提交失败，请检查本机卡片权限" }
                                    } label: { GlimmerChoiceLabel(number: index + 1, title: option) }
                                    .buttonStyle(GlimmerChoiceStyle())
                                    .disabled((submittedChoiceID == choice.id && activity.feed?.choice_result?.status != "retry") ||
                                              (activity.feed?.choice_result?.choice_id == choice.id && activity.feed?.choice_result?.status != "retry"))
                                }
                                Text(activity.feed?.choice_result?.choice_id == choice.id
                                     ? activity.feed?.choice_result?.message ?? choiceIssue
                                     : choiceIssue.isEmpty ? "点击选项，或在微信回复编号。" : choiceIssue)
                                    .font(.caption).foregroundStyle(GlimmerTheme.secondary)
                            }.glimmerSurface(GlimmerTheme.warningWash)
                        }
                        if isCurrent, activity.issue.isEmpty, activity.feed?.choice == nil,
                           activity.feed?.choice_result?.thread_id == task.thread_id,
                           let result = activity.feed?.choice_result, result.status == "sent" {
                            Label(result.message, systemImage: "checkmark.circle.fill")
                                .font(.caption).foregroundStyle(GlimmerTheme.success)
                        }
                        if activity.issue.isEmpty,
                           let reply = currentConversationReply(activity.feed, threadID: task.thread_id, isCurrent: isCurrent) {
                            ConversationReplyView(reply: reply)
                        }
                        switch expanded ? section : "概览" {
                        case "过程": steps(task)
                        case "工具": tools(task)
                        case "结果": results(task)
                        default: overview(task)
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 2)
                }
            } else {
                if !history.issue.isEmpty { notice(history.issue) }
                VStack(spacing: 12) {
                    Spacer()
                    GlimmerIcon(size: 64)
                    Text(model.state?.action ?? "等待新的任务")
                        .font(.system(size: 16, weight: .semibold, design: .rounded))
                    Text(history.issue.isEmpty ? "任务开始后，微光会在这里\n记录进展、工作说明与回复。" : "历史暂时无法载入，\n修复后会恢复分类与工具记录。")
                        .font(.callout).foregroundStyle(GlimmerTheme.secondary)
                        .multilineTextAlignment(.center)
                    Spacer()
                }.frame(maxWidth: .infinity)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .foregroundStyle(GlimmerTheme.ink)
        .tint(GlimmerTheme.accent)
        .onChange(of: model.state?.task_id) { _ in selection = nil }
    }

    private func notice(_ text: String) -> some View {
        Label(text, systemImage: "exclamationmark.circle")
            .font(.caption).foregroundStyle(GlimmerTheme.warning).fixedSize(horizontal: false, vertical: true)
    }

    private func overview(_ task: HistoryTask) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            if task.status == .waiting { notice("需要你确认：" + task.action) }
            if task.failures > 0 { notice("最近记录中有 \(task.failures) 次失败调用，可在工具页查看；不等于整个任务失败。") }
            if isCurrent, activity.issue.isEmpty, activity.feed?.thread_id == task.thread_id,
               let pending = activity.feed?.pending.last, task.status.isActive {
                Label("执行中 · " + pending.name, systemImage: "circle.dotted")
                    .font(.caption).foregroundStyle(GlimmerTheme.accent)
            }
            WorkExplanationView(text: task.latestExplanation, title: task.status == .running ? "正在处理" : "工作说明")
                .frame(height: expanded ? 125 : 90)
            HStack {
                Text("最近调用 \(task.calls.count) · 工作记录 \(task.steps.count)")
                Spacer()
                Text(Date(timeIntervalSince1970: task.updated_at), style: .time)
            }.font(.caption2).foregroundStyle(GlimmerTheme.secondary)
            ForEach(Array(task.calls.suffix(expanded ? 2 : 1).reversed())) { call in
                ToolActivityRow(call: call, expanded: false).glimmerSurface()
            }
            if task.legacy { notice("旧版仅保留部分摘要，缺失的调用历史无法补齐。") }
        }
    }

    private func steps(_ task: HistoryTask) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("最近 30 条公开工作记录").font(.caption).foregroundStyle(.secondary)
            ForEach(task.steps.reversed()) { step in
                VStack(alignment: .leading, spacing: 5) {
                    HStack {
                        Text(step.kind == "final" ? "本轮回复" : step.kind == "progress" ? "任务进度" : "工作说明")
                        Spacer()
                        Text(Date(timeIntervalSince1970: step.time), style: .time)
                    }.font(.caption2).foregroundStyle(.secondary)
                    Text(step.text).font(.callout).textSelection(.enabled)
                }
                Divider()
            }
            if task.steps.isEmpty { Text("尚无工作记录").foregroundStyle(.secondary) }
        }
    }

    private func tools(_ task: HistoryTask) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Picker("类型", selection: $category) {
                    ForEach(["全部", "命令", "文件", "网页", "MCP", "其他"], id: \.self) { Text($0).tag($0) }
                }
                Toggle("仅失败", isOn: $failuresOnly).toggleStyle(.checkbox).font(.caption)
            }
            Text("保存最近 20 条 · 当前筛选 \(filtered.count) 条").font(.caption2).foregroundStyle(.secondary)
            ForEach(filtered) { call in
                ToolActivityRow(call: call, expanded: true)
                    .glimmerSurface()
            }
            if filtered.isEmpty { Text("没有符合筛选条件的调用").foregroundStyle(.secondary) }
        }
    }

    private func results(_ task: HistoryTask) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(task.status.title, systemImage: task.status == .succeeded ? "checkmark.circle" : "doc.text")
                .font(.headline)
            Text(task.action).font(.callout.weight(.medium)).textSelection(.enabled)
            if !task.detail.isEmpty { Text(task.detail).font(.callout).textSelection(.enabled) }
            if let final = task.steps.last(where: { $0.kind == "final" }) {
                Divider()
                Text("最近一次公开回复").font(.caption).foregroundStyle(.secondary)
                Text(final.text).font(.callout).textSelection(.enabled)
            }
            Text("状态来自任务进度记录；工具调用完成、本轮回复结束，都不代表已通过人工验收。")
                .font(.caption).foregroundStyle(.secondary)
            if !isCurrent && task.status.isActive { notice("该任务切换时尚未结束，当前结果未知。") }
        }
    }
}
