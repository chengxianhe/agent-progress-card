import AppKit
import SwiftUI

/// Place the brand in the native titlebar, immediately after the window buttons.
@MainActor
final class GlimmerTitlebarAccessory: NSTitlebarAccessoryViewController {
    init(title: String) {
        super.init(nibName: nil, bundle: nil)
        let content = HStack(spacing: 5) {
            GlimmerIcon(size: 16)
            Text(title).font(.system(size: 11, weight: .medium))
                .foregroundStyle(GlimmerTheme.ink)
        }
        .frame(width: 76, height: 22)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(title + " 窗口标题")
        let host = NSHostingView(rootView: content)
        host.sizingOptions = []
        host.frame = NSRect(x: 0, y: 0, width: 76, height: 22)
        view = host
        layoutAttribute = .leading
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError("Not used") }
}
