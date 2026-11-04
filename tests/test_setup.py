"""Tests for setup.sh, run against simulated computers.

Each test builds a PATH containing only basic system tools and stand-ins for python3, git,
ssh, curl, claude, codex, brew, apt-get and the rest, whose behaviour is set by files in a
state directory. setup.sh is run with /bin/bash (on macOS that is bash 3.2, the oldest we
support), a throwaway HOME, and the INIT_MATH_UNAME / INIT_MATH_PROC_VERSION overrides that
let a Mac pretend to be Linux or WSL. Nothing touches the real machine or the network.
"""

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETUP = ROOT / "setup.sh"

# Real tools the scripts need; each is linked into the fake PATH.
SYSTEM_TOOLS = [
    "bash", "sh", "grep", "sed", "cat", "date", "dirname", "basename", "id", "chmod", "mv",
    "mkdir", "touch", "env", "uname", "tr", "head", "ln", "rm", "less", "sleep", "awk",
    "tee",
]

# Stand-ins. Each logs its call to $FAKE_LOG and reads its behaviour from $FAKE_STATE.
STUBS = {
    "python3": r'''
        v=$(cat "$FAKE_STATE/python" 2>/dev/null || echo 3.12)
        case "$*" in
          *version_info\[:2\]*) echo "$v" ;;
          *sys.exit*) maj=${v%%.*}; min=${v#*.}; [ "$maj" -gt 3 ] || [ "$min" -ge 11 ] ;;
          --version) echo "Python $v.0" ;;
        esac''',
    "git": r'''
        case "$1" in
          ls-remote) [ -f "$FAKE_STATE/repo-access" ] ;;
          config) [ -f "$FAKE_STATE/no-git-identity" ] && exit 1; echo "Someone" ;;
          *) echo "git version 2.45.0" ;;
        esac''',
    "ssh": r'''
        if [ -f "$FAKE_STATE/github-knows-key" ]; then
          echo "Hi someone! You've successfully authenticated, but GitHub does not provide shell access." >&2
        else
          echo "git@github.com: Permission denied (publickey)." >&2
        fi
        exit 1''',
    "ssh-keygen": r'''
        case " $* " in *" -y "*) [ ! -f "$FAKE_STATE/key-locked" ]; exit ;; esac
        f=""; while [ $# -gt 0 ]; do [ "$1" = -f ] && f=$2; shift; done
        echo "ssh-ed25519 AAAAFAKE someone" > "$f.pub"; : > "$f"''',
    "ssh-add": r'''touch "$FAKE_STATE/github-knows-key"''',
    "curl": r'''
        url=""; for a in "$@"; do url=$a; done
        case "$url" in
          *claude.ai/install.sh) echo "mkdir -p \"\$HOME/.local/bin\"; ln -sf \"$FAKE_ALL/claude\" \"\$HOME/.local/bin/claude\"" ;;
          *codex/install.sh) echo "mkdir -p \"\$HOME/.local/bin\"; ln -sf \"$FAKE_ALL/codex\" \"\$HOME/.local/bin/codex\"" ;;
          *) echo "echo fake installer for $url" ;;
        esac''',
    "claude": r'''
        case "$1 ${2:-}" in
          "auth status") [ -f "$FAKE_STATE/claude-login" ] ;;
          "auth login") touch "$FAKE_STATE/claude-login" ;;
          "plugin list") if [ -f "$FAKE_STATE/claude-plugin" ]; then
                           v=$(cat "$FAKE_STATE/claude-plugin")
                           if [ -n "$v" ]; then
                             printf '[\n  {\n    "id": "init-math@init-math",\n    "version": "%s",\n    "enabled": true\n  }\n]\n' "$v"
                           else echo '[{"id": "init-math@init-math", "enabled": true}]'; fi
                         else echo '[]'; fi ;;
          # install keeps an installed copy; update takes the marketplace's version
          "plugin install") [ -f "$FAKE_STATE/claude-plugin" ] ||
                              cat "$FAKE_STATE/available" > "$FAKE_STATE/claude-plugin" 2>/dev/null ||
                              touch "$FAKE_STATE/claude-plugin" ;;
          "plugin update") [ -f "$FAKE_STATE/claude-plugin" ] &&
                             { cat "$FAKE_STATE/available" > "$FAKE_STATE/claude-plugin" 2>/dev/null || :; } ;;
        esac''',
    "codex": r'''
        case "$1 ${2:-}" in
          "login status") [ -f "$FAKE_STATE/codex-login" ] ;;
          "login ") touch "$FAKE_STATE/codex-login" ;;
          "plugin list") echo "PLUGIN   STATUS   VERSION   SOURCE"
                         [ -f "$FAKE_STATE/codex-plugin" ] &&
                           echo "init-math@init-math  installed, enabled  $(cat "$FAKE_STATE/codex-plugin")  git" ;;
          # like Codex: add keeps an installed copy as it is; remove then add replaces it
          "plugin add") [ -f "$FAKE_STATE/codex-plugin" ] ||
                          cat "$FAKE_STATE/available" > "$FAKE_STATE/codex-plugin" 2>/dev/null ||
                          touch "$FAKE_STATE/codex-plugin" ;;
          "plugin remove") rm -f "$FAKE_STATE/codex-plugin" ;;
        esac
        exit $?''',
    "sudo": r'''exec "$@"''',
    "apt-get": r'''
        [ "$1" = install ] || exit 0
        for p in "$@"; do
          case "$p" in
            python3|git|curl) ln -sf "$FAKE_ALL/$p" "$FAKE_BIN/$p" ;;
            openssh-client) ln -sf "$FAKE_ALL/ssh" "$FAKE_BIN/ssh"; ln -sf "$FAKE_ALL/ssh-keygen" "$FAKE_BIN/ssh-keygen" ;;
          esac
        done''',
    "brew": r'''
        if [ "$1" = install ]; then
          [ "$2" = python ] && echo 3.13 > "$FAKE_STATE/python" && ln -sf "$FAKE_ALL/python3" "$FAKE_BIN/python3"
          [ "$2" = git ] && ln -sf "$FAKE_ALL/git" "$FAKE_BIN/git"
        fi
        exit 0''',
    "xcode-select": r'''[ -f "$FAKE_STATE/clt" ] && echo /Library/Developer/CommandLineTools''',
    "sw_vers": r'''echo 15.0''',
    "wslview": r''':''',
    "clip.exe": r'''cat > /dev/null''',
}

ALL_PRESENT = ["python3", "git", "ssh", "ssh-keygen", "curl", "claude", "codex", "sudo"]


class Machine:
    """A simulated computer: a fake PATH, a HOME and a state directory."""

    def __init__(self, tmp, os_name="Linux", tools=(), state=(), python="3.12", proc_version=""):
        self.tmp = Path(tmp)
        self.all = self.tmp / "all"
        self.bin = self.tmp / "bin"
        self.home = self.tmp / "home"
        self.state = self.tmp / "state"
        self.work = self.tmp / "work"
        for d in (self.all, self.bin, self.home, self.state, self.work):
            d.mkdir()
        self.log = self.tmp / "calls.log"
        self.log.touch()
        for t in SYSTEM_TOOLS:
            real = shutil.which(t, path="/usr/bin:/bin:/usr/sbin:/sbin")
            if real:
                (self.bin / t).symlink_to(real)
        for name, body in STUBS.items():
            f = self.all / name
            f.write_text('#!/bin/bash\necho "%s $*" >> "$FAKE_LOG"\n%s\n'
                         % (name, textwrap.dedent(body).strip()))
            f.chmod(0o755)
        for t in tools:
            (self.bin / t).symlink_to(self.all / t)
        for s in state:
            (self.state / s).touch()
        (self.state / "python").write_text(python)
        self.os_name = os_name
        self.proc_version = self.tmp / "proc_version"
        self.proc_version.write_text(proc_version)

    def env(self, **extra):
        env = {
            "PATH": str(self.bin),
            "HOME": str(self.home),
            "SHELL": "/bin/bash",
            "TERM": "dumb",
            "FAKE_LOG": str(self.log),
            "FAKE_STATE": str(self.state),
            "FAKE_ALL": str(self.all),
            "FAKE_BIN": str(self.bin),
            "INIT_MATH_UNAME": self.os_name,
            "INIT_MATH_PROC_VERSION": str(self.proc_version),
            "INIT_MATH_STUB_DIR": str(self.tmp / "no-stubs-here"),
            "INIT_MATH_BREW_DIRS": str(self.tmp / "no-homebrew-here"),
            "INIT_MATH_PLAN": str(self.work / "plan.sh"),
            # The SSH path (a private copy); test_public_repository_needs_no_ssh runs the default.
            "INIT_MATH_REPO_URL": "git@github.com:nkohen/init-math.git",
        }
        env.update(extra)
        return env

    def run(self, *args, **extra):
        p = subprocess.run(["/bin/bash", str(SETUP), *args], cwd=self.work, env=self.env(**extra),
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
        return p.returncode, p.stdout + p.stderr

    def run_plan(self, **extra):
        p = subprocess.run(["/bin/bash", str(self.work / "plan.sh")], cwd=self.work,
                           env=self.env(SETUP_NONINTERACTIVE="1", **extra), stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=60)
        return p.returncode, p.stdout + p.stderr

    @property
    def plan(self):
        return (self.work / "plan.sh").read_text()

    @property
    def calls(self):
        return self.log.read_text()


READY = ["github-knows-key", "repo-access", "claude-login", "claude-plugin"]


class SetupTest(unittest.TestCase):
    def machine(self, **kw):
        d = tempfile.mkdtemp(prefix="setup-test-")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return Machine(d, **kw)

    def test_ready_machine_reports_ready(self):
        m = self.machine(tools=ALL_PRESENT, state=READY)
        rc, out = m.run("--check", "--harness", "claude")
        self.assertEqual(rc, 0, out)
        self.assertIn("Everything is ready", out)
        self.assertIn("/init-math:init-math", out)
        self.assertFalse((m.work / "plan.sh").exists())

    def test_check_mode_writes_nothing(self):
        m = self.machine(tools=["curl"])
        rc, out = m.run("--check", "--harness", "claude")
        self.assertEqual(rc, 1, out)
        self.assertIn("Python 3.11 or newer: not found", out)
        self.assertFalse((m.work / "plan.sh").exists())
        self.assertNotIn("apt-get", m.calls)

    def test_harness_is_detected(self):
        m = self.machine(tools=ALL_PRESENT, state=READY)
        (m.bin / "claude").unlink()
        rc, out = m.run("--check")
        self.assertIn("Codex is installed but not logged in", out)
        self.assertNotIn("Claude Code", out)

    def test_fresh_linux_plan_and_unattended_run(self):
        m = self.machine(tools=["sudo"])
        (m.bin / "apt-get").symlink_to(m.all / "apt-get")
        rc, out = m.run("--plan-only", "--harness", "claude")
        self.assertEqual(rc, 0, out)
        plan = m.plan
        self.assertIn("apt-get install -y python3 git curl openssh-client", plan)
        self.assertIn("ssh-keygen", plan)
        self.assertIn("https://claude.ai/install.sh", plan)
        self.assertIn("claude auth login", plan)
        self.assertIn("claude plugin install", plan)
        self.assertNotIn("codex", plan)
        self.assertIn("Along the way you will be asked to:", out)
        self.assertEqual(m.calls.count("apt-get"), 0, "--plan-only must not install anything")

        rc, out = m.run_plan()
        calls = m.calls
        self.assertIn("apt-get install -y python3 git curl openssh-client", calls)
        self.assertTrue((m.home / ".ssh" / "id_ed25519.pub").exists())
        self.assertTrue((m.home / ".local" / "bin" / "claude").exists())
        self.assertIn('export PATH="$HOME/.local/bin:$PATH"', (m.home / ".bashrc").read_text())
        # Unattended: the steps that need a person are listed, not run.
        self.assertIn("Left for you to do:", out)
        self.assertIn("add your SSH key to GitHub", out)
        self.assertIn("log in to Claude Code", out)
        self.assertNotIn("claude auth login", calls)
        self.assertNotIn("claude plugin install", calls)
        # The final check runs and is honest that the machine is not ready.
        self.assertIn("Not ready yet", out)
        self.assertNotEqual(rc, 0)

        # Once the person has done their part, running the same plan again finishes the job.
        for s in ("github-knows-key", "repo-access", "claude-login"):
            (m.state / s).touch()
        before = m.calls.count("apt-get")
        rc, out = m.run_plan()
        self.assertEqual(rc, 0, out)
        self.assertEqual(m.calls.count("apt-get"), before, "the done apt step must skip itself")
        self.assertEqual(m.calls.count("ssh-keygen -q"), 1, "an existing key must not be replaced")
        self.assertIn("claude plugin marketplace add git@github.com:nkohen/init-math.git", m.calls)
        self.assertIn("claude plugin install init-math@init-math", m.calls)
        self.assertIn("Everything is ready", out)

    def test_yes_runs_the_plan_unattended(self):
        m = self.machine(tools=["python3", "git", "curl", "ssh", "ssh-keygen", "claude"],
                         state=["claude-login"])
        rc, out = m.run("--yes", "--harness", "claude")
        self.assertIn("Left for you to do:", out)
        self.assertIn("add your SSH key to GitHub", out)
        self.assertNotIn("Press Enter", out)
        self.assertNotIn("Stopped during", out)
        self.assertIn("-N", m.calls.split("ssh-keygen", 1)[1].splitlines()[0])
        log = (m.home / "init-math-setup.log").read_text()
        self.assertIn("==== init-math setup", log)
        self.assertIn("Left for you to do:", log, "the run's output is also in the log")

    def test_old_python_on_wsl_suggests_newer_ubuntu(self):
        m = self.machine(tools=ALL_PRESENT, state=READY, python="3.10",
                         proc_version="Linux version 5.15.0-microsoft-standard-WSL2")
        (m.bin / "apt-get").symlink_to(m.all / "apt-get")
        rc, out = m.run("--plan-only", "--harness", "claude", WSL_DISTRO_NAME="Ubuntu-22.04")
        self.assertIn("Linux in WSL (Ubuntu-22.04)", out)
        self.assertIn("Python 3.10 is too old", out)
        self.assertIn("installs Ubuntu 24.04 next to this one", m.plan)
        self.assertNotIn("apt-get install", m.plan, "apt cannot fix an old Python")

    def test_wsl1_is_told_to_convert(self):
        m = self.machine(tools=ALL_PRESENT, state=READY,
                         proc_version="Linux version 4.4.0-19041-Microsoft")
        rc, out = m.run("--plan-only", "--harness", "claude", WSL_DISTRO_NAME="Ubuntu")
        self.assertIn("WSL version 1", out)
        self.assertIn("wsl --set-version Ubuntu 2", m.plan)

    def test_mac_without_command_line_tools_never_runs_apple_stubs(self):
        m = self.machine(os_name="Darwin", tools=["curl"])
        stub_dir = m.tmp / "applestubs"
        stub_dir.mkdir()
        for t in ("python3", "git"):
            f = stub_dir / t
            f.write_text('#!/bin/bash\ntouch "$FAKE_STATE/apple-dialog-opened"\n')
            f.chmod(0o755)
        (m.bin / "xcode-select").symlink_to(m.all / "xcode-select")
        (m.bin / "sw_vers").symlink_to(m.all / "sw_vers")
        rc, out = m.run("--plan-only", "--harness", "claude", INIT_MATH_STUB_DIR=str(stub_dir),
                        PATH="%s:%s" % (m.bin, stub_dir))
        self.assertFalse((m.state / "apple-dialog-opened").exists())
        self.assertIn("Python 3.11 or newer: not found", out)
        self.assertIn("git: not found", out)
        plan = m.plan
        self.assertIn("raw.githubusercontent.com/Homebrew/install", plan)
        self.assertIn("brew shellenv", plan)
        self.assertIn("brew install python", plan)
        self.assertIn("brew install git", plan)

    def test_mac_with_brew_and_old_python(self):
        m = self.machine(os_name="Darwin", tools=ALL_PRESENT + ["brew", "xcode-select", "sw_vers"],
                         state=READY + ["clt"], python="3.9")
        rc, out = m.run("--plan-only", "--harness", "claude")
        self.assertIn("Python 3.9 is too old", out)
        self.assertNotIn("Homebrew/install", m.plan)
        self.assertIn("brew install python", m.plan)
        rc, out = m.run_plan()
        self.assertEqual(rc, 0, out)
        self.assertIn("brew install python", m.calls)
        self.assertIn("Everything is ready", out)

    def test_existing_key_unknown_to_github(self):
        m = self.machine(tools=ALL_PRESENT, state=["claude-login", "claude-plugin"])
        (m.home / ".ssh").mkdir()
        (m.home / ".ssh" / "id_rsa.pub").write_text("ssh-rsa AAAA old\n")
        rc, out = m.run("--plan-only", "--harness", "claude")
        self.assertIn("GitHub does not recognize your SSH key yet", out)
        self.assertNotIn("Create an SSH key", m.plan)
        self.assertIn("Add the key to your GitHub account", m.plan)

    def test_no_repository_access_names_who_to_ask(self):
        m = self.machine(tools=ALL_PRESENT, state=["github-knows-key", "claude-login"])
        rc, out = m.run("--plan-only", "--harness", "claude")
        self.assertIn("cannot see this copy of init-math yet: ask its owner", out)
        self.assertIn("Check that your GitHub account can see init-math", m.plan)

    def test_missing_access_does_not_stop_the_rest(self):
        # Waiting for access must not leave the agent program uninstalled and logged out.
        m = self.machine(tools=["python3", "git", "curl", "ssh", "ssh-keygen"],
                         state=["github-knows-key"])
        m.run("--plan-only", "--harness", "claude")
        rc, out = m.run_plan()
        self.assertIn("plan continues without it", out)
        self.assertIn("curl -fsSL https://claude.ai/install.sh", m.calls)
        self.assertIn("send its owner your GitHub user name", out)
        self.assertNotIn("claude plugin install", m.calls)
        self.assertNotIn("Stopped during", out)

    def test_step_explanations_are_shown_while_running(self):
        m = self.machine(tools=["python3", "git", "curl", "ssh", "ssh-keygen", "claude"],
                         state=["claude-login"])
        m.run("--plan-only", "--harness", "claude")
        rc, out = m.run_plan()
        self.assertIn("never leaves", out)
        self.assertIn("safe to share", out)
        self.assertIn("without a passphrase", out)
        self.assertNotIn("Needs you:", out)
        self.assertNotIn("STEP=", out)

    def test_new_key_has_no_passphrase_even_when_interactive(self):
        m = self.machine(tools=["python3", "git", "curl", "ssh", "ssh-keygen", "claude"],
                         state=["claude-login"])
        m.run("--plan-only", "--harness", "claude")
        self.assertIn('ssh-keygen -q -t ed25519 -N ""', m.plan)
        self.assertEqual(m.plan.count("ssh-keygen -"), 1)

    def test_key_with_passphrase_on_mac_goes_to_keychain(self):
        m = self.machine(os_name="Darwin", tools=ALL_PRESENT + ["brew", "xcode-select", "sw_vers", "ssh-add"],
                         state=["clt", "key-locked", "repo-access", "claude-login", "claude-plugin"])
        (m.home / ".ssh").mkdir()
        (m.home / ".ssh" / "id_ed25519").write_text("locked\n")
        (m.home / ".ssh" / "id_ed25519.pub").write_text("ssh-ed25519 AAAA me\n")
        rc, out = m.run("--plan-only", "--harness", "claude")
        self.assertIn("has a passphrase", out)
        self.assertIn("ssh-add --apple-use-keychain", m.plan)
        rc, out = m.run_plan()  # unattended: typing the passphrase is left for the person
        self.assertIn("unlock your SSH key", out)
        self.assertNotIn("ssh-add", m.calls)

    def test_key_with_passphrase_on_linux_explains_the_agent(self):
        m = self.machine(tools=ALL_PRESENT, state=["key-locked", "repo-access", "claude-login"])
        (m.home / ".ssh").mkdir()
        (m.home / ".ssh" / "id_ed25519").write_text("locked\n")
        (m.home / ".ssh" / "id_ed25519.pub").write_text("ssh-ed25519 AAAA me\n")
        m.run("--plan-only", "--harness", "claude")
        rc, out = m.run_plan()
        self.assertIn('eval "$(ssh-agent -s)"', out)
        self.assertNotEqual(rc, 0)

    def test_key_with_passphrase_from_windows_says_where_to_type(self):
        # Started from PowerShell, "this window" is PowerShell once setup stops: name the Linux.
        m = self.machine(tools=ALL_PRESENT, state=["key-locked", "repo-access", "claude-login"])
        (m.home / ".ssh").mkdir()
        (m.home / ".ssh" / "id_ed25519").write_text("locked\n")
        (m.home / ".ssh" / "id_ed25519.pub").write_text("ssh-ed25519 AAAA me\n")
        m.run("--plan-only", "--harness", "claude", INIT_MATH_FROM_WINDOWS="1")
        rc, out = m.run_plan(INIT_MATH_FROM_WINDOWS="1", WSL_DISTRO_NAME="Ubuntu-24.04")
        self.assertIn("wsl -d Ubuntu-24.04", out)
        self.assertIn('eval "$(ssh-agent -s)"', out)
        self.assertIn("bash ~/init-math-setup.sh", out)
        self.assertNotEqual(rc, 0)

    def test_plan_only_from_windows_points_back_to_powershell(self):
        m = self.machine(tools=ALL_PRESENT, state=["key-locked", "repo-access", "claude-login"])
        rc, out = m.run("--plan-only", "--harness", "claude", INIT_MATH_FROM_WINDOWS="1")
        self.assertIn("(without -PlanOnly)", out)
        self.assertNotIn("Run it with:", out)

    def test_git_identity_is_asked_for(self):
        m = self.machine(tools=ALL_PRESENT, state=READY + ["no-git-identity"])
        rc, out = m.run("--plan-only", "--harness", "claude")
        self.assertIn("git does not know your name and email yet", out)
        self.assertIn("git config --global user.email", m.plan)
        rc, out = m.run_plan()
        self.assertIn("tell git your name and email", out)

    def test_mac_non_administrator_is_told_before_homebrew(self):
        m = self.machine(os_name="Darwin", tools=["curl", "xcode-select", "sw_vers"])
        (m.bin / "id").unlink()
        f = m.bin / "id"
        f.write_text('#!/bin/bash\n[ "$1" = -Gn ] && { echo "staff everyone"; exit 0; }\n[ "$1" = -u ] && { echo 501; exit 0; }\necho someone\n')
        f.chmod(0o755)
        rc, out = m.run("--plan-only", "--harness", "claude")
        self.assertIn("not an administrator", out)
        p = subprocess.run(["/bin/bash", str(m.work / "plan.sh")], cwd=m.work,
                           env=m.env(), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
        self.assertIn("Ask whoever manages this Mac", p.stdout + p.stderr)
        self.assertNotIn("Homebrew/install/HEAD/install.sh", m.calls)

    def test_started_from_windows_says_how_to_rerun_there(self):
        m = self.machine(tools=["python3", "git", "curl", "ssh", "ssh-keygen"],
                         proc_version="Linux version 5.15.0-microsoft-standard-WSL2")
        m.run("--plan-only", "--harness", "claude", INIT_MATH_FROM_WINDOWS="1")
        rc, out = m.run_plan()
        self.assertIn("powershell -ExecutionPolicy Bypass -File setup-windows.ps1", out)

    def test_ssh_flag_uses_ssh(self):
        m = self.machine(tools=["python3", "git", "curl", "ssh", "ssh-keygen", "claude"],
                         state=["claude-login"])
        rc, out = m.run("--plan-only", "--harness", "claude", "--ssh", INIT_MATH_REPO_URL="")
        self.assertIn("REPO_URL='git@github.com:nkohen/init-math.git'", m.plan)
        self.assertIn("ssh-keygen", m.plan)
        self.assertIn("setup.sh --ssh'", m.plan)  # a rerun stays on SSH

    def test_public_repository_needs_no_ssh(self):
        m = self.machine(tools=["python3", "git", "curl", "claude"], state=["claude-login"])
        rc, out = m.run("--plan-only", "--harness", "claude", INIT_MATH_REPO_URL="")  # the default
        self.assertNotIn("SSH", out)
        self.assertNotIn("ssh-keygen", m.plan)
        self.assertNotIn("GitHub account", m.plan)
        rc, out = m.run_plan()
        self.assertEqual(rc, 0, out)
        self.assertIn("claude plugin marketplace add https://github.com/nkohen/init-math.git", m.calls)

    def test_old_plugin_is_updated(self):
        """An installed plugin older than this setup's version is reported and updated: Claude
        Code by `plugin update`; Codex keeps an installed copy, so remove and add again."""
        for harness, state in (("claude", "claude-plugin"), ("codex", "codex-plugin")):
            with self.subTest(harness):
                m = self.machine(tools=ALL_PRESENT, state=["github-knows-key", "repo-access",
                                                           f"{harness}-login"])
                (m.state / state).write_text("0.1.0")
                (m.state / "available").write_text("0.2.0")
                rc, out = m.run("--check", "--harness", harness, INIT_MATH_VERSION="0.2.0")
                self.assertEqual(rc, 1, out)
                self.assertIn("init-math 0.1.0 installed; setup updates it to 0.2.0", out)
                m.run("--plan-only", "--harness", harness, INIT_MATH_VERSION="0.2.0")
                rc, out = m.run_plan()
                self.assertEqual(rc, 0, out)
                self.assertEqual((m.state / state).read_text(), "0.2.0")
                if harness == "claude":
                    self.assertIn("claude plugin marketplace update init-math", m.calls)
                    self.assertIn("claude plugin update init-math@init-math", m.calls)
                else:
                    self.assertIn("codex plugin marketplace upgrade init-math", m.calls)
                    self.assertIn("codex plugin remove init-math@init-math", m.calls)
                self.assertIn(f"init-math installed", out)  # the final check is OK again

    def test_plugin_version_from_this_folder(self):
        """Without INIT_MATH_VERSION, the version is plugin.json next to setup.sh; a current
        install is OK."""
        want = json.loads((SETUP.parent / "plugin.json").read_text())["version"]
        m = self.machine(tools=ALL_PRESENT, state=READY)
        (m.state / "claude-plugin").write_text(want)
        rc, out = m.run("--check", "--harness", "claude")
        self.assertEqual(rc, 0, out)
        (m.state / "claude-plugin").write_text("0.0.1")
        rc, out = m.run("--check", "--harness", "claude")
        self.assertIn(f"setup updates it to {want}", out)

    def test_codex_plan(self):
        m = self.machine(tools=ALL_PRESENT, state=["github-knows-key", "repo-access"])
        rc, out = m.run("--plan-only", "--harness", "codex")
        self.assertIn("Log in to Codex", m.plan)
        self.assertIn("codex plugin add", m.plan)
        self.assertNotIn("claude", m.plan)

    def test_windows_shell_points_to_powershell_script(self):
        m = self.machine(os_name="MINGW64_NT-10.0")
        rc, out = m.run()
        self.assertEqual(rc, 1)
        self.assertIn("setup-windows.ps1", out)

    def test_plan_is_valid_bash(self):
        m = self.machine(tools=["sudo"])
        (m.bin / "apt-get").symlink_to(m.all / "apt-get")
        m.run("--plan-only", "--harness", "both")
        p = subprocess.run(["/bin/bash", "-n", str(m.work / "plan.sh")], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        if shutil.which("shellcheck"):
            p = subprocess.run(["shellcheck", "-s", "bash", "-S", "warning", str(SETUP),
                                str(m.work / "plan.sh")], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stdout)

    def test_windows_line_endings_are_caught(self):
        d = Path(tempfile.mkdtemp(prefix="setup-crlf-"))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        crlf = d / "setup.sh"
        crlf.write_bytes(SETUP.read_bytes().replace(b"\n", b"\r\n"))
        p = subprocess.run(["/bin/bash", str(crlf), "--check"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn("Windows line endings", p.stdout)


if __name__ == "__main__":
    unittest.main()
