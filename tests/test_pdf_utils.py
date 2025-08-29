def test_tsv_to_full_latex_article_generates_tex(data_env, tmp_path):
    base = data_env["base_dir"]
    mods = data_env["mods"]

    # Create minimal TSV file
    tsv_dir = tmp_path / "csv"
    tsv_dir.mkdir(parents=True, exist_ok=True)
    tsv_path = tsv_dir / "row1.csv"
    tsv_path.write_text(
        "\t".join(
            [
                "5-001",
                "Test compound",
                r"\\ce{OH. + CO_3^{2-} -> CO_3^{.-}}",
                "7",
                "1.0 x 10^9",
                "note",
                "REF",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    tex_path = mods["pdf_utils"].tsv_to_full_latex_article(tsv_path)
    assert tex_path.exists()
    content = tex_path.read_text(encoding="utf-8")
    assert "usepackage[version=4]{mhchem}" in content
    assert "\\ce{" in content


def test_compile_tex_to_pdf_is_mockable(monkeypatch, data_env, tmp_path):
    mods = data_env["mods"]
    # Create a dummy tex file
    tex = tmp_path / "x.tex"
    tex.write_text("\\documentclass{article}\\begin{document}x\\end{document}", encoding="utf-8")

    class Dummy:
        def __init__(self):
            self.returncode = 0
            self.stdout = "ok"

    def fake_run(*args, **kwargs):
        return Dummy()

    import subprocess

    monkeypatch.setattr(subprocess, "run", fake_run)
    rc, out = mods["pdf_utils"].compile_tex_to_pdf(tex)
    assert rc == 0
    assert out == "ok"
