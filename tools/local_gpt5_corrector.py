#!/usr/bin/env python3
"""
Local GPT-5-style TSV corrector.

Applies the same transformation rules used in tools/csv_ai_corrector.py's system prompt,
but locally with deterministic heuristics (no API calls).

- Input: original TSV (csv) files from an --orig-folder
- Output: corrected TSVs written to --ai-folder (overwriting if requested)
- Drives selection from a JSONL report produced by tools/compare_csv_structure --json-report

Rules implemented:
- Use TAB (\t) as delimiter in output; never output the literal two-character sequence "\t".
- Exactly 7 columns per row: [ID, Name, Reaction, pH, Rate, Comments, Reference].
- Lines with <3 fields (or leading tabs) are continuation rows: ensure first 3 columns are empty.
- Fix rows that contain literal "\\t" sequences by converting them to real tabs.
- Pad/truncate to 7 columns; consolidate extras into Comments and (when matches reference pattern) Reference.
- Preserve and lightly normalize LaTeX/mhchem tokens already present (do not aggressively rewrite chemistry).

This is a conservative structural fixer intended to resolve row/column mismatches and collapsed rows.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable
from pathlib import Path

REFERENCE_PATTERNS = [
    re.compile(r"^[0-9]{2}[A-Z][0-9]{3}$"),  # e.g., 83R031
    re.compile(r"^[0-9]{6}$"),  # e.g., 771130
]

# Basic detector for likely numeric pH tokens (allows ranges and approximate symbol)
PH_PATTERN = re.compile(r"^(~|≈|∼)?\s*\d+(\.\d+)?(\s*-\s*\d+(\.\d+)?)?$")

# Detect typical rate format (in math mode), else leave untouched
RATE_IN_MATH = re.compile(r"^\$.*\$$")
RATE_NUMBERISH = re.compile(r"^[0-9\.\s×xEe\^\-\+\(\)\\]+$")

# Quick check for whether a line looks like it uses literal \t sequences instead of tabs
CONTAINS_LITERAL_T = re.compile(r"\\t")


def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return p.read_text(encoding="utf-8-sig")


def is_reference_token(tok: str) -> bool:
    s = tok.strip()
    for pat in REFERENCE_PATTERNS:
        if pat.match(s):
            return True
    return False


def ensure_rate_math(tok: str) -> str:
    s = tok.strip()
    if not s:
        return s
    if s.startswith("$") and s.endswith("$"):
        return s
    # If it looks like a numeric/scientific expression, wrap it in $...$
    if RATE_NUMBERISH.match(s):
        return f"${s}$"
    return s


def normalize_to_7_cols_main(cols: list[str]) -> list[str]:
    # Main (non-continuation) row: cols[0:3] should be ID, Name, Reaction
    if len(cols) < 7:
        cols = cols + [""] * (7 - len(cols))
    elif len(cols) > 7:
        # Keep 0..4; fold extras into comments and reference if applicable
        head = cols[:5]
        tail = cols[5:]
        # Last token may be a reference code
        ref = ""
        if tail:
            if is_reference_token(tail[-1]):
                ref = tail[-1].strip()
                tail = tail[:-1]
        comments = " ".join(t.strip() for t in tail if t.strip())
        cols = head + [comments, ref]
        # If still not 7, pad
        if len(cols) < 7:
            cols = cols + [""] * (7 - len(cols))
    # Post tweaks
    # pH (col 3) leave as-is unless empty but one of later columns looks like pH; avoid heavy inference
    # Rate (col 4) ensure wrapped if clearly numeric-ish
    cols[4] = ensure_rate_math(cols[4])
    return cols[:7]


def normalize_to_7_cols_cont(cols: list[str]) -> list[str]:
    # Continuation row: force three leading empty columns
    core = cols
    # If the first three entries are not empty, insert empties
    # However, typical continuation input may already start with empties after split
    # We'll construct as: ["", "", ""] + the remainder
    if len(core) >= 3 and (core[0] or core[1] or core[2]):
        # treat the line as continuation regardless (we were told it's continuation)
        pass
    # Make sure we only carry columns 4..n for continuation
    # After ensuring literal tabs, typical continuation has columns aligned from index 3 onward
    # If fewer than 4 fields, pad
    if len(core) < 4:
        core = core + [""] * (4 - len(core))
    # Build new row: 3 empties + [pH, Rate, Comments, Reference] consolidated to total 7 columns
    pH = core[3].strip() if len(core) > 3 else ""
    rate = core[4].strip() if len(core) > 4 else ""
    rest = core[5:] if len(core) > 5 else []

    # Try to peel a reference from the tail
    ref = ""
    if rest:
        if is_reference_token(rest[-1]):
            ref = rest[-1].strip()
            rest = rest[:-1]
    comments = " ".join(t.strip() for t in rest if t.strip())

    rate = ensure_rate_math(rate)

    out = ["", "", "", pH, rate, comments, ref]
    # Ensure exactly 7
    if len(out) < 7:
        out = out + [""] * (7 - len(out))
    return out[:7]


def line_to_cols(line: str) -> list[str]:
    # Replace any literal \t sequences with actual tabs
    if CONTAINS_LITERAL_T.search(line):
        line = line.replace("\\t", "\t")
    # Split by real tabs
    cols = line.split("\t")
    return cols


def is_continuation(cols: list[str]) -> bool:
    # Continuation if fewer than 3 fields OR first three are empty
    if len(cols) < 3:
        return True
    if cols[0].strip() == "" and cols[1].strip() == "" and cols[2].strip() == "":
        return True
    # Also treat lines that begin with nothing but whitespace before 3rd tab as continuation
    return False


def correct_tsv_text(raw: str) -> str:
    lines = [ln for ln in raw.splitlines() if ln.strip() != ""]
    out_lines: list[str] = []
    for ln in lines:
        cols = line_to_cols(ln)
        if is_continuation(cols):
            fixed = normalize_to_7_cols_cont(cols)
        else:
            fixed = normalize_to_7_cols_main(cols)
        out_lines.append("\t".join(fixed))
    return "\n".join(out_lines) + "\n"


def load_flagged_names_from_jsonl(report_path: Path) -> list[str]:
    names: list[str] = []
    for ln in read_text(report_path).splitlines():
        if not ln.strip():
            continue
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        if rec.get("has_difference"):
            name = rec.get("filename")
            if isinstance(name, str):
                names.append(name)
    return names


def process_files(
    orig_folder: Path, ai_folder: Path, names: Iterable[str], overwrite: bool = True
) -> tuple[int, int]:
    ai_folder.mkdir(parents=True, exist_ok=True)
    wrote = 0
    skipped = 0
    for nm in names:
        src = orig_folder / nm
        dst = ai_folder / nm
        if not src.exists():
            # Skip missing source files silently
            skipped += 1
            continue
        if dst.exists() and not overwrite:
            skipped += 1
            continue
        raw = read_text(src)
        fixed = correct_tsv_text(raw)
        dst.write_text(fixed, encoding="utf-8")
        wrote += 1
    return wrote, skipped


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Local GPT-5-style TSV corrector (offline)")
    p.add_argument(
        "--orig-folder",
        "-i",
        type=str,
        required=True,
        help="Path to original TSV/CSV folder (source)",
    )
    p.add_argument("--ai-folder", "-a", type=str, help="Output folder (defaults to <orig>_ai)")
    p.add_argument(
        "--from-json-report",
        type=str,
        required=True,
        help="Path to JSONL report from compare_csv_structure",
    )
    p.add_argument("--overwrite", action="store_true", help="Overwrite outputs if exist")
    return p


def main(argv: list[str] | None = None) -> int:
    ap = build_arg_parser()
    args = ap.parse_args(argv)

    orig_folder = Path(args.orig_folder).resolve()
    ai_folder = (
        Path(args.ai_folder).resolve()
        if args.ai_folder
        else orig_folder.with_name(orig_folder.name + "_ai")
    )
    report_path = Path(args.from_json_report).resolve()

    if not orig_folder.exists() or not orig_folder.is_dir():
        raise SystemExit(f"Original folder not found: {orig_folder}")
    if not report_path.exists():
        raise SystemExit(f"Report file not found: {report_path}")

    names = load_flagged_names_from_jsonl(report_path)
    wrote, skipped = process_files(orig_folder, ai_folder, names, overwrite=args.overwrite)
    print(f"[DONE] wrote={wrote} skipped={skipped} total={len(names)} -> {ai_folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
