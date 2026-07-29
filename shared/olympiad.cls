\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{olympiad}[2027/01/01 v1.4 Competition-agnostic olympiad class]

% ============================================================
%  olympiad.cls  —  v1.3
%  Competition-agnostic, language-agnostic class for olympiad
%  documents.
%
%  Design contract:
%    - No hardcoded natural-language strings anywhere in this file
%    - No grade-specific commands (\nineth etc.)
%    - No grammatical agreement logic
%    - No competition-specific layout
%    - Problem/solution numbering is injected by build.py;
%      LaTeX counters track only intra-document sub-items
%
%  What this file provides:
%    1. Key-value option processing (language, tour, grade, type, style)
%    2. \ifOlymp... conditionals for layout files to branch on
%    3. \OlympLang — single active language code (ru / kz / ...)
%    4. \OlympString{key} — language-neutral slot accessor
%    5. task environment + tasknum / tasksolnum counters
%    6. \problem, \solution, \subproblem — structural commands
%    7. \tasksol, \taskref, \solref
%    8. Caption label format hook
%
%  Depends on:  expl3, xparse, etoolbox, caption, babel
%  Does NOT load: geometry, fancyhdr, enumitem, siunitx,
%                 tikz, graphicx, amsmath, hyperref, ...
%                 (those belong in olympiad-layout / olympiad-math)
%
%  CHANGELOG v1.2 -> v1.3
%    - Option processing rewritten to use the LaTeX kernel's own
%      \DeclareKeys / \ProcessKeyOptions (available since the
%      2022-06-01 LaTeX release) instead of the now-obsolete
%      l3keys2e package's \ProcessKeysOptions. The old mechanism
%      is documented to suffer from "space stripping and expansion
%      issues" -- this is exactly what caused the
%      "Missing \begin{document}" / leaked "olympiad" text bug and
%      is the prime suspect for the infinite-compile hang. See
%      https://ctan.org/pkg/l3keys2e and LaTeX News 35.
%    - \RequirePackage{l3keys2e} removed: no longer needed, the
%      replacement is built directly into the format.
%
%  CHANGELOG v1.3 patches (this revision)
%    - \solution was declared \newcommand{\solution}[3]{...} but
%      the body only ever uses #1/#2, and every real call site
%      supplies 2 arguments. Since LaTeX doesn't validate that a
%      call supplies as many arguments as were declared, this made
%      \solution{Title}{Points} silently swallow whatever token or
%      group came NEXT in the source as its unused #3 -- often a
%      \subproblem/\subsolution call, sometimes worse. Fixed to
%      \newcommand{\solution}[2]{...}. If you ever see a
%      \subproblem/\subsolution/\tasksol call "disappear" and its
%      own braced arguments leak out as plain text right after a
%      \problem/\solution call, check this arity mismatch first --
%      it's a very easy one to reintroduce by copy-pasting a
%      3-argument-shaped comment onto a genuinely 2-argument macro.
%    - \newline in \subproblem/\subsolution replaced with \par: a
%      \newline (== a low-level \\) requires being mid-paragraph
%      (horizontal mode); right after a \centerline-based heading
%      TeX is in vertical mode with no "current line" to end, so
%      \newline there raised a hard "There's no line here to end"
%      the moment ANY blank line appeared before the next
%      \subproblem/\subsolution in the source (a blank line is
%      \par, and \par landing in vertical mode is what exposed the
%      dangling \newline). \par is always safe in both modes.
%    - New \OlympCurrentPrefix (see below \figref for the
%      rationale): the one and only place "which problem/subproblem
%      or solution/subsolution block are we in" gets computed.
%      \thefigure, \figref, \pic/\cpic/\cpics (olympiad-layout.sty)
%      and the eq environment/\eqref (olympiad-marking.sty) all
%      call it instead of each reconstructing the same
%      \ifOlympProblems/\ifOlympSolutions branch locally -- two
%      independent reconstructions of this string had drifted out
%      of sync, which is why \figref was returning "??".
%
%  CHANGELOG v1.3 -> v1.4
%    - New style=... option (default respa), processed exactly like
%      language/tour/type: a \g__olymp_style_<name>_bool per known
%      style plus a bridged \ifOlympStyle<Name> conditional. Lets
%      layout packages (olympiad-layout.sty) gate their ENTIRE body
%      on "which competition-family's visual convention is active"
%      instead of being implicitly respa-only. olympiad.cls itself
%      never branches on style -- it only hosts the option, matching
%      its own "no competition-specific layout" design contract.
% ============================================================

\RequirePackage{expl3}

% ============================================================
% PART 1 — KEY-VALUE OPTION PROCESSING
% ============================================================
%
% expl3 PRIMER for this file:
%   \ExplSyntaxOn/Off — switch expl3 mode (spaces ignored, _ : are letters)
%   \bool_new:N \g__foo_bar_bool  — declare a global boolean, initially false
%   \bool_gset_true:N \g__foo_bar_bool — set it true
%   \str_case:nnF {value} { {case}{code} ... } {fallback} — expandable
%     string switch; the fallback branch runs if nothing matched
%   \DeclareKeys { key .code:n = {...} , ... } — kernel key-value
%     declaration (successor to l3keys2e's \keys_define:nn)
%   \ProcessKeyOptions — parse \documentclass[...] options against the
%     keys above, using the current class name as the key "family"
%     automatically (no l3keys2e-style {module} argument needed)
%
% \DeclareKeys has no built-in "choice" property (unlike l3keys), so
% each multi-valued option below is a single .code:n key that
% validates its own value with \str_case:nnF and raises \ClassError
% on anything unrecognised.
%
% DEFAULTS: \ProcessKeyOptions only ever runs the .code:n of an
% option that the user actually supplied. Defaults are therefore
% simply the booleans' initial state, set explicitly below, *before*
% \ProcessKeyOptions runs -- there is no separate ".default:n" to
% maintain in parallel, so defaults and reality cannot drift apart.
% ============================================================

\ExplSyntaxOn

\bool_new:N \g__olymp_theory_bool
\bool_new:N \g__olymp_experiment_bool
\bool_new:N \g__olymp_problems_bool
\bool_new:N \g__olymp_solutions_bool
\bool_new:N \g__olymp_marking_bool
\int_new:N  \g__olymp_grade_int
\int_new:N  \g__olymp_year_int

\tl_new:N   \g__olymp_font_tl % font size string

% Language booleans: one per supported language code.
% Adding a new language later only requires adding a bool here
% and a case entry in the "language" key below — nothing else changes.
\bool_new:N \g__olymp_lang_ru_bool
\bool_new:N \g__olymp_lang_kz_bool

% Style booleans: one per supported VISUAL layout style. A "style" is
% a whole competition-family's typographic/page-design convention
% (page geometry, headers/footers, figure and answer-box commands,
% ...) implemented in olympiad-layout.sty (or a sibling layout
% package) behind a matching \ifOlympStyle... conditional. Adding a
% new style later only requires adding a bool here and a case entry
% in the "style" key below -- the layout package itself then gates
% its own body on the resulting \ifOlympStyle... flag.
\bool_new:N \g__olymp_style_bool

% ---- set the documented defaults: language=ru, tour=theory,      ----
% ---- grade=11, type=problems, style=respa, font=12pt, year=2026  ----
\bool_gset_true:N \g__olymp_lang_ru_bool
\bool_gset_true:N \g__olymp_theory_bool
\bool_gset_true:N \g__olymp_problems_bool
\bool_gset_true:N \g__olymp_style_bool
\int_gset:Nn \g__olymp_grade_int {11}
\int_gset:Nn \g__olymp_year_int {\the\year} % current year by default
\tl_gset:Nn \g__olymp_font_tl {12pt}

\DeclareKeys
  {
    font .tl_gset:N = \g__olymp_font_tl,

    language .code:n = {
      \str_case:nnF {#1}
        {
          {ru}   {
            \bool_gset_true:N  \g__olymp_lang_ru_bool
            \bool_gset_false:N \g__olymp_lang_kz_bool
          }
          {kz}   {
            \bool_gset_false:N \g__olymp_lang_ru_bool
            \bool_gset_true:N  \g__olymp_lang_kz_bool
          }
        }
        {
          \ClassError{olympiad}
            { Unknown~value~`#1'~for~key~`language' }
            { Use~language=ru~or~language=kz. }
        }
    } ,

    tour .code:n = {
      \str_case:nnF {#1}
        {
          {theory}     {
            \bool_gset_true:N  \g__olymp_theory_bool
            \bool_gset_false:N \g__olymp_experiment_bool
          }
          {experiment} {
            \bool_gset_false:N \g__olymp_theory_bool
            \bool_gset_true:N  \g__olymp_experiment_bool
          }
        }
        {
          \ClassError{olympiad}
            { Unknown~value~`#1'~for~key~`tour' }
            { Use~tour=theory~or~tour=experiment. }
        }
    } ,

    % grade stores an integer; build.py passes 9, 10, 11, etc.
    grade .code:n = { \int_gset:Nn \g__olymp_grade_int {#1} } ,

    % year stores an integer; build.py passes 2026, ..., etc.
    year .code:n = { \int_gset:Nn \g__olymp_year_int {#1} } ,

    type .code:n = {
      \str_case:nnF {#1}
        {
          {problems}  {
            \bool_gset_true:N  \g__olymp_problems_bool
            \bool_gset_false:N \g__olymp_solutions_bool
            \bool_gset_false:N \g__olymp_marking_bool
          }
          {solutions} {
            \bool_gset_false:N \g__olymp_problems_bool
            \bool_gset_true:N  \g__olymp_solutions_bool
            \bool_gset_false:N \g__olymp_marking_bool
          }
          {marking}   {
            \bool_gset_false:N \g__olymp_problems_bool
            \bool_gset_false:N \g__olymp_solutions_bool
            \bool_gset_true:N  \g__olymp_marking_bool
          }
        }
        {
          \ClassError{olympiad}
            { Unknown~value~`#1'~for~key~`type' }
            { Use~type=problems,~type=solutions,~or~type=marking. }
        }
    } ,

    % style selects which VISUAL layout a document uses -- see the
    % \g__olymp_style_bool comment above. Layout packages (e.g.
    % olympiad-layout.sty) branch on the resulting \ifOlympStyle...
    % conditional to gate their own body; olympiad.cls itself stays
    % entirely style-agnostic and never branches on this.
    style .code:n = {
      \str_case:nnF {#1}
        {
          {respa} { \bool_gset_true:N \g__olymp_style_bool }
        }
        {
          \ClassError{olympiad}
            { Unknown~value~`#1'~for~key~`style' }
            { Use~style=respa~(more~styles~can~be~added~here~as~olympiad-layout.sty~grows~support~for~them). }
        }
    } ,
  }

\ProcessKeyOptions

\LoadClass[\g__olymp_font_tl]{article}

\RequirePackage{siunitx}         % loaded first — owns the S column
\RequirePackage{physics2}
\usephysicsmodule{ab}

\RequirePackage{xparse}
\RequirePackage{etoolbox}
\RequirePackage{caption}

\ExplSyntaxOff


% ============================================================
% PART 2 — BRIDGE TO CLASSIC CONDITIONALS
% ============================================================
%
% \bool_if:NTF \g__olymp_foo_bool { true } { false }
% translates each expl3 bool into a classic \newif pair.
% After this block no expl3 syntax is needed in layout files.
% ============================================================

\ExplSyntaxOn

\newif\ifOlympTheory
\bool_if:NTF \g__olymp_theory_bool     { \OlympTheorytrue     } { \OlympTheoryfalse     }

\newif\ifOlympExperiment
\bool_if:NTF \g__olymp_experiment_bool { \OlympExperimenttrue } { \OlympExperimentfalse }

\newif\ifOlympProblems
\bool_if:NTF \g__olymp_problems_bool   { \OlympProblemstrue   } { \OlympProblemsfalse   }

\newif\ifOlympSolutions
\bool_if:NTF \g__olymp_solutions_bool  { \OlympSolutionstrue  } { \OlympSolutionsfalse  }

\newif\ifOlympMarking
\bool_if:NTF \g__olymp_marking_bool    { \OlympMarkingtrue    } { \OlympMarkingfalse    }

% Per-language conditionals — one pair per supported language.
% Layout files use \ifOlympLangRu ... \fi
\newif\ifOlympLangRu
\bool_if:NTF \g__olymp_lang_ru_bool { \OlympLangRutrue } { \OlympLangRufalse }

\newif\ifOlympLangKz
\bool_if:NTF \g__olymp_lang_kz_bool { \OlympLangKztrue } { \OlympLangKzfalse }

% Style conditionals — one pair per supported layout style. Layout
% packages use \ifOlympStyleRespa ... \fi to gate their own body.
\newif\ifOlympStyleRespa
\bool_if:NTF \g__olymp_style_bool { \OlympStyleRespatrue } { \OlympStyleRespafalse }

% \OlympGrade — plain integer macro, usable in headers and \edef
\edef\OlympGrade { \int_use:N \g__olymp_grade_int }
\edef\OlympYear { \int_use:N \g__olymp_year_int }

\ExplSyntaxOff


% ============================================================
% PART 3 — \OlympLang AND THE STRING SLOT SYSTEM
% ============================================================
%
% \OlympLang expands to the active language code: "ru", "kz", ...
%
% \OlympString{key}
%   Expands to \OlympStr@<key>@<lang>.
%   build.py injects \def\OlympStr@<key>@<lang>{...} for every
%   string the layout needs.
%   olympiad-<comp>.sty defines fallback defaults.
%
% Adding a new language: build.py injects the new lang's strings,
% the class gets a new \bool and \newif pair in parts 1–2,
% and \OlympLang gets set below. Nothing else changes.
% ============================================================

\def\OlympLang{ru}
\ifOlympLangRu \def\OlympLang{ru}\fi
\ifOlympLangKz \def\OlympLang{kz}\fi

\newcommand{\OlympString}[1]{%
  \csname OlympStr@#1@\OlympLang\endcsname
}

% Safety net: if a slot is accessed but was never defined by
% build.py or the competition .sty, produce a visible placeholder
% rather than a cryptic "undefined control sequence" error.
% \@ifundefined checks whether the csname is defined.
\newcommand{\OlympStringFallback}[1]{%
  % #1 = key, #2 = lang
  \@ifundefined{OlympStr@#1@\OlympLang}%
    {\textbf{[?OlympStr:#1:\OlympLang]}}%
    {\csname OlympStr@#1@\OlympLang\endcsname}%
}

% Will be used to inject the text into the \OlympString
\newcommand{\SetOlympString}[2]%
{%
    \expandafter\def\csname OlympStr@#1@\OlympLang\endcsname{#2}%
}

% ============================================================
% PART 4 — LANGUAGE AND ENCODING
% ============================================================
% Loaded here unconditionally. The competition .sty can call
% \addto\captionsrussian{...} afterwards to adjust babel strings.

\RequirePackage[T2A, T1]{fontenc}
\RequirePackage[utf8]{inputenc}
\RequirePackage{amsmath, amssymb, amsthm, amsfonts} % Advanced math structures
\RequirePackage{mathtext} % <--- This fixes the math-mode Cyrillic issue
\RequirePackage[english, russian, strings]{babel}


% ============================================================
% PART 5 — DOCUMENT STRUCTURE COUNTERS
% ============================================================
%
% problemnum / solnum: which problem/solution we are on.
%   These CAN be driven by build.py (\setcounter injected into
%   the wrapper), but keeping them as LaTeX counters provides
%   \label/\ref support and costs nothing.
%
% tasknum / tasksolnum: sub-item counters within a single
%   problem or solution. These MUST be LaTeX counters — build.py
%   cannot know in advance how many \item calls will appear.
%
% \printcounter is useful for handling subproblems/subsolutions
% outputs nothing if \thecounter=0, and A,B,C,... otherwise.
%
% ============================================================

\newcounter{problemnum}                 \setcounter{problemnum}{0}
\newcounter{subproblemnum}[problemnum]  \setcounter{subproblemnum}{0}
\newcounter{tasknum}[problemnum]        \setcounter{tasknum}{0}
\newcounter{solnum}                     \setcounter{solnum}{0}
\newcounter{subsolnum}[solnum]          \setcounter{subsolnum}{0}
\newcounter{tasksolnum}[solnum]         \setcounter{tasksolnum}{0}
\newcounter{figcounter}[problemnum]     \setcounter{figcounter}{0}

% taskalphanum: labels items (a), (b), (c), ... for
% task[type=subproblem] (Part 10). Not parented to problemnum/
% subproblemnum like tasknum -- the environment itself resets it to 0
% at the start of EVERY type=subproblem block (self-contained, always
% starts at (a)), so an automatic parent-triggered reset would be
% redundant.
\newcounter{taskalphanum}

% blocknum: a single FLAT counter, unrelated to the
% problemnum/subproblemnum or solnum/subsolnum families, that steps
% once per \solution or \subsolution (see Parts 8-9). Its only job is
% giving \theHequation (olympiad-marking.sty) a plain, single-parent
% counter to anchor hyperref's PDF destination names to. Equation
% anchors need to be unique across DIFFERENT \solution/\subsolution
% blocks (which each reset the real `equation' counter to 0 for
% readable "(1), (2), ..." display) -- chngcntr's usual
% \counterwithin*{equation}{X} approach cannot do this reliably here,
% because it depends on hyperref having been loaded BEFORE X was
% \newcounter'd, which can never be true for counters declared in
% this class (loaded via \documentclass, always before the user's own
% \usepackage{hyperref}). A single manually-stepped counter sidesteps
% that entirely: nothing about it depends on hyperref's own counter
% tracking, so there's no load-order constraint to violate.
\newcounter{blocknum}                   \setcounter{blocknum}{0}

\ExplSyntaxOn
\DeclareExpandableDocumentCommand{\printcounter}{ m }{%
  \int_compare:nNnT { \value{#1} } > { 0 } { \int_to_Alph:n { \value{#1} } }%
}
\ExplSyntaxOff

% ============================================================
% \OlympCurrentPrefix -- the SINGLE, canonical "which block are we
% in" prefix (e.g. "1", "1A", "2B") shared by EVERYTHING that
% numbers or labels things per problem/subproblem or solution/
% subsolution: \thefigure and \figref here, and \pic/\cpic/\cpics
% in olympiad-layout.sty, and the eq environment/\eqref in
% olympiad-marking.sty. There must be exactly ONE definition of
% "current prefix" in the whole system -- every prior bug in this
% area (\figref returning "??", eq labels not matching \eqref) came
% from two DIFFERENT pieces of code independently reconstructing
% this same string and drifting out of sync. Don't reconstruct it
% locally anywhere else; call this instead.
%
% type=marking (\ifOlympMarking) reuses the \ifOlympSolutions branch
% verbatim (solnum/subsolnum), not a no-op: \solution/\subsolution
% step those counters unconditionally regardless of type, so they're
% just as meaningful under type=marking. Before this branch existed,
% \ifOlympProblems and \ifOlympSolutions were BOTH false under
% type=marking (type is one-of-three, see Part 1), so this macro
% silently expanded to nothing -- breaking \eqref/\figref/\eq's
% default label (still latent wherever \OlympString{figlabel} is
% defined per-competition, e.g. strings-*.tex, which has the same
% \ifOlympProblems/\ifOlympSolutions-only pattern and needs the same
% fix there).
% ============================================================
\newcommand{\OlympCurrentPrefix}{%
  \ifOlympProblems
    \arabic{problemnum}\printcounter{subproblemnum}%
  \fi
  \ifOlympSolutions
    \arabic{solnum}\printcounter{subsolnum}%
  \fi
  \ifOlympMarking
    \arabic{solnum}\printcounter{subsolnum}%
  \fi
}

% ============================================================
% PART 6 — CAPTION LABEL FORMAT HOOK
% ============================================================
%
% We declare the caption format using \OlympString so the label
% text ("Рис." / "N-сурет.") comes from slots, not hardcoded.
%
% build.py or olympiad-<comp>.sty must define:
%   \OlympStr@figlabel@ru   e.g. {Рис.~#2.}
%   \OlympStr@figlabel@kz   e.g. {#2-сурет.}
%
% The format uses #2 (the counter value) per caption's interface.
% We defer setup to \AtBeginDocument so slots are filled first.
% ============================================================

\AtBeginDocument{%
  \@ifundefined{OlympStr@figlabel@\OlympLang}{}{%
    \DeclareCaptionLabelFormat{olymp@figlabel}{%
      \OlympString{figlabel}%  #1=prefix (unused), #2=counter
    }%
    \ifOlympMarking\else
    \captionsetup[figure]{labelformat=olymp@figlabel, labelsep=space}%
    \fi
  }%
}

\renewcommand{\thefigure}{\OlympCurrentPrefix.\arabic{figcounter}}


% ============================================================
% PART 7 — \problem
% ============================================================
%
% \problem{Title}{Points}
%   Title — problem title, passed by build.py from problem.yaml
%   Points — point value string, already grammatically correct
%            (build.py resolved "10 баллов" / "10 ұпай")
%
% The command sets the LaTeX counter to N (for \taskref cross-
% references), resets tasknum, starts a new page, and calls
% \OlympProblemHeading which layout can redefine.
%
% No starred variant. No hardcoded subtitle text.
% If a problem needs "three independent parts" text, that is
% content — it goes in the problem's .tex file directly.
% ============================================================

% Heading hook: layout redefines this for typography control
\newcommand{\OlympProblemHeading}[1]{%
  \centerline{\large\textbf{#1}}%
}

\newcommand{\problem}[2]{%
  % #1 = title, #2 = points string
  \stepcounter{problemnum}%
  \setcounter{subproblemnum}{0}%
  \setcounter{tasknum}{0}%
  \setcounter{figcounter}{0}%
  \par%
  \OlympProblemHeading{%
    \ifOlympTheory\OlympString{problem}~\theproblemnum.~\fi#1~(#2 \OlympString{points_long})%
  }%
}


% ============================================================
% PART 8 — \solution
% ============================================================
%
% \solution{Title}{Points}
%   #1 = title, #2 = points string. Auto-numbers via \thesolnum
%   (no explicit "number" argument -- was a stale 3rd argument in
%   an earlier revision; see the top-of-file changelog).
%   Sets solnum and resets tasksolnum/subsolnum/equation counter.
%   Under type=marking (\ifOlympMarking), the heading additionally
%   appends "--- \OlympString{marking_scheme}" -- competition .sty /
%   strings-*.tex files must define OlympStr@marking_scheme@<lang>
%   for this (e.g. \SetOlympString{marking_scheme}{Марк-схема}), same
%   as any other \OlympString slot. \subsolution does the same.
%
% \solutionsheader
%   Standalone command for the "РЕШЕНИЯ / ШЕШІМДЕР" block header.
%   Separate from \solution so build.py can emit it once before
%   the first \solution call, or not at all for single-problem
%   files.
% ============================================================

\newcommand{\OlympSolutionHeading}[1]{%
  \centerline{\large\textbf{#1}}%
}

\newcommand{\solution}[2]{%
  % #1 = title, #2 = points string
  \stepcounter{solnum}%
  \setcounter{tasksolnum}{0}%
  \setcounter{subsolnum}{0}%
  \setcounter{equation}{0}%
  \stepcounter{blocknum}%
  \par%
  \OlympSolutionHeading{%
    \ifOlympTheory\OlympString{problem}~\thesolnum.~\fi#1~(#2 \OlympString{points_long})%
  }%
}



% ============================================================
% PART 9 — \subproblem and \subsolution
% ============================================================
%
% \subproblem{Label}{Points}
%   For the multi-part Problem 1 pattern (parts А, Б, В).
%   Label  — single letter or short label, e.g. "А"
%   Points — already-formatted string from build.py
%
%   \subsolution increments solnum so that \eq numbering
%   and \eqref refs remain consistent across sub-problems.
%   Resets tasksolnum and equation counter per sub-solution.
%
%   Heading uses slot "subproblem" so competition .sty can
%   set:  \def\OlympStr@subproblem@ru{Задача 1A}
%         \def\OlympStr@subproblem@kz{Есеп 1A}
%   and:  \def\OlympStr@subsolution@ru{Задача 1A}
%         \def\OlympStr@subsolution@kz{Есеп 1A}
%
%   \par (not \newline): \newline requires being mid-paragraph
%   (horizontal mode). Right after a \centerline-based heading TeX
%   is in vertical mode with no current line, so \newline there
%   raised "There's no line here to end" the moment a blank line
%   preceded the next \subproblem/\subsolution. \par is safe in
%   both modes.
% ============================================================

\newcommand{\subproblem}[2]{%
  % #1 = label (e.g. А), #2 = points string
  \setcounter{figcounter}{0}%
  \stepcounter{subproblemnum}%
  \par%
  \centerline{\textbf{\OlympString{problem}~\theproblemnum\printcounter{subproblemnum}.~#1~(#2 \OlympString{points_short})}}%
}

\newcommand{\subsolution}[2]{%
  % #1 = label (e.g. А), #2 = points string
  \stepcounter{subsolnum}%
  \setcounter{tasksolnum}{0}%
  \setcounter{equation}{0}%
  \setcounter{figcounter}{0}%
  \stepcounter{blocknum}%
  \par%
  \vspace{6pt}%
  \ifOlympMarking
    \centerline{\textbf{\OlympString{problem}~\thesolnum\printcounter{subsolnum}.~#1~(#2 \OlympString{points_short})~---~\OlympString{marking_scheme}}}%
  \else
    \centerline{\textbf{\OlympString{problem}~\thesolnum\printcounter{subsolnum}.~#1~(#2 \OlympString{points_short})}}%
  \fi
}

% ============================================================
% PART 10 — task ENVIRONMENT
% ============================================================
%
% Wraps numbered sub-tasks within a problem statement.
% Each \item auto-increments tasknum and produces label "N.M"
% where N = \theproblemnum, M = \arabic{tasknum}.
%
% \begin{task}[type=subproblem] ... \end{task}
%   Same list, but labels each \item "(a)", "(b)", "(c)", ... instead
%   of the numbered "N.M" style -- for a task that's really a set of
%   lettered/alternative sub-parts (e.g. "(a) ... (b) ...") rather
%   than a fresh top-level numbered task. Aliases: type=alternative,
%   type=alphabetic -- all three are identical; pick whichever reads
%   best at the call site. An unrecognised type=... value warns and
%   falls back to the default numbered style (mirrors \eq/\criterion
%   in olympiad-marking.sty).
%
%   Uses its own counter (taskalphanum, Part 5), reset to 0 at the
%   START of every type=subproblem block, so each such list is
%   self-contained and always starts at (a) regardless of any other
%   task[type=subproblem] elsewhere in the document. This replaces an
%   ad hoc \newcounter{taskstar}-per-file pattern some problems
%   hand-rolled for the same effect, which breaks the moment a SECOND
%   file needing it is \input into the same document (\newcounter
%   errors on a name already taken).
%
% Deliberately uses raw list — no enumitem keys here.
% olympiad-layout.sty issues \setlist or patches this env
% to control spacing, indentation, and font.
% ============================================================

\ExplSyntaxOn

\bool_new:N \l__olymp_task_alphabetic_bool

\DeclareKeys[olymp/task]
  {
    type .code:n = {
      \str_case:nnF {#1}
        {
          {subproblem}  { \bool_set_true:N \l__olymp_task_alphabetic_bool }
          {alternative} { \bool_set_true:N \l__olymp_task_alphabetic_bool }
          {alphabetic}  { \bool_set_true:N \l__olymp_task_alphabetic_bool }
        }
        {
          \ClassWarning{olympiad}
            { type=#1~is~not~recognised~by~the~task~environment~(only~subproblem~/~alternative~/~alphabetic~are);~using~the~default~numbered~style }
        }
    } ,
  }

\NewDocumentEnvironment{task}{ O{} }
  {
    \bool_set_false:N \l__olymp_task_alphabetic_bool
    \SetKeys[olymp/task]{#1}
    \bool_if:NT \l__olymp_task_alphabetic_bool { \setcounter{taskalphanum}{0} }
    \begin{list}{}{
      \setlength{\leftmargin}{18pt}
      \setlength{\labelwidth}{0pt}
      \setlength{\labelsep}{0pt}
      \bool_if:NTF \l__olymp_task_alphabetic_bool
        {
          \renewcommand{\makelabel}[1]{
            \refstepcounter{taskalphanum}
            \textbf{(\alph{taskalphanum})}~
          }
        }
        {
          \renewcommand{\makelabel}[1]{
            \refstepcounter{tasknum}
            \textbf{\theproblemnum\printcounter{subproblemnum}.\arabic{tasknum}}~
          }
        }
    }
  }
  {
    \end{list}
  }

\ExplSyntaxOff


% ============================================================
% PART 11 — \tasksol, \taskref, \solref
% ============================================================
%
% \tasksol  — starts a solution sub-task, incrementing
%             tasksolnum and printing the "N.M" label
% \taskref{M} — bold reference to sub-task M of current problem
% \solref{M}  — bold reference to sub-task M of current solution
%
% \figref{N} — reference the Nth picture within the CURRENT
%   problem/subproblem or solution/subsolution block. Delegates to
%   \OlympCurrentPrefix instead of reconstructing the
%   \ifOlympProblems/\ifOlympSolutions branch locally -- see that
%   macro's own comment for why.
%
% The \hspace* mirrors task's leftmargin; layout can adjust.
% ============================================================

\newcommand{\tasksol}{%
  \vspace{6pt}%
  \hspace*{18pt}%
  \stepcounter{tasksolnum}%
  \textbf{\thesolnum.\thetasksolnum}~%
}

\newcommand{\taskref}[1]{\textbf{\theproblemnum.#1}}
\newcommand{\solref}[1]{\textbf{\thesolnum.#1}}

\newcommand{\figref}[1]
{
  \ifOlympProblems%
  \arabic{problemnum}\printcounter{subproblemnum}.\ref{fig:\OlympCurrentPrefix.#1}%
  \fi%
  \ifOlympSolutions%
  \arabic{solnum}\printcounter{subsolnum}.\ref{fig:\OlympCurrentPrefix.#1}%
  \fi%
}
% (figcounter resets per \problem/\subproblem/\subsolution, see
% Part 5/9). Authors never type or track the problem number
% themselves: \OlympCurrentPrefix is resolved at compile time, so
% figure references survive problems being reordered/renumbered by
% build.py. Pairs with the label key that \pic/\cpic/\cpics in
% olympiad-layout.sty must use:
%   \label{fig:\OlympCurrentPrefix.\thefigcounter}

\RequirePackage{lipsum}

% ============================================================
% END OF olympiad.cls
% ============================================================