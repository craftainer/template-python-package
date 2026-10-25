#!/usr/bin/env bash
# Whether the Makefile in the current directory defines a rule for a target,
# without running any recipe (not even `$(MAKE)` lines).
#
# Usage: has_make_target.sh TARGET
# Exit:  0 = defined, 1 = not defined, 2 = the Makefile failed to parse
#        (make's output is printed).
#
# Reads make's rule database (`make -p`, documented in the GNU make manual
# under "Summary of Options") through a goal that does not exist, with `-q`
# so nothing runs. Within the dump, `# Not a target:` marks a name that is
# only a prerequisite or a file, which is not a rule, and a line like
# `target: VAR := x` is a target-specific variable, also not a rule.
#
# A Makefile that fails to parse either never reaches the dump or ends in an
# error besides the probe goal's own "No rule to make target": make's own
# diagnostics start with `file:line: ***` or `make: ***` (a bare `***` in
# the dump can be recipe or variable text, so only those count).
set -u
target=${1:?usage: has_make_target.sh TARGET}
out=$(LC_ALL=C make -pqRr ".${target}-probe" 2>&1 || true)
if ! grep -q '^# Make data base' <<< "$out" ||
  grep -E '^[^[:space:]#]+(:[0-9]+)?: \*\*\*' <<< "$out" | grep -qvF ".${target}-probe"; then
  echo "$out"
  exit 2
fi
awk -v t="$target" '
  /^# Not a target:/ { nt = 1; next }
  !nt && index($0, t ":") == 1 && $0 ~ ("^" t "::?( |$)") && $0 !~ /^[^ ]+:+ +[^ ]+ +[:+?!]*= / { found = 1 }
  { nt = 0 }
  END { exit !found }
' <<< "$out"
