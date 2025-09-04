#!/usr/bin/env python3
"""
CSV AI Corrector - First 10 Reactions with Stop Option

Process only the first 10 CSV files in a folder with OpenAI (gpt-4.1-mini) and
write corrected CSVs into a sibling folder named <input_folder>_ai, retaining
original filenames. Includes ability to stop execution by pressing 'q'.

Environment:
  - OPENAI_API_KEY must be set (can be provided via .env if python-dotenv is installed)

Usage:
  python csv_ai_corrector_first_10.py
"""

from __future__ import annotations

import msvcrt
import os
import re
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


DEFAULT_SYSTEM_PROMPT = """
You are an expert data cleaner. You will receive the full contents of a TSV (tab-delimited) text file representing 7-column rows of chemistry data. This file will be used later to generate LaTeX, so all LaTeX/mhchem content must remain valid.

Output/format constraints:

Return ONLY the corrected file contents. No commentary, no code fences.

Use the TAB character (\\t) as the column delimiter in the output. Do NOT change the delimiter to commas or semicolons.

Each row must have exactly 7 columns in the order:
ID<TAB>Name<TAB>Reaction<TAB>pH<TAB>Rate<TAB>Comments<TAB>Reference.

If a row has fewer than 7 columns, append empty cells until there are 7.

Continuation row handling - CRITICAL RULES:

1. If a line starts with tabs (empty first columns) OR has fewer than 3 non-empty fields at the start, it's a continuation row for the previous reaction.

2. For continuation rows: Keep columns 1, 2, 3 EMPTY (just tabs), then fill columns 4, 5, 6, 7 with new data.

3. NEVER remove data from continuation rows - if you see values like pH, Rate, Comments, Reference in continuation rows, preserve them ALL.

4. Example structure:
   Row 1 (main): ID<TAB>Name<TAB>Reaction<TAB>pH<TAB>Rate<TAB>Comments<TAB>Reference
   Row 2 (cont): <TAB><TAB><TAB>pH<TAB>Rate<TAB>Comments<TAB>Reference
   Row 3 (cont): <TAB><TAB><TAB>pH<TAB>Rate<TAB>Comments<TAB>Reference

5. Each continuation row must still have exactly 7 columns - just the first 3 are empty.

6. DO NOT merge continuation row data into the main row - keep them as separate lines.

7. DO NOT duplicate reference numbers - each continuation row should have its own reference if provided.

8. SPECIFIC EXAMPLE of correct continuation row handling:
   INPUT:
   "1\tSilver(I) Ion\t$\ce{^{\cdot}OH + Ag^+ -> AgOH^+}$\t\t$1.4 \times 10^{10}$\tAverage of 2 values.\t
   \t\t\t\t$1.2 \times 10^{10}$\tp.r.; P.b.k. at 320 nm.\t83R031
   \t\t\t7\t$1.5 \times 10^{10}$\tp.r.; P.b.k. at 313 and 365 nm.\t680436"

   OUTPUT:
   "1\tSilver(I) Ion\t$\ce{^.OH + Ag^+ -> AgOH^+}$\t\t$1.4 \times 10^{10}$\tAverage of 2 values.\t
   \t\t\t\t$1.2 \times 10^{10}$\tp.r.; P.b.k. at 320 nm.\t83R031
   \t\t\t7\t$1.5 \times 10^{10}$\tp.r.; P.b.k. at 313 and 365 nm.\t680436"

   Notice: pH values (including "7"), rates, comments, and references are all preserved exactly.

Delimiter normalization: If the input line uses non-TAB separators between fields (e.g., the Unicode arrow →, ASCII |, or runs of multiple spaces) and the line clearly contains exactly seven fields in the schema, treat those separators as column delimiters and convert them to single TABs. Never alter arrows that appear inside LaTeX or \\ce{...} chemistry.

Never merge multiple logical rows into one. Each line corresponds to exactly one output row.

LaTeX/mhchem preservation:

Preserve LaTeX blocks and commands exactly: \\ce{...}, \\text{...}, ^{...}, {...}, $...$, \\(...\\), \\[...\\].

Do not alter reaction arrows (->, <-, <=>).

Do not escape backslashes, remove braces, or convert to Unicode.

Preserve radical/charge notation as-is (e.g., .OH, ^{.}OH, ^-, ^{2-}, etc.).

Chemistry token normalization:

If a chemical formula appears in math mode using $_..$ (e.g., FeSO$_4$, O$_2$, HClO$_4$), normalize it to mhchem style inside \\ce{...}:

FeSO$_4$ → $\\ce{FeSO4}$

O$_2$ → $\\ce{O2}$

HClO$_4$ → $\\ce{HClO4}$

Reaction rate constant formatting:

When you see reaction rate constants like "k(^.OH + EtOH)" or "k(OH + H2O2)", format them as: $k(\\ce{^.OH + EtOH})$ or $k(\\ce{OH + H2O2})$.

The pattern is: k(...chemistry...) → $k(\\ce{...chemistry...})$

This applies to any kinetic notation where k, k_obs, k_rel, etc. are followed by parentheses containing chemical species and reactions.

Examples:
- "rel. to k(^.OH + EtOH)" → "rel. to $k(\\ce{^.OH + EtOH})$"
- "k(H + O2)" → "$k(\\ce{H + O2})$"
- "k_obs(NO3- + OH)" → "$k_{obs}(\\ce{NO3- + OH})$"

Only wrap chemistry tokens in $...$ or \\ce{...} if the input already used them OR if they fit the reaction rate constant pattern above. Do NOT introduce new wrapping outside of these specific cases.

Keep prose unchanged (e.g., "Average of 2 values.", "at 340 nm").

Do not wrap entire sentences.

Numeric/units:

Preserve scientific notation as written (e.g., 4.3 × 10^8).

Do not alter units or formatting.

Whitespace/quoting:

Remove stray newlines inside a cell.

Collapse repeated spaces to one, except inside LaTeX/math.

Quote any field containing a tab or double quotes using standard CSV quoting (double quotes; embedded quotes doubled).
"""


def check_for_stop():
    """Check if user wants to stop execution by pressing 'q' key"""
    if msvcrt.kbhit():
        key = msvcrt.getch().decode("utf-8").lower()
        if key == "q":
            print("\n>>> User requested stop. Exiting...")
            return True
    return False


def _is_likely_chemical_token(inner: str) -> bool:
    """Heuristic: return True for plausible mhchem tokens or short reaction fragments."""
    if not inner:
        return False
    if not re.search(r"[A-Z]", inner):
        return False
    # contains spaces => treat as potential reaction fragment
    if " " in inner:
        if any(c in inner for c in (";", ":", ",")):
            return False
        if not ("+" in inner or "->" in inner or "<-" in inner or "<=>" in inner):
            return False
        if not re.fullmatch(r"[A-Za-z0-9\.\+\-\^\{\}\(\)\s<=>]+", inner):
            return False
        return True
    # single token
    if inner[0].islower():
        return False
    if not re.fullmatch(r"[A-Za-z0-9\.\+\-\^\{\}\(\)]+", inner):
        return False
    return True


def _sanitize_ce_wrapping(tsv_text: str, protected_reaction_col: int = 2) -> str:
    """Unwrap incorrect $\\ce{...}$ across all columns except the Reaction column."""
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


def extract_csv_text(text: str) -> str:
    """Extract plain CSV content from a model response."""
    if not text:
        return ""

    # Prefer ```csv ... ```
    m = re.search(r"```csv\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if m:
        content = m.group(1).strip("\r\n")
    elif re.search(r"```\s*(.*?)```", text, flags=re.DOTALL):
        # Fallback to the first fenced block
        m = re.search(r"```\s*(.*?)```", text, flags=re.DOTALL)
        content = m.group(1).strip("\r\n")
    else:
        # Otherwise, hope the model returned plain CSV
        content = text.strip()

    # Fix literal \n in the content to actual newlines
    content = content.replace("\\n", "\n")

    return content


def correct_csv_with_openai(
    csv_text: str,
    *,
    model: str = "gpt-4.1-mini",
    temperature: float = 0.0,
    system_prompt: str | None = None,
    max_retries: int = 3,
) -> str:
    """Send CSV text to OpenAI to correct it and return the corrected CSV text."""
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
                "Please correct the following tab-delimited (\\\\t) file, keep tabs as the delimiter, and return ONLY the corrected contents:\\n\\n"
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
            print(f"OpenAI request attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                # Exponential-ish backoff
                time.sleep(1.5 * attempt)
            else:
                raise RuntimeError(
                    f"OpenAI request failed after {max_retries} attempts: {e}"
                ) from e

    # Should never reach here
    raise RuntimeError(f"Unexpected failure: {last_err}")


def process_single_csv_with_openai(
    src_path: Path,
    dst_path: Path,
    *,
    model: str = "gpt-4.1-mini",
    system_prompt: str | None = None,
) -> bool:
    """Process a single CSV file with OpenAI and save the result. Returns True if user requested stop."""
    try:
        # Check for stop before processing
        if check_for_stop():
            return True

        # Read the source file
        try:
            raw = src_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw = src_path.read_text(encoding="utf-8-sig")

        print("  Sending to OpenAI for correction...")

        # Check for stop during processing
        if check_for_stop():
            return True

        # Process with OpenAI
        corrected = correct_csv_with_openai(
            raw,
            model=model,
            system_prompt=system_prompt,
        )

        # Check for stop after OpenAI response
        if check_for_stop():
            return True

        # Sanitize and save
        corrected = _sanitize_ce_wrapping(corrected).strip() + "\n"
        dst_path.write_text(corrected, encoding="utf-8")

        print(f"  ✓ Corrected and saved to: {dst_path.name}")
        return False

    except Exception as e:
        print(f"  ✗ Error processing {src_path.name}: {e}")
        return False


def process_first_10_reactions_with_openai():
    """Process only the first 10 CSV files with OpenAI correction and user stop capability"""
    print(
        "Starting OpenAI correction of first 10 reactions from table8_exported/sub_tables_images/csv"
    )
    print("Press 'q' at any time to stop execution")
    print("-" * 80)

    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY is not set!")
        print("Please set your OpenAI API key in the environment.")
        return

    # Input and output directories
    input_folder = Path("E:/ICP_notebooks/Buxton/table8_exported/sub_tables_images/csv")
    output_folder = Path("E:/ICP_notebooks/Buxton/table8_exported/sub_tables_images/csv_ai")

    if not input_folder.exists():
        print(f"Error: Input directory {input_folder} does not exist!")
        return

    # Create output directory
    output_folder.mkdir(parents=True, exist_ok=True)

    # Get all CSV files and sort them
    csv_files = sorted(list(input_folder.glob("*.csv")))

    if not csv_files:
        print("No CSV files found in the input directory!")
        return

    print(f"Found {len(csv_files)} CSV files. Processing first 10 with OpenAI...")

    # Process only first 10 files
    processed = 0
    for i, csv_path in enumerate(csv_files[:10], 1):
        print(f"\\nProcessing [{i}/10]: {csv_path.name}")

        # Check for stop before processing each file
        if check_for_stop():
            print("\\n>>> User requested stop. Exiting...")
            break

        # Output path
        dst_path = output_folder / csv_path.name

        # Skip if already exists (unless user wants to overwrite)
        if dst_path.exists():
            print(f"  → Already exists: {dst_path.name} (skipping)")
            processed += 1
            continue

        try:
            stopped = process_single_csv_with_openai(
                csv_path,
                dst_path,
                model="gpt-4-1106-preview",  # Use gpt-4 turbo for better results
                system_prompt=DEFAULT_SYSTEM_PROMPT,
            )

            if stopped:
                break

            processed += 1

            # Small delay to allow user to press 'q' and to respect API rate limits
            time.sleep(0.5)

        except Exception as e:
            print(f"  ✗ Error processing {csv_path.name}: {e}")
            continue

    print("\\n" + "=" * 80)
    print("OpenAI correction completed!")
    print(f"Files processed: {processed}/10")
    print(f"Output directory: {output_folder}")
    print(f"Remaining files in source: {len(csv_files) - 10} (not processed)")


if __name__ == "__main__":
    process_first_10_reactions_with_openai()
