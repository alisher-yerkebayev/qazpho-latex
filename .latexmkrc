# This is the ONE real .latexmkrc for the whole project -- every
# competition/language directory's own .latexmkrc is just a stub that
# does `do "$root/.latexmkrc"` to load THIS file (see
# scaffolding.py's render_latexmkrc() for why a stub has to exist in
# each directory at all: latexmk only reads .latexmkrc from
# system/$HOME/cwd, never from parent directories, so there's no way
# to make a single file "just be found" from every subdirectory).
# Change TEXINPUTS/pdf_mode/etc. here and every stub picks it up.

# 1. Ask Git for the absolute path to the repository root
my $root = `git rev-parse --show-toplevel`;
chomp($root);

# 2. There's no reliable location-independent fallback if git isn't
#    available: this file gets loaded two different ways (directly, as
#    the current-directory rc, when cwd IS the project root; or via a
#    per-directory stub's `do "$root/.latexmkrc"` otherwise), and Perl's
#    usual "where am I" tricks (__FILE__, FindBin) don't resolve
#    consistently across both -- latexmk's own rc-file loader evals rc
#    file contents as a string with no #line directive, so __FILE__
#    resolves to "(eval N)", not this file's real path, when loaded that
#    first way. Fail loudly instead of silently computing a wrong root.
if (!$root) {
    die "qazpho-latex .latexmkrc: 'git rev-parse --show-toplevel' failed -- ",
        "this project's TEXINPUTS setup needs to run from inside the git ",
        "checkout with git available on PATH.\n";
}

# 3. Rebuild TEXINPUTS using the absolute path
#    (Using double-slashes '//' instructs TeX to search subdirectories recursively)
$ENV{'TEXINPUTS'} = "$root/;" .
                    "$root/shared/;" .
                    "$root/units//;" .
                    "../;" . 
                    ($ENV{'TEXINPUTS'} // '');

$pdf_mode = 1;
