import argparse
import os
import sys
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pdf_utils import compile_tex_to_pdf, tsv_to_full_latex_article
from tsv_utils import correct_tsv_file


def find_sources(root: Path, recursive: bool, exts: list[str]) -> list[Path]:
    patterns: list[str] = []
    for ext in exts:
        ext = ext.lower().lstrip(".")
        if recursive:
            patterns.append(f"**/*.{ext}")
        else:
            patterns.append(f"*.{ext}")
    seen: set[Path] = set()
    out: list[Path] = []
    for pat in patterns:
        for p in root.glob(pat):
            if p.is_file():
                rp = p.resolve()
                if rp not in seen:
                    seen.add(rp)
                    out.append(rp)
    return sorted(out)


def process_one(
    path: Path, root: Path, out_base: Path, skip_pdf: bool = False
) -> tuple[Path, bool, bool, str | None]:
    # Determine the output directory under out_base, mirroring relative path from root
    try:
        rel_dir = path.parent.relative_to(root)
    except ValueError:
        rel_dir = Path("")
    out_dir = out_base / rel_dir

    try:
        # Normalize/clean TSV fields in-place according to app rules
        correct_tsv_file(path)
    except Exception as e:
        return path, False, False, f"Failed to correct TSV for {path.name}: {e}"

    try:
        latex_path = tsv_to_full_latex_article(path, out_dir=out_dir)
    except Exception as e:
        return path, False, False, f"Failed to generate LaTeX for {path.name}: {e}"

    latex_ok = latex_path.exists()

    if skip_pdf:
        return path, latex_ok, False, None

    # Compile with the same engine/flags as the main app
    try:
        code, out = compile_tex_to_pdf(latex_path)
        if code != 0:
            # Return the tool output for diagnostics
            return path, latex_ok, False, out
        pdf_path = latex_path.with_suffix(".pdf")
        return path, latex_ok, pdf_path.exists(), None
    except FileNotFoundError as e:
        # Most likely xelatex is not installed / not in PATH
        return (
            path,
            latex_ok,
            False,
            f"LaTeX engine not found: {e}. Ensure 'xelatex' is installed and on PATH.",
        )
    except Exception as e:
        return path, latex_ok, False, str(e)


def main(argv: Iterable[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Batch-convert CSV/TSV files to LaTeX and PDF using the same rules as the main app.\n"
            "Results are written under <input_dir>/latex, preserving subdirectory structure."
        )
    )
    p.add_argument("input_dir", type=Path, help="Directory containing .csv/.tsv files")
    p.add_argument("--recursive", "-r", action="store_true", help="Recurse into subdirectories")
    p.add_argument(
        "--exts",
        default="csv,tsv",
        help="Comma-separated list of file extensions to include (default: csv,tsv)",
    )
    p.add_argument(
        "--latex-only",
        action="store_true",
        help="Generate LaTeX but skip PDF compilation",
    )
    p.add_argument("--jobs", "-j", type=int, default=0, help="Parallel jobs (0=auto)")
    p.add_argument("--quiet", "-q", action="store_true", help="Reduce console output")

    args = p.parse_args(list(argv) if argv is not None else None)

    root: Path = args.input_dir.resolve()
    if not root.exists() or not root.is_dir():
        print(f"Input directory does not exist or is not a directory: {root}", file=sys.stderr)
        return 2

    out_base = root / "latex"
    out_base.mkdir(parents=True, exist_ok=True)

    exts = [e.strip().lstrip(".") for e in str(args.exts).split(",") if e.strip()]
    sources = find_sources(root, args.recursive, exts)

    if not sources:
        if not args.quiet:
            print("No input files found.")
        return 0

    total = len(sources)
    ok_latex = 0
    ok_pdf = 0
    failures: list[tuple[Path, str]] = []

    if not args.quiet:
        print(f"Discovered {total} files:")
        for s in sources:
            print(f"  - {s}")
        print()

    # Parallel execution
    max_workers = args.jobs if args.jobs and args.jobs > 0 else (os.cpu_count() or 4)
    if not args.quiet:
        print(f"Running with {max_workers} parallel workers...\n")

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        fut_map = {
            ex.submit(process_one, src, root, out_base, args.latex_only): src for src in sources
        }
        for fut in as_completed(fut_map):
            src, latex_ok, pdf_ok, err = fut.result()
            results.append((src, latex_ok, pdf_ok, err))

    # Aggregate and report
    for src, latex_ok, pdf_ok, err in results:
        ok_latex += int(latex_ok)
        ok_pdf += int(pdf_ok)
        rel = src.relative_to(root) if src.is_absolute() and str(src).startswith(str(root)) else src
        if err:
            if not args.quiet:
                print(f"[FAIL] {rel}: {err}")
            failures.append((src, err))
        else:
            if not args.quiet:
                if args.latex_only:
                    print(f"[OK]   {rel}: LaTeX generated")
                else:
                    print(f"[OK]   {rel}: PDF compiled")

    print()
    print(
        f"Done. LaTeX OK: {ok_latex}/{total}; PDF OK: {ok_pdf}/{total if not args.latex_only else 0}"
    )
    if failures:
        print("Failures:")
        for pth, msg in failures:
            print(f"  - {pth}: {msg}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
