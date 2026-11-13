import SwiftUI

struct WorkExplanationView: View {
    let text: String
    var title = "工作说明"

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(title, systemImage: "sparkle")
                .font(.caption.weight(.semibold))
                .foregroundStyle(GlimmerTheme.accent)
            ScrollView {
                Text(text.isEmpty ? "等待新的工作说明。" : text)
                    .font(.callout)
                    .lineSpacing(4)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .glimmerSurface()
    }
}
