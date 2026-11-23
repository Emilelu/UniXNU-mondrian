# Run a command inside WSL without flashing a console window.
#
# PowerShell 5.1 cannot combine -WindowStyle Hidden with -RedirectStandardOutput
# (the redirect gets swallowed), so the redirection is handed to cmd.exe and
# PowerShell only starts it hidden and waits.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/wsl-hidden.ps1 `
#       -Command 'cd /mnt/e/hackios/k60-gates && K60_ALLOW_BUILD=1 bash scripts/build-ios27-linux.sh' `
#       -Log 'E:\hackios\k60-gates\build\build.log'
param(
    [Parameter(Mandatory = $true)][string]$Command,
    [Parameter(Mandatory = $true)][string]$Log,
    [string]$Distro = ""
)

$wsl = 'wsl.exe'
if ($Distro) { $wsl = "$wsl -d $Distro" }
$inner = '{0} -e bash -lc "{1}" > "{2}" 2>&1' -f $wsl, ($Command -replace '"', '\"'), $Log
$proc = Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\cmd.exe') `
    -ArgumentList '/c', $inner -WindowStyle Hidden -Wait -PassThru
exit $proc.ExitCode
