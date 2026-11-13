import Foundation

@main struct ChoiceFormTests {
    static func main() throws {
        let base: [String: Any] = ["id": "fixture", "thread_id": "thread", "created_at": 1,
                                   "question": "回答", "options": []]
        func read(_ fields: Any) throws -> CardChoice {
            var input = base
            input["fields"] = fields
            return try JSONDecoder().decode(CardChoice.self, from: JSONSerialization.data(withJSONObject: input))
        }
        let field: [String: Any] = ["id": "q1", "title": "说明", "options": []]
        let one = try read([field])
        let duplicate = try read([field, field])
        let empty = try read([])
        assert(one.isValid)
        assert(!duplicate.isValid)
        assert(!empty.isValid)
        var long = field
        long["title"] = String(repeating: "x", count: 301)
        let oversized = try read([long])
        assert(!oversized.isValid)
        print("Choice form model tests passed")
    }
}
