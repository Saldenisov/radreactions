import csv
import subprocess
from pathlib import Path
import re
from tsv_utils import fix_radical_dots


def _strip_math_delims(s: str) -> str:
    """Remove surrounding inline/block math delimiters if present.
    Examples: $...$, \(...\), \[...\]
    """
    s = s.strip()
    if len(s) >= 2 and s.startswith("$") and s.endswith("$"):
        return s[1:-1].strip()
    if s.startswith(r"\(") and s.endswith(r"\)"):
        return s[2:-2].strip()
    if s.startswith(r"\[") and s.endswith(r"\]"):
        return s[2:-2].strip()
    return s


def _normalize_reaction(s: str) -> str:
    # Use the simplified normalization the user suggested
    s = s.replace("→", "->").replace("⟶", "->").replace("⟹", "=>")
    s = s.replace("·", r"\cdot ")
    s = fix_radical_dots(s)
    s = re.sub(r"\^\s*(\\dot\{[A-Za-z]\})", r"\1", s)
    s = re.sub(r"\^\{\\cdot\s*([+-])\}", r"^{\\cdot\1}", s)
    s = re.sub(r"\^\{\s*([+-])\s*\}", r"^{\1}", s)
    
    # mhchem-safe radical/charge normalization
    # O^{\cdot-} -> O^{.-} (mhchem prefers simple dot notation)
    s = re.sub(r"\^\{\\cdot\s*([+-])\}", r"^{.\1}", s)
    # CO2^{-} -> CO2^- (remove braces around simple charges)
    s = re.sub(r"\^\{([+-])\}", r"^\1", s)
    
    # Fix prefix notation: wrap n-, i-, sec-, tert- in \text{}
    s = re.sub(r"\b([nist])-\b", r"\\text{\1-}", s)  # n-, i-, s-, t-
    s = re.sub(r"\b(sec|tert)-\b", r"\\text{\1-}", s)  # sec-, tert-
    s = re.sub(r"\bn\s*\{\-\}", r"\\text{n-}", s)      # n{-} -> \text{n-}
    
    # Handle prose/notes inside reactions - wrap in \text{} or convert to arrow notation
    # H\ abstr. -> [\text{H abstraction}] (arrow annotation)
    s = re.sub(r"H\\\s*abstr\.", r"[\\text{H abstraction}]", s)
    # General pattern: if we see plain words, wrap them
    s = re.sub(r"\babstr\b\.?", r"\\text{abstraction}", s)
    s = re.sub(r"\bproducts\b", r"\\text{products}", s)
    
    # Remove subscript underscores (mhchem doesn't use _)
    s = re.sub(r"([A-Za-z])_([0-9]+)", r"\1\2", s)
    
    # Ensure we don't end or start with a bare arrow inside \ce{...}
    # Append placeholder if RHS is missing
    if re.search(r"(<\=|\=>|<\->|->|<-|<\=>)\s*$", s):
        s = s.rstrip() + " ~"
    # Prepend placeholder if LHS is missing
    if re.match(r"^\s*(<\=|\=>|<\->|->|<-|<\=>)", s):
        s = "~ " + s.lstrip()
    
    return s


def _wrap_ce(s: str) -> str:
    s = _strip_math_delims(s)
    # If already contains \ce{...}, assume caller supplied valid mhchem content
    if r"\ce{" in s:
        # Still normalize unicode arrows globally
        return _normalize_reaction(s)
    s = _normalize_reaction(s)
    return r"\ce{" + s + r"}"


def _normalize_math(s: str) -> str:
    # Replace unicode times and minus with LaTeX (single backslash commands)
    s = s.replace("×", r"\times")
    s = s.replace("·", r"\cdot")
    s = s.replace("−", "-")
    return s

def escape_latex(s):
    s = s.replace("\\", "\\textbackslash{}")
    for a, b in [("&", "\\&"), ("%", "\\%"), ("#", "\\#"),
                 ("_", "\\_"), ("{", "\\{"), ("}", "\\}"),
                 ("^", "\\^{}"), ("~", "\\~{}")]:
        s = s.replace(a, b)
    return s


def _split_preserve_math_and_ce(s: str):
    """Yield (segment, is_raw) where raw segments are math ($...$, \(...\), \[...\]) or \ce{...}.
    Balanced-brace scan for \ce, simple scans for math blocks.
    """
    out = []
    i = 0
    n = len(s)

    def append_segment(a: int, b: int, is_raw: bool) -> None:
        if a < b:
            out.append((s[a:b], is_raw))

    while i < n:
        ch = s[i]
        # $ ... $ math (handles escaped $)
        if ch == '$':
            j = i + 1
            while j < n:
                if s[j] == '\\' and j + 1 < n:
                    j += 2
                    continue
                if s[j] == '$':
                    j += 1
                    break
                j += 1
            append_segment(i, min(j, n), True)
            i = min(j, n)
            continue

        # \( ... \) math
        if s.startswith(r"\(", i):
            j = s.find(r"\)", i + 2)
            j = (j + 2) if j != -1 else n
            append_segment(i, j, True)
            i = j
            continue

        # \[ ... \] math
        if s.startswith(r"\[", i):
            j = s.find(r"\]", i + 2)
            j = (j + 2) if j != -1 else n
            append_segment(i, j, True)
            i = j
            continue

        # \ce{ ... } with balanced braces
        if s.startswith(r"\ce{", i):
            j = i + 4
            depth = 0
            if j < n and s[j] == '{':
                depth = 1
                j += 1
                while j < n and depth > 0:
                    c = s[j]
                    if c == '{':
                        depth += 1
                    elif c == '}':
                        depth -= 1
                    elif c == '\\' and j + 1 < n:
                        j += 2
                        continue
                    j += 1
            append_segment(i, j, True)
            i = j
            continue

        # Plain text up to next special opener
        next_positions = []
        for opener in ['$', r"\(", r"\[", r"\ce{"]:
            pos = s.find(opener, i)
            if pos != -1:
                next_positions.append(pos)
        j = min(next_positions) if next_positions else n
        append_segment(i, j, False)
        i = j

    return out


def _normalize_inline_chem_to_ce(s: str) -> str:
    """Convert common math-mode chemistry ($...$ or \( ... \)) into \ce{...},
    and normalize mhchem payloads used in prose fields (pH/comments/reference).
    Examples converted:
      $\mathrm{\cdot OH + CO_3^{2-}}$ -> \ce{.OH + CO3^{2-}}
      $\ce{^\cdot{OH} + CO_3^{2-}}$   -> \ce{.OH + CO3^{2-}}
    """
    def norm_payload(payload: str) -> str:
        t = payload
        # unify whitespace
        t = re.sub(r"\s+", " ", t).strip()
        # normalize radical dot usages
        t = t.replace(r"\\cdot", ".")  # \cdot -> .
        # specific fix for ^\cdot{OH} -> .OH
        t = re.sub(r"\^\s*\\cdot\s*\{?\s*OH\s*\}?", r".OH", t)
        # mhchem-safe charge notation: O^{\cdot-} -> O^{.-}, CO2^{-} -> CO2^-
        t = re.sub(r"\^\{\\cdot\s*([+-])\}", r"^{.\1}", t)
        t = re.sub(r"\^\{([+-])\}", r"^\1", t)
        # remove spaces around +, - and inside superscripts
        t = re.sub(r"\s*\+\s*", "+", t)
        t = re.sub(r"\s*-\s*", "-", t)
        t = re.sub(r"\^\s*\{\s*", "^{", t)
        t = re.sub(r"\s*\}\s*", "}", t)
        # subscripts like CO_3 -> CO3, OH_2 -> OH2 (remove underscores)
        t = re.sub(r"([A-Za-z])_([0-9]+)", r"\1\2", t)
        t = re.sub(r"([A-Za-z]{2,})_([0-9]+)", r"\1\2", t)
        # wrap chemical prefixes and descriptors in \text{}
        t = re.sub(r"\b([0-9]+-[A-Za-z]+)\b", r"\\text{\1}", t)  # 3-HX -> \text{3-HX}
        return t

    # $\mathrm{...}$ -> \ce{...}
    s = re.sub(r"\$\\mathrm\{([^}]*)\}\$",
               lambda m: r"\\ce{" + norm_payload(m.group(1)) + r"}", s)
    # \(\mathrm{...}\) -> \ce{...}
    s = re.sub(r"\\\(\\mathrm\{([^}]*)\}\\\)",
               lambda m: r"\\ce{" + norm_payload(m.group(1)) + r"}", s)
    # $\ce{...}$ -> \ce{...} with normalized payload
    def _norm_ce_math(m):
        inner = m.group(1)
        inner = norm_payload(inner)
        return r"\\ce{" + inner + r"}"
    s = re.sub(r"\$\\ce\{([^}]*)\}\$", _norm_ce_math, s)
    # \(\ce{...}\) -> \ce{...}
    s = re.sub(r"\\\(\\ce\{([^}]*)\}\\\)", _norm_ce_math, s)

    # normalize bare \ce{...} (not wrapped in math)
    def _norm_ce_payload(m):
        inner = m.group(1)
        inner = norm_payload(inner)
        return r"\ce{" + inner + r"}"
    s = re.sub(r"\\ce\{([^}]*)\}", _norm_ce_payload, s)
    return s


def escape_text_allow_ce(s: str) -> str:
    """Escape text while preserving inline math ($, \(\), \[\]) and \ce{...} blocks.
    Before escaping, convert common math chemistry ($\mathrm{...}$) to \ce{...}.
    """
    s = _normalize_inline_chem_to_ce(s)
    pieces = []
    for seg, is_raw in _split_preserve_math_and_ce(s):
        if is_raw:
            pieces.append(seg)
        else:
            pieces.append(escape_latex(seg))
    return ''.join(pieces)

def tsv_to_full_latex_article(tsv_path):
    tsv_path = Path(tsv_path)
    latex_dir = tsv_path.parent / "latex"
    latex_dir.mkdir(exist_ok=True)
    latex_path = latex_dir / (tsv_path.stem + ".tex")

    header = [
        "No.",
        "Compound name",
        "Reaction equation",
        "pH",
        r"\parbox{3.5cm}{\centering Rate constant\\ (L\,mol$^{-1}$\,s$^{-1}$)}",
        "Comments",
        "Reference"
    ]

    rows = []
    with open(tsv_path, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            row = row + [""] * (7 - len(row))
            rows.append(row)

    latex = [
        "\\documentclass[a4paper,12pt]{article}",
        "\\usepackage{booktabs}",
        "\\usepackage[version=4]{mhchem}",
        "\\usepackage{pdflscape}",
        "\\usepackage{geometry}",
        "\\geometry{margin=1cm}",
        "",
        "\\begin{document}",
        "\\begin{landscape}",
        "\\begin{table}[htbp]", 
        "\\centering",
        "\\footnotesize",
        "\\renewcommand{\\arraystretch}{1.2}",
        "\\begin{tabular}{lp{5cm}p{6cm}llp{8cm}l}",
        "\\toprule",
        " & ".join(header) + " \\\\",
        "\\midrule"
    ]

    for row in rows:
        reaction_raw = row[2]
        reaction_cell = _wrap_ce(reaction_raw) if reaction_raw.strip() else "~"

        ph_cell = escape_text_allow_ce(row[3]) if row[3].strip() else "~"

        rate_raw = _strip_math_delims(row[4])
        rate_cell = f"$%s$" % (_normalize_math(rate_raw)) if rate_raw.strip() else "~"

        comments_cell = escape_text_allow_ce(row[5]) if row[5].strip() else "~"

        formatted = [
            escape_latex(row[0]),
            escape_latex(row[1]),
            reaction_cell,
            ph_cell,
            rate_cell,
            comments_cell,
            escape_text_allow_ce(row[6]) if row[6].strip() else "~",
        ]
        latex.append(" \u0026 ".join(formatted) + " " + ("\\"*2))

    latex.extend([
        "\\bottomrule",
        "\\end{tabular}",
        "%\\caption{Kinetic data table}",
        "%\\label{tab:kinetics}",
        "\\end{table}",
        "\\end{landscape}",
        "\\end{document}"
    ])

    with open(latex_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(latex))
    return latex_path

def compile_tex_to_pdf(latex_path):
    latex_path = Path(latex_path)
    proc = subprocess.run([
        'xelatex', '-interaction=nonstopmode', '-halt-on-error',
        latex_path.name
    ], cwd=latex_path.parent, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return proc.returncode, proc.stdout
