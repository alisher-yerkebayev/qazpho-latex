# Stub only. latexmk itself only ever reads .latexmkrc from three fixed
# places -- system, $HOME, and the literal current directory -- it never
# walks up parent directories looking for one (checked directly against
# latexmk.pl's own rc-search code, not just observed behavior). So every
# directory a document gets compiled from still needs a file with this
# exact name; the point of this stub is that it's the ONLY thing that
# needs to exist here. All real config (TEXINPUTS etc.) lives once at
# qazpho-latex/.latexmkrc and is loaded below -- edit that file, not this
# one, when the shared config needs to change.
my $root = `git rev-parse --show-toplevel`;
chomp($root);
do "$root/.latexmkrc";
