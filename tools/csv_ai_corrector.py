#!/usr/bin/env python3
"""
CSV AI Corrector (CLI)

Process all CSV files in a folder one-by-one with OpenAI (gpt-4.1-mini) and
write corrected CSVs into a sibling folder named <input_folder>_ai, retaining
original filenames.

Environment:
  - OPENAI_API_KEY must be set (can be provided via .env if python-dotenv is installed)

Examples (PowerShell / Windows):
  # Ensure the API key is set in your environment
  # $env:OPENAI_API_KEY = "{{OPENAI_API_KEY}}"  # set this yourself; do not echo it

  # Run the CLI
  # python -m tools.csv_ai_corrector --input-folder E:\path\to\my_csvs

Notes:
  - The tool sends the entire CSV content to the model and expects plain CSV in response.
  - For very large CSVs, you may need to chunk or down-scope the input; we can extend the tool later.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import logging
import os
import re
import sys
import time
from pathlib import Path

# Best-effort: load .env if present
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:
    pass

try:
    from openai import OpenAI  # Requires openai>=1.0.0
except Exception as e:  # pragma: no cover (import-time failure)
    raise RuntimeError(
        "The 'openai' package is required. Install dependencies (pip install -r requirements.txt)."
    ) from e


DEFAULT_SYSTEM_PROMPT = r"""
You are an expert data cleaner. You will receive the full contents of a TSV (tab-delimited) text file representing 7-column rows of chemistry data. This file will be used later to generate LaTeX, so all LaTeX/mhchem content must remain valid.

Output/format constraints

Return ONLY the corrected file contents. No commentary, no code fences.

Use the TAB character (\t) as the column delimiter in the output. Do NOT change the delimiter to commas or semicolons.
All delimiters must be actual ASCII TAB characters (U+0009). Do not output the literal characters "\t" or "\\t" anywhere in the file.

Each row must have exactly 7 columns in the order:
ID<TAB>Name<TAB>Reaction<TAB>pH<TAB>Rate<TAB>Comments<TAB>Reference.

If a row has fewer than 7 columns, append empty cells until there are 7.

If a line starts with tabs or has fewer than 3 fields (no ID/Name/Reaction), treat it as a continuation row belonging to the most recent complete entry. For continuation rows, always begin the line with exactly three literal TAB characters (ASCII U+0009) to represent the empty ID, Name, and Reaction columns. Only columns 4–7 are filled in these rows. Never output the two-character sequence "\t" or "\\t"; use real TAB characters.

LaTeX/mhchem rules

Every chemical formula or reaction must be wrapped in $\ce{...}$.

Reactions: wrap the entire reaction (reactants, arrows, products) in \ce{}. Keep arrows as written (->, <=>, \rightleftharpoons).

Standalone formulas: replace math-mode forms with \ce{}. Examples:

FeSO$_4$ → $\ce{FeSO4}$

O$_2$ → $\ce{O2}$

HClO$_4$ → $\ce{HClO4}$

ClOH$^-$ → $\ce{ClOH^-}$

H$^+$ → $\ce{H^+}$

Cl$^\cdot$ → $\ce{Cl^.}$

Cl$_2^{-\cdot}$ → $\ce{Cl2^{-.}}$

Radicals: use ^., e.g. $\ce{^.OH}$, $\ce{Cl^.}$.

Parenthetical formulas: wrap them, e.g. (Cl$_2^-$) → ($\ce{Cl2^-}$).

Kinetics notation: if k(...) contains chemistry, wrap only the inside. Examples:

k(Cl$^\cdot$ + Cl$^-$) → $k(\ce{Cl^. + Cl^-})$

rel. to k(^.OH + EtOH) → rel. to $k(\ce{^.OH + EtOH})$

Do not wrap standalone variables (k, K, K_eq) or pure numbers.

Decision rules

If it looks like chemistry (elements, charges, radicals, subscripts/superscripts), wrap it in \ce{}.

If it contains species and connectors (+, ->, <=>, etc.), wrap the entire reaction.

Prefer wrapping as chemistry rather than leaving raw math.

Do not change

Non-chemistry math (e.g. $4.3 \times 10^9$).

Units, plain text, or column order.

EXAMPLES

Input:
30 Chloride ion $\ce{^{\cdot}OH + Cl^- -> ClOH^-}$ $\sim$2 $4.3 \times 10^{9}$ p.r.; D.k. at 240 nm as well as p.b.k. at 340 nm (Cl$_2^-$); $k$ and $K$ also given for ClOH$^-$ + H$^+ \rightleftharpoons$ Cl$^\cdot$ + H$_2$O and Cl$^\cdot$ + Cl$^-$ $\rightleftharpoons$ Cl$2^{-\cdot}$; $K{eq} = 0.70$. 731039

Output:
30 Chloride ion $\ce{^.OH + Cl^- -> ClOH^-}$ $\sim$2 $4.3 \times 10^{9}$ p.r.; D.k. at 240 nm as well as p.b.k. at 340 nm ($\ce{Cl2^-}$); $k$ and $K$ also given for $\ce{ClOH^- + H^+ \rightleftharpoons Cl^. + H2O}$ and $\ce{Cl^. + Cl^- \rightleftharpoons Cl2^{-.}}$; $K_{eq} = 0.70$. 731039

Input:
50 Bis(ethylenediamine)dichlorocobalt(III) ion $\ce{^{\cdot}OH + Co(en)_2Cl_2^+ ->}$ $3.1 \times 10^8$ Average of 3 values.
4.4 $3.1 \times 10^8$ p.r.; C.k.; rel. to $k(\ce{^{\cdot}OH + SCN^-})$. 79A003
6.0 $3.3 \times 10^8$ p.r.; C.k.; rel. to $k(\ce{^{\cdot}OH + BzO^-})$. 79A003
2.9-4.5 $\sim 3.0 \times 10^8$ p.r.; P.b.k. (condy.) 79A003

Output:
50 Bis(ethylenediamine)dichlorocobalt(III) ion $\ce{^.OH + Co(en)2Cl2^+ ->}$ $3.1 \\times 10^8$ Average of 3 values.
			4.4	$3.1 \\times 10^8$	p.r.; C.k.; rel. to $k(\ce{^.OH + SCN^-})$.	79A003
			6.0	$3.3 \\times 10^8$	p.r.; C.k.; rel. to $k(\ce{^.OH + BzO^-})$.	79A003
			2.9-4.5	$\\sim 3.0 \\times 10^8$	p.r.; P.b.k. (condy.)	79A003

Input:
rel. to k(^.OH + EtOH) = 1.9 × 10^9

Output:
rel. to $k(\ce{^.OH + EtOH})$ = 1.9 × 10^9

Input:
p.b.k. at 340 nm (Cl$_2^-$); $k$ and $K$ also given for ClOH$^-$ + H$^+$

Output:
p.b.k. at 340 nm ($\ce{Cl2^-}$); $k$ and $K$ also given for $\ce{ClOH^- + H^+}$

Input:
complex formed from Co$^{2+}$ and 2,2'-bipyridine (bpy)

Output:
complex formed from $\ce{Co^{2+}}$ and 2,2'-bipyridine (bpy)

Input:
k(Cl$^\cdot$ + Cl$^-$) = 1.2 × 10^10

Output:
$k(\ce{Cl^. + Cl^-})$ = 1.2 × 10^10


Output: the corrected TSV file with only the chemistry cleaned into valid \ce{} form and strict tab/column alignment as shown.
"""


def _is_likely_chemical_token(inner: str) -> bool:
    """Heuristic: return True for plausible mhchem tokens or short reaction fragments.
    Single-token criteria (no spaces):
      - Start with '.', '(' or an uppercase letter.
      - Allowed chars: A-Za-z0-9 . + - ^ { } ( ) _ \
      - At least one uppercase letter.
    Phrase criteria (with spaces):
      - Contains a connector (+, ->, <-, <=>, \\rightleftharpoons, →, ↔).
      - No semicolons/colons/commas.
      - Only allowed chars plus spaces: A-Za-z0-9 . + - ^ { } ( ) _ < = > \\ and spaces.
      - At least one uppercase letter.
    """
    if not inner:
        return False
    if not re.search(r"[A-Z]", inner):
        return False
    # contains spaces => treat as potential reaction fragment
    if " " in inner:
        if any(c in inner for c in (";", ":", ",")):
            return False
        has_connector = (
            "+" in inner
            or "->" in inner
            or "<-" in inner
            or "<=>" in inner
            or "\\rightleftharpoons" in inner
            or "→" in inner
            or "↔" in inner
        )
        if not has_connector:
            return False
        # Allow backslash LaTeX macros and underscores
        if not re.fullmatch(r"[A-Za-z0-9\.\+\-\^\{\}\(\)_\\\s<=>→↔]+", inner):
            return False
        return True
    # single token
    if inner[0].islower():
        return False
    # Allow underscores and backslashes for mhchem-style tokens
    if not re.fullmatch(r"[A-Za-z0-9\.\+\-\^\{\}\(\)_\\]+", inner):
        return False
    return True


def _sanitize_ce_wrapping(tsv_text: str, protected_reaction_col: int = 2) -> str:
    """Unwrap incorrect $\\ce{...}$ across all columns except the Reaction column.
    We only unwrap clearly non-chemical phrases accidentally wrapped by the model.
    """
    lines = tsv_text.splitlines()
    out_lines: list[str] = []
    for line in lines:
        if not line:
            out_lines.append(line)
            continue
        cols = line.split("\t")
        for idx in range(len(cols)):
            if idx == protected_reaction_col:
                continue
            s = cols[idx]
            i = 0
            new_s_parts: list[str] = []
            while i < len(s):
                if s.startswith("$\\ce{", i):
                    j = i + len("$\\ce{")
                    depth = 1
                    while j < len(s) and depth > 0:
                        ch = s[j]
                        if ch == "{":
                            depth += 1
                        elif ch == "}":
                            depth -= 1
                        j += 1
                    # j is at first char after the matching '}' or end
                    # Expect a trailing '$' after the closing brace
                    k = j
                    if k < len(s) and s[k] == "$":
                        end_idx = k + 1
                    else:
                        end_idx = j
                    inner = s[i + len("$\\ce{") : j - 1]
                    if _is_likely_chemical_token(inner):
                        new_s_parts.append(s[i:end_idx])
                    else:
                        # unwrap
                        new_s_parts.append(inner)
                    i = end_idx
                else:
                    new_s_parts.append(s[i])
                    i += 1
            cols[idx] = "".join(new_s_parts)
        out_lines.append("\t".join(cols))
    return "\n".join(out_lines)


def _normalize_math_mode_chemistry(tsv_text: str) -> str:
    """
    Convert patterns like FeSO$_4$, O$_2$, and Cl$_2^{-\\cdot}$ into mhchem form inside $\\ce{...}$.
    Example: "Cl$_2^{-\\cdot}$" -> "$\\ce{Cl_2^{-\\cdot}}$"
    This is applied post-model to ensure consistency even if the model misses it.
    """
    # Regex: Base chemical token (starts with uppercase), followed by a math block that
    # includes at least one of '_' or '^' (sub/superscripts), like $_4$, $_2^{...}$, etc.
    pattern = re.compile(r"\b([A-Z][A-Za-z0-9()]*?)\$([^$]*?[\_^][^$]*?)\$")

    def repl(m: re.Match[str]) -> str:
        base = m.group(1)
        math = m.group(2)
        # Normalize by removing extraneous spaces inside the math content
        math_norm = re.sub(r"\s+", "", math)
        ce_inner = f"{base}{math_norm}"
        # Guard: if it already looks like a \ce{...}, skip wrapping
        if ce_inner.startswith("\\ce{") or ce_inner.startswith("$\\ce{"):
            return m.group(0)
        # Ensure it looks like a plausible chemical token before wrapping
        if not _is_likely_chemical_token(base):
            return m.group(0)
        return f"$\\ce{{{ce_inner}}}$"

    # Apply repeatedly until stable in case of nested/adjacent patterns
    prev = None
    out = tsv_text
    for _ in range(3):
        prev = out
        out = pattern.sub(repl, out)
        if out == prev:
            break
    return out


def extract_csv_text(text: str) -> str:
    """Extract plain CSV content from a model response.

    Heuristics:
      - Prefer fenced blocks labeled as csv first.
      - Then any generic fenced block.
      - Otherwise, return the raw text.
    """
    if not text:
        return ""

    # Prefer ```csv ... ```
    m = re.search(r"```csv\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip("\r\n")

    # Fallback to the first fenced block
    m = re.search(r"```\s*(.*?)```", text, flags=re.DOTALL)
    if m:
        return m.group(1).strip("\r\n")

    # Otherwise, hope the model returned plain CSV
    return text.strip()


def correct_csv_with_openai(
    csv_text: str,
    *,
    model: str = "gpt-4.1-mini",
    temperature: float = 0.0,
    system_prompt: str | None = None,
    max_retries: int = 3,
) -> str:
    """Send CSV text to OpenAI to correct it and return the corrected CSV text.

    Retries a few times on transient failures.
    """
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Please set it in your environment (or .env)."
        )

    client = OpenAI()
    sys_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

    messages = [
        {"role": "system", "content": sys_prompt},
        {
            "role": "user",
            "content": (
                "Please correct the following tab-delimited (\\t) file, keep tabs as the delimiter, and return ONLY the corrected contents:\n\n"
                f"{csv_text}"
            ),
        },
    ]

    last_err: BaseException | None = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
            )
            out = resp.choices[0].message.content or ""
            return extract_csv_text(out)
        except Exception as e:  # Broad catch to avoid SDK-version-specific imports
            last_err = e
            logging.warning("OpenAI request attempt %d/%d failed: %s", attempt, max_retries, e)
            if attempt < max_retries:
                # Exponential-ish backoff
                time.sleep(1.5 * attempt)
            else:
                raise RuntimeError(
                    f"OpenAI request failed after {max_retries} attempts: {e}"
                ) from e

    # Should never reach here
    raise RuntimeError(f"Unexpected failure: {last_err}")


def _parse_marked_blocks(text: str) -> list[tuple[str, str]]:
    """Parse output blocks wrapped in markers into (filename, content) pairs.

    Expected format:
      <<<BEGIN FILE: filename>>>
      ... corrected TSV ...
      <<<END FILE>>>
    Returns a list preserving order.
    """
    lines = text.splitlines()
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("<<<BEGIN FILE:") and line.endswith(">>>"):
            # Extract filename between the colon and closing >>>
            header = line
            try:
                name = header[len("<<<BEGIN FILE:") : -3].strip()
            except Exception:
                name = ""
            i += 1
            buf: list[str] = []
            while i < len(lines):
                if lines[i].strip() == "<<<END FILE>>>":
                    break
                buf.append(lines[i])
                i += 1
            # i is at END or end of file
            content = "\n".join(buf).strip("\r\n")
            out.append((name, content))
            # Skip END marker if present
            if i < len(lines) and lines[i].strip() == "<<<END FILE>>>":
                i += 1
        else:
            i += 1
    return out


def correct_multi_csv_with_openai(
    files: list[tuple[str, str]],
    *,
    model: str = "gpt-4.1-mini",
    temperature: float = 0.0,
    system_prompt: str | None = None,
    max_retries: int = 3,
) -> dict[str, str]:
    """Send multiple CSV texts to OpenAI in one request; return mapping filename -> corrected text.

    'files' is a list of (filename, csv_text) pairs. The response must contain one block per input
    wrapped by markers that we parse and map back by filename.
    """
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Please set it in your environment (or .env)."
        )

    client = OpenAI()
    sys_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

    preface = (
        "You will receive multiple TSV files, each wrapped with markers. For EACH input block, return ONLY the corrected TSV contents wrapped with the SAME markers and SAME filename.\n"
        "- Use TAB (\\t) as delimiter.\n"
        "- Preserve input order.\n"
        "- Do NOT add code fences or commentary.\n\n"
        "Input blocks follow this format exactly:\n"
        "<<<BEGIN FILE: filename>>>\n"
        "...contents...\n"
        "<<<END FILE>>>\n\n"
        "Return one corresponding output block per input, using the same markers and filename."
    )

    blocks: list[str] = []
    for name, csv_text in files:
        blocks.append(f"<<<BEGIN FILE: {name}>>>\n{csv_text}\n<<<END FILE>>>")
    user_content = preface + "\n\n" + "\n\n".join(blocks)

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_content},
    ]

    last_err: BaseException | None = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
            )
            out = resp.choices[0].message.content or ""
            parsed = _parse_marked_blocks(out)
            result: dict[str, str] = {}
            for name, content in parsed:
                result[name] = content
            return result
        except Exception as e:
            last_err = e
            logging.warning(
                "OpenAI multi-file request attempt %d/%d failed: %s", attempt, max_retries, e
            )
            if attempt < max_retries:
                time.sleep(1.5 * attempt)
            else:
                raise RuntimeError(
                    f"OpenAI multi-file request failed after {max_retries} attempts: {e}"
                ) from e

    raise RuntimeError(f"Unexpected failure (multi): {last_err}")


def process_folder(
    input_folder: Path,
    *,
    glob_pattern: str = "*.csv",
    output_suffix: str = "_ai",
    model: str = "gpt-4.1-mini",
    overwrite: bool = False,
    dry_run: bool = False,
    system_prompt_file: Path | None = None,
    workers: int = 5,
    submit_delay: float = 0.05,
    batch_size: int = 1,
    parallel: bool = True,
) -> None:
    if not input_folder.exists() or not input_folder.is_dir():
        raise FileNotFoundError(f"Input folder not found: {input_folder}")

    output_folder = input_folder.with_name(input_folder.name + output_suffix)
    output_folder.mkdir(parents=True, exist_ok=True)

    # Manifest of scanned files to support resume: only process files from the snapshot
    manifest_path = output_folder / "_scan_manifest.txt"

    if manifest_path.exists():
        names = [
            ln.strip()
            for ln in manifest_path.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        files = [input_folder / n for n in names]
        files = [p for p in files if p.is_file()]
        logging.info(
            "Using existing manifest at %s listing %d file(s). New files (if any) are ignored.",
            manifest_path,
            len(files),
        )
    else:
        files = sorted([p for p in input_folder.glob(glob_pattern) if p.is_file()])
        names = [p.name for p in files]
        manifest_path.write_text("\n".join(names) + "\n", encoding="utf-8")
        logging.info("Created manifest at %s with %d file(s).", manifest_path, len(files))

    if not files:
        logging.info("No files matched pattern '%s' under %s", glob_pattern, input_folder)
        return

    system_prompt: str | None = None
    if system_prompt_file is not None:
        if not system_prompt_file.exists():
            raise FileNotFoundError(f"System prompt file not found: {system_prompt_file}")
        system_prompt = system_prompt_file.read_text(encoding="utf-8")

    total = len(files)
    logging.info(
        "[START] Processing %d file(s) from %s -> %s | model=%s | workers=%d | batch=%d",
        total,
        input_folder,
        output_folder,
        model,
        workers,
        batch_size,
    )

    processed = 0
    skipped = 0
    failed = 0
    completed = 0

    # Pre-skip files that already have outputs when not overwriting
    to_process: list[tuple[int, Path, Path]] = []
    for idx, src in enumerate(files, 1):
        dst = output_folder / src.name
        if dst.exists() and not overwrite:
            completed += 1
            skipped += 1
            pct = (completed * 100.0) / total
            logging.info(
                "[%3d/%3d %5.1f%%] SKIP (exists) %s -> %s",
                idx,
                total,
                pct,
                src.name,
                dst.name,
            )
        else:
            to_process.append((idx, src, dst))

    if not to_process:
        logging.info(
            "[DONE] processed=%d, skipped=%d, failed=%d, total=%d -> %s",
            processed,
            skipped,
            failed,
            total,
            output_folder,
        )
        return

    def _worker(idx: int, src: Path, dst: Path):
        try:
            try:
                raw = src.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                raw = src.read_text(encoding="utf-8-sig")
            corrected = correct_csv_with_openai(
                raw,
                model=model,
                system_prompt=system_prompt,
            )
            corrected = _sanitize_ce_wrapping(corrected).strip() + "\n"
            if dry_run:
                return ("dry", idx, src.name, str(dst))
            else:
                dst.write_text(corrected, encoding="utf-8")
                return ("ok", idx, src.name, str(dst))
        except Exception as e:
            return ("error", idx, src.name, str(dst), str(e))

    def _batch_worker(batch: list[tuple[int, Path, Path]]):
        """Process a batch of files in a single model request. Returns a list of status tuples."""
        try:
            # Read inputs
            names_and_texts: list[tuple[str, str]] = []
            for _, src, _ in batch:
                try:
                    raw = src.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    raw = src.read_text(encoding="utf-8-sig")
                names_and_texts.append((src.name, raw))

            # Call multi-file correction
            name_to_corrected = correct_multi_csv_with_openai(
                names_and_texts,
                model=model,
                system_prompt=system_prompt,
            )

            statuses: list[tuple] = []
            for idx, src, dst in batch:
                if src.name not in name_to_corrected:
                    statuses.append(
                        ("error", idx, src.name, str(dst), "missing output for file in batch")
                    )
                    continue
                corrected = name_to_corrected[src.name]
                corrected = _sanitize_ce_wrapping(corrected).strip() + "\n"
                if dry_run:
                    statuses.append(("dry", idx, src.name, str(dst)))
                else:
                    dst.write_text(corrected, encoding="utf-8")
                    statuses.append(("ok", idx, src.name, str(dst)))
            return statuses
        except Exception as e:
            # Mark all files in this batch as failed
            return [("error", idx, src.name, str(dst), str(e)) for (idx, src, dst) in batch]

    # Execute work (sequential or parallel) with graceful Ctrl-C handling
    if batch_size <= 1:
        if not parallel or workers <= 1:
            logging.info("Running sequentially (no parallel workers).")
            for idx, src, dst in to_process:
                try:
                    status_tuple = _worker(idx, src, dst)
                except KeyboardInterrupt:
                    logging.warning("Interrupted by user (Ctrl-C). Stopping after current file...")
                    break
                status = status_tuple[0]
                if status == "ok":
                    processed += 1
                    completed += 1
                    _, idx, srcname, dstpath = status_tuple
                    pct = (completed * 100.0) / total
                    logging.info(
                        "[%3d/%3d %5.1f%%] Wrote %s -> %s",
                        idx,
                        total,
                        pct,
                        srcname,
                        Path(dstpath).name,
                    )
                elif status == "dry":
                    processed += 1
                    completed += 1
                    _, idx, srcname, dstpath = status_tuple
                    pct = (completed * 100.0) / total
                    logging.info(
                        "[%3d/%3d %5.1f%%] DRY-RUN (no write): %s",
                        idx,
                        total,
                        pct,
                        Path(dstpath).name,
                    )
                elif status == "error":
                    completed += 1
                    failed += 1
                    _, idx, srcname, dstpath, err = status_tuple
                    pct = (completed * 100.0) / total
                    logging.error(
                        "[%3d/%3d %5.1f%%] ERROR processing %s -> %s: %s",
                        idx,
                        total,
                        pct,
                        srcname,
                        Path(dstpath).name,
                        err,
                    )
        else:
            futures: list[cf.Future] = []
            interrupted = False
            ex = cf.ThreadPoolExecutor(max_workers=workers)
            try:
                for j, (idx, src, dst) in enumerate(to_process, 1):
                    if submit_delay and j > 1:
                        time.sleep(submit_delay)
                    futures.append(ex.submit(_worker, idx, src, dst))

                for fut in cf.as_completed(futures):
                    try:
                        status_tuple = fut.result()
                    except Exception as e:
                        status_tuple = ("error", 0, "", "", str(e))
                    status = status_tuple[0]
                    if status == "ok":
                        processed += 1
                        completed += 1
                        _, idx, srcname, dstpath = status_tuple
                        pct = (completed * 100.0) / total
                        logging.info(
                            "[%3d/%3d %5.1f%%] Wrote %s -> %s",
                            idx,
                            total,
                            pct,
                            srcname,
                            Path(dstpath).name,
                        )
                    elif status == "dry":
                        processed += 1
                        completed += 1
                        _, idx, srcname, dstpath = status_tuple
                        pct = (completed * 100.0) / total
                        logging.info(
                            "[%3d/%3d %5.1f%%] DRY-RUN (no write): %s",
                            idx,
                            total,
                            pct,
                            Path(dstpath).name,
                        )
                    elif status == "error":
                        completed += 1
                        failed += 1
                        _, idx, srcname, dstpath, err = status_tuple
                        pct = (completed * 100.0) / total
                        logging.error(
                            "[%3d/%3d %5.1f%%] ERROR processing %s -> %s: %s",
                            idx,
                            total,
                            pct,
                            srcname,
                            Path(dstpath).name,
                            err,
                        )
            except KeyboardInterrupt:
                interrupted = True
                logging.warning("Interrupted by user (Ctrl-C). Cancelling pending tasks...")
                for f in futures:
                    f.cancel()
                try:
                    ex.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass
                raise
            finally:
                if not interrupted:
                    try:
                        ex.shutdown(wait=True)
                    except Exception:
                        pass
    else:
        # Batch mode
        # Group items into batches
        batches: list[list[tuple[int, Path, Path]]] = []
        for k in range(0, len(to_process), batch_size):
            batches.append(to_process[k : k + batch_size])

        if not parallel or workers <= 1:
            logging.info("Running in batches sequentially (batch size=%d).", batch_size)
            for j, batch in enumerate(batches, 1):
                if submit_delay and j > 1:
                    time.sleep(submit_delay)
                try:
                    status_list = _batch_worker(batch)
                except KeyboardInterrupt:
                    logging.warning("Interrupted by user (Ctrl-C). Stopping after current batch...")
                    break
                for status_tuple in status_list:
                    status = status_tuple[0]
                    if status == "ok":
                        processed += 1
                        completed += 1
                        _, idx, srcname, dstpath = status_tuple
                        pct = (completed * 100.0) / total
                        logging.info(
                            "[%3d/%3d %5.1f%%] Wrote %s -> %s",
                            idx,
                            total,
                            pct,
                            srcname,
                            Path(dstpath).name,
                        )
                    elif status == "dry":
                        processed += 1
                        completed += 1
                        _, idx, srcname, dstpath = status_tuple
                        pct = (completed * 100.0) / total
                        logging.info(
                            "[%3d/%3d %5.1f%%] DRY-RUN (no write): %s",
                            idx,
                            total,
                            pct,
                            Path(dstpath).name,
                        )
                    elif status == "error":
                        completed += 1
                        failed += 1
                        _, idx, srcname, dstpath, err = status_tuple
                        pct = (completed * 100.0) / total
                        logging.error(
                            "[%3d/%3d %5.1f%%] ERROR processing %s -> %s: %s",
                            idx,
                            total,
                            pct,
                            srcname,
                            Path(dstpath).name,
                            err,
                        )
        else:
            futures: list[cf.Future] = []
            interrupted = False
            ex = cf.ThreadPoolExecutor(max_workers=workers)
            try:
                for j, batch in enumerate(batches, 1):
                    if submit_delay and j > 1:
                        time.sleep(submit_delay)
                    futures.append(ex.submit(_batch_worker, batch))

                for fut in cf.as_completed(futures):
                    try:
                        status_list = fut.result()
                    except Exception as e:
                        # If batch failed catastrophically, mark unknown files as errors
                        status_list = [("error", 0, "", "", str(e))]
                    for status_tuple in status_list:
                        status = status_tuple[0]
                        if status == "ok":
                            processed += 1
                            completed += 1
                            _, idx, srcname, dstpath = status_tuple
                            pct = (completed * 100.0) / total
                            logging.info(
                                "[%3d/%3d %5.1f%%] Wrote %s -> %s",
                                idx,
                                total,
                                pct,
                                srcname,
                                Path(dstpath).name,
                            )
                        elif status == "dry":
                            processed += 1
                            completed += 1
                            _, idx, srcname, dstpath = status_tuple
                            pct = (completed * 100.0) / total
                            logging.info(
                                "[%3d/%3d %5.1f%%] DRY-RUN (no write): %s",
                                idx,
                                total,
                                pct,
                                Path(dstpath).name,
                            )
                        elif status == "error":
                            completed += 1
                            failed += 1
                            _, idx, srcname, dstpath, err = status_tuple
                            pct = (completed * 100.0) / total
                            logging.error(
                                "[%3d/%3d %5.1f%%] ERROR processing %s -> %s: %s",
                                idx,
                                total,
                                pct,
                                srcname,
                                Path(dstpath).name,
                                err,
                            )
            except KeyboardInterrupt:
                interrupted = True
                logging.warning("Interrupted by user (Ctrl-C). Cancelling pending batches...")
                for f in futures:
                    f.cancel()
                try:
                    ex.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass
                raise
            finally:
                if not interrupted:
                    try:
                        ex.shutdown(wait=True)
                    except Exception:
                        pass

    logging.info(
        "[DONE] processed=%d, skipped=%d, failed=%d, total=%d -> %s",
        processed,
        skipped,
        failed,
        total,
        output_folder,
    )


def process_single_file(
    input_file: Path,
    *,
    output_folder: Path | None = None,
    model: str = "gpt-4.1-mini",
    overwrite: bool = False,
    dry_run: bool = False,
    system_prompt: str | None = None,
) -> bool:
    """Process a single CSV file with OpenAI.

    Args:
        input_file: Path to the input CSV file
        output_folder: Path to the output folder (if None, uses input_file.parent/"csv_ai")
        model: OpenAI model to use
        overwrite: Whether to overwrite existing output files
        dry_run: Whether to just simulate the run without writing
        system_prompt: Optional custom system prompt

    Returns:
        True if successful, False otherwise
    """
    if not input_file.exists() or not input_file.is_file():
        print(f"[ERROR] Input file not found: {input_file}")
        return False

    # Determine output folder and output file path
    if output_folder is None:
        output_folder = input_file.parent.with_name(input_file.parent.name + "_ai")

    output_folder.mkdir(parents=True, exist_ok=True)
    output_file = output_folder / input_file.name

    # Check if output exists
    if output_file.exists() and not overwrite:
        print(f"[SKIP] Output file already exists: {output_file}")
        return True

    # Process the file
    try:
        print(f"Processing: {input_file.name}")

        try:
            raw = input_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw = input_file.read_text(encoding="utf-8-sig")

        corrected = correct_csv_with_openai(
            raw,
            model=model,
            system_prompt=system_prompt,
        )
        corrected = _sanitize_ce_wrapping(corrected).strip() + "\n"

        if dry_run:
            print(f"[DRY-RUN] Would write corrected content to: {output_file}")
            return True
        else:
            output_file.write_text(corrected, encoding="utf-8")
            print(f"[SUCCESS] Wrote corrected content to: {output_file}")
            return True

    except Exception as e:
        print(f"[ERROR] Failed to process {input_file.name}: {e}")
        return False


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=("Correct CSV files in a folder or a single file using OpenAI.")
    )
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--input-folder",
        "-i",
        type=str,
        help="Path to the folder containing CSV files.",
    )
    group.add_argument(
        "--file",
        "-f",
        type=str,
        help="Path to a single CSV file to process.",
    )
    p.add_argument(
        "--glob",
        type=str,
        default="*.csv",
        help="Glob pattern to select input files (default: *.csv).",
    )
    p.add_argument(
        "--model",
        type=str,
        default="gpt-4.1-mini",
        help="OpenAI model to use (default: gpt-4.1-mini).",
    )
    p.add_argument(
        "--output-suffix",
        type=str,
        default="_ai",
        help="Suffix appended to input folder name to create output folder (default: _ai).",
    )
    p.add_argument(
        "--output-folder",
        "-o",
        type=str,
        help="Optional explicit output folder path (overrides --output-suffix).",
    )
    p.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing outputs if present.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without writing files (prints progress only).",
    )
    p.add_argument(
        "--system-prompt-file",
        type=str,
        help=("Optional path to a file containing a custom system prompt to guide corrections."),
    )
    p.add_argument(
        "--workers",
        "-j",
        type=int,
        default=5,
        help="Number of parallel workers (default: 5).",
    )
    p.add_argument(
        "--submit-delay",
        type=float,
        default=0.05,
        help="Delay in seconds between queueing tasks (default: 0.05).",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help=(
            "Number of input files to send in a single model request (default: 1). "
            "Each corrected output is still written to its own file."
        ),
    )
    p.add_argument(
        "--sequential",
        action="store_true",
        help="Process files sequentially (disables parallelism regardless of --workers).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    try:
        # Load system prompt if specified
        system_prompt = None
        if args.system_prompt_file:
            system_prompt_file = Path(args.system_prompt_file).resolve()
            if not system_prompt_file.exists():
                raise FileNotFoundError(f"System prompt file not found: {system_prompt_file}")
            system_prompt = system_prompt_file.read_text(encoding="utf-8")

        # Process a single file if specified
        if args.file:
            input_file = Path(args.file).resolve()

            # Determine output folder
            if args.output_folder:
                output_folder = Path(args.output_folder).resolve()
            else:
                # Default to parent_folder + _ai
                output_folder = input_file.parent.with_name(
                    input_file.parent.name + args.output_suffix
                )

            success = process_single_file(
                input_file,
                output_folder=output_folder,
                model=args.model,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
                system_prompt=system_prompt,
            )
            return 0 if success else 1
        else:  # Process folder
            input_folder = Path(args.input_folder).resolve()
            process_folder(
                input_folder,
                glob_pattern=args.glob,
                output_suffix=args.output_suffix,
                model=args.model,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
                system_prompt_file=Path(args.system_prompt_file).resolve()
                if args.system_prompt_file
                else None,
                workers=args.workers,
                submit_delay=args.submit_delay,
                batch_size=args.batch_size,
                parallel=(not args.sequential),
            )
            return 0
    except KeyboardInterrupt:
        print("[INFO] Cancelled by user (Ctrl-C)", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
