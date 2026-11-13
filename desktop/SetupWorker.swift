import Foundation
import Darwin

enum SetupWorker {
    static func run(_ arguments: [String], completion: @escaping (Data?) -> Void) {
        do {
            let worker = try BundledPython.process(module: "agent_progress_card.setup_session", arguments: arguments)
            let output = Pipe()
            worker.standardOutput = output
            worker.terminationHandler = { _ in
                let data = try? output.fileHandleForReading.read(upToCount: 32_769)
                try? output.fileHandleForReading.close()
                DispatchQueue.main.async {
                    completion(data.flatMap { $0.count <= 32_768 ? $0 : nil })
                }
            }
            try worker.run()
            DispatchQueue.global().asyncAfter(deadline: .now() + 12) {
                if worker.isRunning {
                    worker.terminate()
                    DispatchQueue.global().asyncAfter(deadline: .now() + 2) {
                        if worker.isRunning { kill(worker.processIdentifier, SIGKILL) }
                    }
                }
            }
        } catch { completion(nil) }
    }
}
