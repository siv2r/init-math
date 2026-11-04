#!/usr/bin/env bash
if grep -q "$(printf '\r')" "$0" 2>/dev/null; then printf '%s\n' "setup.sh has Windows line endings. Fix it with:  tr -d '\r' < setup.sh > setup-fixed.sh  and run  bash setup-fixed.sh"; exit 1; fi #
# init-math setup.
#
# Checks what this computer has, writes a plan containing only the steps it still needs,
# shows you the plan, and runs it only if you say yes. Nothing is installed before that.
#
#   bash setup.sh                  check, write the plan, ask before running it
#   bash setup.sh --check          only report what is ready and what is missing
#   bash setup.sh --yes            run the plan without asking (steps that need you are
#                                  listed at the end instead of run)
#   bash setup.sh --plan-only      write the plan for you to read, and stop
#   bash setup.sh --harness claude | codex | both
#                                  which agent program to set up (asked if not given)
#   bash setup.sh --ssh            download init-math over SSH instead of HTTPS (sets up
#                                  an SSH key for GitHub if this computer has none)
#
# The plan is written to init-math-setup-plan.sh in the current folder. It is a plain
# script you can read before running; every step in it checks first and skips itself if
# it is already done, so running it again after a failure is safe.
#
# To update init-math later, download its newest version and run setup again: an older
# installed plugin is updated to the version of the folder setup.sh is in.

set -u

# init-math is public and is downloaded over HTTPS. Over SSH (--ssh, or INIT_MATH_REPO_URL
# set to a git@github.com: address, as for a private copy) the SSH key and access steps
# come in by themselves.
REPO_URL="${INIT_MATH_REPO_URL:-https://github.com/nkohen/init-math.git}"
SSH_URL="git@github.com:nkohen/init-math.git"
PLUGIN="init-math@init-math"
MARKETPLACE="init-math"
MIN_PY="3.11"
# The init-math version this setup came with: plugin.json next to this file, or (when run
# from Windows, which copies only this file into Linux) the version setup-windows.ps1 passes.
# An installed plugin older than this is updated; empty = unknown, nothing is compared.
WANT_VERSION="${INIT_MATH_VERSION:-}"
if [ -z "$WANT_VERSION" ] && [ -f "$(dirname "$0")/plugin.json" ]; then
  WANT_VERSION="$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$(dirname "$0")/plugin.json" | head -n 1)"
fi

MODE=run
HARNESS="${INIT_MATH_HARNESS:-}"
NONINTERACTIVE="${SETUP_NONINTERACTIVE:-0}"
SSH_FLAG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --check) MODE=check ;;
    --plan-only) MODE=plan ;;
    --yes) NONINTERACTIVE=1 ;;
    --harness) shift; HARNESS="${1:-}" ;;
    --harness=*) HARNESS="${1#--harness=}" ;;
    --ssh) [ -n "${INIT_MATH_REPO_URL:-}" ] || REPO_URL="$SSH_URL"; SSH_FLAG=" --ssh" ;;
    -h|--help) sed -n '3,24p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1 (try --help)"; exit 2 ;;
  esac
  shift
done
case "$HARNESS" in ""|claude|codex|both) ;; *) echo "--harness must be claude, codex or both"; exit 2 ;; esac

SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
PLAN="${INIT_MATH_PLAN:-$PWD/init-math-setup-plan.sh}"
# How to run setup again, in words for where the person started it.
if [ "${INIT_MATH_FROM_WINDOWS:-}" = 1 ]; then
  RERUN="in PowerShell, the same command as before: powershell -ExecutionPolicy Bypass -File setup-windows.ps1"
else
  RERUN="bash $SELF$SSH_FLAG"
fi
UNAME_S="${INIT_MATH_UNAME:-$(uname -s)}"
PROC_VERSION="${INIT_MATH_PROC_VERSION:-/proc/version}"

say() { printf '%s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

# ver_ge A B: is version A (like 3.12) at least B?
ver_ge() {
  a1=${1%%.*}; a2=${1#*.}; a2=${a2%%.*}
  b1=${2%%.*}; b2=${2#*.}; b2=${b2%%.*}
  [ "$a1" -gt "$b1" ] || { [ "$a1" -eq "$b1" ] && [ "$a2" -ge "$b2" ]; }
}

# ---------------------------------------------------------------- what kind of computer
OS=other; WSL=0; WSL1=0; PKG=none
case "$UNAME_S" in
  Darwin) OS=mac ;;
  Linux) OS=linux ;;
  MINGW*|MSYS*|CYGWIN*) OS=windows ;;
esac
if [ "$OS" = windows ]; then
  say "This looks like Windows (Git Bash or similar). init-math runs inside WSL, Windows'"
  say "built-in Linux. In PowerShell, in the folder holding these files, run:"
  say ""
  say "    powershell -ExecutionPolicy Bypass -File setup-windows.ps1"
  say ""
  say "It sets up WSL if needed and then runs this script inside it."
  exit 1
fi
if [ "$OS" = other ]; then
  say "This computer reports itself as '$UNAME_S'. init-math supports macOS and Linux"
  say "(including WSL on Windows)."
  exit 1
fi
if [ "$OS" = linux ] && grep -qi microsoft "$PROC_VERSION" 2>/dev/null; then
  WSL=1
  grep -qi 'wsl2' "$PROC_VERSION" 2>/dev/null || WSL1=1
fi
# Where Homebrew puts itself: /opt/homebrew on Apple-chip Macs, /usr/local on Intel ones.
BREW_DIRS="${INIT_MATH_BREW_DIRS:-/opt/homebrew/bin /usr/local/bin}"
brew_somewhere() { for d in $BREW_DIRS; do [ -x "$d/brew" ] && return 0; done; return 1; }
if [ "$OS" = mac ]; then
  if have brew; then PKG=brew
  elif brew_somewhere; then PKG=brew-off-path
  fi
elif have apt-get; then PKG=apt
elif have dnf; then PKG=dnf
fi
OS_LABEL="Linux"
[ "$OS" = mac ] && OS_LABEL="macOS $(sw_vers -productVersion 2>/dev/null)"
[ "$WSL" = 1 ] && OS_LABEL="Linux in WSL (${WSL_DISTRO_NAME:-unknown distribution})"

# On a Mac without the Command Line Tools, /usr/bin/python3 and /usr/bin/git are stand-ins
# that open an install dialog when run. Never run them blind.
CLT=1
if [ "$OS" = mac ] && ! xcode-select -p >/dev/null 2>&1; then CLT=0; fi
STUB_DIR="${INIT_MATH_STUB_DIR:-/usr/bin}"
is_stub() { [ "$OS" = mac ] && [ "$CLT" = 0 ] && [ "$(command -v "$1")" = "$STUB_DIR/$1" ]; }

# ---------------------------------------------------------------- checks
PY_VER=""; PY_STATE=missing
if have python3 && ! is_stub python3; then
  PY_VER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)"
  if [ -n "$PY_VER" ] && ver_ge "$PY_VER" "$MIN_PY"; then PY_STATE=ok
  elif [ -n "$PY_VER" ]; then PY_STATE=old
  fi
fi
GIT_STATE=missing
if have git && ! is_stub git; then GIT_STATE=ok; fi
CURL_STATE=missing; have curl && CURL_STATE=ok

USE_SSH=0
case "$REPO_URL" in git@*) USE_SSH=1 ;; esac
KEY_STATE=none; KEY_PRIV=""; GH_STATE=unknown; ACCESS_STATE=unknown
if [ "$USE_SSH" = 1 ]; then
  for k in id_ed25519 id_ecdsa id_rsa; do
    if [ -f "$HOME/.ssh/$k.pub" ]; then KEY_STATE=present; KEY_PRIV="$HOME/.ssh/$k"; break; fi
  done
  if have ssh; then
    if ssh -T -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 \
        git@github.com 2>&1 | grep -q "successfully authenticated"; then
      GH_STATE=ok
    else
      GH_STATE=no
    fi
  fi
  if [ "$GH_STATE" = ok ] && [ "$GIT_STATE" = ok ]; then
    if GIT_SSH_COMMAND="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new" \
        git ls-remote "$REPO_URL" HEAD >/dev/null 2>&1; then
      ACCESS_STATE=ok
    else
      ACCESS_STATE=no
    fi
  fi
fi

# A key with a passphrase cannot be used by these unattended checks unless an SSH agent
# holds it unlocked.
KEY_LOCKED=0
if [ "$KEY_STATE" = present ] && [ "$GH_STATE" != ok ] && [ -f "$KEY_PRIV" ] && have ssh-keygen \
    && ! ssh-keygen -y -P "" -f "$KEY_PRIV" >/dev/null 2>&1; then
  KEY_LOCKED=1
fi

# The name and email git records as the author of each change in a project.
GITID_STATE=missing
if [ "$GIT_STATE" = ok ] && [ -n "$(git config --global user.name 2>/dev/null)" ] \
    && [ -n "$(git config --global user.email 2>/dev/null)" ]; then
  GITID_STATE=ok
fi

# Homebrew installs only from an administrator account.
MAC_ADMIN=1
if [ "$OS" = mac ] && ! id -Gn 2>/dev/null | tr ' ' '\n' | grep -qx admin; then MAC_ADMIN=0; fi

# The installed plugin's version, or nothing if unknown. Claude: `plugin list --json`;
# Codex: the first x.y.z on the plugin's `plugin list` line (its columns vary).
plugin_version() {
  if [ "$1" = claude ]; then
    claude plugin list --json 2>/dev/null | tr -d '\n' | sed -n 's/.*"id": *"'"$PLUGIN"'"[^}]*"version": *"\([^"]*\)".*/\1/p'
  else
    codex plugin list 2>/dev/null | awk -v p="$PLUGIN" '$1 == p && /installed/ {
      for (i = 2; i <= NF; i++) if ($i ~ /^[0-9]+\.[0-9]+\.[0-9]+/) { print $i; exit } }'
  fi
}

# harness_state NAME: missing | off-path | logged-out | ready | plugin-old | plugin-ok
harness_state() {
  name=$1
  if ! have "$name"; then
    if [ -x "$HOME/.local/bin/$name" ]; then echo off-path; else echo missing; fi
    return
  fi
  if [ "$name" = claude ]; then
    claude auth status --json >/dev/null 2>&1 || { echo logged-out; return; }
    claude plugin list --json 2>/dev/null | grep -q "\"$PLUGIN\"" || { echo ready; return; }
  else
    codex login status >/dev/null 2>&1 || { echo logged-out; return; }
    codex plugin list 2>/dev/null | grep -Eq "^$PLUGIN +installed" || { echo ready; return; }
  fi
  have="$(plugin_version "$name")"
  if [ -n "$WANT_VERSION" ] && [ -n "$have" ] && [ "$have" != "$WANT_VERSION" ]; then
    echo plugin-old
  else
    echo plugin-ok
  fi
}
CLAUDE_STATE="$(harness_state claude)"
CODEX_STATE="$(harness_state codex)"

if [ -z "$HARNESS" ]; then
  if [ "$CLAUDE_STATE" != missing ] && [ "$CODEX_STATE" != missing ]; then HARNESS=both
  elif [ "$CLAUDE_STATE" != missing ]; then HARNESS=claude
  elif [ "$CODEX_STATE" != missing ]; then HARNESS=codex
  elif [ "$MODE" != check ] && [ "$NONINTERACTIVE" != 1 ]; then
    say ""
    say "Which agent program will you use? Pick the one you have a subscription for:"
    say "  1) Claude Code (Anthropic: a Claude Pro or Max plan, or an API key)"
    say "  2) Codex (OpenAI: a ChatGPT Plus, Pro or Team plan, or an API key)"
    say "  3) both"
    printf 'Your choice [1]: '
    { read -r ans </dev/tty; } 2>/dev/null || ans=""
    case "$ans" in 2) HARNESS=codex ;; 3) HARNESS=both ;; *) HARNESS=claude ;; esac
  else
    HARNESS=claude
  fi
fi
WANT_CLAUDE=0; WANT_CODEX=0
case "$HARNESS" in claude) WANT_CLAUDE=1 ;; codex) WANT_CODEX=1 ;; both) WANT_CLAUDE=1; WANT_CODEX=1 ;; esac

# ---------------------------------------------------------------- report
TODO=0
row() { printf '  %-10s %s\n' "$1" "$2"; [ "$1" = OK ] || TODO=$((TODO + 1)); }
say ""
say "Checking this computer ($OS_LABEL):"
if [ "$WSL1" = 1 ]; then
  row "TO DO" "WSL version 1: Claude Code and Codex need WSL 2 (the plan says how)"
fi
case "$PY_STATE" in
  ok) row OK "Python $PY_VER" ;;
  old) row "TO DO" "Python $PY_VER is too old; $MIN_PY or newer is needed" ;;
  *) row "TO DO" "Python $MIN_PY or newer: not found" ;;
esac
if [ "$GIT_STATE" = ok ]; then row OK "git"; else row "TO DO" "git: not found"; fi
if [ "$GITID_STATE" = ok ]; then row OK "git knows your name and email"
elif [ "$GIT_STATE" = ok ]; then row "NEEDS YOU" "git does not know your name and email yet"; fi
if [ "$CURL_STATE" = ok ]; then row OK "curl"; else row "TO DO" "curl: not found"; fi
if [ "$USE_SSH" = 1 ]; then
  if [ "$GH_STATE" = ok ]; then row OK "GitHub recognizes your SSH key"
  elif [ "$KEY_LOCKED" = 1 ]; then row "NEEDS YOU" "your SSH key has a passphrase, which these checks cannot type"
  elif [ "$KEY_STATE" = present ]; then row "NEEDS YOU" "GitHub does not recognize your SSH key yet"
  else row "NEEDS YOU" "no SSH key yet (GitHub needs one to download init-math)"
  fi
  case "$ACCESS_STATE" in
    ok) row OK "you can download init-math from GitHub" ;;
    no) row "NEEDS YOU" "your GitHub account cannot see this copy of init-math yet: ask its owner to add it" ;;
  esac
fi
hrow() {
  label=$1; st=$2
  case "$st" in
    plugin-ok) row OK "$label, logged in, init-math installed" ;;
    plugin-old) row "TO DO" "$label has init-math $(plugin_version "$3") installed; setup updates it to $WANT_VERSION" ;;
    ready) row "TO DO" "$label is ready; init-math is not installed in it yet" ;;
    logged-out) row "NEEDS YOU" "$label is installed but not logged in" ;;
    off-path) row "TO DO" "$label is installed but your terminal cannot find it (PATH)" ;;
    *) row "TO DO" "$label: not installed" ;;
  esac
}
[ "$WANT_CLAUDE" = 1 ] && hrow "Claude Code" "$CLAUDE_STATE" claude
[ "$WANT_CODEX" = 1 ] && hrow "Codex" "$CODEX_STATE" codex
if [ "$OS" = mac ] && [ "$MAC_ADMIN" = 0 ] && [ "$PKG" = none ] && { [ "$PY_STATE" != ok ] || [ "$GIT_STATE" != ok ]; }; then
  row "NEEDS YOU" "this Mac account is not an administrator, which installing Homebrew needs"
fi
if [ "$TODO" != 0 ]; then
  say ""
  say "  (TO DO: setup does it for you.  NEEDS YOU: setup asks you to do something along the way.)"
fi

next_steps() {
  say ""
  if [ "$WSL" = 1 ]; then
    D="${WSL_DISTRO_NAME:-Ubuntu-24.04}"
    say "Next: open this Linux. In PowerShell type  wsl -d $D  (or, for Ubuntu 24.04, choose"
    say "'Ubuntu 24.04 LTS' in the Start menu; an older 'Ubuntu' entry there is a different Linux)."
    say "Then type these lines in it to make a folder for your projects and start the agent"
    say "program there:"
  else
    say "Next: open a NEW terminal window, then make a folder for your projects and start the"
    say "agent program there:"
  fi
  say ""
  say "    mkdir -p ~/research && cd ~/research"
  say ""
  say "(~/research holds your projects; the interview makes each project's own folder inside it.)"
  if [ "$WANT_CLAUDE" = 1 ]; then
    say "    claude"
    say ""
    say "and type  /init-math:init-math  into Claude Code."
  fi
  if [ "$WANT_CODEX" = 1 ]; then
    [ "$WANT_CLAUDE" = 1 ] && say "" && say "or, for Codex:" && say ""
    say "    codex"
    say ""
    say "and type  Use the init-math:init-math skill to set up a research project.  into Codex."
  fi
  say ""
  say "The first time, the agent program asks a few setup questions (Claude Code: a colour"
  say "theme, any is fine) and whether you trust the folder (yes). During the interview it"
  say "asks before running each command on your computer: the interview's own commands are"
  say "init-math's checks (they start with  python3  and mention init_project.py) and look-ups"
  say "of which programs you have. The interview asks before it creates anything."
}

if [ "$TODO" = 0 ]; then
  say ""
  say "Everything is ready."
  next_steps
  exit 0
fi
if [ "$MODE" = check ]; then
  say ""
  if [ "${INIT_MATH_FROM_WINDOWS:-}" = 1 ]; then
    say "Not ready yet. In PowerShell, run  powershell -ExecutionPolicy Bypass -File setup-windows.ps1"
    say "(without -Check) to get a plan that fixes this."
  else
    say "Not ready yet. Run  bash $SELF$SSH_FLAG  (without --check) to get a plan that fixes this."
  fi
  exit 1
fi

# ---------------------------------------------------------------- write the plan
STEPS=""; NSTEPS=0; YOU=""
add_you() { case "$YOU" in *"- $1"*) ;; *) YOU="$YOU
  - $1" ;; esac; }

{
cat <<EOF
#!/usr/bin/env bash
# init-math setup plan for this computer ($OS_LABEL), written by setup.sh on $(date '+%Y-%m-%d %H:%M').
#
# It contains only the steps this computer still needs. Every step checks first and
# skips itself if the work is already done, so you can run this file again after fixing
# a problem. Steps marked "needs you" stop and tell you what to do.
#
# Run it with:  bash $PLAN

set -Eeo pipefail
REPO_URL='$REPO_URL'
PLUGIN='$PLUGIN'
MARKETPLACE='$MARKETPLACE'
WANT_VERSION='$WANT_VERSION'
SETUP_SH='$SELF'
RERUN='$RERUN'
OS='$OS'
STUB_DIR='$STUB_DIR'
NONINTERACTIVE="\${SETUP_NONINTERACTIVE:-0}"
EOF
[ "$OS" = mac ] && printf "BREW_DIRS='%s'\n" "$BREW_DIRS"
cat <<'EOF'
LEFT_FOR_YOU=""
STEP=""
trap 'echo; echo "Stopped during step: $STEP"; echo "Fix the problem shown above, then run this setup again: $RERUN"; echo "If you cannot tell what went wrong: everything shown here is also in ~/init-math-setup.log. Ask the agent helping you to read it, or report it at https://github.com/nkohen/init-math/issues."' ERR

# A step that needs you: in unattended runs, note it and move on.
needs_you() {
  if [ "$NONINTERACTIVE" = 1 ]; then
    case "$LEFT_FOR_YOU" in *"- $1"*) ;; *) LEFT_FOR_YOU="$LEFT_FOR_YOU
  - $1" ;; esac
    echo "  (left for you: $1)"
    return 1
  fi
  return 0
}
# Something only you can do, which does not stop the rest of the plan: listed at the end.
leave_for_you() {
  case "$LEFT_FOR_YOU" in *"- $1"*) ;; *) LEFT_FOR_YOU="$LEFT_FOR_YOU
  - $1" ;; esac
}
pause() { printf '\n%s ' "$1"; read -r _ </dev/tty; }
# Print a step's explanation (the comment lines under its heading in this file).
why() {
  awk -v h="# ---- Step $1:" 'index($0, h) == 1 { f = 1; next }
    f && /^# Needs you:/ { next }
    f && /^STEP=/ { next }
    f && /^echo; echo "== Step/ { next }
    f && /^#/ { sub(/^# ?/, "   "); print; next }
    f { exit }' "$0"
}
# Run as root (as in a container) without sudo; otherwise sudo asks for your password.
SUDO=sudo; [ "$(id -u)" = 0 ] && SUDO=""
# On a Mac without Apple's Command Line Tools, /usr/bin/python3 and /usr/bin/git only
# open an install dialog. Treat them as missing.
stub() { [ "$OS" = mac ] && ! xcode-select -p >/dev/null 2>&1 && [ "$(command -v "$1")" = "$STUB_DIR/$1" ]; }

# The file your shell reads when a new terminal opens.
profile_file() {
  case "${SHELL:-}" in
    */zsh) echo "$HOME/.zshrc" ;;
    *) if [ "$OS" = mac ]; then echo "$HOME/.bash_profile"; else echo "$HOME/.bashrc"; fi ;;
  esac
}
# Add a line to that file once, and apply it to this run too.
add_to_profile() {
  f="$(profile_file)"
  touch "$f"
  grep -qxF "$1" "$f" || { printf '\n# added by init-math setup\n%s\n' "$1" >> "$f"; echo "  added to $f: $1"; }
  eval "$1"
}
python_ok() { command -v python3 >/dev/null 2>&1 && ! stub python3 && python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; }
repo_ok() {
  case "$REPO_URL" in git@*) ;; *) return 0 ;; esac
  GIT_SSH_COMMAND="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new" git ls-remote "$REPO_URL" HEAD >/dev/null 2>&1
}
open_url() {
  if [ "$OS" = mac ]; then open "$1"; return 0; fi
  for o in wslview explorer.exe xdg-open; do
    command -v "$o" >/dev/null 2>&1 && { "$o" "$1" >/dev/null 2>&1; return 0; }
  done
  return 0
}
EOF
} > "$PLAN.tmp"

step() {  # step TITLE NEEDS-YOU(what, or "") BODY(from stdin)
  NSTEPS=$((NSTEPS + 1))
  STEPS="$STEPS
  $NSTEPS. $1${2:+  [you: $2]}"
  [ -n "$2" ] && add_you "$2"
  {
    printf '\n# ---- Step %s: %s\n' "$NSTEPS" "$1"
    [ -n "$2" ] && printf '# Needs you: %s.\n' "$2"
    printf 'STEP=%q\necho; echo "== Step %s: %s"; why %s || true\n' "$1" "$NSTEPS" "$1" "$NSTEPS"
    cat
  } >> "$PLAN.tmp"
}

if [ "$WSL1" = 1 ]; then
  step "Switch this Linux to WSL 2" "run one command in Windows PowerShell" <<EOF
# Why: Claude Code and Codex do not run on WSL version 1.
echo "In Windows PowerShell, run:   wsl --set-version ${WSL_DISTRO_NAME:-Ubuntu} 2"
echo "then run this setup again:   \$RERUN"
exit 1
EOF
fi

if [ "$OS" = mac ]; then
  if [ "$PKG" = none ] && { [ "$PY_STATE" != ok ] || [ "$GIT_STATE" != ok ]; }; then
    step "Install Homebrew (the standard Mac package installer)" "type your Mac password" <<'EOF'
# Why: Python and git are installed with it. Its installer also installs Apple's
# Command Line Tools if they are missing. Official command from https://brew.sh
# It asks you to press Return, then for your Mac login password: nothing appears while
# you type, which is normal. Downloading Apple's tools can take many minutes with little
# on screen. At the end it prints "Next steps" about your PATH: ignore them, the next
# step of this plan does that for you.
brew_dir() { for d in $BREW_DIRS; do [ -x "$d/brew" ] && { echo "$d"; return 0; }; done; return 1; }
if ! command -v brew >/dev/null 2>&1 && ! brew_dir >/dev/null && needs_you "install Homebrew (it asks for your Mac password)"; then
  if ! id -Gn | tr ' ' '\n' | grep -qx admin; then
    echo "Homebrew can only be installed from an administrator account, and this Mac account"
    echo "is not one. Ask whoever manages this Mac to do one of these, then run this setup"
    echo "again:  $RERUN"
    echo "  - install Homebrew (https://brew.sh), or make you an administrator;"
    echo "  - or install Python 3.11 or newer from https://www.python.org/downloads/macos/ and"
    echo "    Apple's Command Line Tools (xcode-select --install, for git)."
    exit 1
  fi
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
EOF
  fi
  if [ "$PKG" != brew ] && { [ "$PKG" != none ] || [ "$PY_STATE" != ok ] || [ "$GIT_STATE" != ok ]; }; then
    step "Make Homebrew available in every new terminal" "" <<'EOF'
# Why: Homebrew's installer asks you to do this yourself; this does it for you.
for d in $BREW_DIRS; do
  if [ -x "$d/brew" ]; then add_to_profile "eval \"\$($d/brew shellenv)\""; break; fi
done
EOF
  fi
  if [ "$PY_STATE" != ok ]; then
    step "Install Python with Homebrew" "" <<'EOF'
# Why: the projects' checks and hooks run python3 and need version 3.11 or newer.
python_ok || brew install python
hash -r
python_ok || { echo "python3 is still older than 3.11 here: $(command -v python3)"; false; }
EOF
  fi
  if [ "$GIT_STATE" != ok ]; then
    step "Install git with Homebrew" "" <<'EOF'
# Why: every project is a git repository, and init-math is downloaded with git.
if ! command -v git >/dev/null 2>&1 || stub git; then brew install git; hash -r; fi
EOF
  fi
else
  NEED_PKGS=""
  [ "$PY_STATE" = missing ] && NEED_PKGS="$NEED_PKGS python3"
  [ "$GIT_STATE" != ok ] && NEED_PKGS="$NEED_PKGS git"
  [ "$CURL_STATE" != ok ] && NEED_PKGS="$NEED_PKGS curl"
  if [ "$USE_SSH" = 1 ] && ! have ssh; then NEED_PKGS="$NEED_PKGS ssh"; fi
  # The step skips itself once every one of these commands exists.
  HAVE_ALL=""
  for c in $NEED_PKGS; do HAVE_ALL="${HAVE_ALL:+$HAVE_ALL && }command -v $c >/dev/null 2>&1"; done
  PW_NOTE="# It asks for your Linux password (on Windows: the one you chose when Ubuntu was
# installed). Nothing appears while you type, which is normal; press Enter when done."
  if [ -n "$NEED_PKGS" ]; then
    case "$PKG" in
      apt)
        APT_PKGS="${NEED_PKGS/ ssh/ openssh-client}"
        step "Install${NEED_PKGS} with apt" "type your Linux password" <<EOF
# Why: the projects' checks and hooks run python3 (3.11 or newer), projects are git
# repositories, and the installers below are downloaded with curl.
$PW_NOTE
if ! { $HAVE_ALL; }; then
  \$SUDO apt-get update
  \$SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y${APT_PKGS}
  hash -r
fi
EOF
        ;;
      dnf)
        DNF_PKGS="${NEED_PKGS/ ssh/ openssh-clients}"
        step "Install${NEED_PKGS} with dnf" "type your Linux password" <<EOF
# Why: the projects' checks and hooks run python3 (3.11 or newer), projects are git
# repositories, and the installers below are downloaded with curl.
$PW_NOTE
if ! { $HAVE_ALL; }; then
  \$SUDO dnf install -y${DNF_PKGS}
  hash -r
fi
EOF
        ;;
      *)
        step "Install${NEED_PKGS}" "install some programs yourself" <<EOF
echo "This Linux has neither apt nor dnf, so install these yourself:${NEED_PKGS}"
echo "(python3 must be 3.11 or newer), then run this setup again:  \$RERUN"
exit 1
EOF
        ;;
    esac
  fi
  if [ "$PY_STATE" != ok ]; then
    if [ "$WSL" = 1 ]; then
      OLD_PY_ADVICE="echo 'This Linux is too old for init-math. Run setup-windows.ps1 again from Windows PowerShell:'
echo 'it installs Ubuntu 24.04 next to this one (which it leaves as it is) and uses that.'"
    else
      OLD_PY_ADVICE="echo 'Install Python 3.11 or newer so that  python3 --version  shows it (a newer release of your'
echo 'Linux distribution is the simplest way), then run this setup again:  \$RERUN'"
    fi
    step "Check that Python is 3.11 or newer" "" <<EOF
# Why: older system Pythons cannot run the projects' checks.
if ! python_ok; then
  echo "python3 here is \$(python3 --version 2>&1); init-math needs 3.11 or newer."
  $OLD_PY_ADVICE
  exit 1
fi
EOF
  fi
fi

if [ "$GITID_STATE" != ok ]; then
  step "Tell git your name and email" "type your name and email" <<'EOF'
# Why: a project records who made each change, and git asks for a name and email before
# it records anything. They are saved on this computer, in ~/.gitconfig, and appear in a
# project's history; they leave this computer only if you share a project.
if [ -z "$(git config --global user.name)" ] || [ -z "$(git config --global user.email)" ]; then
  if needs_you "tell git your name and email"; then
    printf 'Your name (for example Jane Doe): '; read -r n </dev/tty
    printf 'Your email: '; read -r e </dev/tty
    [ -n "$n" ] && git config --global user.name "$n"
    [ -n "$e" ] && git config --global user.email "$e"
  fi
fi
EOF
fi

if [ "$USE_SSH" = 1 ] && [ "$GH_STATE" != ok ]; then
  if [ "$KEY_STATE" != present ]; then
    step "Create an SSH key (this computer's ID for GitHub)" "" <<'EOF'
# Why: over SSH, GitHub lets you download init-math only from a computer it
# recognizes. The key is two files in ~/.ssh: a private one that never leaves
# this computer, and a public one (ending in .pub) that you give to GitHub. It is made
# without a passphrase, because this setup's checks cannot type one.
if [ ! -f "$HOME/.ssh/id_ed25519.pub" ] && [ ! -f "$HOME/.ssh/id_ecdsa.pub" ] && [ ! -f "$HOME/.ssh/id_rsa.pub" ]; then
  mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
  ssh-keygen -q -t ed25519 -N "" -f "$HOME/.ssh/id_ed25519" -C "init-math ${USER:-$(id -un)}@$(uname -n)"
  echo "   Created ~/.ssh/id_ed25519 (private) and ~/.ssh/id_ed25519.pub (public)."
fi
EOF
  fi
  if [ "$KEY_LOCKED" = 1 ]; then
    if [ "$OS" = mac ]; then
      step "Unlock your SSH key in the Mac keychain" "type your SSH key's passphrase once" <<EOF
# Why: your key has a passphrase, which this setup's checks cannot type. This stores it
# in your Mac keychain, as GitHub's guide suggests, so it is not asked again.
gh_ok() { ssh -T -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 git@github.com 2>&1 | grep -q "successfully authenticated"; }
if ! gh_ok && needs_you "unlock your SSH key (it has a passphrase)"; then
  ssh-add --apple-use-keychain '$KEY_PRIV'
fi
EOF
    else
      step "Load your SSH key into an SSH agent" "unlock your SSH key" <<EOF
# Why: your key has a passphrase, which this setup's checks cannot type.
gh_ok() { ssh -T -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 git@github.com 2>&1 | grep -q "successfully authenticated"; }
if ! gh_ok; then
  leave_for_you "unlock your SSH key, then run setup again in the same window (see below)"
  echo "Your SSH key ($KEY_PRIV) has a passphrase, which this setup's checks cannot type."
  if [ "\${INIT_MATH_FROM_WINDOWS:-}" = 1 ]; then
    echo "In PowerShell, type  wsl -d \$WSL_DISTRO_NAME  to open this Linux, run these three lines there"
    echo "(the second asks for the passphrase):"
    echo '    eval "\$(ssh-agent -s)"'
    echo "    ssh-add '$KEY_PRIV'"
    echo "    bash ~/init-math-setup.sh"
  else
    echo "In this window, run these two lines (the second asks for the passphrase), then run"
    echo "setup again in the same window:"
    echo '    eval "\$(ssh-agent -s)"'
    echo "    ssh-add '$KEY_PRIV'"
  fi
  exit 1
fi
EOF
    fi
  fi
  step "Add the key to your GitHub account" "paste your key into a GitHub web page" <<'EOF'
# Why: GitHub must know this computer's key before it lets it download init-math.
# You paste the PUBLIC half of the key (the .pub file); that is safe to share. The
# private half never leaves this computer.
gh_ok() { ssh -T -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 git@github.com 2>&1 | grep -q "successfully authenticated"; }
if ! gh_ok && needs_you "add your SSH key to GitHub"; then
  for k in id_ed25519 id_ecdsa id_rsa; do [ -f "$HOME/.ssh/$k.pub" ] && { KEY="$HOME/.ssh/$k.pub"; break; }; done
  echo "Your public key (one line):"; echo; cat "$KEY"; echo
  if command -v pbcopy >/dev/null 2>&1; then pbcopy < "$KEY" && echo "(It is also copied to your clipboard.)"
  elif command -v clip.exe >/dev/null 2>&1; then clip.exe < "$KEY" && echo "(It is also copied to your clipboard.)"
  fi
  echo "A GitHub page opens (sign in if asked): https://github.com/settings/ssh/new"
  echo "Give the key any title, paste the line above into \"Key\", and click \"Add SSH key\"."
  open_url "https://github.com/settings/ssh/new"
  tries=0
  until gh_ok; do
    tries=$((tries + 1))
    [ "$tries" -gt 3 ] && { echo "GitHub still does not recognize the key. Check that you pasted the whole line, starting with ssh-."; false; }
    pause "Press Enter when you have added it..."
  done
  echo "GitHub recognizes this computer."
fi
EOF
fi
if [ "$USE_SSH" = 1 ] && [ "$ACCESS_STATE" != ok ]; then
  step "Check that your GitHub account can see init-math" "ask its owner for access, if you have not yet" <<'EOF'
# Why: a private copy lets in only the GitHub accounts its owner adds. If yours
# cannot see it yet, the rest of the plan still runs and this is listed at the end.
if ! repo_ok; then
  leave_for_you "get access to init-math: send its owner your GitHub user name, accept the invitation (by email, or on https://github.com/notifications), then run setup again"
  echo "Your GitHub account cannot see init-math yet; the plan continues without it."
fi
EOF
fi

if [ "$WANT_CLAUDE" = 1 ]; then
  if [ "$CLAUDE_STATE" = missing ]; then
    step "Install Claude Code" "" <<'EOF'
# Why: Claude Code is the agent program that runs the interview and your projects.
# Official installer from https://code.claude.com/docs/en/setup
# If it prints advice about your PATH, ignore it: the next step does that.
command -v claude >/dev/null 2>&1 || [ -x "$HOME/.local/bin/claude" ] || curl -fsSL https://claude.ai/install.sh | bash
EOF
  fi
  if [ "$CLAUDE_STATE" = missing ] || [ "$CLAUDE_STATE" = off-path ]; then
    step "Let your terminal find Claude Code" "" <<'EOF'
# Why: the installer puts claude in ~/.local/bin, which new terminals may not search.
command -v claude >/dev/null 2>&1 || add_to_profile 'export PATH="$HOME/.local/bin:$PATH"'
EOF
  fi
  if [ "$CLAUDE_STATE" != ready ] && [ "$CLAUDE_STATE" != plugin-ok ] && [ "$CLAUDE_STATE" != plugin-old ]; then
    step "Log in to Claude Code" "sign in to Claude in your web browser" <<'EOF'
# Why: Claude Code works under your Anthropic account (a Claude plan or an API key).
# A browser window opens for you to sign in. If none does, press c to copy the link and
# paste it into your browser. If the browser then shows a code, copy it, paste it here
# and press Enter. (To paste in this window: Cmd+V on a Mac, right-click or Ctrl+Shift+V
# elsewhere.)
if ! claude auth status --json >/dev/null 2>&1 && needs_you "log in to Claude Code"; then
  claude auth login
fi
EOF
  fi
  step "Install or update the init-math plugin in Claude Code" "" <<'EOF'
# Why: the plugin holds the interview that creates your project. Every command here is
# safe to repeat: they report "already installed" or "already at the latest version".
# The last two fetch init-math's newest version and update an older installed copy.
if ! repo_ok; then
  leave_for_you "install the init-math plugin: run setup again once GitHub lets you download init-math"
  echo "Skipped: GitHub does not let this computer download init-math yet."
elif claude auth status --json >/dev/null 2>&1; then
  claude plugin marketplace add "$REPO_URL"
  claude plugin install "$PLUGIN"
  claude plugin marketplace update "$MARKETPLACE" || echo "(Could not update init-math here; the final check below says if it is out of date.)"
  claude plugin update "$PLUGIN" || echo "(Could not update init-math here; the final check below says if it is out of date.)"
fi
EOF
fi

if [ "$WANT_CODEX" = 1 ]; then
  if [ "$CODEX_STATE" = missing ]; then
    step "Install Codex" "" <<'EOF'
# Why: Codex is the agent program that runs the interview and your projects.
# Official installer from https://learn.chatgpt.com/docs/codex/cli (it also adds itself
# to your shell's startup file; if it suggests restarting the terminal, there is no need).
command -v codex >/dev/null 2>&1 || [ -x "$HOME/.local/bin/codex" ] || curl -fsSL https://chatgpt.com/codex/install.sh | sh
EOF
  fi
  if [ "$CODEX_STATE" = missing ] || [ "$CODEX_STATE" = off-path ]; then
    step "Let your terminal find Codex" "" <<'EOF'
command -v codex >/dev/null 2>&1 || add_to_profile 'export PATH="$HOME/.local/bin:$PATH"'
EOF
  fi
  if [ "$CODEX_STATE" != ready ] && [ "$CODEX_STATE" != plugin-ok ] && [ "$CODEX_STATE" != plugin-old ]; then
    step "Log in to Codex" "sign in to ChatGPT in your web browser" <<'EOF'
# Why: Codex works under your OpenAI account (a ChatGPT plan or an API key).
# A browser window opens for you to sign in. If none does, copy the link shown into your
# browser. If the browser says it cannot reach the page (common on Windows), press
# Ctrl-C here and run  codex login --device-auth  instead, which shows a code to enter
# on a web page.
if ! codex login status >/dev/null 2>&1 && needs_you "log in to Codex"; then
  codex login
fi
EOF
  fi
  step "Install or update the init-math plugin in Codex" "" <<'EOF'
# Why: the plugin holds the interview that creates your project. Every command here is
# safe to repeat. The upgrade fetches init-math's newest version; Codex keeps an installed
# plugin as it was, so an older copy is removed and installed again (your projects do not
# depend on it: each one is independent of init-math once created).
if ! repo_ok; then
  leave_for_you "install the init-math plugin: run setup again once GitHub lets you download init-math"
  echo "Skipped: GitHub does not let this computer download init-math yet."
elif codex login status >/dev/null 2>&1; then
  codex plugin marketplace add "$REPO_URL"
  codex plugin add "$PLUGIN"
  codex plugin marketplace upgrade "$MARKETPLACE" || echo "(Could not update init-math here; the final check below says if it is out of date.)"
  have="$(codex plugin list 2>/dev/null | awk -v p="$PLUGIN" '$1 == p && /installed/ {
    for (i = 2; i <= NF; i++) if ($i ~ /^[0-9]+\.[0-9]+\.[0-9]+/) { print $i; exit } }')"
  if [ -n "$WANT_VERSION" ] && [ -n "$have" ] && [ "$have" != "$WANT_VERSION" ]; then
    echo "init-math $have is installed; installing $WANT_VERSION."
    codex plugin remove "$PLUGIN" && codex plugin add "$PLUGIN" || echo "(Could not update init-math here; the final check below says if it is out of date.)"
  fi
fi
EOF
fi

cat >> "$PLAN.tmp" <<EOF

# ---- Last: check everything again.
STEP="final check"
trap - ERR
if [ -n "\$LEFT_FOR_YOU" ]; then
  echo; echo "Left for you to do:\$LEFT_FOR_YOU"
  echo; echo "Then run this setup again:  \$RERUN"
fi
echo; echo "== Final check"
INIT_MATH_REPO_URL="\$REPO_URL" INIT_MATH_FROM_WINDOWS="\${INIT_MATH_FROM_WINDOWS:-}" bash "\$SETUP_SH" --check --harness $HARNESS
EOF
mv "$PLAN.tmp" "$PLAN"
chmod +x "$PLAN"

say ""
say "The plan has $NSTEPS step(s):$STEPS"
if [ -n "$YOU" ]; then
  say ""
  say "Along the way you will be asked to:$YOU"
fi
say ""
say "It is saved as $PLAN so you can read exactly what it will run."

if [ "$MODE" = plan ]; then
  if [ "${INIT_MATH_FROM_WINDOWS:-}" = 1 ]; then
    say "To carry it out, run in PowerShell:  powershell -ExecutionPolicy Bypass -File setup-windows.ps1"
    say "(without -PlanOnly)."
  else
    say "Run it with:  bash $PLAN"
  fi
  exit 0
fi
# Everything the run shows also goes to a log file, so a problem can be read from the file
# (by the agent helping, or with a report) instead of copied out of the window. `script` keeps the
# window a real terminal, which the installers and logins in the plan need; passwords are
# not shown on screen, so they are not in the log either.
LOG="$HOME/init-math-setup.log"
run_plan() {
  printf '\n==== init-math setup, %s\n' "$(date '+%Y-%m-%d %H:%M')" >> "$LOG" 2>/dev/null || true
  if [ "$NONINTERACTIVE" = 1 ]; then
    if ! have tee; then
      SETUP_NONINTERACTIVE=1 exec bash "$PLAN"
    fi
    set +e
    SETUP_NONINTERACTIVE=1 bash "$PLAN" 2>&1 | tee -a "$LOG"
    exit "${PIPESTATUS[0]}"
  fi
  if [ -t 0 ] && [ -t 1 ] && have script; then
    if script --version 2>/dev/null | grep -q util-linux; then
      exec script -q -a -e -c "bash $(printf %q "$PLAN")" "$LOG"
    fi
    exec script -q -a "$LOG" bash "$PLAN"
  fi
  exec bash "$PLAN"
}
if [ "$NONINTERACTIVE" = 1 ]; then
  run_plan
fi
while :; do
  printf '\nRun it now? [y]es / [v]iew it first (press q to come back) / [n]o: '
  { read -r ans </dev/tty; } 2>/dev/null || ans=n
  case "$ans" in
    y|Y|yes) run_plan ;;
    v|V) "${PAGER:-less}" "$PLAN" </dev/tty || cat "$PLAN" ;;
    *) say "Nothing was changed. To run it later: $RERUN"; exit 0 ;;
  esac
done
