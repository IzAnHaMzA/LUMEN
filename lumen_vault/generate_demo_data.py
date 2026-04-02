#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYLLABUS_DIR = ROOT / "k scheme syllabus"
PAPERS_DIR = ROOT / "previous year question paper" / "Question Papers"
OUT_FILE = Path(__file__).resolve().parent / "data" / "library_index.json"


SEM_MAP = {
    "311": "Sem 1",
    "321": "Sem 1",
    "331": "Sem 1",
    "312": "Sem 2",
    "322": "Sem 2",
    "332": "Sem 2",
    "313": "Sem 3",
    "323": "Sem 3",
    "333": "Sem 3",
    "314": "Sem 4",
    "324": "Sem 4",
    "334": "Sem 4",
    "315": "Sem 5",
    "325": "Sem 5",
    "316": "Sem 6",
    "326": "Sem 6",
}


def web_path(path: Path) -> str:
    return "/" + path.relative_to(ROOT).as_posix()


def semester_from_code(code: str) -> str:
    if len(code) < 3:
        return "Unknown"
    return SEM_MAP.get(code[:3], "Unknown")


def parse_program_folder(folder_name: str) -> tuple[str, str]:
    # Examples:
    # "AI - AI - Diploma In Artificial Intelligence"
    # "SE - Diploma In Computer Science"
    parts = [p.strip() for p in folder_name.split(" - ")]
    if not parts:
        return "NA", folder_name
    code = parts[0]
    display = folder_name
    if len(parts) >= 2:
        # keep original full folder title for fidelity
        display = folder_name
    return code, display


def build_syllabus_index() -> tuple[list[dict], dict]:
    subjects: list[dict] = []
    by_code: dict[str, list[dict]] = defaultdict(list)

    for program_dir in sorted([d for d in SYLLABUS_DIR.iterdir() if d.is_dir()]):
        prog_code, prog_name = parse_program_folder(program_dir.name)
        for html_file in sorted(program_dir.glob("*.html")):
            m = re.match(r"^\s*(\d{5,6})\s*-\s*(.+)\.html$", html_file.name, flags=re.I)
            if not m:
                continue
            code = m.group(1).strip()
            title = m.group(2).strip()
            item = {
                "paper_code": code,
                "subject": title,
                "program_code": prog_code,
                "program_name": prog_name,
                "semester": semester_from_code(code),
                "syllabus_path": web_path(html_file),
            }
            subjects.append(item)
            by_code[code].append(item)
    return subjects, by_code


def build_papers_index() -> tuple[dict, list[str]]:
    papers_by_code: dict[str, dict] = {}
    sessions_set = set()
    if not PAPERS_DIR.exists():
        return papers_by_code, []

    for code_dir in sorted([d for d in PAPERS_DIR.iterdir() if d.is_dir()]):
        code = code_dir.name.strip()
        files = []
        sessions = []
        for pdf in sorted(code_dir.glob("*.pdf")):
            # "Summer - 2025 - 311302.pdf"
            session_label = pdf.stem.rsplit(" - ", 1)[0].strip()
            sessions_set.add(session_label)
            sessions.append(session_label)
            files.append({"session": session_label, "path": web_path(pdf), "name": pdf.name})
        papers_by_code[code] = {
            "code": code,
            "sessions": sorted(set(sessions)),
            "files": files,
            "count": len(files),
        }
    return papers_by_code, sorted(sessions_set)


def build_programs(subjects: list[dict]) -> list[dict]:
    stats = {}
    for s in subjects:
        key = s["program_name"]
        if key not in stats:
            stats[key] = {
                "program_code": s["program_code"],
                "program_name": s["program_name"],
                "subjects": 0,
            }
        stats[key]["subjects"] += 1
    return sorted(stats.values(), key=lambda x: (x["program_code"], x["program_name"]))


def main() -> None:
    subjects, by_code = build_syllabus_index()
    papers_by_code, sessions = build_papers_index()

    for code, rows in by_code.items():
        sessions_for_code = papers_by_code.get(code, {}).get("sessions", [])
        for row in rows:
            row["available_sessions"] = sessions_for_code
            row["papers_count"] = len(sessions_for_code)

    all_subjects = sorted(
        subjects,
        key=lambda x: (
            x["program_code"],
            x["semester"],
            x["paper_code"],
            x["subject"].lower(),
        ),
    )

    unique_codes = sorted(by_code.keys())
    coverage = {}
    for code in unique_codes:
        coverage[code] = papers_by_code.get(code, {}).get("sessions", [])

    data = {
        "meta": {
            "project_name": "Lumen Vault",
            "subjects_total": len(all_subjects),
            "programs_total": len({s["program_name"] for s in all_subjects}),
            "unique_codes_total": len(unique_codes),
            "papers_total": sum(v.get("count", 0) for v in papers_by_code.values()),
            "sessions_total": len(sessions),
        },
        "sessions": sessions,
        "programs": build_programs(all_subjects),
        "subjects": all_subjects,
        "papers_by_code": papers_by_code,
        "coverage": coverage,
    }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote: {OUT_FILE}")
    print(
        f"subjects={data['meta']['subjects_total']} "
        f"unique_codes={data['meta']['unique_codes_total']} "
        f"papers={data['meta']['papers_total']}"
    )


if __name__ == "__main__":
    main()

