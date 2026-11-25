<#
.SYNOPSIS
  Compact the WSL2 ext4.vhdx down to the size of the data it actually holds.

.DESCRIPTION
  A WSL distribution that builds kernels grows its virtual disk by gigabytes and
  never gives the space back: deleting files inside the guest frees blocks for
  the guest filesystem, not for Windows. Only `diskpart compact vdisk` returns
  them, and it refuses to run unless the disk is *uncompressed*, *unencrypted*
  and *not sparse* (/mnt/e/iOS Port/Work/scratch notes, P-246 family).

  The order therefore matters and this script is that order:

    1. wsl --shutdown                     release the guest's handle on the file
    2. wsl --manage <distro> --set-sparse false
    3. diskpart: attach vdisk readonly / compact vdisk / detach vdisk   (UAC)
    4. wsl --manage <distro> --set-sparse true   (restore, in a finally block)

  Step 3 needs an elevated console. The script relaunches only itself elevated,
  keeps step 1/2/4 in the calling (non-elevated) window, and reports the byte
  count before and after. `wsl --shutdown` is unconditional, so do not run this
  while another lane is mid-build.

.PARAMETER Distro
  Distribution name. Default: the default distribution reported by `wsl -l -q`.

.PARAMETER Vhdx
  Path of the ext4.vhdx. Default: discovered from the registry for -Distro.

.PARAMETER NoShutdown
  Skip step 1. Use only when you have already stopped WSL yourself.

.PARAMETER RestoreSparse
  Re-enable the sparse flag at the end. Default: on. Pass -RestoreSparse:$false
  to leave the disk non-sparse (the next compact then needs no flag change).

.EXAMPLE
  .\scripts\compact-wsl.ps1
  Compacts the default distribution and prints how much D: got back.

.EXAMPLE
  .\scripts\compact-wsl.ps1 -Distro Ubuntu-24.04 -WhatIf
  Prints every step and the sizes it would work on, changes nothing.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
  [string] $Distro,
  [string] $Vhdx,
  [switch] $NoShutdown,
  [bool] $RestoreSparse = $true
)

$ErrorActionPreference = 'Stop'
$Wsl = Join-Path $env:SystemRoot 'System32\wsl.exe'
$GiB = 1GB
$Sep = '-' * 72

function Write-Step([string] $text) { Write-Host "==> $text" -ForegroundColor Cyan }
function Write-Note([string] $text) { Write-Host "    $text" -ForegroundColor DarkGray }

function Get-GuestUsedGiB {
  param([string] $Name)
  # --output=used is in 1K blocks. wsl.exe itself writes boot warnings to stderr
  # (for example a drive it cannot mount), and with $ErrorActionPreference = Stop
  # a native command's stderr becomes a terminating error, so relax the policy
  # for the duration of this probe instead of failing the whole run on a warning.
  $prev = $ErrorActionPreference
  $ErrorActionPreference = 'SilentlyContinue'
  $raw = & $Wsl -d $Name -u root -e bash -lc 'df --output=used -k / | tail -1' 2>$null
  $code = $LASTEXITCODE
  $ErrorActionPreference = $prev
  if ($code -ne 0 -or -not $raw) { return $null }
  $kb = [int64]($raw.Trim())
  return [math]::Round($kb / 1MB, 1)
}

function Find-Vhdx {
  param([string] $Name)
  $base = Join-Path $env:LOCALAPPDATA 'Packages'
  $cand = Get-ChildItem -Path $base -Directory -Filter 'CanonicalGroupLimited*' -ErrorAction SilentlyContinue |
    ForEach-Object {
      Get-ChildItem -Path $_.FullName -Recurse -Filter 'ext4.vhdx' -ErrorAction SilentlyContinue
    } | Select-Object -First 20
  if (-not $cand) { return $null }
  if ($Name) {
    # The distro name appears in the package folder for Store installs.
    $hit = $cand | Where-Object { $_.FullName -match [regex]::Escape($Name.Replace('Ubuntu-', 'Ubuntu')) }
    if ($hit) { return $hit[0].FullName }
  }
  return $cand[0].FullName
}

function Get-VhdxSizeGiB { param([string] $Path) return [math]::Round((Get-Item -LiteralPath $Path).Length / $GiB, 1) }

# ---------------------------------------------------------------- elevation --
# Only the diskpart half needs elevation, so relaunch only that half.
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
  if (-not $Vhdx) { $Vhdx = Find-Vhdx -Name $Distro }
  if (-not $Vhdx -or -not (Test-Path -LiteralPath $Vhdx)) {
    throw "Cannot find ext4.vhdx. Pass -Vhdx 'D:\path\to\ext4.vhdx'."
  }

  Write-Step 'measuring before'
  Write-Note "vhdx   : $Vhdx ($(Get-VhdxSizeGiB $Vhdx) GiB)"
  $freeBefore = [math]::Round((Get-PSDrive D).Free / $GiB, 1)

  if (-not $NoShutdown) {
    if ($PSCmdlet.ShouldProcess('WSL', 'wsl --shutdown')) {
      Write-Step 'wsl --shutdown'
      & $Wsl --shutdown | Out-Null
      Start-Sleep -Seconds 5
    }
  }
  if ($PSCmdlet.ShouldProcess($Distro, 'set sparse false')) {
    Write-Step "wsl --manage $Distro --set-sparse false"
    & $Wsl --manage $Distro --set-sparse false 2>$null | Out-Null
  }

  $before = Get-VhdxSizeGiB $Vhdx
  $dp = Join-Path $env:TEMP 'k60-compact-vdisk.txt'
  # Built as a variable first: Set-Content honours -WhatIf, so writing the file
  # before the dry-run branch would make the dry run read a file that is not there.
  $dpLines = @(
    "select vdisk file=`"$Vhdx`""
    'attach vdisk readonly'
    'compact vdisk'
    'detach vdisk'
    'exit'
  )

  $log = Join-Path $env:TEMP 'k60-compact-out.txt'
  if ($WhatIfPreference) {
    Write-Step 'would run, in an elevated diskpart:'
    $dpLines | ForEach-Object { Write-Note $_ }
    Write-Step "would then run: wsl --manage $Distro --set-sparse true"
    Write-Host $Sep
    Write-Host ("vhdx   : {0} GiB now; guest holds {1} GiB, so the floor is about {1} GiB" -f (Get-VhdxSizeGiB $Vhdx), (Get-GuestUsedGiB $Distro))
    Write-Host ("D: free: {0} GiB now" -f $freeBefore)
    Write-Host $Sep
    return
  }
  $dpLines | Set-Content -LiteralPath $dp -Encoding ascii

  Write-Step 'diskpart compact vdisk (elevated)'
  # -Verb RunAs forces UseShellExecute, which refuses -RedirectStandardOutput
  # ("Parameter set cannot be resolved"). Elevate a cmd.exe that does the
  # redirection instead, so the diskpart transcript still lands in $log.
  $cmdLine = '/c diskpart /s "{0}" > "{1}" 2>&1' -f $dp, $log
  $proc = Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\cmd.exe') `
    -ArgumentList $cmdLine -Verb RunAs -Wait -PassThru -ErrorAction Stop
  Get-Content -LiteralPath $log -ErrorAction SilentlyContinue | ForEach-Object { Write-Note $_ }

  try {
    if ($RestoreSparse) {
      Write-Step "wsl --manage $Distro --set-sparse true"
      & $Wsl --manage $Distro --set-sparse true 2>$null | Out-Null
    }
  }
  finally {
    $after = Get-VhdxSizeGiB $Vhdx
    $freeAfter = [math]::Round((Get-PSDrive D).Free / $GiB, 1)
    Write-Host $Sep
    Write-Host ("vhdx   : {0} GiB -> {1} GiB   (freed {2} GiB)" -f $before, $after, ($before - $after))
    Write-Host ("D: free: {0} GiB -> {1} GiB" -f $freeBefore, $freeAfter)
    Write-Host ("guest  : {0} GiB used (this is the floor the vhdx cannot go below)" -f (Get-GuestUsedGiB $Distro))
    if ($after -ge $before) {
      Write-Host 'No shrink: the guest holds at least this much data, or a build is still holding files open.' -ForegroundColor Yellow
    }
    Write-Host $Sep
  }
  return
}

# ------------------------------------------------------------- elevated path --
Write-Step "diskpart compact on $Vhdx (elevated)"
$dp = Join-Path $env:TEMP 'k60-compact-vdisk.txt'
if (-not (Test-Path -LiteralPath $dp)) { throw "Missing $dp; run the script without elevation instead." }
& (Join-Path $env:SystemRoot 'System32\diskpart.exe') /s $dp
