import SwiftUI

struct ConversationReplyView: View {
    let reply: ConversationReply

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Label("当前会话 · 最近回复", systemImage: "text.bubble")
                Spacer()
                Text(Date(timeIntervalSince1970: reply.time), style: .time)
            }.font(.caption).foregroundStyle(GlimmerTheme.secondary)
            Text(reply.text).font(.callout).textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .glimmerSurface()
    }
}
