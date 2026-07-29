# Folder layout assumed:
#   qazpho-latex/
#     shared/   olympiad.cls, olympiad-layout.sty, olympiad-marking.sty
#     units/    olympiad-units-base.sty, olympiad-units-gost.sty, olympiad-units-ru.sty
#     competitions/    respa/, ...
#
# This file lives 6 levels below the project root
# (competitions/respa/oblast/2100-01/11/ru), so every path below needs
# 6 "../" to reach qazpho-latex/. The bare "../../../../../../" entry lets
# kpathsea resolve compound-relative \input paths written from the
# project root (e.g. \input{competitions/respa/strings-config.tex}
# and figures/*.png shared at .../<grade>/figures/, one level above
# ru/kz).

$ENV{'TEXINPUTS'} = '../../../../../../;../../../../../../shared/;../../../../../../units//;../;' . ($ENV{'TEXINPUTS'} // '');
$pdf_mode = 1;
