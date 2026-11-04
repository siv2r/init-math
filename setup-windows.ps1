# init-math setup for Windows.
#
# init-math runs inside WSL, the Linux system built into Windows. This script:
#   1. checks everything Windows needs for it, all at once: an up-to-date WSL, the Virtual
#      Machine Platform feature, virtualization switched on in the computer's firmware, and
#      a Linux distribution new enough for init-math (Ubuntu 24.04 is installed if not);
#   2. shows the list, and with your go-ahead does the steps it can, in order. It stops where
#      Windows needs a restart; run it again afterwards and finished steps are skipped;
#   3. copies setup.sh (which must sit next to this file) into your Linux home folder and
#      runs it there. setup.sh checks what Linux still needs, shows you a plan, and asks
#      before it runs anything.
#
# Run it from PowerShell, in the folder holding this file and setup.sh:
#
#   powershell -ExecutionPolicy Bypass -File setup-windows.ps1
#
# Options:  -Check  (only report)   -PlanOnly  (write setup.sh's plan and stop)
#           -Harness claude|codex|both  (passed on to setup.sh)

param(
    [switch]$Check,
    [switch]$PlanOnly,
    [ValidateSet("", "claude", "codex", "both")][string]$Harness = ""
)

$ErrorActionPreference = "Stop"
$Wanted = "Ubuntu-24.04"

function Say([string]$text) { Write-Host $text }

# Everything this script shows is also saved here, so that nobody has to copy the window when
# something goes wrong. The Linux part keeps its own log, ~/init-math-setup.log inside Linux.
$WinLog = Join-Path $HOME "init-math-setup-windows.log"
$Logging = $false
try { Start-Transcript -LiteralPath $WinLog -Append | Out-Null; $Logging = $true } catch { }

function Exit-Setup([int]$code) {
    if ($Logging) { try { Stop-Transcript | Out-Null } catch { } }
    exit $code
}

function Stop-WithMessage([string]$text, [switch]$NoLog) {
    Say ""
    Say $text
    Say ""
    if ($Logging -and -not $NoLog) {
        Say "If you cannot tell what went wrong: everything shown here is also saved in $WinLog."
        Say "Ask the agent helping you to read it, or report it at https://github.com/nkohen/init-math/issues."
        Say ""
    }
    Exit-Setup 1
}

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$setup = Join-Path $here "setup.sh"
if (-not (Test-Path -LiteralPath $setup)) {
    Stop-WithMessage "setup.sh must be in the same folder as this file ($here). Download both files."
}
$rerun = "powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`""

# Run wsl.exe and return its output as text. Older WSL versions print UTF-16, which shows up
# here with NUL characters between letters; WSL_UTF8 asks newer ones for UTF-8, and removing
# NULs handles the older ones. Error output is dropped: Windows PowerShell would otherwise
# treat it as a failure of this script.
function Invoke-Wsl([string[]]$wslArgs) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $env:WSL_UTF8 = "1"
        $out = & wsl.exe @wslArgs 2>$null | Out-String
        $script:WslCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $old
    }
    return ($out -replace "`0", "")
}

# The installed Linux distributions, from `wsl --list --verbose`.
function Get-Distros {
    if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) { return @() }
    $lines = (Invoke-Wsl @("--list", "--verbose")) -split "`r?`n"
    if ($script:WslCode -ne 0) { return @() }
    $result = @()
    foreach ($line in ($lines | Select-Object -Skip 1)) {
        $clean = $line.Trim()
        if ($clean -eq "") { continue }
        $isDefault = $clean.StartsWith("*")
        $parts = ($clean.TrimStart("*").Trim()) -split "\s+"
        if ($parts.Count -lt 3) { continue }
        $name = $parts[0..($parts.Count - 3)] -join " "
        if ($name -like "docker-desktop*") { continue }
        $result += [pscustomobject]@{
            Name = $name; Version = $parts[-1]; Default = $isDefault
            Release = ""; Python = ""; Uid = ""; NewEnough = $false; Probed = $false
        }
    }
    return $result
}

# Ask a distribution which release it is, which Python it has, and whether it has a user of
# its own yet (Ubuntu creates one the first time it is opened; until then it runs as root).
# A WSL 2 distribution cannot start while virtualization is off, so it is not asked then.
function Read-Distro($d) {
    # One line, with no double quotes: Windows PowerShell 5.1 does not pass those on intact.
    $probe = '. /etc/os-release 2>/dev/null; echo ID=$ID VER=$VERSION_ID ' +
        'PY=$(python3 -c ''import sys; print(*sys.version_info[:2], sep=chr(46))'' 2>/dev/null) ' +
        'UID=$(id -u)  # init-math-probe'
    $out = Invoke-Wsl @("-d", $d.Name, "--exec", "sh", "-c", $probe)
    if ($script:WslCode -ne 0 -or "$out" -notmatch "ID=(\S*) VER=(\S*) PY=(\S*) UID=(\S*)") { return }
    $id = $Matches[1]; $ver = $Matches[2]; $py = $Matches[3]
    $d.Probed = $true
    $d.Uid = $Matches[4]
    $d.Python = $py
    $d.Release = "$id $ver".Trim()
    $new = $false
    if ($py -match "^3\.(\d+)$" -and [int]$Matches[1] -ge 11) { $new = $true }
    if ($id -eq "ubuntu" -and $ver -match "^(\d+)\." -and [int]$Matches[1] -ge 24) { $new = $true }
    if ($id -eq "debian" -and $ver -match "^(\d+)" -and [int]$Matches[1] -ge 12) { $new = $true }
    $d.NewEnough = $new
}

# Virtualization: "on" (the hypervisor runs), "vmp-off" (the processor allows it but the
# Virtual Machine Platform feature is off or waits for a restart), "firmware-off" (also off
# in the computer's firmware settings), or "unknown". While the hypervisor runs, the
# processor's own flag reads False, so the hypervisor is asked first.
function Get-Virtualization {
    if ($env:INIT_MATH_TEST_VIRT) { return $env:INIT_MATH_TEST_VIRT }   # for bin/test-setup-windows
    try {
        if ((Get-CimInstance Win32_ComputerSystem).HypervisorPresent) { return "on" }
        if (@(Get-CimInstance Win32_Processor)[0].VirtualizationFirmwareEnabled) { return "vmp-off" }
        return "firmware-off"
    } catch {
        return "unknown"
    }
}

# Run a command in an administrator PowerShell window, which Windows asks permission for.
# The window stays open if the command fails, so its message can be read.
function Invoke-AsAdmin([string]$command, [string]$what) {
    $script = "$command; `$c = `$LASTEXITCODE; if (`$c -ne 0) { Read-Host 'That did not work (see above). Press Enter to close this window' }; exit `$c"
    try {
        $p = Start-Process -ErrorAction Stop -FilePath "powershell.exe" -Verb RunAs -Wait -PassThru -ArgumentList @("-NoProfile", "-Command", $script)
    } catch {
        Stop-WithMessage ("Windows did not give permission to $what, so nothing was changed. If it asked for " +
            "someone else's administrator password (a computer your university or employer manages), ask your " +
            "IT department to $what for you, then run this again:`n`n    $rerun")
    }
    return $p.ExitCode
}

function Show-FirmwareSteps {
    Say "How to turn on virtualization in the firmware (the settings the computer has before Windows starts):"
    Say "  1. Save your work and close your programs."
    Say "  2. Windows 10: Settings > Update & Security > Recovery > Advanced startup > Restart now."
    Say "     Windows 11: Settings > System > Recovery > Advanced startup > Restart now."
    Say "  3. On the blue screen choose Troubleshoot > Advanced options > UEFI Firmware Settings > Restart."
    Say "  4. In the firmware menu, find the virtualization setting. It is called Intel Virtualization"
    Say "     Technology, VT-x, SVM Mode or AMD-V, usually under Advanced or CPU Configuration. Set it to"
    Say "     Enabled, then save and exit (often the F10 key). If it is already Enabled, just exit."
    Say "  If you cannot find it, or the computer is managed by your university or employer, ask IT."
}

# ---- Check what Windows has -------------------------------------------------------------

$hasWsl = [bool](Get-Command wsl.exe -ErrorAction SilentlyContinue)
$modern = $false
if ($hasWsl) {
    [void](Invoke-Wsl @("--version"))   # the WSL built into Windows 10 does not know --version
    $modern = ($script:WslCode -eq 0)
}
$virt = Get-Virtualization
$distros = @(Get-Distros)
foreach ($d in $distros) {
    if ($d.Version -eq "1" -or $virt -eq "on" -or $virt -eq "unknown") { Read-Distro $d }
}

# Prefer Ubuntu 24.04, then the default distribution, then any other new enough one.
$distro = $distros | Where-Object { $_.Name -eq $Wanted } | Select-Object -First 1
if (-not $distro) { $distro = $distros | Where-Object { $_.NewEnough -and $_.Default } | Select-Object -First 1 }
if (-not $distro) { $distro = $distros | Where-Object { $_.NewEnough } | Select-Object -First 1 }
# A WSL 2 distribution that could not be asked (virtualization off) is kept if it is the
# default: it is checked again once virtualization is on.
if (-not $distro) {
    $distro = $distros | Where-Object { -not $_.Probed -and $_.Version -eq "2" -and $_.Default } | Select-Object -First 1
}

$rows = @()
$todo = @()
if (-not $hasWsl) {
    Stop-WithMessage ("This Windows has no WSL. init-math needs Windows 10 version 2004 or newer, or Windows 11. " +
        "Run Windows Update, then run this again.")
}
if ($modern) {
    $rows += , @("OK", "WSL is up to date")
} else {
    $rows += , @("TO DO", "WSL is the old version built into Windows 10; setup updates it")
    $todo += "update"
}
switch ($virt) {
    "on" { $rows += , @("OK", "virtualization is on") }
    "vmp-off" {
        $rows += , @("TO DO", "the Virtual Machine Platform feature is off; setup turns it on (a restart follows)")
        $todo += "vmp"
    }
    "firmware-off" {
        $rows += , @("TO DO", "virtualization is not running; setup makes sure the Virtual Machine Platform feature is on (a restart follows)")
        $rows += , @("NEEDS YOU", "virtualization appears to be off in this computer's firmware; setup shows how to turn it on")
        $todo += "vmp"
        $todo += "firmware"
    }
    default { $rows += , @("?", "could not check virtualization; setup finds out when it starts Linux") }
}
if (-not $distro) {
    $old = @($distros | Where-Object { $_.Probed -and -not $_.NewEnough })
    if ($old.Count -gt 0) {
        $o = $old[0]
        $what = "your '$($o.Name)'"
        if ($o.Release) { $what += " ($($o.Release)" + $(if ($o.Python) { ", Python $($o.Python))" } else { ")" }) }
        $rows += , @("TO DO", "$what is too old for init-math; setup installs Ubuntu 24.04 next to it and leaves it as it is")
    } else {
        $rows += , @("TO DO", "no Linux distribution yet; setup installs Ubuntu 24.04")
    }
    $todo += "install"
} else {
    $label = "Linux: '$($distro.Name)'"
    if ($distro.Release) { $label += " ($($distro.Release))" }
    if ($distro.Version -eq "1") {
        $rows += , @("TO DO", "$label runs on WSL version 1; setup converts it to version 2, which Claude Code and Codex need")
        $todo += "convert"
    } elseif ($distro.Probed -or $distro.Name -eq $Wanted) {
        $rows += , @("OK", "$label on WSL 2")
    } else {
        $rows += , @("?", "$label on WSL 2; whether it is new enough is checked once virtualization is on")
    }
    if ($distro.Uid -eq "0") {
        $rows += , @("NEEDS YOU", "'$($distro.Name)' has no Linux user yet; setup opens it so you can choose one")
        $todo += "user"
    }
}

Say ""
Say "Checking Windows:"
foreach ($r in $rows) { Say ("  {0,-10} {1}" -f $r[0], $r[1]) }
Say ""

# From here on, programs' error output is shown to the user rather than ending this script:
# Windows PowerShell 5.1 would otherwise stop at the first progress line a program writes
# to its error output (curl and apt inside setup.sh do).
$ErrorActionPreference = "Continue"

# ---- Windows steps ----------------------------------------------------------------------

if ($todo.Count -gt 0) {
    if ($Check) {
        Stop-WithMessage "Windows is not ready yet. Run this again without -Check to get a plan that fixes this."
    }
    Say "Before the Linux part of setup, Windows needs these, in this order:"
    $n = 1
    if ($todo -contains "update") {
        Say "  $n. Update WSL (wsl --update). Windows asks for permission."; $n++
    }
    if ($todo -contains "vmp") {
        Say "  $n. Turn on the Virtual Machine Platform feature (wsl --install --no-distribution)."
        Say "     Windows asks for permission. Then Windows must restart."; $n++
    }
    if ($todo -contains "firmware") {
        Say "  $n. During that restart, turn on virtualization in the firmware settings. You do this;"
        Say "     setup shows how."; $n++
    }
    if ($todo -contains "convert") {
        Say "  $n. Convert '$($distro.Name)' to WSL version 2 (wsl --set-version). It can take a few minutes."; $n++
    }
    if ($todo -contains "install") {
        Say "  $n. Install Ubuntu 24.04 (wsl --install -d $Wanted). Any Linux you already have is left as it is."
        Say "     A window opens in which you choose a Linux user name and password:"
        Say "       - the name in lowercase letters, no spaces (for example jane);"
        Say "       - the password does not appear as you type. Write it down: whenever setup or Ubuntu"
        Say "         asks for 'your password' later, it means this one;"
        Say "       - when the window shows a line ending in  $  (like  jane@laptop:~$ ), type  exit  and"
        Say "         press Enter."; $n++
    }
    if ($todo -contains "user") {
        Say "  $n. Open '$($distro.Name)' once to choose its Linux user name and password."; $n++
    }
    Say "Where a restart is needed, setup stops; run it again afterwards and finished steps are skipped."
    Say "On a computer your university or employer manages, ask your IT department to update WSL and turn"
    Say "on the Virtual Machine Platform feature; the rest you can do in your own account."
    Say ""
    if ($PlanOnly) {
        Say "That is the plan for Windows. Once it is done, setup.sh makes the plan for the Linux part."
        Exit-Setup 0
    }
    $answer = Read-Host "Go ahead? [y/N]"
    if ("$answer".Trim() -notmatch "^(y|yes)$") { Stop-WithMessage "Nothing was changed." -NoLog }

    if ($todo -contains "update") {
        Say "Updating WSL..."
        [void](Invoke-AsAdmin "wsl.exe --update; if (`$LASTEXITCODE -ne 0) { wsl.exe --update --web-download }" "update WSL")
        [void](Invoke-Wsl @("--version"))
        if ($script:WslCode -ne 0) {
            Stop-WithMessage ("WSL could not be updated. Install 'Windows Subsystem for Linux' from the Microsoft Store, " +
                "then run this again:`n`n    $rerun")
        }
        Say "WSL is up to date."
    }
    if ($todo -contains "vmp") {
        Say "Turning on the Virtual Machine Platform feature..."
        $c = Invoke-AsAdmin "wsl.exe --install --no-distribution" "turn on the Virtual Machine Platform feature"
        Say ""
        if ($c -ne 0) {
            Say "The administrator window reported a problem (it showed the message). If that message said"
            Say "the change needs a restart, that is fine: go on below. Otherwise, ask your IT department to"
            Say "turn on the Virtual Machine Platform feature, or report it at https://github.com/nkohen/init-math/issues."
            Say ""
        }
        if ($todo -contains "firmware") {
            Show-FirmwareSteps
            Say ""
            Say "The restart in step 2 above is the restart Windows needs."
        } else {
            Say "Now restart Windows (Start menu > Power > Restart)."
        }
        Say "Afterwards, open PowerShell in this folder again and run:"
        Say ""
        Say "    $rerun"
        Exit-Setup 0
    }
    if ($todo -contains "convert") {
        & wsl.exe --set-version $distro.Name 2
        if ($LASTEXITCODE -ne 0) {
            Stop-WithMessage "The conversion failed; the message above says why. Run this again once it is fixed:`n`n    $rerun"
        }
    }
    if ($todo -contains "install" -or $todo -contains "user") {
        if ($todo -contains "install") {
            Say "Installing Ubuntu 24.04. A new window opens; follow it, and come back here when it closes."
            Start-Process -FilePath "wsl.exe" -ArgumentList @("--install", "-d", $Wanted) -Wait
        } else {
            Say "Opening '$($distro.Name)'. Choose your Linux user name and password in the new window, then"
            Say "type  exit  there and press Enter."
            Start-Process -FilePath "wsl.exe" -ArgumentList @("-d", $distro.Name) -Wait
        }
        $distros = @(Get-Distros)
        $distro = $distros | Where-Object { $_.Name -eq $(if ($todo -contains "install") { $Wanted } else { $distro.Name }) } | Select-Object -First 1
        if ($distro) { Read-Distro $distro }
        if (-not $distro -or -not $distro.Probed -or $distro.Uid -eq "0") {
            Say ""
            Say "Linux is not ready yet. If Windows asked you to restart, restart now. Then open"
            Say "'Ubuntu 24.04 LTS' from the Start menu once, choose your Linux user name and password, type"
            Say "exit, and run this again in PowerShell, in the folder holding it:"
            Say ""
            Say "    $rerun"
            Exit-Setup 0
        }
        Say "Linux is ready. Continuing with the setup."
        Say ""
    }
}

Say "Using the Linux distribution '$($distro.Name)'."

# ---- Linux steps ------------------------------------------------------------------------

# Copy setup.sh into the Linux home folder. It travels through standard input so that no
# Windows path has to be translated. On the Linux side, the byte-order mark that Windows
# PowerShell puts in front of piped text, and carriage returns, are removed (bash cannot
# read them; Windows tools, and PowerShell's pipe itself, may add them).
$text = [System.IO.File]::ReadAllText($setup)
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
$text | & wsl.exe -d $distro.Name --cd "~" --exec sh -c "sed '1s/^\xEF\xBB\xBF//' | tr -d '\r' > init-math-setup.sh"
if ($LASTEXITCODE -ne 0) {
    Stop-WithMessage "Could not copy setup.sh into '$($distro.Name)'. Open it from the Start menu once to finish its setup, then run this again:`n`n    $rerun"
}

$passOn = @()
if ($Check) { $passOn += "--check" }
if ($PlanOnly) { $passOn += "--plan-only" }
if ($Harness) { $passOn += @("--harness", $Harness) }

# setup.sh updates an older installed plugin to the version of this folder; inside Linux it
# cannot see this folder's plugin.json, so the version travels with it.
$version = ""
$pluginJson = Join-Path $here "plugin.json"
if (Test-Path $pluginJson) {
    try { $version = [string]((Get-Content -Raw $pluginJson | ConvertFrom-Json).version) } catch { $version = "" }
}

Say "Running setup.sh inside Linux. (Its plan is saved in your Linux home folder.)"
& wsl.exe -d $distro.Name --cd "~" --exec env INIT_MATH_FROM_WINDOWS=1 "INIT_MATH_VERSION=$version" bash init-math-setup.sh @passOn
$code = $LASTEXITCODE
Say ""
if ($PlanOnly -and $code -eq 0) {
    Say "Nothing was changed. To carry out the plan, run (without -PlanOnly):"
    Say ""
    Say "    $rerun"
} elseif ($code -eq 0) {
    Say "From now on, work inside Linux, not in PowerShell: type  wsl -d $($distro.Name)  in PowerShell"
    if ($distro.Name -eq $Wanted) { Say "(or choose 'Ubuntu 24.04 LTS' in the Start menu) and type the commands there." }
    else { Say "and type the commands there." }
    Say "If an agent program is also installed on Windows itself, typing its name in PowerShell"
    Say "starts that Windows copy, which does not have init-math."
} else {
    Say "Setup is not finished. Do what it says above, then run this again in PowerShell, in the"
    Say "folder holding it (steps already done are skipped):"
    Say ""
    Say "    $rerun"
    if ($Logging) {
        Say ""
        Say "Everything shown here is also saved in $WinLog, and the Linux part in"
        Say "~/init-math-setup.log inside Linux."
    }
}
Exit-Setup $code
