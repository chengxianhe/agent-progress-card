import AppKit
import SwiftUI

/// The 微光 palette resolves against the system appearance, including native sheets.
enum GlimmerTheme {
    private static func adaptive(_ light: UInt32, _ dark: UInt32) -> Color {
        Color(nsColor: NSColor(name: nil) { appearance in
            let value = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? dark : light
            return NSColor(srgbRed: Double((value >> 16) & 255) / 255,
                           green: Double((value >> 8) & 255) / 255,
                           blue: Double(value & 255) / 255, alpha: 1)
        })
    }

    static let canvas = adaptive(0xEAEBED, 0x282A2E)
    static let surface = adaptive(0xF1F2F3, 0x2E3035)
    static let inset = adaptive(0xE2E4E7, 0x32353A)
    static let border = adaptive(0xCACDD2, 0x42454B)
    static let accent = adaptive(0x815C43, 0xC7AC92)
    static let accentWash = adaptive(0xE7E2DC, 0x343230)
    static let ink = adaptive(0x3C4047, 0xC7C8CB)
    static let secondary = adaptive(0x626872, 0x9C9EA4)
    static let success = adaptive(0x4E6959, 0xA1B4A8)
    static let successWash = adaptive(0xE1E7E2, 0x2D3531)
    static let warning = adaptive(0x75603F, 0xC5AF91)
    static let warningWash = adaptive(0xE9E4DB, 0x33312E)
    static let failure = adaptive(0x985D59, 0xC9948E)

    static let icon: NSImage? = Bundle.main.url(forResource: "AppIcon", withExtension: "png")
        .flatMap { NSImage(contentsOf: $0) }
}

struct GlimmerIcon: View {
    var size: CGFloat = 34

    var body: some View {
        Group {
            if let icon = GlimmerTheme.icon {
                Image(nsImage: icon).resizable().interpolation(.high)
            } else {
                Image(systemName: "sparkles").resizable().scaledToFit()
                    .padding(size * 0.22).foregroundStyle(GlimmerTheme.accent)
            }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

struct GlimmerSurface: ViewModifier {
    var fill: Color

    func body(content: Content) -> some View {
        content
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(fill, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .strokeBorder(GlimmerTheme.border.opacity(0.8), lineWidth: 0.5)
                    .allowsHitTesting(false)
            }
    }
}

extension View {
    func glimmerSurface(_ fill: Color = GlimmerTheme.surface) -> some View {
        modifier(GlimmerSurface(fill: fill))
    }
}

struct GlimmerStatusBadge: View {
    let status: TaskStatus
    var historical = false

    private var tint: Color {
        if historical { return GlimmerTheme.secondary }
        switch status {
        case .running: return GlimmerTheme.accent
        case .waiting: return GlimmerTheme.warning
        case .succeeded: return GlimmerTheme.success
        case .failed: return GlimmerTheme.failure
        }
    }

    var body: some View {
        HStack(spacing: 5) {
            Image(systemName: historical ? "clock" : symbol)
            Text(historical ? "历史记录" : status.title)
        }
        .font(.system(size: 10, weight: .semibold))
        .foregroundStyle(tint)
        .padding(.horizontal, 8).padding(.vertical, 5)
        .background(tint.opacity(0.10), in: Capsule())
        .fixedSize()
    }

    private var symbol: String {
        switch status {
        case .running: return "circle.dotted"
        case .waiting: return "hand.raised"
        case .succeeded: return "checkmark"
        case .failed: return "exclamationmark"
        }
    }
}

struct GlimmerChoiceLabel: View {
    let number: Int
    let title: String

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 9) {
            Text("\(number)").font(.system(size: 11, weight: .semibold, design: .rounded))
                .frame(width: 20, height: 20)
                .background(GlimmerTheme.accentWash, in: Circle())
            Text(title).font(.callout.weight(.medium))
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
            Image(systemName: "chevron.right").font(.system(size: 9, weight: .semibold))
                .foregroundStyle(GlimmerTheme.secondary)
        }
        .accessibilityElement(children: .combine)
    }
}

struct GlimmerChoiceStyle: ButtonStyle {
    @Environment(\.isEnabled) private var enabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(GlimmerTheme.ink)
            .padding(.horizontal, 10).padding(.vertical, 9)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(configuration.isPressed ? GlimmerTheme.accentWash : GlimmerTheme.surface,
                        in: RoundedRectangle(cornerRadius: 9, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .strokeBorder(GlimmerTheme.border, lineWidth: 0.5)
                    .allowsHitTesting(false)
            }
            .contentShape(RoundedRectangle(cornerRadius: 9))
            .opacity(enabled ? 1 : 0.55)
    }
}

private struct GlimmerContentHeight: PreferenceKey {
    static var defaultValue: CGFloat = 0

    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = max(value, nextValue())
    }
}

/// Short questions fit their contents; long choices and forms stay scrollable.
struct GlimmerQuestionScroll<Content: View>: View {
    let content: Content
    @State private var height: CGFloat = 180

    init(@ViewBuilder content: () -> Content) { self.content = content() }

    var body: some View {
        ScrollView {
            content.background {
                GeometryReader { proxy in
                    Color.clear.preference(key: GlimmerContentHeight.self, value: proxy.size.height)
                }
            }
        }
        .frame(height: min(max(height, 1), 300))
        .onPreferenceChange(GlimmerContentHeight.self) { height = $0 }
    }
}
