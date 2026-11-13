import SwiftUI

struct ChoiceFormView: View {
    let choice: CardChoice
    @State private var answers: [String: String] = [:]
    @State private var issue = ""
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(choice.fields ?? []) { field in
                Text(field.title).font(.callout)
                let value = Binding<String>(get: { answers[field.id] ?? "" },
                                            set: { answers[field.id] = $0 })
                if field.options.isEmpty {
                    TextField("填写回答", text: value).textFieldStyle(.roundedBorder)
                } else {
                    Picker("请选择", selection: value) {
                        Text("请选择").tag("")
                        ForEach(field.options, id: \.self) { Text($0).tag($0) }
                    }
                }
            }
            Button("提交回答") {
                do {
                    try choice.submitForm(answers)
                    dismiss()
                } catch { issue = "请填写全部问题，或稍后重试" }
            }.buttonStyle(.borderedProminent)
            Text("回答作为本人聊天发送，不代交原生表单或授予工具权限。")
                .font(.caption).foregroundStyle(.secondary)
            if !issue.isEmpty { Text(issue).foregroundStyle(.orange) }
        }
    }
}
