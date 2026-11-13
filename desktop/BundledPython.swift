import Foundation

/// Every app worker uses the sealed runtime, independent of PATH or developer tools.
enum BundledPython {
    enum Failure: LocalizedError {
        case missing
        var errorDescription: String? { "应用缺少运行组件，请重新下载完整安装包。" }
    }

    static func process(module: String, arguments: [String] = []) throws -> Process {
        guard let resources = Bundle.main.resourceURL else { throw Failure.missing }
        let contents = Bundle.main.bundleURL.appendingPathComponent("Contents", isDirectory: true)
        let python = contents.appendingPathComponent("Resources/Python/bin/python3")
        guard FileManager.default.isExecutableFile(atPath: python.path) else { throw Failure.missing }
        let worker = Process()
        worker.executableURL = python
        worker.arguments = ["-I", "-B", resources.appendingPathComponent("worker.py").path, module] + arguments
        var environment = ProcessInfo.processInfo.environment
        environment.removeValue(forKey: "PYTHONHOME")
        environment.removeValue(forKey: "PYTHONPATH")
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["WEIGUANG_STATE_DIR"] = CardPaths.directory.path
        environment["SSL_CERT_FILE"] = "/etc/ssl/cert.pem"
        worker.environment = environment
        worker.standardInput = FileHandle.nullDevice
        worker.standardOutput = FileHandle.nullDevice
        worker.standardError = FileHandle.nullDevice
        return worker
    }

    static var available: Bool {
        FileManager.default.isExecutableFile(atPath: Bundle.main.bundleURL
            .appendingPathComponent("Contents/Resources/Python/bin/python3").path)
    }
}
