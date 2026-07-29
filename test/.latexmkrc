# .latexmkrc — place this in test/ (or in the project root, phys-olympiad/,
# if you want every subfolder that has its own .latexmkrc to inherit it).
#
# Folder layout assumed:
#   phys-olympiad/
#     shared/   olympiad.cls, olympiad-layout.sty
#     units/    olympiad-units-base.sty, olympiad-units-gost.sty, olympiad-units-ru.sty
#     test/     test-respa2026.tex, respa2026_11_*.tex, .latexmkrc  <-- this file
#
# This appends ../shared and ../units to the kpathsea search path via the
# TEXINPUTS environment variable, so \documentclass{olympiad},
# \usepackage{olympiad-layout}, \usepackage{olympiad-units-ru} (and its
# internal \RequirePackage{olympiad-units-gost} / olympiad-units-base
# cascade) are all found without copying any files into test/.
#
# "//" at the end of a path tells kpathsea to search that directory AND
# all its subdirectories recursively. The trailing bare separator
# re-appends whatever TEXINPUTS was already set to (often empty), which
# in turn makes kpathsea fall back to its normal system search path.
#
# NOTE: On Windows the path separator for TEXINPUTS is ";"; on
# Linux/macOS it is ":". Adjust the separator below if you move this
# project to a non-Windows machine (or build it with WSL/Linux latexmk).
# Forward slashes work fine in kpathsea/MiKTeX on Windows too, so there
# is no need for backslashes here.

$ENV{'TEXINPUTS'} = '../shared/;../units//;' . ($ENV{'TEXINPUTS'} // '');

# If you ever run latexmk from WSL/Linux/macOS instead of native Windows,
# use this form instead (colon-separated):
# $ENV{'TEXINPUTS'} = '../shared/:../units//:' . ($ENV{'TEXINPUTS'} // '');

$pdf_mode = 1;