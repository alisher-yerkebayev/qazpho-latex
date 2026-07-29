# Folder layout assumed:
#   qazpho-latex/
#     shared/   olympiad.cls, olympiad-layout.sty, olympiad-marking.sty
#     units/    olympiad-units-base.sty, olympiad-units-gost.sty, olympiad-units-ru.sty
#     competitions/    respa/, ...

$ENV{'TEXINPUTS'} = '../shared/;../units//;../competitions//;' . ($ENV{'TEXINPUTS'} // '');
$pdf_mode = 1;