import SwiftUI

struct NativeQuestionView: View {
    let question: NativeQuestion

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("最近的客户端提问", systemImage: "questionmark.bubble")
                .font(.callout.weight(.semibold))
            Text(Date(timeIntervalSince1970: question.time), style: .date)
                .font(.caption).foregroundStyle(.secondary)
            Text(question.text).font(.callout).textSelection(.enabled)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct NativeQuestionSheet: View {
    let question: NativeQuestion
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ScrollView { NativeQuestionView(question: question) }
            Button("知道了，回原客户端回答") { dismiss() }.buttonStyle(.borderedProminent)
        }.padding(18).frame(width: 340, height: 360)
    }
}

// A single presentation prevents a native notice from hiding a manual choice sheet.
enum PromptPresentation: Identifiable {
    case choice(CardChoice)
    case question(NativeQuestion)

    var id: String {
        switch self {
        case .choice(let choice): return "choice:" + choice.id
        case .question(let question): return "question:" + question.id
        }
    }
}
