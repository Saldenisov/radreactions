import csv
import re

def tsv_to_visible(tsv_text, tab_symbol="→"):
    return tsv_text.replace('\t', tab_symbol)

def visible_to_tsv(visible_text, tab_symbol="→"):
    return visible_text.replace(tab_symbol, '\t')

def fix_radical_dots(s):
    s = re.sub(r'\^\{\.\-\}', r'^{\\cdot-}', s)
    s = re.sub(r'\^\{\.\}', r'^{\\cdot}', s)
    s = s.replace(r'\bullet', r'\cdot')
    return s

def fix_units(s):
    # Replace L^{-1} with L$^{-1}$ (and similar) if not already in math mode
    s = re.sub(r'L\^\{([-\d+\w]+)\}', r'L$\^{\1}$', s)
    return s

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
            # Only fix columns that are not escaped in LaTeX
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
