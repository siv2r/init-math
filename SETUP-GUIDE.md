# Setup guide (for the agent)

You are helping someone install init-math, a tool that sets up mathematics research
projects worked on by AI agents. The person is most likely a mathematician, not a
programmer: they may never have used a terminal. They pasted a sentence asking you to walk
them through this guide. Follow it one step at a time.

The setup scripts in this folder do the actual work: `setup.sh` (Mac, Linux, and Linux
inside Windows) and `setup-windows.ps1` (Windows). Each checks what the computer has,
writes a plan, and installs only what is missing. Your job is to run their read-only
checks, explain in plain words what you see, hand the person each command they need to run,
and confirm afterwards that it worked.

## Getting or updating init-math

The person's sentence asked you to download init-math into `~/research/init-math` and follow
this guide, so that copy exists now. From here on, "this folder" is that copy: run every
command in this guide from it (`cd` there first). If the person later asks to update
init-math, fetch the newest copy the same way, then go through the steps again from step 2;
setup updates the installed plugin, and their projects are not touched.

Before replacing an existing copy, look at it: if it holds anything besides init-math's own
files and setup's plan (`init-math-setup-plan.sh`), ask the person first. The command
unpacks into a fresh folder and swaps it in only when the download worked and holds
`setup.sh`:

- Mac, Linux, or a Bash shell on Windows:

  ```bash
  cd ~ && rm -rf research/init-math.new && mkdir -p research/init-math.new &&
    curl -fsSL -o research/init-math.tar.gz https://github.com/nkohen/init-math/archive/refs/heads/main.tar.gz &&
    tar xzf research/init-math.tar.gz -C research/init-math.new --strip-components=1 &&
    test -f research/init-math.new/setup.sh && rm -f research/init-math.tar.gz &&
    rm -rf research/init-math && mv research/init-math.new research/init-math
  ```

- PowerShell on Windows (`curl.exe` and `tar.exe` come with Windows 10 and 11):

  ```powershell
  $d = "$HOME\research\init-math"; $n = "$d.new"; $t = "$env:TEMP\init-math.tar.gz"
  Remove-Item -Recurse -Force $n -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force $n | Out-Null
  curl.exe -fsSL -o $t https://github.com/nkohen/init-math/archive/refs/heads/main.tar.gz
  if ($LASTEXITCODE -eq 0) { tar.exe -xzf $t -C $n --strip-components=1 }
  if ($LASTEXITCODE -eq 0 -and (Test-Path "$n\setup.sh")) {
    Remove-Item -Recurse -Force $d -ErrorAction SilentlyContinue; Move-Item $n $d }
  ```

If it fails because your own shell has no network (some harnesses sandbox it), ask for
permission to run it outside the sandbox, or give the person the command to run in their
own window.

## Ground rules

- **One step at a time.** Say what the next step does and why in two or three sentences,
  give the exact command if there is one, then wait for the person to report back before
  moving on. Do not give them the whole list at once.
- **Plain words.** No unexplained jargon. When you must use a term (terminal, WSL, SSH key,
  firmware), explain it in one sentence the first time.
- **You run only the read-only commands** listed under "Commands you run", and the download
  above. Everything that
  installs or changes the computer is run by the person, in a terminal window of their own
  (a second window, not this chat): the scripts ask yes/no questions, passwords and
  permissions there, and you cannot answer those from here. Do not run the installing
  commands yourself, and do not install, delete or change anything by other means.
- **Never ask for a password, and never type one.** If a script asks for one, it is
  for the person to type in their own window. Their password does not appear on the
  screen as they type; tell them that before the first time.
- **Check after each step.** When the person says a step is done, run the check again and
  confirm the row now says `OK`. If it does not, read what they paste, explain it, and fix
  that before going on.
- **If they ask whether something is safe,** read the relevant part of `setup.sh` or
  `setup-windows.ps1` (or the written plan) and explain what it does. Each step in the plan
  has a comment saying why it is there. Every step first checks, and skips itself if it is
  already done, so running a script again after a failure is safe.
- **Do not set up the research project in this conversation.** This conversation installs
  init-math; the project is created by a new agent session started inside Linux (step 6).
  If the person asks to "use it here" or to keep working in this window, explain why not: a
  project is only fully working in a session started in its own folder, inside Linux on
  Windows. Started anywhere else (this window, the Windows side, a parent folder), the agent
  sees none of the project's procedures, automatic checks, reviewers or model settings,
  and nothing tells the person so. Then give the step 6 instructions again. Never install
  init-math's skill into this folder, run its generator from here (for example through
  `wsl.exe`), or write an AGENTS.md or CLAUDE.md that points into another folder.
- **If you are stuck** after two attempts at the same problem, help the person write a
  short report for init-math's issue page, <https://github.com/nkohen/init-math/issues> (a colleague
  Nadav invited writes to Nadav instead): what they were doing, which computer they have,
  and the setup log attached (see "Reading the setup log" below). Read the log with them
  first: it holds their user name and folder paths.

## Commands you run

These only report: they install nothing and change no settings. (They do write the plan
file, on Windows also a copy of `setup.sh` in the Linux home folder, and over SSH the check may
record GitHub's address in `~/.ssh/known_hosts`.) Run them from this folder. An exit status
of 1 from a check just means "not ready yet"; it is not an error.

| Computer | Command | What it shows |
|---|---|---|
| Mac or Linux | `bash setup.sh --check --harness claude` | a table: `OK`, `TO DO` (setup does it), `NEEDS YOU` (the person does something along the way) |
| Mac or Linux | `bash setup.sh --plan-only --harness claude` | writes the plan to `init-math-setup-plan.sh` in this folder; read it to explain the steps |
| Windows | `powershell -ExecutionPolicy Bypass -File setup-windows.ps1 -Check -Harness claude` | a table for Windows; once Windows is ready, also the table for the Linux part |
| Windows | `powershell -ExecutionPolicy Bypass -File setup-windows.ps1 -PlanOnly -Harness claude` | the Windows plan, in order, with the restart points; once Windows is ready, the Linux plan (saved in the Linux home folder) |

Replace `claude` by `codex` or `both` if the person will use Codex (see step 1). On
Windows the Windows commands work from PowerShell and from Git Bash alike.

On Windows, once Linux is installed, you can read the Linux plan with
`wsl.exe -d Ubuntu-24.04 --exec bash -c 'cat ~/init-math-setup-plan.sh'` (with the
distribution name the Windows table showed).

### Reading the setup log

Everything a setup run shows is also saved in a log, so the person never has to copy their
window. Read the end of it yourself (it may contain color codes; ignore them):

- **Mac or Linux:** `tail -n 200 ~/init-math-setup.log`
- **Windows**, the Windows part: `powershell -Command 'Get-Content -Tail 200 $HOME\init-math-setup-windows.log'`;
  the Linux part: `wsl.exe -d Ubuntu-24.04 --exec bash -c 'tail -n 200 ~/init-math-setup.log'`

Each run starts with a line `==== init-math setup, <date and time>` (on Windows, a
transcript header), so the latest run is at the end.

Your own shell may be more restricted than the person's window (no network, no access to
their keys or keychain). If an SSH or login row says `NEEDS YOU` but the person says that
already works, believe them: the run checks again before each step and skips what is done.

## The steps

### 1. Agree on the agent program

Ask which agent program they will use for their research: Claude Code (needs a Claude Pro
or Max plan; Max is recommended, since a working session uses many agents and Pro may hit
its usage limits) or Codex (needs a paid ChatGPT plan). Most people who are talking to you in
Claude Code will want Claude Code. Use the answer in every command (`--harness` /
`-Harness`).

### 2. Check the computer

Run the check for their computer. Then explain the table row by row, in plain words: what
is already there, what setup will do, and what it will need from them. Do not paste the
table back; summarize it, grouped as "already fine", "setup does this", "you will be asked
to". If every row is `OK`, skip to step 6. A row saying an older init-math is installed and
setup updates it means the person is updating: the same run does it, and their existing
projects are not touched.

### 3. Windows only: get Windows ready

Skip this on a Mac or Linux. On Windows, init-math runs inside WSL, the Linux system built
into Windows. The Windows table can show these items; explain the ones present:

- **WSL is the old version built into Windows 10**: setup updates it. Windows asks for
  permission in a pop-up; the person clicks Yes.
- **The Virtual Machine Platform feature is off**: setup turns it on (another permission
  pop-up), after which Windows must restart.
- **Virtualization appears to be off in the firmware** (`NEEDS YOU`): the firmware is the
  computer's own settings, before Windows starts. During the restart the person turns
  virtualization on there. They cannot talk to you while doing it, so before they restart,
  give them the steps below and suggest they photograph the screen or write them down:
  1. Windows 10: Settings > Update & Security > Recovery > Advanced startup > Restart now.
     Windows 11: Settings > System > Recovery > Advanced startup > Restart now.
  2. On the blue screen: Troubleshoot > Advanced options > UEFI Firmware Settings > Restart.
  3. Find the setting called Intel Virtualization Technology, VT-x, SVM Mode or AMD-V
     (usually under Advanced or CPU Configuration), set it to Enabled, save and exit (often
     the F10 key). If it is already Enabled, just exit.
  On a computer managed by a university or employer, IT may have to do this. If after a
  restart the check still shows "virtualization is not running" together with this row,
  the firmware setting is still off; the restart itself did not fail.
- **No Linux distribution yet**, or **too old for init-math**: setup installs Ubuntu 24.04.
  An older one stays as it is. A new window opens in which the person chooses a Linux user
  name (lowercase, no spaces) and a password, typed twice, invisibly. Tell them to write
  that password down: whenever anything in Linux asks for "your password" later, it means
  this one. When that window shows a line ending in `$`, they type `exit` and press Enter.
- **Runs on WSL version 1**: setup converts it to version 2. It takes a few minutes. A
  Linux whose row says "too old" is never converted; it is left exactly as it is.
- **No Linux user yet** (`NEEDS YOU`): setup opens Linux once so they can choose a user
  name and password, as above.
- **`?` rows** are things the script could not check yet; they are checked again later.
  They are not problems.

Then have the person do the Windows part. If their Windows plan has no restart in it, the
same run continues straight into the Linux part, so go through step 4 with them first.

1. Ask them to open a second PowerShell window in this same folder (in File Explorer, open
   this folder, click the address bar, type `powershell`, press Enter).
2. Give them this line to paste there and press Enter:
   `powershell -ExecutionPolicy Bypass -File setup-windows.ps1 -Harness claude`
   (with their harness). It shows the same table, its plan, and asks `Go ahead? [y/N]`;
   they type `y` and press Enter. They keep the first window for talking to you and use
   the second only for setup commands.
3. Tell them what comes next, as far as their table goes: the permission pop-ups, the
   restart, the Ubuntu window.

On a computer managed by a university or employer, the permission pop-ups may ask for
someone else's administrator password. Then IT has to update WSL and turn on the Virtual
Machine Platform feature; the person can do the rest in their own account. Offer to write
the request to IT.

**If Windows restarts,** this conversation ends. Before the restart, tell the person how
to come back: open this folder in File Explorer, click the address bar, type `powershell`,
press Enter, type `claude --continue` and press Enter (that reopens this conversation;
`claude` and the same sentence as before works too, since the check shows where things
stand). After a restart, run the Windows check again and continue from what it shows;
before they run the setup command again, go through step 4 with them.

If the script stops with a message of its own ("This Windows has no WSL", "WSL could not
be updated", "Windows did not give permission"), read it to the person and do what it says.
For "WSL could not be updated", installing "Windows Subsystem for Linux" from the Microsoft
Store is the usual fix.

When the Windows rows are all `OK`, the same run continues into the Linux part without
stopping.

### 4. Explain the plan

Run the plan-only command and read the plan. On Windows, while Linux is not installed yet
there is no Linux plan to read; explain from this list instead. Walk the person through
what the run will ask of them, in order (only what applies):

- **Their computer password** (on Windows: the Linux password they chose), for installing
  programs. Invisible as they type; that is normal.
- **On a Mac without Homebrew** (a program that installs other programs): it asks them to
  press Return, then for the Mac password, then downloads Apple's command-line tools, which
  can take 5 to 20 minutes with little on the screen. They should not close the window.
  If the check said they are not an administrator of this Mac, the Mac's owner or IT has
  to install Homebrew or make their account an administrator. Installing Python 3.11 or
  newer from python.org (plus Apple's Command Line Tools for git) also works, and needs
  the administrator too. Offer to write that request.
- **Git name and email**: git is the program that keeps a project's history; it records
  who made each change. Any name and the email they use for GitHub are fine.
- **Only over SSH** (`bash setup.sh --ssh`, for someone who prefers it, or a private copy
  through `INIT_MATH_REPO_URL`; the default HTTPS download needs none of this):
  - **An SSH key on GitHub**: a pair of files that lets GitHub recognize this computer.
    Setup shows a line starting `ssh-ed25519`, copies it, and opens the GitHub page where
    it goes; they paste it into the "Key" box, give it any title, and click "Add SSH key". If they are not signed in to
    GitHub in that browser, they sign in first. If they already had a key protected by a
    passphrase (a password for the key): on a Mac setup asks them to type it once; on Linux
    and Windows setup stops and prints the lines to run, then to run setup again.
  - **Access to the private copy**: if their GitHub account cannot see it yet, setup
    continues without the plugin and lists that at the end. Help them send the copy's owner
    their GitHub user name, accept the invitation that comes by email, then run setup again.
- **Logging in to the agent program**: a browser page opens; they sign in with the
  account of their plan. On Windows this is a second login even if Claude Code already
  runs on Windows: the research happens inside Linux, which needs its own copy. If no
  browser opens, setup prints a link; they copy it into their browser (in Claude Code,
  pressing `c` copies it), and paste any code the page shows back into the window
  (right-click, or Ctrl+Shift+V).

### 5. Run setup

- **Mac or Linux:** ask them to open a second Terminal window (on a Mac: Cmd+Space, type
  Terminal, press Return), and give them two lines: `cd` followed by this folder's full
  path (quote it if it has spaces), then `bash setup.sh --harness claude` (with their
  harness). It asks `Run it now? [y]es / [v]iew it first / [n]o:`; they type `y`.
- **Windows:** the command from step 3 already runs this part. Have them run it again in
  their second PowerShell window only if it stopped before the Linux part finished.

While it runs, setup explains each step before taking it. If it stops with a message,
read the end of the setup log yourself ("Reading the setup log" above), then explain and
fix. Running setup again after fixing something is safe.

### 6. Confirm and say what comes next

Run the check again. When every row is `OK`, setup is done. (For a private copy, if the
only row left is access to it, setup is done apart from that: once its owner has added
them, they run setup again and it installs the plugin.) Then tell them how to start
their first project:

1. Open a terminal: on a Mac, Terminal; on Windows, "Ubuntu 24.04 LTS" from the Start
   menu, or `wsl -d Ubuntu-24.04` in PowerShell (from now on they work inside Linux, not
   PowerShell). If they had an older Linux, a plain `wsl` or a Start-menu entry named just
   "Ubuntu" opens that one, which has no init-math. On Windows, projects belong in the
   Linux home folder, not on the Windows drive.
2. Type `mkdir -p ~/research` and `cd ~/research`, then `claude` (or `codex`).
   `~/research` holds their projects: the interview creates the project's own folder
   inside it, named after the topic, so they should not make that folder themselves. If
   they already keep projects somewhere (say `~/dev`), they can start there instead.
3. In the agent's chat, type `/init-math:init-math` (Claude Code) or `Use the
   init-math:init-math skill to set up a research project.` (Codex). A short interview
   about their research follows: what they work on and the questions they want answered.
   It chooses the technical settings itself and lists them at the end.

Then ask whether they usually use Claude Code or Codex inside VS Code. If not, skip this.
If so, tell them only what applies:

- They can run the interview in a terminal as above, and work in VS Code afterwards.
- Afterwards, open the **project's own folder** in VS Code (the one the interview creates,
  not `~/research`): the agent reads the project's instructions and checks from the open
  folder.
- **Windows:** VS Code must be connected to Linux. In Ubuntu, `cd` into the project and
  type `code .`; the first time, VS Code offers its WSL extension, which they accept, and
  the window's bottom-left corner then reads "WSL: Ubuntu-24.04". If it offers to install
  the Claude Code or Codex extension "in WSL", they accept that too. A VS Code window opened
  from the Start menu works on Windows files and does not see init-math.
- **Claude Code:** the extension shares the terminal version's login, settings and
  plugins; nothing else to do.
- **Codex:** the Codex extension does not support plugins and may not run the project's
  automatic checks (hooks; not verified). They should run `codex` in VS Code's built-in
  terminal (Terminal > New Terminal) instead.

The interview's last message says how to start working in the new project. In that
project, typing `/getting-started` (Claude Code) or `$getting-started` (Codex; or "use the
getting-started skill") walks them through the first session the way you walked them
through setup, starting with `bin/doctor`, which checks that the session really loaded the
project. If the agent does not know the getting-started skill, it was started in the
wrong folder. Codex lists a project's skills under `/skills` and runs one when you type
`$` and its name; they are not `/` commands.

They may close this conversation now; nothing else here is needed.

## When the person asks

The README is kept short and sends these questions to you. Answer from here, in plain words.

- **What it costs.** By default the main agent and the reviewers run on the strongest model
  their Claude Code or Codex plan offers, and routine work on a cheaper one. Each review is
  a separate agent run, so a session uses several times what an ordinary chat would;
  reviews run when a finding is recorded, not on every step. On Claude Pro they may reach
  the usage limit during a session (not measured); Max is recommended. In a project,
  `bin/usage-report` shows token counts by model, and `docs/OWNER.md` ("Models") says how
  to change the models.
- **What leaves the computer.** What they type and the files the agents read go to
  Anthropic (Claude Code) or OpenAI (Codex), as in any chat, and the agents may search the
  web without asking. A project is a local git repository with no remote: nothing is pushed
  or published.
- **Updating init-math.** Fetch the newest copy ("Getting or updating init-math" above) and
  go through the steps again from step 2: setup updates the installed plugin. That updates
  the interview only; a project already created is never changed by it.
- **Coming back to a project.** Open a terminal (on Windows, Ubuntu), `cd` into the
  project and start the agent there; the project's files hold its state.
- **Undo.**
  - The plugin: `claude plugin uninstall init-math@init-math`, then `claude plugin
    marketplace remove init-math` (Codex: `codex plugin remove init-math@init-math`, then
    `codex plugin marketplace remove init-math`).
  - A project: delete its folder; nothing was pushed anywhere.
  - An SSH key that setup created (with `--ssh`, or before init-math was public): delete it
    on GitHub (Settings > SSH and GPG keys), then `~/.ssh/id_ed25519` and its `.pub`.
  - Lines setup added to `~/.zshrc` or `~/.bashrc` follow a comment `# added by init-math
    setup`; delete both lines.
  - Ubuntu on Windows, if setup installed it: `wsl --unregister Ubuntu-24.04` in
    PowerShell deletes it and everything inside it, their projects included. Say so plainly
    before they run it.
  - Claude Code or Codex: their makers' own uninstall instructions.
- **Running setup without an agent.** `bash setup.sh` (Windows: `powershell
  -ExecutionPolicy Bypass -File setup-windows.ps1`, which readies Windows, then copies
  `setup.sh` into Linux and runs it there). Options: `--check` (report only), `--plan-only`
  (write `init-math-setup-plan.sh` and stop, to read it first), `--yes` (run without asking;
  steps that need them are listed at the end), `--harness claude|codex|both`, `--ssh`
  (download over SSH instead of HTTPS; setup makes and registers a key if needed). On
  Windows: `-Check`, `-PlanOnly`, `-Harness`. In the tables, `TO DO` is done by setup and
  `NEEDS YOU` asks them along the way.
- **Installing by hand.** Once the agent program is installed and logged in:
  `claude plugin marketplace add https://github.com/nkohen/init-math.git`, then `claude
  plugin install init-math@init-math` (Codex: `codex plugin marketplace add …` with the
  same address, then `codex plugin add init-math@init-math`). Over SSH the address is
  `git@github.com:nkohen/init-math.git`. Install before starting the harness, or restart
  it afterwards.
- **Working in Linux on Windows.** After setup they work inside Ubuntu, not PowerShell
  ("Ubuntu 24.04 LTS" in the Start menu, or `wsl -d Ubuntu-24.04`). Projects belong in the
  Linux home folder, not under `/mnt/c/` (slower, with permission problems); Windows files
  are under `/mnt/c/Users/<name>/`. In File Explorer, Linux files are under "Linux" in the
  left panel, or `explorer.exe .` opens the current folder. If a login does not open a
  browser, they copy the printed link into the Windows browser and paste any code back
  with a right-click or Ctrl+Shift+V.
