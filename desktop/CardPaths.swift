import Foundation

enum CardPaths {
    static var directory: URL {
        if let path = ProcessInfo.processInfo.environment["WEIGUANG_STATE_DIR"], path.hasPrefix("/") {
            return URL(fileURLWithPath: path, isDirectory: true)
        }
        return FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/AgentProgressCard", isDirectory: true)
    }
}
