import Foundation

@main
struct NativeQuestionTests {
    static func main() throws {
        let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: file) }
        var body: [String: Any] = ["version": 1, "thread_id": "fixture-thread", "checked_at": 101.0,
            "last_event_at": 100.0, "error": "", "turn_active": false,
            "commentary": "", "calls": [], "pending": []]
        func read() throws -> ActivityFeed {
            try JSONSerialization.data(withJSONObject: body).write(to: file)
            return try ActivityFeed.read(from: file)
        }
        let legacy = try read()
        precondition(legacy.latest_question == nil)
        let question: [String: Any] = ["id": "native:fixture", "time": 100.0, "kind": "question",
            "text": "问题\n1. 甲\n2. 乙\n请在原客户端回答", "replayed": false]
        body["latest_question"] = question
        let feed = try read()
        precondition(feed.latest_question?.text.contains("2. 乙") == true)
        precondition(feed.choice == nil)
        for replacement in [question.merging(["kind": "analysis"]) { _, new in new },
            question.merging(["text": String(repeating: "x", count: 3201)]) { _, new in new },
            question.merging(["time": -1.0]) { _, new in new }] {
            body["latest_question"] = replacement
            do { _ = try read(); fatalError("Invalid native question accepted") } catch {}
        }
        print("PASS: native question decoding, legacy compatibility, bounds and no synthetic choice")
    }
}
