#!/usr/bin/env python3
"""Import a novel and split it into traceable chapter files using only stdlib."""

from __future__ import annotations

import argparse
import html
import re
import shutil
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from common import atomic_write_json, atomic_write_text, require_safe_id, sha256_file, utc_now


HEADING_RE = re.compile(
    r"(?im)^(?P<title>\s*(?:第[零〇一二两三四五六七八九十百千万0-9]{1,12}[章节卷回部篇]|"
    r"chapter\s+[0-9ivxlcdm]+)\s*[^\n]{0,80})\s*$"
)
TAG_RE = re.compile(r"<[^>]+>")


def read_text_file(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("无法识别文本编码，请先转换为 UTF-8")


def read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml_data = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml_data)
    namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for paragraph in root.findall(".//w:p", namespaces):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", namespaces)).strip()
        if text:
            paragraphs.append(text)
    return "\n\n".join(paragraphs)


def html_to_text(value: str) -> str:
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", value)
    value = re.sub(r"(?i)</?(?:p|div|h[1-6]|li|br|blockquote)[^>]*>", "\n", value)
    value = TAG_RE.sub("", value)
    value = html.unescape(value)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def read_epub(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
        rootfile = next(
            (node.attrib.get("full-path") for node in container.iter() if node.tag.endswith("rootfile")),
            None,
        )
        if not rootfile:
            raise ValueError("EPUB 缺少 OPF rootfile")
        opf = ElementTree.fromstring(archive.read(rootfile))
        base = Path(rootfile).parent
        manifest: dict[str, str] = {}
        spine: list[str] = []
        for node in opf.iter():
            if node.tag.endswith("item") and node.attrib.get("id") and node.attrib.get("href"):
                manifest[node.attrib["id"]] = node.attrib["href"]
            elif node.tag.endswith("itemref") and node.attrib.get("idref"):
                spine.append(node.attrib["idref"])
        ordered = [str((base / manifest[item_id]).as_posix()) for item_id in spine if item_id in manifest]
        if not ordered:
            ordered = [name for name in names if name.lower().endswith((".xhtml", ".html", ".htm"))]
        sections = []
        for name in ordered:
            if name not in names:
                continue
            raw = archive.read(name)
            text = raw.decode("utf-8", errors="replace")
            clean = html_to_text(text)
            if clean:
                sections.append(clean)
        return "\n\n".join(sections)


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".markdown"}:
        return read_text_file(path)
    if suffix == ".docx":
        return read_docx(path)
    if suffix == ".epub":
        return read_epub(path)
    raise ValueError("仅支持 TXT、MD、Markdown、DOCX、EPUB；扫描 PDF 请先 OCR 为 UTF-8 TXT")


def normalize_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\u3000", " ")
    value = "\n".join(line.rstrip() for line in value.splitlines())
    return re.sub(r"\n{4,}", "\n\n\n", value).strip()


def split_chapters(text: str, fallback_chars: int) -> list[dict[str, str]]:
    matches = list(HEADING_RE.finditer(text))
    chapters: list[dict[str, str]] = []
    if matches:
        prefix = text[: matches[0].start()].strip()
        if prefix:
            chapters.append({"title": "序章/正文前说明", "text": prefix})
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            body = text[match.start() : end].strip()
            if body:
                chapters.append({"title": match.group("title").strip(), "text": body})
    if chapters:
        return chapters

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    current: list[str] = []
    current_chars = 0
    part_index = 1
    for paragraph in paragraphs:
        if current and current_chars + len(paragraph) > fallback_chars:
            chapters.append({"title": f"自动分段 {part_index}", "text": "\n\n".join(current)})
            part_index += 1
            current = []
            current_chars = 0
        current.append(paragraph)
        current_chars += len(paragraph)
    if current:
        chapters.append({"title": f"自动分段 {part_index}", "text": "\n\n".join(current)})
    return chapters


def main() -> int:
    parser = argparse.ArgumentParser(description="导入小说并生成分章索引")
    parser.add_argument("--source", required=True)
    parser.add_argument("--series-root", required=True)
    parser.add_argument("--series-id", required=True)
    parser.add_argument("--title")
    parser.add_argument("--fallback-chars", type=int, default=12000)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    series_root = Path(args.series_root).expanduser().resolve()
    series_id = require_safe_id(args.series_id, "series_id")
    if not source.is_file():
        raise FileNotFoundError(f"小说源文件不存在：{source}")
    if not 3000 <= args.fallback_chars <= 50000:
        raise ValueError("fallback-chars 必须在 3000-50000 之间")

    chapter_index_path = series_root / "chapters" / "chapter_index.json"
    if chapter_index_path.exists() and not args.force:
        existing = __import__("common").read_json(chapter_index_path)
        if existing.get("source_sha256") == sha256_file(source):
            print(f"已导入且源文件未变化：{chapter_index_path}")
            return 0
        raise FileExistsError("目标项目已经导入另一版本源文件；请更换 series_id，或明确使用 --force")

    text = normalize_text(extract_text(source))
    if len(text) < 100:
        raise ValueError("抽取到的正文过短，无法作为小说导入")
    chapters = split_chapters(text, args.fallback_chars)
    if not chapters:
        raise ValueError("没有识别到可用正文")

    for relative in (
        "input/source", "chapters/raw", "summaries", "bible", "plan", "episodes", "review",
        "queue/ready", "queue/running", "queue/done", "queue/failed", "world_state",
    ):
        (series_root / relative).mkdir(parents=True, exist_ok=True)
    copied_source = series_root / "input" / "source" / source.name
    if not copied_source.exists() or not source.samefile(copied_source):
        shutil.copy2(source, copied_source)

    chapter_rows = []
    total_chars = 0
    for number, chapter in enumerate(chapters, start=1):
        chapter_id = f"CH{number:04d}"
        chapter_path = series_root / "chapters" / "raw" / f"{chapter_id}.txt"
        atomic_write_text(chapter_path, chapter["text"].strip() + "\n")
        chars = len(chapter["text"])
        total_chars += chars
        chapter_rows.append({
            "chapter_id": chapter_id,
            "order": number,
            "title": chapter["title"],
            "relative_path": f"chapters/raw/{chapter_id}.txt",
            "char_count": chars,
            "sha256": sha256_file(chapter_path),
        })

    now = utc_now()
    index = {
        "schema_version": "1.0", "series_id": series_id, "source_filename": source.name,
        "source_sha256": sha256_file(source), "source_char_count": len(text),
        "chapter_count": len(chapter_rows), "indexed_char_count": total_chars,
        "coverage_ratio": round(total_chars / max(1, len(text)), 6), "created_at": now,
        "chapters": chapter_rows,
    }
    atomic_write_json(chapter_index_path, index)

    series_path = series_root / "series.json"
    if not series_path.exists() or args.force:
        atomic_write_json(series_path, {
            "schema_version": "1.0", "series_id": series_id,
            "title": args.title or source.stem, "status": "planning", "created_at": now,
            "source_sha256": index["source_sha256"], "episode_count": None,
        })
    progress_path = series_root / "progress.json"
    if not progress_path.exists() or args.force:
        atomic_write_json(progress_path, {
            "schema_version": "1.0", "series_id": series_id, "status": "planning",
            "planned_count": 0, "ready_count": 0, "running_count": 0,
            "done_count": 0, "failed_count": 0, "current_episode_project_id": None,
            "updated_at": now,
        })
    if not (series_root / "asset_registry.json").exists():
        atomic_write_json(series_root / "asset_registry.json", {
            "schema_version": "1.2", "series_id": series_id,
            "asset_root": "series_assets", "assets": [], "updated_at": now,
        })
    (series_root / "series_assets").mkdir(parents=True, exist_ok=True)
    if not (series_root / "world_state" / "current.json").exists():
        atomic_write_json(series_root / "world_state" / "current.json", {
            "schema_version": "1.0", "series_id": series_id, "after_episode": 0,
            "characters": [], "locations": [], "props": [], "open_clues": [], "updated_at": now,
        })
    print(f"导入完成：{len(chapter_rows)} 个章节/分段，项目目录：{series_root}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1)
