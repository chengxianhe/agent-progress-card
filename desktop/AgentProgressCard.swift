import AppKit
import SwiftUI

@MainActor
final class CardModel: ObservableObject {
    @Published var state: ProgressState?
    @Published var readError = false
    @Published var now = Date()
    let file: URL
    private var timer: Timer?

    init() {
        file = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/AgentProgressCard/state.json")
        reload()
        timer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.reload() }
        }
        timer?.tolerance = 0.5
    }

    func reload() {
        now = Date()
        guard FileManager.default.fileExists(atPath: file.path) else {
            readError = state != nil
            return
        }
        do {
            state = try ProgressState.read(from: file)
            readError = false
        } catch {
            readError = true
        }
    }
}

@MainActor
final class CardDelegate: NSObject, NSApplicationDelegate {
    private var panel: CardWindow!
    private let model = CardModel()
    private let activity = ActivityModel()

    func applicationDidFinishLaunching(_ notification: Notification) {
        if let icon = GlimmerTheme.icon { NSApp.applicationIconImage = icon }
        let menu = NSMenu()
        let item = NSMenuItem()
        menu.addItem(item)
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "显示微光", action: #selector(showCard), keyEquivalent: "0")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "退出微光", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        item.submenu = appMenu
        NSApp.mainMenu = menu
        panel = CardWindow()
        panel.title = "微光"
        panel.titleVisibility = .hidden
        panel.addTitlebarAccessoryViewController(GlimmerTitlebarAccessory(title: "微光"))
        panel.titlebarAppearsTransparent = true
        panel.backgroundColor = NSColor(GlimmerTheme.canvas)
        panel.isReleasedWhenClosed = false
        panel.hidesOnDeactivate = false
        panel.setFrameAutosaveName("AgentProgressCard")
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.contentView = CardHostingView(rootView: CardView(model: model, activity: activity, resize: { [weak self] expanded in
            self?.panel.setExpanded(expanded)
        }, pin: { [weak self] pinned in
            self?.panel.level = pinned ? .floating : .normal
            self?.panel.collectionBehavior = pinned ? [.canJoinAllSpaces, .fullScreenAuxiliary] : [.moveToActiveSpace]
        }))
        if !panel.setFrameUsingName("AgentProgressCard"), let screen = NSScreen.main {
            panel.setFrameOrigin(NSPoint(x: screen.visibleFrame.maxX - panel.frame.width - 24,
                                        y: screen.visibleFrame.maxY - panel.frame.height - 24))
        }
        let restoredTop = panel.frame.maxY
        panel.setContentSize(NSSize(width: 380, height: 360))
        panel.setFrameOrigin(NSPoint(x: panel.frame.minX, y: restoredTop - panel.frame.height))
        panel.constrainToScreen()
        showCard()
    }

    @objc func showCard() {
        panel?.deminiaturize(nil)
        panel?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showCard()
        return true
    }
}

extension NSPanel {
    func constrainToScreen() {
        guard let screen = screen ?? NSScreen.main else { return }
        setFrame(constrainFrameRect(frame, to: screen), display: true)
    }
}

@main
struct AgentProgressCard {
    @MainActor static func main() {
        let app = NSApplication.shared
        let delegate = CardDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.regular)
        withExtendedLifetime(delegate) { app.run() }
    }
}
