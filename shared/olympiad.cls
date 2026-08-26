\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{olympiad}[2027/01/01 Competition-agnostic olympiad class]

% ============================================================
%  olympiad.cls
%  Competition-, language-, and style-agnostic class for olympiad
%  documents.
%
%  Design contract:
%    - No hardcoded natural-language strings anywhere in this file
%    - No competition-specific layout
%    - Problem/solution numbering is injected by build.py;
%      LaTeX counters track only intra-document sub-items
%
%  What this file provides:
%    1. Key-value option processing (language, tour, grade, type, style)
%    2. \ifOlymp... conditionals for layout files to branch on
%    3. \OlympLang — single active language code (ru / kz / ...)
%    4. \OlympString{key} — language-neutral slot accessor
%    5. problemnum/solnum/tasknum/... counters and \OlympCurrentPrefix
%    6. Caption label format hook
%
%  Depends on:  expl3, xparse, etoolbox, caption, babel
%  Does NOT load: geometry, fancyhdr, enumitem, siunitx,
%                 tikz, graphicx, amsmath, hyperref, ...
%                 (those belong in olympiad-layout)
% ============================================================

\RequirePackage{iftex}
\ifXeTeX\else
  \ClassError{olympiad}
    { This~class~requires~XeLaTeX }
    { Compile~with~xelatex,~e.g.~`latexmk~-pdfxe'~(this~project's~
      build.py~and~.latexmkrc~already~do~this~by~default). }
\fi

\RequirePackage{expl3}

% ============================================================
% KEY-VALUE OPTION PROCESSING
% ============================================================

\ExplSyntaxOn

\bool_new:N \g__olymp_theory_bool
\bool_new:N \g__olymp_experiment_bool
\bool_new:N \g__olymp_problems_bool
\bool_new:N \g__olymp_solutions_bool
\bool_new:N \g__olymp_marking_bool
\bool_new:N \g__olymp_jury_bool
\int_new:N  \g__olymp_grade_int
\int_new:N  \g__olymp_year_int

\tl_new:N   \g__olymp_font_tl % font size string

% Language booleans: one per supported language code.
\bool_new:N \g__olymp_lang_ru_bool
\bool_new:N \g__olymp_lang_kz_bool

% Style booleans: one per supported VISUAL layout style.
\bool_new:N \g__olymp_style_respa_bool
\bool_new:N \g__olymp_style_ipho_bool % new boolean v1.5-> v1.6

% ---- set the documented defaults: language=ru, tour=theory,      ----
% ---- grade=11, type=problems, style=respa, font=12pt, year=2026  ----
\bool_gset_true:N \g__olymp_lang_ru_bool
\bool_gset_true:N \g__olymp_theory_bool
\bool_gset_true:N \g__olymp_problems_bool
\bool_gset_true:N \g__olymp_style_respa_bool
\int_gset:Nn \g__olymp_grade_int {11} % fallback default
\int_gset:Nn \g__olymp_year_int {\the\year} % current year by default
\tl_gset:Nn \g__olymp_font_tl {11pt} % 11pt as a fallback default

\DeclareKeys
  {
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
            \bool_gset_false:N \g__olymp_jury_bool
          }
          {solutions} {
            \bool_gset_false:N \g__olymp_problems_bool
            \bool_gset_true:N  \g__olymp_solutions_bool
            \bool_gset_false:N \g__olymp_marking_bool
            \bool_gset_false:N \g__olymp_jury_bool
          }
          {marking}   {
            \bool_gset_false:N \g__olymp_problems_bool
            \bool_gset_false:N \g__olymp_solutions_bool
            \bool_gset_true:N \g__olymp_marking_bool
            \bool_gset_false:N  \g__olymp_jury_bool
          }
          {jury}   {
            \bool_gset_false:N \g__olymp_problems_bool
            \bool_gset_false:N \g__olymp_solutions_bool
            \bool_gset_false:N \g__olymp_marking_bool
            \bool_gset_true:N  \g__olymp_jury_bool
          }
        }
        {
          \ClassError{olympiad}
            { Unknown~value~`#1'~for~key~`type' }
            { Use~type=problems,~type=solutions,~type=marking,~or~type=jury. }
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
          {respa} {
            \bool_gset_true:N  \g__olymp_style_respa_bool
            \bool_gset_false:N \g__olymp_style_ipho_bool
          }
          {ipho} {
            \bool_gset_false:N \g__olymp_style_respa_bool
            \bool_gset_true:N  \g__olymp_style_ipho_bool
          }
        }
        {
          \ClassError{olympiad}
            { Unknown~value~`#1'~for~key~`style' }
            { Use~style=respa/ipho~(more~styles~can~be~added~here~as~olympiad-layout.sty~grows~support~for~them). }
        }
    } ,
  }

\ProcessKeyOptions


\ExplSyntaxOff


% ============================================================
% BRIDGE TO CLASSIC CONDITIONALS
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

\newif\ifOlympJury
\bool_if:NTF \g__olymp_jury_bool    { \OlympJurytrue    } { \OlympJuryfalse    }

% Per-language conditionals — one pair per supported language.
% Layout files use \ifOlympLangRu ... \fi
\newif\ifOlympLangRu
\bool_if:NTF \g__olymp_lang_ru_bool { \OlympLangRutrue } { \OlympLangRufalse }

\newif\ifOlympLangKz
\bool_if:NTF \g__olymp_lang_kz_bool { \OlympLangKztrue } { \OlympLangKzfalse }

% Style conditionals — one pair per supported layout style, each
% bridged from its OWN boolean (see the Part 1 comment above). Layout
% packages use \ifOlympStyleRespa ... \fi to gate their own body.
\newif\ifOlympStyleRespa
\bool_if:NTF \g__olymp_style_respa_bool { \OlympStyleRespatrue } { \OlympStyleRespafalse }
\newif\ifOlympStyleIpho
\bool_if:NTF \g__olymp_style_ipho_bool { \OlympStyleIphotrue } { \OlympStyleIphofalse }

\ifOlympStyleRespa \tl_gset:Nn \g__olymp_font_tl {12pt} \fi
\ifOlympStyleIpho \tl_gset:Nn \g__olymp_font_tl {9pt} \fi

% \OlympGrade — plain integer macro, usable in headers and \edef
\edef\OlympGrade { \int_use:N \g__olymp_grade_int }
\edef\OlympYear { \int_use:N \g__olymp_year_int }

\LoadClass[\g__olymp_font_tl]{article}

\ExplSyntaxOff

\RequirePackage{siunitx}        % loaded first — owns the S column
\RequirePackage{physics2}       \usephysicsmodule{ab}
\RequirePackage{derivative}
\RequirePackage[version=4]{mhchem}

\RequirePackage{xparse}
\RequirePackage{etoolbox}
\RequirePackage{caption}
\RequirePackage{comment}

% ============================================================
% \OlympLang AND THE STRING SLOT SYSTEM
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

% \OlympIfStringDefined{key}{content} -- expands to <content> only if
% that slot was ever \SetOlympString'd, otherwise expands to nothing.
% For slots that are genuinely OPTIONAL per competition -- e.g. a logo
% or tour icon image path (see strings-config.tex) -- where not every
% competition/style has one, and the right behavior for "no such
% picture" is to skip the \includegraphics entirely, not print an
% [?OlympStr:...] placeholder (\OlympStringFallback's job) or error.
\newcommand{\OlympIfStringDefined}[2]{%
  \@ifundefined{OlympStr@#1@\OlympLang}{}{#2}%
}

% ============================================================
% LANGUAGE AND ENCODING
% ============================================================
% Loaded here unconditionally. The competition .sty can call
% \addto\captionsrussian{...} afterwards to adjust babel strings.
%
% fontenc/inputenc/mathtext are gone as of v1.5 (XeLaTeX) -- fontspec
% needs neither (XeTeX's input is natively UTF-8 and font selection is
% OpenType, not 8-bit NFSS encodings), and mathtext's whole job was
% letting pdfTeX accept literal Cyrillic inside math mode, which
% XeTeX/fontspec already does without help. \setmainfont etc. are
% deliberately NOT called here -- that's per-style, in
% olympiad-layout.sty's \ifOlympStyle...\fi blocks (see this class's
% own design contract at the top: no competition/style-specific
% layout in this file).
\RequirePackage{fontspec}
\RequirePackage{amsmath, amssymb, amsthm, amsfonts} % Advanced math structures
\RequirePackage[english, russian, strings]{babel}


% ============================================================
% DOCUMENT STRUCTURE COUNTERS
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
% task[type=subproblem] (see specific style .sty-files). Not parented to problemnum/
% subproblemnum like tasknum -- the environment itself resets it to 0
% at the start of EVERY type=subproblem block (self-contained, always
% starts at (a)), so an automatic parent-triggered reset would be
% redundant.
\newcounter{taskalphanum}

% blocknum: a single FLAT counter, unrelated to the
% problemnum/subproblemnum or solnum/subsolnum families, that steps
% once per \solution or \subsolution (see Parts 8-9). Its only job is
% giving \theHequation (olympiad-marking.sty) a plain, single-parent
% counter to anchor hyperref's PDF destination names to.
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
% type=jury (\ifOlympJury) and type=marking (\ifOlympMarking) both
% reuse the \ifOlympSolutions branch verbatim (solnum/subsolnum), not
% a no-op: \solution/\subsolution step those counters unconditionally
% regardless of type, so they're just as meaningful under either --
% jury is the dense internal scheme table, marking is the separate
% student-facing scheme document, and both number problems the same
% way solutions does (they're built from the same \solution/
% \subsolution calls, just followed by \input{marking.tex} instead of
% \input{solution.tex}).
% ============================================================
\newcommand{\OlympCurrentPrefix}{%
  \ifOlympProblems
    \arabic{problemnum}\printcounter{subproblemnum}%
  \fi
  \ifOlympSolutions
    \arabic{solnum}\printcounter{subsolnum}%
  \fi
  \ifOlympJury
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
    \ifOlympMarking\else\ifOlympJury\else % figures are not used here anyway
    \captionsetup[figure]{labelformat=olymp@figlabel, labelsep=space}%
    \fi\fi
  }%
}

\renewcommand{\thefigure}{\OlympCurrentPrefix.\arabic{figcounter}}

\RequirePackage{lipsum}

% ============================================================
% END OF olympiad.cls
% ============================================================