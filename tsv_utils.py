import csv
import re

def tsv_to_visible(tsv_text, tab_symbol="→"):
    return tsv_text.replace('\t', tab_symbol)

def visible_to_tsv(visible_text, tab_symbol="→"):
    return visible_text.replace(tab_symbol, '\t')

def _split_preserve_math_and_ce(s: str):
    """Yield (segment, is_raw) where raw segments are math ($...$, \(...\), \[...\]) or \ce{...}."""
    out = []
    i = 0
    n = len(s)
    def append(a,b,raw):
        if a < b:
            out.append((s[a:b], raw))
    while i < n:
        ch = s[i]
        if ch == '$':
            j = i+1
            while j < n:
                if s[j] == '\\' and j+1 < n:
                    j += 2
                    continue
                if s[j] == '$':
                    j += 1
                    break
                j += 1
            append(i, min(j,n), True)
            i = min(j,n)
            continue
        if s.startswith(r"\(", i):
            j = s.find(r"\)", i+2)
            j = j+2 if j != -1 else n
            append(i, j, True)
            i = j
            continue
        if s.startswith(r"\[", i):
            j = s.find(r"\]", i+2)
            j = j+2 if j != -1 else n
            append(i, j, True)
            i = j
            continue
        if s.startswith(r"\ce{", i):
            j = i+4
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
                    elif c == '\\' and j+1 < n:
                        j += 2
                        continue
                    j += 1
            append(i, j, True)
            i = j
            continue
        # plain text chunk
        nexts = []
        for opener in ['$', r"\(", r"\[", r"\ce{"]:
            k = s.find(opener, i)
            if k != -1:
                nexts.append(k)
        j = min(nexts) if nexts else n
        append(i, j, False)
        i = j
    return out

def _apply_outside_math_ce(text: str, transform):
    parts = []
    for seg, raw in _split_preserve_math_and_ce(text):
        parts.append(seg if raw else transform(seg))
    return ''.join(parts)

def fix_radical_dots(s):
    """Fix dot/radical markers but do not touch content inside \ce{...} or math blocks."""
    def _fix(seg: str) -> str:
        seg = re.sub(r'\^\{\.\-\}', r'^{\\cdot-}', seg)
        seg = re.sub(r'\^\{\.\}', r'^{\\cdot}', seg)
        seg = seg.replace(r'\bullet', r'\cdot')
        return seg
    return _apply_outside_math_ce(s, _fix)

def fix_units(s):
    # Replace L^{-1} with L$^{-1}$ (and similar) if not already in math mode; avoid changing inside math/\ce
    def _fix(seg: str) -> str:
        return re.sub(r'L\^\{([-\d+\w]+)\}', r'L$\^{\1}$', seg)
    return _apply_outside_math_ce(s, _fix)

def sanitize_field(s):
    # Remove newlines and excessive whitespace inside a cell
    return ' '.join(s.replace('\n', ' ').replace('\r', ' ').split())

def correct_tsv_file(tsv_path):
    rows = []
    with open(tsv_path, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            row = row + [""] * (7 - len(row))
            # Sanitize every field
            row = [sanitize_field(cell) for cell in row]
            # Conservatively fix outside math/\ce only
            row[2] = fix_radical_dots(row[2])
            row[3] = fix_radical_dots(row[3])
            row[4] = fix_radical_dots(row[4])
            row[5] = fix_radical_dots(row[5])
            row[5] = fix_units(row[5])
            rows.append(row)
    with open(tsv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerows(rows)
    return "\n".join(["\t".join(row) for row in rows])
