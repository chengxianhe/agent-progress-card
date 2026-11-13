import Foundation

struct NativeQuestion: Decodable, Identifiable {
    let id: String
    let time: Double
    let text: String
    let kind: String
    let replayed: Bool
    let inactive: Bool?

    var isValid: Bool {
        !id.isEmpty && id.count <= 200 && time.isFinite && time > 0 &&
            !text.isEmpty && text.count <= 3200 && kind == "question"
    }
}
