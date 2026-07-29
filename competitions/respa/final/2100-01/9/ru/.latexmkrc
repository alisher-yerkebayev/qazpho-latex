# Stub only -- see qazpho-latex/.latexmkrc for the real config and
# competitions/scaffolding-respa.py's render_latexmkrc() for why this
# file has to exist here at all.
my $root = `git rev-parse --show-toplevel`;
chomp($root);
do "$root/.latexmkrc";
