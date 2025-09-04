#!/usr/bin/env python3
"""
Compare CSV/TSV structure between an original folder and an AI-processed folder.

- Pairs files by filename: <orig>/<name> vs <ai>/<name>
- Compares:
  - number of non-empty rows
  - per-row number of columns (by detected delimiter)
  - missing/extra IDs (based on first column when non-empty)
- Reports files whose structure differs.
- Processes in batches (default: 5 files) for clearer progress.

Examples (PowerShell / Windows):
  # Compare a CSV folder against its sibling "_ai" folder
  python -m tools.compare_csv_structure \
    --orig-folder E:\ICP_notebooks\Buxton\table8_exported\sub_tables_images\csv \
    --batch-size 5

  # Explicit AI folder override
  python -m tools.compare_csv_structure \
    --orig-folder E:\path\to\csv \
    --ai-folder   E:\path\to\csv_ai

  # Emit a JSONL report for further analysis
  python -m tools.compare_csv_structure \
    -i E:\path\to\csv --json-report E:\path\to\report.jsonl

Notes:
- Delimiter detection is heuristic: prefers TAB if present in any line; otherwise COMMA.
- Empty/whitespace-only lines are ignored for structural counts.
- The first column is treated as the reaction ID when non-empty for ID set comparisons.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return p.read_text(encoding="utf-8-sig")


def _iter_nonempty_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.strip() != ""]


def _sniff_delimiter(lines: Iterable[str]) -> str:
    # If any line contains a tab, treat as TSV
    for ln in lines:
        if "\t" in ln:
            return "\t"
    return ","


@dataclass
class RowStruct:
    cols: int
    id_value: str


@dataclass
class FileStruct:
    filename: str
    row_structs: list[RowStruct]
    delimiter: str

    @property
    def row_count(self) -> int:
        return len(self.row_structs)

    def ids_set(self) -> set[str]:
        return {r.id_value for r in self.row_structs if r.id_value != ""}


def _parse_file_structure(p: Path, *, force_delim: Optional[str] = None) -> FileStruct:
    raw = _read_text(p)
    lines = _iter_nonempty_lines(raw)
    delim = force_delim or _sniff_delimiter(lines)

    row_structs: list[RowStruct] = []
    for ln in lines:
        parts = ln.split(delim)
        first = parts[0].strip() if parts else ""
        row_structs.append(RowStruct(cols=len(parts), id_value=first))

    return FileStruct(filename=p.name, row_structs=row_structs, delimiter=delim)


@dataclass
class FileComparison:
    filename: str
    orig_rows: int
    ai_rows: int
    row_count_equal: bool
    mismatched_rows: list[dict]
    missing_ids_in_ai: list[str]
    extra_ids_in_ai: list[str]
    ai_wrong_col_rows: list[dict]

    @property
    def has_difference(self) -> bool:
        return (
            not self.row_count_equal
            or len(self.mismatched_rows) > 0
            or len(self.missing_ids_in_ai) > 0
            or len(self.extra_ids_in_ai) > 0
            or len(self.ai_wrong_col_rows) > 0
        )


def compare_structures(
    orig: FileStruct,
    ai: FileStruct,
    *,
    max_mismatches_detail: int = 50,
    expected_ai_cols: Optional[int] = None,
) -> FileComparison:
    mismatches: list[dict] = []
    ai_wrong_cols: list[dict] = []

    # Compare per-row column counts for the overlapping prefix
    limit = min(len(orig.row_structs), len(ai.row_structs))
    for i in range(limit):
        oc = orig.row_structs[i].cols
        ac = ai.row_structs[i].cols
        if oc != ac:
            if len(mismatches) < max_mismatches_detail:
                mismatches.append(
                    {
                        "row": i + 1,
                        "orig_cols": oc,
                        "ai_cols": ac,
                        "orig_id": orig.row_structs[i].id_value,
                        "ai_id": ai.row_structs[i].id_value,
                    }
                )
            else:
                # Stop collecting details but keep counting beyond limit
                pass

    # Strict AI column count check
    if expected_ai_cols is not None:
        for i, r in enumerate(ai.row_structs, start=1):
            if r.cols != expected_ai_cols:
                ai_wrong_cols.append(
                    {
                        "row": i,
                        "ai_cols": r.cols,
                        "expected": expected_ai_cols,
                        "ai_id": r.id_value,
                        "orig_cols": orig.row_structs[i - 1].cols if i - 1 < len(orig.row_structs) else None,
                        "orig_id": orig.row_structs[i - 1].id_value if i - 1 < len(orig.row_structs) else None,
                    }
                )

    # Compare ID presence (based on first column when non-empty)
    orig_ids = orig.ids_set()
    ai_ids = ai.ids_set()
    missing_ids = sorted(orig_ids - ai_ids)
    extra_ids = sorted(ai_ids - orig_ids)

    return FileComparison(
        filename=orig.filename,
        orig_rows=orig.row_count,
        ai_rows=ai.row_count,
        row_count_equal=(orig.row_count == ai.row_count),
        mismatched_rows=mismatches,
        missing_ids_in_ai=missing_ids,
        extra_ids_in_ai=extra_ids,
        ai_wrong_col_rows=ai_wrong_cols,
    )


def compare_folders(
    orig_folder: Path,
    ai_folder: Path,
    *,
    glob_pattern: str = "*.csv",
    batch_size: int = 5,
    max_mismatches_detail: int = 50,
    force_delim_orig: Optional[str] = None,
    force_delim_ai: Optional[str] = None,
    show_details: bool = False,
    max_details: int = 10,
    strict_7_cols: bool = False,
) -> tuple[list[FileComparison], list[str]]:
    """Compare structures of file pairs in two folders.

    Returns:
      - list of FileComparison
      - list of missing files (present in orig but missing in ai)
    """
    if not orig_folder.exists() or not orig_folder.is_dir():
        raise FileNotFoundError(f"Original folder not found: {orig_folder}")
    if not ai_folder.exists() or not ai_folder.is_dir():
        raise FileNotFoundError(f"AI folder not found: {ai_folder}")

    orig_files = sorted([p for p in orig_folder.glob(glob_pattern) if p.is_file()])

    comparisons: list[FileComparison] = []
    missing_files: list[str] = []

    total = len(orig_files)
    if total == 0:
        return comparisons, missing_files

    for start in range(0, total, batch_size if batch_size > 0 else total):
        batch = orig_files[start : start + (batch_size if batch_size > 0 else total)]
        print(f"[BATCH] {start + 1}-{start + len(batch)} of {total}")
        for p in batch:
            ai_p = ai_folder / p.name
            if not ai_p.exists():
                missing_files.append(p.name)
                print(f"  [MISSING] {p.name} (no counterpart in AI folder)")
                continue
            try:
                orig_struct = _parse_file_structure(p, force_delim=force_delim_orig)
                ai_struct = _parse_file_structure(ai_p, force_delim=force_delim_ai)
                cmp = compare_structures(
                    orig_struct,
                    ai_struct,
                    max_mismatches_detail=max_mismatches_detail,
                    expected_ai_cols=(7 if strict_7_cols else None),
                )
                if cmp.has_difference:
                    print(
                        f"  [DIFF] {p.name} | rows: orig={cmp.orig_rows} ai={cmp.ai_rows} | "
                        f"mismatch_rows={len(cmp.mismatched_rows)} | "
                        f"missing_ids={len(cmp.missing_ids_in_ai)} extra_ids={len(cmp.extra_ids_in_ai)} | "
                        f"ai_wrong_cols={len(cmp.ai_wrong_col_rows)}"
                    )
                    # Optional detail dump
                    if show_details:
                        to_show = min(max_details, len(cmp.mismatched_rows))
                        for k in range(to_show):
                            d = cmp.mismatched_rows[k]
                            rid = f"orig_id={d['orig_id']} ai_id={d['ai_id']}" if d.get('orig_id') or d.get('ai_id') else ""
                            print(
                                f"    row {d['row']}: orig_cols={d['orig_cols']} ai_cols={d['ai_cols']} {rid}"
                            )
                        if len(cmp.mismatched_rows) > to_show:
                            print(f"    ... {len(cmp.mismatched_rows) - to_show} more row mismatches")
                        if cmp.ai_wrong_col_rows:
                            wshow = min(max_details, len(cmp.ai_wrong_col_rows))
                            for k in range(wshow):
                                d = cmp.ai_wrong_col_rows[k]
                                rid = f"ai_id={d['ai_id']}"
                                print(
                                    f"    [STRICT] row {d['row']}: ai_cols={d['ai_cols']} expected={d['expected']} {rid}"
                                )
                            if len(cmp.ai_wrong_col_rows) > wshow:
                                print(f"    ... {len(cmp.ai_wrong_col_rows) - wshow} more strict AI column issues")
                        if cmp.missing_ids_in_ai:
                            show_ids = cmp.missing_ids_in_ai[:10]
                            print(f"    missing_ids_in_ai (first {len(show_ids)}): {show_ids}")
                        if cmp.extra_ids_in_ai:
                            show_ids = cmp.extra_ids_in_ai[:10]
                            print(f"    extra_ids_in_ai (first {len(show_ids)}): {show_ids}")
                else:
                    print(f"  [OK]   {p.name}")
                comparisons.append(cmp)
            except Exception as e:
                print(f"  [ERROR] {p.name}: {e}")

    return comparisons, missing_files


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Compare structure (rows/columns/IDs) of CSV/TSV files between an original folder and an AI folder."
        )
    )
    p.add_argument(
        "--orig-folder",
        "-i",
        type=str,
        required=True,
        help="Path to the original CSV/TSV folder.",
    )
    p.add_argument(
        "--ai-folder",
        "-a",
        type=str,
        help=(
            "Path to the AI-processed folder. If omitted, defaults to <orig>_ai in the same parent directory."
        ),
    )
    p.add_argument(
        "--glob",
        type=str,
        default="*.csv",
        help="Glob pattern to select files (default: *.csv).",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="Number of files to handle per batch for progress output (default: 5).",
    )
    p.add_argument(
        "--json-report",
        type=str,
        help="Optional path to write a JSONL report (one JSON object per file).",
    )
    p.add_argument(
        "--show-details",
        action="store_true",
        help="Print per-file mismatch details (limited by --max-details).",
    )
    p.add_argument(
        "--max-details",
        type=int,
        default=10,
        help="Maximum mismatch details to print per file when --show-details is set (default: 10).",
    )
    p.add_argument(
        "--force-delim-orig",
        choices=["tab", "comma"],
        help="Force delimiter for original files (otherwise auto-detected).",
    )
    p.add_argument(
        "--force-delim-ai",
        choices=["tab", "comma"],
        help="Force delimiter for AI files (otherwise auto-detected).",
    )
    p.add_argument(
        "--fail-on-diff",
        action="store_true",
        help="Exit with code 1 if any differences are found.",
    )
    p.add_argument(
        "--strict-7-cols",
        action="store_true",
        help="Require every AI row to have exactly 7 columns; report any deviation as a difference.",
    )
    return p


def _map_delim(opt: Optional[str]) -> Optional[str]:
    if opt is None:
        return None
    return "\t" if opt == "tab" else ","


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)

    orig_folder = Path(args.orig_folder).resolve()
    if args.ai_folder:
        ai_folder = Path(args.ai_folder).resolve()
    else:
        ai_folder = orig_folder.with_name(orig_folder.name + "_ai")

    force_delim_orig = _map_delim(args.force_delim_orig)
    force_delim_ai = _map_delim(args.force_delim_ai)

    comps, missing = compare_folders(
        orig_folder,
        ai_folder,
        glob_pattern=args.glob,
        batch_size=args.batch_size,
        max_mismatches_detail=args.max_details if args.show_details else 50,
        force_delim_orig=force_delim_orig,
        force_delim_ai=force_delim_ai,
        show_details=args.show_details,
        max_details=args.max_details,
        strict_7_cols=args.strict_7_cols,
    )

    diff_files = [c for c in comps if c.has_difference]

    print()
    print("===== SUMMARY =====")
    print(f"Total files scanned: {len(comps)}")
    print(f"Files with differences: {len(diff_files)}")
    print(f"Missing AI files: {len(missing)}")

    if diff_files:
        print("\nFiles with differences:")
        for c in diff_files[:20]:  # limit list in console
            print(
                f"- {c.filename}: rows {c.orig_rows}->{c.ai_rows}, "
                f"row mismatches={len(c.mismatched_rows)}, "
                f"missing_ids={len(c.missing_ids_in_ai)}, extra_ids={len(c.extra_ids_in_ai)}"
            )
        if len(diff_files) > 20:
            print(f"  ... and {len(diff_files) - 20} more")

    if missing:
        print("\nMissing AI counterparts:")
        for name in missing[:20]:
            print(f"- {name}")
        if len(missing) > 20:
            print(f"  ... and {len(missing) - 20} more")

    if args.json_report:
        try:
            report_path = Path(args.json_report).resolve()
            with report_path.open("w", encoding="utf-8") as f:
                for c in comps:
                    rec = {
                        "filename": c.filename,
                        "orig_rows": c.orig_rows,
                        "ai_rows": c.ai_rows,
                        "row_count_equal": c.row_count_equal,
                        "mismatched_rows": c.mismatched_rows,
                        "missing_ids_in_ai": c.missing_ids_in_ai,
                        "extra_ids_in_ai": c.extra_ids_in_ai,
                        "ai_wrong_col_rows": c.ai_wrong_col_rows,
                        "has_difference": c.has_difference,
                    }
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"\n[REPORT] Wrote JSONL to: {report_path}")
        except Exception as e:
            print(f"[ERROR] Failed to write JSON report: {e}")

    if args.fail_on_diff and (len(diff_files) > 0 or len(missing) > 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
