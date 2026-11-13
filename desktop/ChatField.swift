import Foundation

struct ChatField: Decodable, Identifiable {
    let id: String
    let title: String
    let options: [String]
    var isValid: Bool {
        !id.isEmpty && id.count <= 100 && !title.isEmpty && title.count <= 300 &&
        options.count <= 8 && options.allSatisfy { !$0.isEmpty && $0.count <= 180 } &&
        Set(options).count == options.count
    }
}
