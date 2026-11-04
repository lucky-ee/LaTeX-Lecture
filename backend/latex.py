"""Repair LaTeX that the model's JSON output mangled into control characters."""

import re

# The model's JSON sometimes mangles LaTeX backslashes into control characters:
# - unescaped "\theta", "\frac", "\beta", "\neq", "\rho" decode as tab, form
#   feed, backspace, newline, or carriage return plus the rest of the name;
# - under strict JSON decoding, "\int" (invalid escape "\i") was observed as
#   carriage return + "int".
# A control character followed by letters is restored to whichever command is
# real: "\<escape letter><letters>" first, then "\<letters>". Unknown words are
# left untouched.
_ESCAPE_LETTER = {"\r": "r", "\t": "t", "\f": "f", "\b": "b", "\n": "n"}
_BROKEN_COMMAND = re.compile(r"([\r\t\f\b\n])([A-Za-z]+)")
_LATEX_COMMANDS = frozenset("""
    alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa
    lambda mu nu xi pi varpi rho varrho sigma varsigma tau upsilon phi varphi chi
    psi omega Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega
    int iint iiint oint sum prod coprod lim limsup liminf sup inf max min
    frac dfrac tfrac binom tbinom dbinom sqrt partial nabla infty
    sin cos tan cot sec csc sinh cosh tanh arcsin arccos arctan log ln exp det
    dim ker deg gcd arg hom mod bmod pmod
    forall exists nexists neg not in notin ni subset subseteq supset supseteq
    nsubseteq nsupseteq cup cap bigcup bigcap setminus emptyset varnothing
    land lor lnot implies iff to mapsto gets rightarrow leftarrow
    leftrightarrow Rightarrow Leftarrow Leftrightarrow longrightarrow
    longmapsto nrightarrow nleftarrow uparrow downarrow
    leq geq neq ne le ge nleq ngeq approx equiv sim simeq cong ncong propto
    ll gg mid nmid parallel nparallel perp
    times cdot cdots ldots dots vdots ddots div pm mp circ ast star bullet
    oplus otimes bigoplus bigotimes wedge vee bigwedge bigvee top bot
    therefore because angle triangle backslash
    left right big Big bigg Bigg bigl bigr langle rangle lceil rceil lfloor
    rfloor lbrace rbrace lvert rvert lVert rVert vert Vert
    text textbf textit textrm textsf texttt textnormal mathrm mathbf mathit
    mathbb mathcal mathfrak mathsf boldsymbol operatorname
    bar hat tilde vec dot ddot overline underline widehat widetilde
    overbrace underbrace boxed displaystyle textstyle
    quad qquad begin end newline nolimits limits
""".split())


def repair_latex(latex: str) -> str:
    def restore(match: re.Match) -> str:
        letter, word = _ESCAPE_LETTER[match.group(1)], match.group(2)
        if letter + word in _LATEX_COMMANDS:
            return "\\" + letter + word
        if word in _LATEX_COMMANDS:
            return "\\" + word
        return match.group(0)

    return _BROKEN_COMMAND.sub(restore, latex)
