import csv
import subprocess
from pathlib import Path
import re
from tsv_utils import fix_radical_dots

def escape_latex(s):
    s = s.replace("\\", "\\textbackslash{}")
    for a, b in [("&", "\\&"), ("%", "\\%"), ("#", "\\#"),
                 ("_", "\\_"), ("{", "\\{"), ("}", "\\}"),
                 ("^", "\\^{}"), ("~", "\\~{}")]:
        s = s.replace(a, b)
    return s

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
        "\\usepackage{mhchem}",
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
        formatted = [
            escape_latex(row[0]),
            escape_latex(row[1]),
            fix_radical_dots(row[2]) if row[2].strip() else "~",
            fix_radical_dots(row[3]) if row[3].strip() else "~",
            fix_radical_dots(row[4]) if row[4].strip() else "~",
            fix_radical_dots(row[5]) if row[5].strip() else "~",
            escape_latex(row[6]) if row[6].strip() else "~",
        ]
        latex.append(" & ".join(formatted) + " \\\\")

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
