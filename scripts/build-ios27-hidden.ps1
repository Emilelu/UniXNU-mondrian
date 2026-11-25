# Build the iOS 27 image without opening a console window.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-ios27-hidden.ps1
#   powershell ... -File scripts/build-ios27-hidden.ps1 -Tag r210 -ExtraArgs '--fd E:\...\fd'
#
# Everything after -ExtraArgs is appended to the build command. The log lands in
# build\ios27-<Tag>.log; the exit code is the build's exit code.
param(
    [string]$Tag = "local",
    [string]$Repo = "E:\iOS Port\Sources\Hardware\k60-gates",
    [string]$ExtraArgs = ""
)

$ErrorActionPreference = 'Stop'
$logDir = Join-Path $Repo 'build'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("ios27-{0}.log" -f $Tag)

$command = "cd /mnt/e/iOS Port/Sources/Hardware/k60-gates && K60_ALLOW_BUILD=1 bash scripts/build-ios27-linux.sh"
if ($ExtraArgs) { $command = "$command $ExtraArgs" }

& (Join-Path $PSScriptRoot 'wsl-hidden.ps1') -Command $command -Log $log
exit $LASTEXITCODE
