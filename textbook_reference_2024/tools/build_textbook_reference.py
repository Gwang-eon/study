#!/usr/bin/env python3
import json
import re
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
from PIL import Image


ROMAN_PARTS = "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ"
PART_RE = re.compile(rf"^(?P<title>[{ROMAN_PARTS}]+부\.?.*?)\s+(?P<page>\d+)$")
CHAPTER_RE = re.compile(r"^(?P<title>\d+장\.?.*?)\s+(?P<page>\d+)$")
SECTION_RE = re.compile(r"^(?P<title>\d+절\.?.*?)\s+(?P<page>\d+)$")


@dataclass
class Part:
    index: int
    title: str
    start_page: int


@dataclass
class Chapter:
    index: int
    title: str
    start_page: int
    part_index: int
    part_title: str


@dataclass
class Section:
    index: int
    title: str
    start_page: int
    part_index: int
    part_title: str
    chapter_index: int
    chapter_title: str


@dataclass
class DocEntry:
    kind: str
    title: str
    file_name: str
    start_page: int
    end_page: int
    part_index: int | None = None
    part_title: str | None = None
    chapter_index: int | None = None
    chapter_title: str | None = None
    section_index: int | None = None


def parse_args() -> tuple[Path, Path]:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, help="textbook_reference_2024 directory")
    parser.add_argument("--manifest", default="manifests/pages.json")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    manifest_path = output_dir / args.manifest
    return output_dir, manifest_path


def load_pages(manifest_path: Path) -> dict:
    with manifest_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def clean_line(raw: str) -> str:
    line = raw.replace("\u0000", "").strip()
    line = re.sub(r"\s+", " ", line)
    return line


def parse_toc(pages: list[dict]) -> tuple[list[Part], list[Chapter], list[Section]]:
    toc_pages = [page for page in pages if 2 <= page["pageNumber"] <= 10]
    parts: list[Part] = []
    chapters: list[Chapter] = []
    sections: list[Section] = []
    current_part: Part | None = None
    current_chapter: Chapter | None = None

    for page in toc_pages:
        for raw_line in page["text"].splitlines():
            line = clean_line(raw_line)
            if not line:
                continue
            if line in {"차례", "요양보호사 양성표준교재"}:
                continue
            if re.fullmatch(r"\d+", line):
                continue

            match = PART_RE.match(line)
            if match:
                part = Part(
                    index=len(parts) + 1,
                    title=match.group("title"),
                    start_page=int(match.group("page")),
                )
                parts.append(part)
                current_part = part
                current_chapter = None
                continue

            match = CHAPTER_RE.match(line)
            if match and current_part is not None:
                chapter = Chapter(
                    index=len(chapters) + 1,
                    title=match.group("title"),
                    start_page=int(match.group("page")),
                    part_index=current_part.index,
                    part_title=current_part.title,
                )
                chapters.append(chapter)
                current_chapter = chapter
                continue

            match = SECTION_RE.match(line)
            if match and current_part is not None and current_chapter is not None:
                sections.append(
                    Section(
                        index=len(sections) + 1,
                        title=match.group("title"),
                        start_page=int(match.group("page")),
                        part_index=current_part.index,
                        part_title=current_part.title,
                        chapter_index=current_chapter.index,
                        chapter_title=current_chapter.title,
                    )
                )

    if not parts or not chapters or not sections:
        raise RuntimeError("failed to parse part/chapter/section structure from the table of contents")

    return parts, chapters, sections


def slugify(text: str) -> str:
    value = re.sub(r"\s+", "-", text.strip())
    value = re.sub(r"[^0-9A-Za-z가-힣ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ_-]+", "", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-_") or "untitled"


def next_start(start_page: int, starts: list[int], total_pages: int) -> int:
    later = [value for value in starts if value > start_page]
    return min(later) - 1 if later else total_pages


def build_docs(parts: list[Part], chapters: list[Chapter], sections: list[Section], total_pages: int) -> list[DocEntry]:
    docs: list[DocEntry] = [
        DocEntry(
            kind="frontmatter",
            title="표지 및 차례",
            file_name="00-frontmatter.md",
            start_page=1,
            end_page=parts[0].start_page - 1,
        )
    ]

    chapter_starts = [chapter.start_page for chapter in chapters]
    section_starts = [section.start_page for section in sections]
    all_starts = sorted({*chapter_starts, *section_starts, *(part.start_page for part in parts)})

    for part in parts:
        child_chapters = [chapter for chapter in chapters if chapter.part_index == part.index]
        if child_chapters:
            overview_end = child_chapters[0].start_page - 1
            if overview_end >= part.start_page:
                docs.append(
                    DocEntry(
                        kind="part",
                        title=part.title,
                        file_name=f"part-{part.index:02d}-overview-{slugify(part.title)}.md",
                        start_page=part.start_page,
                        end_page=overview_end,
                        part_index=part.index,
                        part_title=part.title,
                    )
                )

    for chapter in chapters:
        child_sections = [section for section in sections if section.chapter_index == chapter.index]
        if child_sections:
            intro_end = child_sections[0].start_page - 1
            if intro_end >= chapter.start_page:
                docs.append(
                    DocEntry(
                        kind="chapter",
                        title=chapter.title,
                        file_name=f"chapter-{chapter.index:02d}-overview-{slugify(chapter.title)}.md",
                        start_page=chapter.start_page,
                        end_page=intro_end,
                        part_index=chapter.part_index,
                        part_title=chapter.part_title,
                        chapter_index=chapter.index,
                        chapter_title=chapter.title,
                    )
                )

    for section in sections:
        end_page = next_start(section.start_page, all_starts, total_pages)
        docs.append(
            DocEntry(
                kind="section",
                title=section.title,
                file_name=(
                    f"part-{section.part_index:02d}_chapter-{section.chapter_index:02d}_"
                    f"section-{section.index:02d}_{slugify(section.title)}.md"
                ),
                start_page=section.start_page,
                end_page=end_page,
                part_index=section.part_index,
                part_title=section.part_title,
                chapter_index=section.chapter_index,
                chapter_title=section.chapter_title,
                section_index=section.index,
            )
        )

    return sorted(docs, key=lambda item: (item.start_page, item.kind))


def build_page_lookup(book: dict) -> dict[int, dict]:
    return {page["pageNumber"]: page for page in book["pages"]}


def find_doc_for_page(docs: list[DocEntry], page_number: int) -> DocEntry | None:
    for doc in docs:
        if doc.start_page <= page_number <= doc.end_page:
            return doc
    return None


def shrink_image(image: Image.Image, max_side: int = 420) -> Image.Image:
    copy = image.copy()
    copy.thumbnail((max_side, max_side * 2), Image.Resampling.LANCZOS)
    return copy


def dilate(mask: np.ndarray, iterations: int = 2) -> np.ndarray:
    result = mask.copy()
    for _ in range(iterations):
        expanded = result.copy()
        for y_shift in (-1, 0, 1):
            for x_shift in (-1, 0, 1):
                if x_shift == 0 and y_shift == 0:
                    continue
                shifted = np.zeros_like(result)
                y_src_start = max(0, -y_shift)
                y_src_end = result.shape[0] - max(0, y_shift)
                x_src_start = max(0, -x_shift)
                x_src_end = result.shape[1] - max(0, x_shift)
                y_dst_start = max(0, y_shift)
                y_dst_end = y_dst_start + (y_src_end - y_src_start)
                x_dst_start = max(0, x_shift)
                x_dst_end = x_dst_start + (x_src_end - x_src_start)
                shifted[y_dst_start:y_dst_end, x_dst_start:x_dst_end] = result[y_src_start:y_src_end, x_src_start:x_src_end]
                expanded |= shifted
        result = expanded
    return result


def connected_components(mask: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    components: list[tuple[int, int, int, int, int]] = []
    neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1)]

    for y in range(height):
        for x in range(width):
            if not mask[y, x] or visited[y, x]:
                continue
            stack = [(y, x)]
            visited[y, x] = True
            min_y = max_y = y
            min_x = max_x = x
            area = 0

            while stack:
                cy, cx = stack.pop()
                area += 1
                min_y = min(min_y, cy)
                max_y = max(max_y, cy)
                min_x = min(min_x, cx)
                max_x = max(max_x, cx)

                for dy, dx in neighbors:
                    ny = cy + dy
                    nx = cx + dx
                    if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        stack.append((ny, nx))

            components.append((min_x, min_y, max_x + 1, max_y + 1, area))

    return components


def iou(box_a: tuple[int, int, int, int], box_b: tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return 0.0
    inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter_area / float(area_a + area_b - inter_area)


def normalize_line_record(line: dict, scale_x: float, scale_y: float, page_height: float) -> tuple[int, int, int, int]:
    x1 = int(line["x"] * scale_x)
    x2 = int((line["x"] + line["width"]) * scale_x)
    y1_pdf = line["y"]
    y2_pdf = line["y"] + line["height"]
    y1 = int((page_height - y2_pdf) * scale_y)
    y2 = int((page_height - y1_pdf) * scale_y)
    return x1, y1, x2, y2


def choose_label(lines: list[dict], crop_box: tuple[int, int, int, int], scale_x: float, scale_y: float, page_height: float) -> str:
    x1, y1, x2, y2 = crop_box
    scored: list[tuple[int, str]] = []
    for line in lines:
        text = clean_line(line["text"])
        if not text:
            continue
        lx1, ly1, lx2, ly2 = normalize_line_record(line, scale_x, scale_y, page_height)
        overlap_x = max(0, min(x2, lx2) - max(x1, lx1))
        overlap_y = max(0, min(y2, ly2) - max(y1, ly1))
        inside = overlap_x > 0 and overlap_y > 0
        vertical_gap = min(abs(ly2 - y1), abs(ly1 - y2), abs(((ly1 + ly2) // 2) - ((y1 + y2) // 2)))
        horizontal_overlap_ratio = overlap_x / max(1, lx2 - lx1)
        if inside or (vertical_gap < 120 and horizontal_overlap_ratio > 0.2):
            score = vertical_gap
            if inside:
                score = 0
            scored.append((score, text))

    unique = []
    seen = set()
    for _, text in sorted(scored, key=lambda item: (item[0], len(item[1]))):
        if text in seen:
            continue
        seen.add(text)
        unique.append(text)
        if len(unique) == 2:
            break

    if not unique:
        return "무라벨-그림표-후보"
    return " / ".join(unique)


def extract_figures(book: dict, docs: list[DocEntry], output_dir: Path) -> list[dict]:
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    manifest_entries: list[dict] = []

    for page in book["pages"]:
        page_number = page["pageNumber"]
        image_path = output_dir / page["image"]
        if not image_path.exists():
            continue

        with Image.open(image_path) as image_handle:
            original = image_handle.convert("RGB")

        small = shrink_image(original, max_side=420)
        gray = np.asarray(small.convert("L"))
        binary = gray < 245

        small_width, small_height = small.size
        page_width = float(page["width"])
        page_height = float(page["height"])
        scale_x = small_width / page_width
        scale_y = small_height / page_height

        text_mask = np.zeros_like(binary, dtype=bool)
        for line in page["lines"]:
            lx1, ly1, lx2, ly2 = normalize_line_record(line, scale_x, scale_y, page_height)
            pad = 2
            lx1 = max(0, lx1 - pad)
            ly1 = max(0, ly1 - pad)
            lx2 = min(small_width, lx2 + pad)
            ly2 = min(small_height, ly2 + pad)
            text_mask[ly1:ly2, lx1:lx2] = True

        candidate_mask = dilate(binary & ~text_mask, iterations=2)
        components = connected_components(candidate_mask)
        page_figures = []

        for min_x, min_y, max_x, max_y, area in components:
            width = max_x - min_x
            height = max_y - min_y
            if area < 1000 or width < 35 or height < 22:
                continue
            if width > small_width * 0.96 and height > small_height * 0.96:
                continue
            if min_y < 8 and height < 50:
                continue

            full_x1 = int(min_x * original.width / small_width)
            full_y1 = int(min_y * original.height / small_height)
            full_x2 = int(max_x * original.width / small_width)
            full_y2 = int(max_y * original.height / small_height)
            pad_x = 18
            pad_y = 18
            crop_box = (
                max(0, full_x1 - pad_x),
                max(0, full_y1 - pad_y),
                min(original.width, full_x2 + pad_x),
                min(original.height, full_y2 + pad_y),
            )

            if any(iou(crop_box, existing["crop_box"]) > 0.5 for existing in page_figures):
                continue

            label = choose_label(
                page["lines"],
                crop_box,
                original.width / page_width,
                original.height / page_height,
                page_height,
            )
            page_figures.append({"crop_box": crop_box, "label": label})

        page_figures.sort(key=lambda item: (item["crop_box"][1], item["crop_box"][0]))

        for index, figure in enumerate(page_figures, start=1):
            crop_box = figure["crop_box"]
            label = figure["label"]
            slug = slugify(label)[:60]
            file_name = f"p{page_number:04d}_f{index:02d}_{slug}.png"
            file_path = figures_dir / file_name
            with Image.open(image_path) as image_handle:
                crop = image_handle.convert("RGB").crop(crop_box)
                crop.save(file_path)

            doc = find_doc_for_page(docs, page_number)
            entry = {
                "pageNumber": page_number,
                "file": f"figures/{file_name}",
                "label": label,
                "cropBox": {
                    "x1": crop_box[0],
                    "y1": crop_box[1],
                    "x2": crop_box[2],
                    "y2": crop_box[3],
                },
                "docFile": doc.file_name if doc else None,
                "docTitle": doc.title if doc else None,
            }
            manifest_entries.append(entry)

        if page_number % 20 == 0:
            print(f"figure scan {page_number}/{book['pageCount']}")

    return manifest_entries


def page_link(page_number: int) -> str:
    return f"../pages/page-{page_number:04d}.jpg"


def figure_links(figures_by_page: dict[int, list[dict]], page_number: int) -> list[str]:
    return [f"- `{Path(item['file']).name}` - [image](../{item['file']})" for item in figures_by_page.get(page_number, [])]


def write_doc(doc: DocEntry, page_lookup: dict[int, dict], figures_by_page: dict[int, list[dict]], output_path: Path) -> None:
    lines = [f"# {doc.title}", ""]
    lines.append(f"- 범위: {doc.start_page}쪽 - {doc.end_page}쪽")
    if doc.part_title:
        lines.append(f"- 부: {doc.part_title}")
    if doc.chapter_title:
        lines.append(f"- 장: {doc.chapter_title}")
    lines.append("")

    for page_number in range(doc.start_page, doc.end_page + 1):
        page = page_lookup.get(page_number)
        if not page:
            continue
        lines.append(f"## {page_number}쪽")
        lines.append("")
        lines.append(f"[페이지 이미지]({page_link(page_number)})")
        figure_lines = figure_links(figures_by_page, page_number)
        if figure_lines:
            lines.append("")
            lines.append("### 그림/표 후보")
            lines.extend(figure_lines)
        lines.append("")
        lines.append("### 추출 텍스트")
        lines.append("")
        lines.append("```text")
        lines.append(page["text"].rstrip())
        lines.append("```")
        lines.append("")

    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_index(
    output_dir: Path,
    docs: list[DocEntry],
    parts: list[Part],
    chapters: list[Chapter],
    sections: list[Section],
    figure_entries: list[dict],
) -> None:
    part_docs = defaultdict(list)
    for doc in docs:
        if doc.part_index is not None:
            part_docs[doc.part_index].append(doc)

    lines = [
        "# 요양보호사 양성 표준교재 2024 파싱본",
        "",
        "- 구성: 부/장/절 기준 분할 Markdown, 페이지 이미지, 그림/표 후보, JSON 매니페스트",
        f"- 문서 수: {len(docs)}",
        f"- 그림/표 후보 수: {len(figure_entries)}",
        "",
        "## 시작점",
        "",
        "- [표지 및 차례](markdown/00-frontmatter.md)",
        "- [그림/표 인덱스](figures/index.md)",
        "",
        "## 부별 문서",
        "",
    ]

    for part in parts:
        lines.append(f"### {part.title}")
        lines.append("")
        for doc in part_docs.get(part.index, []):
            lines.append(f"- [{doc.title}](markdown/{doc.file_name})")
        lines.append("")

    (output_dir / "index.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_figure_index(output_dir: Path, figure_entries: list[dict]) -> None:
    grouped = defaultdict(list)
    for entry in figure_entries:
        grouped[entry["docFile"] or "기타"].append(entry)

    lines = [
        "# 그림/표 후보 인덱스",
        "",
        "- 자동 추출 기준이므로 일부는 장식 요소거나 분리 경계가 거칠 수 있습니다.",
        "- 텍스트형 이미지나 표를 찾을 때는 페이지 이미지와 함께 확인하면 됩니다.",
        "",
    ]

    for doc_file, entries in sorted(grouped.items()):
        title = entries[0]["docTitle"] or "미분류"
        lines.append(f"## {title}")
        lines.append("")
        for entry in sorted(entries, key=lambda item: (item["pageNumber"], item["file"])):
            lines.append(
                f"- {entry['pageNumber']}쪽 `{Path(entry['file']).name}` - {entry['label']} - [image](../{entry['file']})"
            )
        lines.append("")

    (output_dir / "figures" / "index.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_manifests(output_dir: Path, parts: list[Part], chapters: list[Chapter], sections: list[Section], docs: list[DocEntry], figure_entries: list[dict]) -> None:
    manifests_dir = output_dir / "manifests"
    (manifests_dir / "structure.json").write_text(
        json.dumps(
            {
                "parts": [asdict(item) for item in parts],
                "chapters": [asdict(item) for item in chapters],
                "sections": [asdict(item) for item in sections],
                "docs": [asdict(item) for item in docs],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (manifests_dir / "figures.json").write_text(
        json.dumps(figure_entries, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    output_dir, manifest_path = parse_args()
    book = load_pages(manifest_path)
    (output_dir / "markdown").mkdir(parents=True, exist_ok=True)
    (output_dir / "figures").mkdir(parents=True, exist_ok=True)
    (output_dir / "manifests").mkdir(parents=True, exist_ok=True)
    pages = book["pages"]
    parts, chapters, sections = parse_toc(pages)
    docs = build_docs(parts, chapters, sections, book["pageCount"])
    page_lookup = build_page_lookup(book)

    figures = extract_figures(book, docs, output_dir)
    figures_by_page = defaultdict(list)
    for item in figures:
        figures_by_page[item["pageNumber"]].append(item)

    markdown_dir = output_dir / "markdown"
    for doc in docs:
        write_doc(doc, page_lookup, figures_by_page, markdown_dir / doc.file_name)
        print(f"wrote markdown {doc.file_name}")

    write_index(output_dir, docs, parts, chapters, sections, figures)
    write_figure_index(output_dir, figures)
    write_manifests(output_dir, parts, chapters, sections, docs, figures)


if __name__ == "__main__":
    main()
