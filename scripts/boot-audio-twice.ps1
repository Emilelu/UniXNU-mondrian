<#
.SYNOPSIS
    Boot the same audio image twice and judge both captures.

.DESCRIPTION
    Iron rule 5 requires the same image booted twice with the serial console armed
    before each boot. Doing that by hand is where a step-8 claim goes wrong: the two
    runs drift apart, or only one of them is judged. This wrapper runs
    boot-and-capture.ps1 twice against the same file, refuses to continue if the
    second run would use a different image, and then judges both evidence
    directories with scripts/judge-audio-capture.py.

    Exit codes: 0 = both runs succeeded, 1 = at least one run failed,
    2 = the probe never ran in at least one run (and no run failed).

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/boot-audio-twice.ps1 -Image E:\k60-work\artifacts\audio-probe-20261114e\boot.img -EvidenceRoot E:\k60-work\evidence\audio-probe-e
#>
param(
    [Parameter(Mandatory=$true)][string]$Image,
    [Parameter(Mandatory=$true)][string]$EvidenceRoot,
    [int]$Seconds=300,
    [int]$IdleSeconds=0,
    [int]$ReopenSeconds=120,
    [int]$WaitFastbootSeconds=300,
    [string]$Fastboot='D:\Android\platform-tools\fastboot.exe',
    [string]$Serial='6033dbec'
)
$ErrorActionPreference='Stop'
if (-not (Test-Path -LiteralPath $Image -PathType Leaf)) { throw "image not found: $Image" }
$Image=(Resolve-Path -LiteralPath $Image).Path
$imageSha=(Get-FileHash -LiteralPath $Image -Algorithm SHA256).Hash.ToLowerInvariant()
$supervisor=Join-Path $PSScriptRoot 'boot-and-capture.ps1'
$judge=Join-Path $PSScriptRoot 'judge-audio-capture.py'
foreach ($p in @($supervisor,$judge)) { if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "missing $p" } }

function Test-TargetFastboot {
    $prev=$ErrorActionPreference; $ErrorActionPreference='Continue'
    try { $text=(& $Fastboot 'devices' 2>&1 | Out-String); $rc=$LASTEXITCODE }
    finally { $ErrorActionPreference=$prev }
    return ($rc -eq 0 -and $text -match ('(?m)^'+[regex]::Escape($Serial)+'\s+fastboot\s*$'))
}

function Wait-Fastboot([int]$Limit) {
    $deadline=(Get-Date).AddSeconds($Limit)
    while ((Get-Date) -lt $deadline) {
        if (Test-TargetFastboot) { return $true }
        Start-Sleep -Seconds 2
    }
    return (Test-TargetFastboot)
}

Write-Host "Image:  $Image"
Write-Host "SHA256: $imageSha"
Write-Host "Root:   $EvidenceRoot"
if (-not (Wait-Fastboot 10)) { throw "target $Serial is not in fastboot; nothing was booted" }

$runs=@()
foreach ($n in 1,2) {
    $out=Join-Path $EvidenceRoot ("run{0}" -f $n)
    if (Test-Path -LiteralPath (Join-Path $out 'boot.json')) { throw "run$n already has evidence: $out" }
    Write-Host ''
    Write-Host "=== run $n of 2 -> $out"
    if ($n -eq 2 -and -not (Wait-Fastboot $WaitFastbootSeconds)) {
        throw "run1 did not return to fastboot within $WaitFastbootSeconds s; run 2 not attempted"
    }
    & $supervisor -Image $Image -OutDir $out -Seconds $Seconds -IdleSeconds $IdleSeconds -ReopenSeconds $ReopenSeconds -Fastboot $Fastboot -Serial $Serial
    $record=Join-Path $out 'boot.json'
    if (-not (Test-Path -LiteralPath $record)) { throw "run$n wrote no boot.json" }
    $meta=Get-Content -LiteralPath $record -Raw | ConvertFrom-Json
    if ($meta.imageSha256 -and $meta.imageSha256.ToLowerInvariant() -ne $imageSha) {
        throw ("run{0} booted a different image: {1}" -f $n, $meta.imageSha256)
    }
    $runs += [pscustomobject]@{ run=$n; dir=$out; accepted=[bool]$meta.bootAccepted; returned=[bool]$meta.returnedToFastboot }
}

Write-Host ''
Write-Host "=== both runs used image $imageSha"
$judgeArgs=@($judge) + ($runs | ForEach-Object { $_.dir })
& python @judgeArgs
$rc=$LASTEXITCODE
Write-Host ''
$runs | ForEach-Object { Write-Host ("run{0}: bootAccepted={1} returnedToFastboot={2} dir={3}" -f $_.run,$_.accepted,$_.returned,$_.dir) }
Write-Host "judge exit: $rc"
exit $rc
