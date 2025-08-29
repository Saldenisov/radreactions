from tsv_utils import fix_radical_dots


def test_fix_radical_dots_replaces_cdot_with_bullet_outside_math():
    s = r"CO_3^{\cdot-} + H^+"
    out = fix_radical_dots(s)
    assert r"^{\bullet-}" in out


def test_fix_radical_dots_does_not_change_inside_math():
    s = r"$CO_3^{\cdot-}$"
    out = fix_radical_dots(s)
    assert out == s
