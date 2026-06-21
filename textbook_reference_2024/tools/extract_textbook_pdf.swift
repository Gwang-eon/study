import AppKit
import Foundation
import PDFKit

struct Config {
    let inputPath: String
    let outputDir: String
    let renderWidth: Int
    let startPage: Int
    let endPage: Int
    let skipExisting: Bool
}

struct LineRecord: Codable {
    let text: String
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

struct PageRecord: Codable {
    let pageNumber: Int
    let width: Double
    let height: Double
    let image: String
    let text: String
    let lines: [LineRecord]
}

struct BookRecord: Codable {
    let sourcePDF: String
    let extractedAt: String
    let pageCount: Int
    let renderWidth: Int
    let pages: [PageRecord]
}

enum ConfigError: Error {
    case usage(String)
}

func parseArgs() throws -> Config {
    var inputPath: String?
    var outputDir: String?
    var renderWidth = 1400
    var startPage = 1
    var endPage = Int.max
    var skipExisting = false

    var index = 1
    while index < CommandLine.arguments.count {
        let arg = CommandLine.arguments[index]
        switch arg {
        case "--input":
            index += 1
            guard index < CommandLine.arguments.count else {
                throw ConfigError.usage("missing value for --input")
            }
            inputPath = CommandLine.arguments[index]
        case "--output":
            index += 1
            guard index < CommandLine.arguments.count else {
                throw ConfigError.usage("missing value for --output")
            }
            outputDir = CommandLine.arguments[index]
        case "--render-width":
            index += 1
            guard index < CommandLine.arguments.count, let value = Int(CommandLine.arguments[index]), value > 0 else {
                throw ConfigError.usage("invalid value for --render-width")
            }
            renderWidth = value
        case "--start-page":
            index += 1
            guard index < CommandLine.arguments.count, let value = Int(CommandLine.arguments[index]), value > 0 else {
                throw ConfigError.usage("invalid value for --start-page")
            }
            startPage = value
        case "--end-page":
            index += 1
            guard index < CommandLine.arguments.count, let value = Int(CommandLine.arguments[index]), value > 0 else {
                throw ConfigError.usage("invalid value for --end-page")
            }
            endPage = value
        case "--skip-existing":
            skipExisting = true
        default:
            throw ConfigError.usage("unknown argument: \(arg)")
        }
        index += 1
    }

    guard let inputPath, let outputDir else {
        throw ConfigError.usage("usage: swift extract_textbook_pdf.swift --input <pdf> --output <dir> [--render-width 1400] [--start-page 1] [--end-page 712] [--skip-existing]")
    }

    return Config(
        inputPath: inputPath,
        outputDir: outputDir,
        renderWidth: renderWidth,
        startPage: startPage,
        endPage: endPage,
        skipExisting: skipExisting
    )
}

func ensureDirectory(_ path: String) throws {
    try FileManager.default.createDirectory(
        at: URL(fileURLWithPath: path),
        withIntermediateDirectories: true
    )
}

func normalizeText(_ raw: String) -> String {
    let withoutNulls = raw.replacingOccurrences(of: "\u{0}", with: "")
    let normalizedNewlines = withoutNulls.replacingOccurrences(of: "\r\n", with: "\n")
        .replacingOccurrences(of: "\r", with: "\n")
    return normalizedNewlines
}

func renderPage(_ page: PDFPage, targetWidth: Int) -> Data? {
    let box = page.bounds(for: .mediaBox)
    guard box.width > 0, box.height > 0 else {
        return nil
    }
    let scale = CGFloat(targetWidth) / box.width
    let imageSize = NSSize(width: box.width * scale, height: box.height * scale)
    let image = page.thumbnail(of: imageSize, for: .mediaBox)
    guard let tiffData = image.tiffRepresentation,
          let rep = NSBitmapImageRep(data: tiffData)
    else {
        return nil
    }
    return rep.representation(using: .jpeg, properties: [.compressionFactor: 0.88])
}

let config: Config
do {
    config = try parseArgs()
} catch {
    fputs("\(error)\n", stderr)
    exit(2)
}

let inputURL = URL(fileURLWithPath: config.inputPath)
guard let document = PDFDocument(url: inputURL) else {
    fputs("failed to open pdf: \(config.inputPath)\n", stderr)
    exit(1)
}

let pageCount = document.pageCount
let clampedStart = max(1, min(config.startPage, pageCount))
let clampedEnd = max(clampedStart, min(config.endPage, pageCount))

let pagesDir = URL(fileURLWithPath: config.outputDir).appendingPathComponent("pages")
let manifestsDir = URL(fileURLWithPath: config.outputDir).appendingPathComponent("manifests")

do {
    try ensureDirectory(config.outputDir)
    try ensureDirectory(pagesDir.path)
    try ensureDirectory(manifestsDir.path)
} catch {
    fputs("failed to create output directories: \(error)\n", stderr)
    exit(1)
}

var records: [PageRecord] = []
let formatter = ISO8601DateFormatter()

for pageIndex in (clampedStart - 1)..<clampedEnd {
    autoreleasepool {
        guard let page = document.page(at: pageIndex) else {
            return
        }

        let pageNumber = pageIndex + 1
        let box = page.bounds(for: .mediaBox)
        let relativeImagePath = String(format: "pages/page-%04d.jpg", pageNumber)
        let absoluteImagePath = URL(fileURLWithPath: config.outputDir).appendingPathComponent(relativeImagePath).path

        if !(config.skipExisting && FileManager.default.fileExists(atPath: absoluteImagePath)) {
            if let imageData = renderPage(page, targetWidth: config.renderWidth) {
                try? imageData.write(to: URL(fileURLWithPath: absoluteImagePath))
            }
        }

        let selection = page.selection(for: box)
        let lineSelections = selection?.selectionsByLine() ?? []
        let lines = lineSelections.map { lineSelection -> LineRecord in
            let bounds = lineSelection.bounds(for: page)
            let text = normalizeText(lineSelection.string ?? "")
                .replacingOccurrences(of: "\n", with: " ")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            return LineRecord(
                text: text,
                x: bounds.origin.x,
                y: bounds.origin.y,
                width: bounds.size.width,
                height: bounds.size.height
            )
        }

        let text = normalizeText(page.string ?? "")
        let record = PageRecord(
            pageNumber: pageNumber,
            width: box.width,
            height: box.height,
            image: relativeImagePath,
            text: text,
            lines: lines
        )
        records.append(record)

        if pageNumber == clampedStart || pageNumber % 20 == 0 || pageNumber == clampedEnd {
            print("extracted page \(pageNumber)/\(pageCount)")
        }
    }
}

let book = BookRecord(
    sourcePDF: inputURL.lastPathComponent,
    extractedAt: formatter.string(from: Date()),
    pageCount: pageCount,
    renderWidth: config.renderWidth,
    pages: records
)

let encoder = JSONEncoder()
encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]

do {
    let data = try encoder.encode(book)
    let manifestURL = manifestsDir.appendingPathComponent("pages.json")
    try data.write(to: manifestURL)
    print("wrote \(manifestURL.path)")
} catch {
    fputs("failed to write manifest: \(error)\n", stderr)
    exit(1)
}
