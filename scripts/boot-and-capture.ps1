#!/usr/bin/env pwsh
<# One boot supervisor, one pre-armed serial reader, one evidence directory.
   This supervisor NEVER opens SerialPort. Only capture-k60-usblog.ps1 does. #>
param(
    [Parameter(Mandatory=$true)][string]$Image,
    [int]$Seconds=300,
    [int]$IdleSeconds=0,
    [int]$ReopenSeconds=120,
    [int]$PanicGraceSeconds=30,
    [int]$WaitFastboot=0,
    [switch]$RebootToFastboot,
    [string]$OutDir,
    [string]$Fastboot='D:\Android\platform-tools\fastboot.exe',
    [string]$Adb='D:\Android\platform-tools\adb.exe',
    [string]$Serial='6033dbec',
    [string]$Actor='',
    [string]$LockPath='E:\iOS Port\Work\state\k60-device-boot.lock'
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'k60-boot-lock.ps1')
if (-not (Test-Path -LiteralPath $Image -PathType Leaf)) { throw "image not found: $Image" }
if (-not (Test-Path -LiteralPath $Fastboot -PathType Leaf)) { throw "fastboot not found: $Fastboot" }
$Image=(Resolve-Path -LiteralPath $Image).Path
$imageSha=(Get-FileHash -LiteralPath $Image -Algorithm SHA256).Hash
if (-not $OutDir) { $OutDir="E:\iOS Port\Work\evidence\usblog-$(Get-Date -Format 'yyyyMMdd-HHmmss-fff')" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
if (Test-Path -LiteralPath (Join-Path $OutDir 'boot.json')) { throw "evidence directory already contains a boot: $OutDir" }
$ready=Join-Path $OutDir 'capture.ready'; $stopFile=Join-Path $OutDir 'capture.stop'
$collector=Join-Path $PSScriptRoot 'capture-k60-usblog.ps1'
$collectorOut=Join-Path $OutDir 'collector.stdout.log'
$collectorErr=Join-Path $OutDir 'collector.stderr.log'
$bootText=Join-Path $OutDir 'fastboot.log'
$metaPath=Join-Path $OutDir 'capture.json'
$bootRecord=Join-Path $OutDir 'boot.json'
$reader=$null; $bootRc=-1; $bootAccepted=$false; $returned=$false; $lastError=$null
$bootClaim=$null; $bootBusy=$false
$started=Get-Date
$meta=[ordered]@{ image=$Image; imageSha256=$imageSha; serial=$Serial; startedAt=$started.ToString('o'); captureArmed=$false; bootAccepted=$false; bootExitCode=-1; returnedToFastboot=$false }
function Invoke-Fastboot([string[]]$Arguments) {
    $prev=$ErrorActionPreference; $ErrorActionPreference='Continue'
    try { $text=(& $Fastboot @Arguments 2>&1 | Out-String); $rc=$LASTEXITCODE }
    finally { $ErrorActionPreference=$prev }
    return [pscustomobject]@{ text=$text; code=$rc }
}
function Test-TargetFastboot {
    $probe=Invoke-Fastboot @('devices')
    return ($probe.code -eq 0 -and $probe.text -match ('(?m)^'+[regex]::Escape($Serial)+'\s+fastboot\s*$'))
}
function Invoke-Adb([string[]]$Arguments) {
    $prev=$ErrorActionPreference; $ErrorActionPreference='Continue'
    try { $text=(& $Adb @Arguments 2>&1 | Out-String); $rc=$LASTEXITCODE }
    finally { $ErrorActionPreference=$prev }
    return [pscustomobject]@{ text=$text; code=$rc }
}
function Test-TargetAdb {
    if (-not (Test-Path -LiteralPath $Adb -PathType Leaf)) { return $false }
    $probe=Invoke-Adb @('devices')
    return ($probe.text -match ('(?m)^'+[regex]::Escape($Serial)+'\s+(device|recovery|sideload)\s*$'))
}
try {
    if ([string]::IsNullOrWhiteSpace($Actor)) {
        throw 'K60_BOOT_ACTOR_REQUIRED: pass -Actor from K60_AGENT_ID; lock attribution cannot be anonymous'
    }
    try {
        $bootClaim = Enter-K60BootLock -Path $LockPath -Actor $Actor -Serial $Serial -Image $Image
    } catch {
        if ($_.Exception.Message -like 'K60_BOOT_BUSY:*') { $bootBusy = $true }
        throw
    }
    if ($RebootToFastboot -and -not (Test-TargetFastboot)) {
        if (-not (Test-TargetAdb)) { throw "target $Serial is neither in fastboot nor reachable by adb" }
        # The reboot happens INSIDE the claim: a reboot outside it would tear down
        # another actor's capture, and the loser would read an image it never booted.
        Write-Host 'Rebooting the target into fastboot under the claim.'
        $reboot=Invoke-Adb @('-s',$Serial,'reboot','bootloader')
        $reboot.text | Set-Content -LiteralPath $bootText -Encoding UTF8
        $deadline=(Get-Date).AddSeconds([Math]::Max($WaitFastboot,60))
        while (-not (Test-TargetFastboot)) {
            if ((Get-Date) -ge $deadline) { throw "target $Serial did not reach fastboot after adb reboot bootloader" }
            Start-Sleep -Seconds 1
        }
    }
    if (-not (Test-TargetFastboot)) { throw "target $Serial is not in fastboot" }
    Write-Host "Image: $Image`nSHA256: $imageSha`nEvidence: $OutDir"
    $engine=Join-Path $PSHOME 'powershell.exe'
    if (-not (Test-Path -LiteralPath $engine)) { $engine=Join-Path $PSHOME 'pwsh.exe' }
    # Start-Process joins argument arrays; quote the actual path-bearing arguments.
    $argv=@('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$collector+'"'),
        '-Seconds',"$Seconds",'-IdleSeconds',"$IdleSeconds",'-ReopenSeconds',"$ReopenSeconds",
        '-PanicGraceSeconds',"$PanicGraceSeconds",'-OutDir',('"'+$OutDir+'"'),
        '-ReadyFile',('"'+$ready+'"'),'-StopFile',('"'+$stopFile+'"'))
    # Windows PowerShell 5.1 builds a case-insensitive StringDictionary from the
    # process environment before it starts a child. This host exports case
    # variants of the same variable (NO_PROXY + no_proxy, HTTPS_PROXY +
    # https_proxy …), so Start-Process throws
    #   Item has already been added. Key in dictionary: 'HTTPS_PROXY' ...
    # and the boot never happens. Collapse every case-variant group to a single
    # canonical (upper-case) name first; the collector only needs the serial port.
    $envNow=[Environment]::GetEnvironmentVariables()
    $groups=@{}
    foreach ($name in $envNow.Keys) { $groups[$name.ToUpperInvariant()]=@($groups[$name.ToUpperInvariant()]) + $name }
    foreach ($canonical in @($groups.Keys)) {
        $variants=@($groups[$canonical] | Where-Object { $_ })
        if ($variants.Count -le 1) { continue }
        $value=[Environment]::GetEnvironmentVariable($canonical,'Process')
        if (-not $value) { $value=$envNow[$variants[0]] }
        foreach ($name in $variants) { [Environment]::SetEnvironmentVariable($name,$null,'Process') }
        [Environment]::SetEnvironmentVariable($canonical,$value,'Process')
    }
    $reader=Start-Process -FilePath $engine -ArgumentList $argv -PassThru -WindowStyle Hidden -RedirectStandardOutput $collectorOut -RedirectStandardError $collectorErr
    $readyDeadline=(Get-Date).AddSeconds(20)
    while (-not (Test-Path -LiteralPath $ready)) {
        $reader.Refresh()
        if ($reader.HasExited) { throw "collector exited before readiness; see $collectorErr" }
        if ((Get-Date) -ge $readyDeadline) { throw 'collector readiness timed out; boot not issued' }
        Start-Sleep -Milliseconds 100
    }
    $meta.captureArmed=$true
    $meta | ConvertTo-Json | Set-Content -LiteralPath $bootRecord -Encoding UTF8
    Write-Host 'Capture armed before fastboot boot.'
    $boot=Invoke-Fastboot @('-s',$Serial,'boot',$Image)
    $bootRc=$boot.code; $boot.text | Set-Content -LiteralPath $bootText -Encoding UTF8
    Write-Host $boot.text
    # fastboot writes progress to stderr, which PowerShell turns into a
    # NativeCommandError record; the exit code can be -1 even when the phone
    # is already running the image. The text is the only trustworthy signal.
    $bootAccepted=($boot.text -match 'Booting\s+OKAY')
    if (-not $bootAccepted) { throw "fastboot boot failed (exit $bootRc); see $bootText" }
    $limit=(Get-Date).AddSeconds($Seconds+190+$ReopenSeconds)
    while ($true) {
        $reader.Refresh()
        if ($reader.HasExited) { break }
        if (Test-TargetFastboot) {
            $returned=$true
            if (-not (Test-Path -LiteralPath $stopFile)) { 'device returned to fastboot' | Set-Content -LiteralPath $stopFile -Encoding ASCII }
        }
        if ((Get-Date) -ge $limit) { throw 'collector exceeded total budget' }
        Start-Sleep -Milliseconds 500
    }
    if (-not $returned) { $returned=Test-TargetFastboot }
} catch {
    $lastError=$_.Exception.Message; Write-Host "Boot supervision error: $lastError"
} finally {
    try {
        if ($reader) {
            $reader.Refresh()
            if (-not $reader.HasExited) {
                'supervisor stopped' | Set-Content -LiteralPath $stopFile -Encoding ASCII
                $end=(Get-Date).AddSeconds(5)
                while (-not $reader.HasExited -and (Get-Date) -lt $end) { Start-Sleep -Milliseconds 100; $reader.Refresh() }
                if (-not $reader.HasExited) { $reader.Kill(); $reader.WaitForExit() }
            }
        }
        $meta.bootAccepted=$bootAccepted; $meta.bootExitCode=$bootRc
        $meta.returnedToFastboot=$returned; $meta.error=$lastError; $meta.finishedAt=(Get-Date).ToString('o')
        $meta.bootClaimBusy=$bootBusy; $meta.actor=$Actor
        $meta | ConvertTo-Json | Set-Content -LiteralPath $bootRecord -Encoding UTF8
    } finally {
        if ($bootClaim) { Exit-K60BootLock -Claim $bootClaim }
    }
}
if (Test-Path -LiteralPath $metaPath) {
    $capture=Get-Content -Raw -LiteralPath $metaPath | ConvertFrom-Json
    Write-Host ("Console verdict: {0}; bytes={1}; complete={2}; returnedToFastboot={3}" -f $capture.state,$capture.bytes,$capture.complete,$returned)
    if ($capture.bytes -gt 0) { Get-Content -LiteralPath (Join-Path $OutDir 'console.log') -Tail 40 }
} else { Write-Host 'Console verdict: collector metadata missing; no kernel diagnosis is supported.' }
Write-Host "Evidence: $OutDir"
# 6 = another actor holds the machine-wide claim; the boot was never issued.
if ($bootBusy) { Write-Host 'Boot claim refused: another actor is booting the device; no fastboot boot was issued.'; exit 6 }
if ($lastError -or -not $bootAccepted) { exit 1 }
if (-not $capture -or $capture.bytes -eq 0) { exit 2 }
if ($returned) { exit 5 }
if (-not $capture.complete) { exit 4 }
exit 0
