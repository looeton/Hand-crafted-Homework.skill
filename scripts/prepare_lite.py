#!/usr/bin/env python3
"""Prepare compact imagegen prompts from one structured answers file."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree

try:
    from package_outputs import load_config, safe_job_id
except ModuleNotFoundError:
    from .package_outputs import load_config, safe_job_id


DEFAULT_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf", ".docx"}
DEFAULT_STYLE = (
    "A4白纸上的自然手写答案，略有潦草和修改，但公式、数字、单位清晰可辨。"
    "只模仿参考笔迹，不复制参考图文字；只写给定答案，不重新计算。"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    parts = []
    for elem in root.iter():
        tag = elem.tag.rsplit("}", 1)[-1]
        if tag == "t" and elem.text:
            parts.append(elem.text)
        elif tag in {"br", "cr"}:
            parts.append("\n")
        elif tag == "p":
            parts.append("\n")
    return "".join(parts).strip()


def read_pdf(path: Path) -> tuple[str, int]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "", 0
    reader = PdfReader(str(path))
    pages = []
    for index, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(f"--- page {index} ---\n{text}")
    return "\n\n".join(pages), len(reader.pages)


def extract(source: Path) -> tuple[str, dict]:
    suffix = source.suffix.lower()
    if suffix == ".docx":
        text = read_docx(source)
        return text, {"kind": "docx", "chars": len(text)}
    if suffix == ".pdf":
        text, pages = read_pdf(source)
        return text, {"kind": "pdf", "pages": pages, "chars": len(text)}
    if suffix in {".png", ".jpg", ".jpeg"}:
        return "", {"kind": "image", "note": "Visual inspection required."}
    raise SystemExit(f"Unsupported input extension: {source.suffix}")


def load_answers(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    pages = data.get("pages") if isinstance(data, dict) else data
    if not isinstance(pages, list) or not pages:
        raise SystemExit("answers.json must contain a non-empty 'pages' list.")
    normalized = []
    for index, page in enumerate(pages, 1):
        if not isinstance(page, dict):
            raise SystemExit(f"answers.json page {index} must be an object.")
        text = str(page.get("answer_text", page.get("answer_outline", ""))).strip()
        if not text:
            raise SystemExit(f"answers.json page {index} has no answer_text.")
        normalized.append(
            {
                "page": index,
                "question_scope": str(page.get("question_scope", "")).strip(),
                "answer_text": text,
                "source_page": page.get("source_page"),
                "assumptions": page.get("assumptions", []),
            }
        )
    return normalized


def job_dir_for(source: Path, config: dict, output_dir: Path | None) -> Path:
    job_id = safe_job_id(source.stem)
    if output_dir:
        return output_dir.resolve() / job_id
    pattern = config.get("output", {}).get("default_folder", "{job_id}")
    return source.parent / pattern.format(job_id=job_id)


def visual_attachment(source: Path, page: dict, visual_dir: Path | None) -> Path:
    if not visual_dir:
        return source
    source_page = page.get("source_page") or page["page"]
    for suffix in (".png", ".jpg", ".jpeg"):
        candidate = visual_dir / f"page{int(source_page):03}{suffix}"
        if candidate.is_file():
            return candidate.resolve()
    raise SystemExit(f"No visual attachment for source page {source_page} in {visual_dir}")


def prepare(source: Path, answers_path: Path, config: dict, sample: Path | None, output_dir: Path | None, visual_dir: Path | None) -> Path:
    job_id = safe_job_id(source.stem)
    job_dir = job_dir_for(source, config, output_dir)
    prompts_dir = job_dir / "prompts"
    pages_dir = job_dir / "pages"
    extracted_dir = job_dir / "extracted"
    cache_dir = job_dir / "_image2_cache"
    for folder in (prompts_dir, pages_dir, extracted_dir, cache_dir):
        folder.mkdir(parents=True, exist_ok=True)

    copied = job_dir / f"source{source.suffix.lower()}"
    shutil.copy2(source, copied)
    extracted_text, metadata = extract(source)
    (extracted_dir / "source_text.txt").write_text(extracted_text + ("\n" if extracted_text else ""), encoding="utf-8")
    metadata.update({"source_input": str(source.resolve()), "source_copy": str(copied.resolve())})
    (extracted_dir / "source_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    style = str(config.get("handwriting_prompt") or DEFAULT_STYLE).strip()
    (cache_dir / "base_prompt.txt").write_text(style + "\n", encoding="utf-8")
    sample_data = None
    if sample:
        sample_data = {"path": str(sample.resolve()), "sha256": sha256(sample)}
        (cache_dir / "sample_image.json").write_text(json.dumps(sample_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    prompts = []
    for page in load_answers(answers_path):
        prompt_name = f"{job_id}_page{page['page']:03}.prompt.txt"
        prompt_path = prompts_dir / prompt_name
        assumptions = page["assumptions"]
        assumption_text = f"\n假设：{assumptions}" if assumptions else ""
        prompt = (
            f"{style}\n\n"
            f"题号范围：{page['question_scope'] or page['page']}\n"
            f"请把下面答案原样写成这一页的手写答案，不要补题、改数字或重新计算：\n"
            f"{page['answer_text']}{assumption_text}\n"
        )
        prompt_path.write_text(prompt, encoding="utf-8")
        attachment = visual_attachment(source, page, visual_dir)
        prompts.append(
            {
                "page": page["page"],
                "prompt_path": str(prompt_path.resolve()),
                "target_png": str((pages_dir / f"{job_id}_page{page['page']:03}.png").resolve()),
                "attach_sample_image": str(sample.resolve()) if sample else None,
                "attach_source_file": str(attachment),
                "source_file": str(source.resolve()),
                "answer_chars": len(page["answer_text"]),
                "prompt_chars": len(prompt),
            }
        )

    manifest = {
        "job_id": job_id,
        "source_input": str(source.resolve()),
        "source_copy": str(copied.resolve()),
        "answers_file": str(answers_path.resolve()),
        "job_dir": str(job_dir.resolve()),
        "sample_image": sample_data,
        "generation": {"tool": "imagegen", "status": "ready_for_imagegen"},
        "imagegen": {"status": "ready_for_imagegen", "note": "Return metadata only; never print PNG base64."},
        "prompts": prompts,
    }
    manifest_path = job_dir / "image2_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", required=True, type=Path)
    parser.add_argument("--answers", required=True, type=Path)
    parser.add_argument("--sample-image", type=Path)
    parser.add_argument("--visual-dir", type=Path, help="Optional page001.png/page002.jpg attachment directory.")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "homework_config.yaml")
    args = parser.parse_args()
    source = args.input_file.resolve()
    answers = args.answers.resolve()
    if not source.is_file() or not answers.is_file():
        raise SystemExit("Input source and answers JSON must exist.")
    sample = args.sample_image.resolve() if args.sample_image else None
    if sample and not sample.is_file():
        raise SystemExit(f"Sample image does not exist: {sample}")
    config = load_config(args.config)
    manifest = prepare(source, answers, config, sample, args.output_dir, args.visual_dir)
    print(f"Prepared: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
