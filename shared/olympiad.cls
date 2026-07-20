\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{olympiad}[2027/01/01 v3.1 Competition-agnostic olympiad class]

% ============================================================
%  olympiad.cls  —  v3.1
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
%    1. Key-value option processing (language, tour, grade, type)
%    2. \ifOlymp... conditionals for layout files to branch on
%    3. \OlympLang — single active language code (ru / kz / ...)
%    4. \OlympString{key} — language-neutral slot accessor
%    5. task environment + tasknum / tasksolnum counters
%    6. \problem, \solution, \subproblem — structural commands
%    7. \tasksol, \taskref, \solref
%    8. \hints, \consts — slot-driven section headers
%    9. Caption label format hook
%
%  Depends on:  expl3, xparse, etoolbox, caption, babel
%  Does NOT load: geometry, fancyhdr, enumitem, siunitx,
%                 tikz, graphicx, amsmath, hyperref, ...
%                 (those belong in olympiad-layout / olympiad-math)
%
%  CHANGELOG v3.0 -> v3.1
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
% \g__olymp_lang_both_bool is derived, not a direct option value
\bool_new:N \g__olymp_lang_both_bool

% ---- set the documented defaults: language=ru, tour=theory, ----
% ---- grade=11, type=problems, font=12pt, year=2026          ----
\bool_gset_true:N \g__olymp_lang_ru_bool
\bool_gset_true:N \g__olymp_theory_bool
\bool_gset_true:N \g__olymp_problems_bool
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
            \bool_gset_false:N \g__olymp_lang_both_bool
          }
          {kz}   {
            \bool_gset_false:N \g__olymp_lang_ru_bool
            \bool_gset_true:N  \g__olymp_lang_kz_bool
            \bool_gset_false:N \g__olymp_lang_both_bool
          }
          {both} {
            \bool_gset_true:N \g__olymp_lang_ru_bool
            \bool_gset_true:N \g__olymp_lang_kz_bool
            \bool_gset_true:N \g__olymp_lang_both_bool
          }
        }
        {
          \ClassError{olympiad}
            { Unknown~value~`#1'~for~key~`language' }
            { Use~language=ru,~language=kz,~or~language=both. }
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
  }

\ProcessKeyOptions

\LoadClass[\g__olymp_font_tl]{article}

\RequirePackage{siunitx}         % loaded first — owns the S column

\RequirePackage{xparse}
\RequirePackage{etoolbox}
\RequirePackage{caption}

% Validation: language=both only valid with tour=experiment
\bool_lazy_and:nnT
  { \bool_if_p:N \g__olymp_lang_ru_bool }
  { \bool_if_p:N \g__olymp_lang_kz_bool }
  {
    \bool_if:NF \g__olymp_experiment_bool
      {
        \ClassError{olympiad}
          { language=both~requires~tour=experiment }
          { Use~language=ru~or~language=kz~for~theory~tours. }
      }
  }

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

\newif\ifOlympBoth
\bool_if:NTF \g__olymp_lang_both_bool  { \OlympBothtrue       } { \OlympBothfalse       }

% Per-language conditionals — one pair per supported language.
% Layout files use \ifOlympLangRu ... \fi
\newif\ifOlympLangRu
\bool_if:NTF \g__olymp_lang_ru_bool { \OlympLangRutrue } { \OlympLangRufalse }

\newif\ifOlympLangKz
\bool_if:NTF \g__olymp_lang_kz_bool { \OlympLangKztrue } { \OlympLangKzfalse }

% \OlympGrade — plain integer macro, usable in headers and \edef
\edef\OlympGrade { \int_use:N \g__olymp_grade_int }
\edef\OlympYear { \int_use:N \g__olymp_year_int }

\ExplSyntaxOff


% ============================================================
% PART 3 — \OlympLang AND THE STRING SLOT SYSTEM
% ============================================================
%
% \OlympLang expands to the active language code: "ru", "kz", ...
% In language=both builds it is not set here — layout code must
% handle bilingual output by calling \OlympString twice, once
% per language, or via \OlympStringBoth.
%
% \OlympString{key}
%   Expands to \OlympStr@<key>@<lang>.
%   build.py injects \def\OlympStr@<key>@<lang>{...} for every
%   string the layout needs.
%   olympiad-<comp>.sty defines fallback defaults.
%
% \OlympStringBoth{key}
%   For language=both builds: emits ru string, then kz string.
%   The separator is \OlympBothSep, defaulting to \quad.
%   Layout files can redefine \OlympBothSep as needed.
%
% Adding a new language: build.py injects the new lang's strings,
% the class gets a new \bool and \newif pair in parts 1–2,
% and \OlympLang gets set below. Nothing else changes.
% ============================================================

\def\OlympLang{ru}
\ifOlympLangRu \def\OlympLang{ru}\fi
\ifOlympLangKz \def\OlympLang{kz}\fi
% language=both: \OlympLang is intentionally left as the last
% assignment above (kz). Use \OlympStringBoth for bilingual output.

\newcommand{\OlympString}[1]{%
  \csname OlympStr@#1@\OlympLang\endcsname
}

\def\OlympBothSep{\quad}

\newcommand{\OlympStringBoth}[1]{%
  \csname OlympStr@#1@ru\endcsname
  \OlympBothSep
  \csname OlympStr@#1@kz\endcsname
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
%   solnum starts at -2 to handle the multi-part Problem 1
%   offset (see \subproblem).
%
% tasknum / tasksolnum: sub-item counters within a single
%   problem or solution. These MUST be LaTeX counters — build.py
%   cannot know in advance how many \item calls will appear.
% ============================================================

\newcounter{problemnum}             \setcounter{problemnum}{0}
\newcounter{tasknum}[problemnum]    \setcounter{tasknum}{0}
\newcounter{solnum}                 \setcounter{solnum}{-2}
\newcounter{tasksolnum}[solnum]     \setcounter{tasksolnum}{0}
\newcounter{figcounter}[problemnum] \setcounter{figcounter}{0}


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
    \captionsetup[figure]{labelformat=olymp@figlabel, labelsep=space}%
  }%
}

\renewcommand{\thefigure}{\arabic{problemnum}.\arabic{figcounter}}


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
  \setcounter{tasknum}{0}%
  \setcounter{figcounter}{0}
  \OlympProblemHeading{%
    \OlympString{problem}~\theproblemnum.~#1~(#2 баллов)%
  }%
}


% ============================================================
% PART 8 — \solution
% ============================================================
%
% \solution{Title}{Points}
%   Same argument contract as \problem.
%   Sets solnum and resets tasksolnum and equation counter.
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

\newcommand{\solution}[3]{%
  % #1 = number, #2 = title, #3 = points string
  \stepcounter{solnum}%
  \setcounter{tasksolnum}{0}%
  \setcounter{equation}{0}%
  \OlympSolutionHeading{%
    \OlympString{problem}~\thesolnum.~#1~(#2 баллов)%
  }%
}

% Solutions block header — emitted once, before first \solution
\newcommand{\solutionsheader}{%
  \newpage
  \thispagestyle{fancy}%
  \begin{center}
    \large\textbf{\textit{\OlympString{solutionsheader}}}%
  \end{center}%
  \vspace{2pt}%
}


% ============================================================
% PART 9 — \subproblem
% ============================================================
%
% \subproblem{Label}{Points}
%   For the multi-part Problem 1 pattern (parts А, Б, В).
%   Label  — single letter or short label, e.g. "А"
%   Points — already-formatted string from build.py
%
%   Increments solnum so that \eq numbering and \eqref refs
%   remain consistent across sub-problems.
%   Resets tasksolnum and equation counter per sub-problem.
%
%   Heading uses slot "subproblem" so competition .sty can
%   set:  \def\OlympStr@subproblem@ru{Задача 1}
%         \def\OlympStr@subproblem@kz{Есеп 1}
% ============================================================

\newcommand{\subproblem}[2]{%
  % #1 = label (e.g. А), #2 = points string
  \setcounter{tasksolnum}{0}%
  \setcounter{equation}{0}%
  \stepcounter{solnum}%
  \vspace{6pt}%
  \centerline{\textbf{\OlympString{subproblem}#1~(#2 балла)}}%
}

% ============================================================
% PART 10 — task ENVIRONMENT
% ============================================================
%
% Wraps numbered sub-tasks within a problem statement.
% Each \item auto-increments tasknum and produces label "N.M"
% where N = \theproblemnum, M = \arabic{tasknum}.
%
% Deliberately uses raw list — no enumitem keys here.
% olympiad-layout.sty issues \setlist or patches this env
% to control spacing, indentation, and font.
% ============================================================

\newenvironment{task}{%
  \begin{list}{}{%
    \setlength{\leftmargin}{18pt}%
    \setlength{\labelwidth}{0pt}%
    \setlength{\labelsep}{0pt}%
    \renewcommand{\makelabel}[1]{%
      \refstepcounter{tasknum}%
      \textbf{\theproblemnum.\arabic{tasknum}}~%
    }%
  }%
}{%
  \end{list}%
}


% ============================================================
% PART 11 — \tasksol, \taskref, \solref
% ============================================================
%
% \tasksol  — starts a solution sub-task, incrementing
%             tasksolnum and printing the "N.M" label
% \taskref{M} — bold reference to sub-task M of current problem
% \solref{M}  — bold reference to sub-task M of current solution
%
% \figref{N} — reference the Nth picture within the CURRENT problem
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


\newcommand{\figref}[1]{%
    \expanded{\noexpand\ref{fig:\theproblemnum-#1}}%
}
% (figcounter resets per \problem, see Part 7). Authors never type
% or track the problem number themselves: \theproblemnum is resolved
% at compile time, so figure references survive problems being
% reordered/renumbered by build.py. Pairs with the label key that
% \pic/\cpic/\cpics in olympiad-layout.sty must use:
%   \label{fig:\theproblemnum-\thefigcounter}
% instead of the old, collision-prone \label{\thefigcounter}.

% ============================================================
% PART 12 — \hints AND \consts
% ============================================================
%
% Slot-driven section headers. Competition .sty defines:
%   \OlympStr@hints@ru, \OlympStr@hints@kz
%   \OlympStr@consts@ru, \OlympStr@consts@kz
%
% No vertical spacing added here — layout .sty handles that
% via \AtBeginEnvironment or by redefining these commands.
% ============================================================

\newcommand{\hints}{%
  \begin{center}
    \textbf{\textit{\OlympString{hints}}}%
  \end{center}%
}

\newcommand{\consts}{%
  \begin{center}
    \textbf{\textit{\OlympString{consts}}}%
  \end{center}%
}

\RequirePackage{lipsum}

% ============================================================
% END OF olympiad.cls
% ============================================================