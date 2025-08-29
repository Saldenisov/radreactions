from pdf_utils import escape_text_allow_ce

s = "p.r.; P.b.k. at 270 nm in $\\ce{N2O}$-satd. soln. contg. 0.5 mol L$^{-1}$ NaOH."
print(escape_text_allow_ce(s))
