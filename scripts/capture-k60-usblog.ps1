#!/usr/bin/env pwsh
<# Single owner of the K60 CDC-ACM console. Writes readiness before boot and
   distinguishes an unseen port, open failure, zero bytes and truncated data. #>
param(
    [int]$Seconds = 300,
    [int]$IdleSeconds = 0,
    [int]$BaudRate = 115200,
    [string]$OutDir,
    [string]$ReadyFile,
    [string]$StopFile,
    [int]$WaitPortSeconds = 180,
    [int]$ReopenSeconds = 120,
    [int]$PanicGraceSeconds = 30
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'k60-capture-state.ps1')
if (-not $OutDir) { $OutDir = "E:\k60-work\evidence\usblog-$(Get-Date -Format 'yyyyMMdd-HHmmss-fff')" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$log = Join-Path $OutDir 'console.log'
$events = Join-Path $OutDir 'capture-events.jsonl'
$metaPath = Join-Path $OutDir 'capture.json'
$utf8 = [System.Text.UTF8Encoding]::new($false)
$mutex = [System.Threading.Mutex]::new($false, 'Local\K60-CDC-ACM-Capture')
$ownsLock = $false
try { $ownsLock = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $ownsLock = $true }
if (-not $ownsLock) {
    [ordered]@{ state='capture-busy'; complete=$false; bytes=0; pid=$PID; error='another collector owns the K60 console' } |
        ConvertTo-Json | Set-Content -LiteralPath $metaPath -Encoding UTF8
    $mutex.Dispose()
    Write-Error 'another collector owns the K60 console; boot was not permitted'
    exit 3
}
function Write-CaptureEvent([string]$kind, [string]$detail) {
    [ordered]@{ at=(Get-Date).ToString('o'); event=$kind; detail=$detail } | ConvertTo-Json -Compress |
        Add-Content -LiteralPath $events -Encoding UTF8
}
function Resolve-K60Port {
    $map = Get-ItemProperty 'HKLM:\HARDWARE\DEVICEMAP\SERIALCOMM' -ErrorAction SilentlyContinue
    if ($map) { foreach ($name in $map.PSObject.Properties.Name) { if ($name -like '*USBSER*') { return $map.$name } } }
    return $null
}
function Open-K60Port([string]$name) {
    $p = [System.IO.Ports.SerialPort]::new($name, $BaudRate, 'None', 8, 'One')
    $p.Handshake = 'None'; $p.DtrEnable = $true; $p.RtsEnable = $false; $p.ReadTimeout = 200
    try { $p.Open(); return $p } catch { $p.Dispose(); throw }
}
$sp = $null; $sw = $null; $portSeen = $false; $portOpened = $false; $bytes = [long]0
$openErrors = 0; $lastError = $null; $panicMarker = $null; $resetMarker = $null
$tail = ''; $stopReason = 'waiting'; $start = Get-Date; $captureStart = $null
$lastData = $null; $lostAt = $null; $reopenCount = 0
$panicMarkers = @('panic(', 'K60PANIC', 'K60CACHE FAIL', 'initproc exited')
$resetMarkers = @('PSCI SYSTEM_RESET to fastboot', 'K60 USBLOG: restart reason published')
try {
    $sw = [System.IO.StreamWriter]::new($log, $false, $utf8)
    Write-CaptureEvent 'ready' 'single collector owns mutex; waiting for USB serial enumeration'
    if ($ReadyFile) { [System.IO.File]::WriteAllText($ReadyFile, "$PID", $utf8) }
    Write-Host 'Capture ready; waiting for K60 USB serial port.'
    $portDeadline = (Get-Date).AddSeconds($WaitPortSeconds)
    while ($true) {
        $now = Get-Date
        if ($StopFile -and (Test-Path -LiteralPath $StopFile) -and ((($now - $start).TotalSeconds) -gt 2)) {
            if (-not $lastData -or ($now - $lastData).TotalSeconds -ge 2) { $stopReason = 'fastboot-return'; break }
        }
        if ($captureStart -and ($now - $captureStart).TotalSeconds -ge $Seconds) { $stopReason = 'budget'; break }
        if (-not $sp) {
            if (-not $captureStart -and $now -ge $portDeadline) { $stopReason = 'port-timeout'; break }
            if ($lostAt -and ($now - $lostAt).TotalSeconds -ge $ReopenSeconds) { $stopReason = 'port-lost'; break }
            $port = Resolve-K60Port
            if ($port) {
                if (-not $portSeen) { Write-CaptureEvent 'port-observed' $port; Write-Host "Port: $port" }
                $portSeen = $true
                try {
                    $sp = Open-K60Port $port
                    $portOpened = $true
                    if (-not $captureStart) { $captureStart = Get-Date } else { $reopenCount++ }
                    $lostAt = $null
                    Write-CaptureEvent 'port-opened' "$port DTR=1"
                    Write-Host "Capturing on $port (DTR on)."
                } catch {
                    $openErrors++; $lastError = $_.Exception.Message
                    if ($openErrors -eq 1 -or ($openErrors % 20) -eq 0) { Write-CaptureEvent 'open-error' $lastError }
                }
            }
            if (-not $sp) { Start-Sleep -Milliseconds 200; continue }
        }
        try {
            $chunk = $sp.ReadExisting()
            if ($chunk.Length -gt 0) {
                $bytes += $utf8.GetByteCount($chunk)
                $sw.Write($chunk); $sw.Flush(); $lastData = Get-Date
                $tail += $chunk
                if ($tail.Length -gt 16000) { $tail = $tail.Substring($tail.Length - 16000) }
                if (-not $panicMarker) { foreach ($marker in $panicMarkers) { if ($tail.Contains($marker)) { $panicMarker = $marker; Write-CaptureEvent 'panic-marker' $marker; break } } }
                if (-not $resetMarker) { foreach ($marker in $resetMarkers) { if ($tail.Contains($marker)) { $resetMarker = $marker; Write-CaptureEvent 'reset-marker' $marker; break } } }
            }
        } catch [System.TimeoutException] {
        } catch {
            $lastError = $_.Exception.Message; Write-CaptureEvent 'read-error' $lastError
            try { $sp.Close(); $sp.Dispose() } catch { }
            $sp = $null; $lostAt = Get-Date
        }
        if ($lastData) {
            $quiet = ((Get-Date) - $lastData).TotalSeconds
            if ($resetMarker -and $quiet -ge 2) { $stopReason = 'reset-marker'; break }
            if ($panicMarker -and $quiet -ge $PanicGraceSeconds) { $stopReason = 'panic-quiet'; break }
            if (-not $panicMarker -and $IdleSeconds -gt 0 -and $quiet -ge $IdleSeconds) { $stopReason = 'idle'; break }
        }
        Start-Sleep -Milliseconds 40
    }
} catch {
    $lastError = $_.Exception.Message; $stopReason = 'collector-error'
    Write-CaptureEvent 'collector-error' $lastError
} finally {
    if ($sp) { try { $sp.Close(); $sp.Dispose() } catch { } }
    if ($sw) { $sw.Close() }
    if (Test-Path -LiteralPath $log) { $bytes = (Get-Item -LiteralPath $log).Length }
    $dataRecent = $false
    if ($lastData) { $dataRecent = ((Get-Date) - $lastData).TotalSeconds -lt 3 }
    $verdict = Get-K60CaptureVerdict -PortSeen $portSeen -PortOpened $portOpened -Bytes $bytes -StopReason $stopReason -DataRecent $dataRecent -PanicSeen ([bool]$panicMarker)
    $meta = [ordered]@{
        state=$verdict.state; complete=$verdict.complete; bytes=$bytes; log=$log
        logSha256=if (Test-Path -LiteralPath $log) { (Get-FileHash -LiteralPath $log -Algorithm SHA256).Hash } else { $null }
        portSeen=$portSeen; portOpened=$portOpened; openErrors=$openErrors; lastError=$lastError
        stopReason=$stopReason; panicMarker=$panicMarker; resetMarker=$resetMarker
        reopenCount=$reopenCount; lastDataAt=if ($lastData) { $lastData.ToString('o') } else { $null }
        startedAt=$start.ToString('o'); finishedAt=(Get-Date).ToString('o'); pid=$PID
    }
    $meta | ConvertTo-Json | Set-Content -LiteralPath $metaPath -Encoding UTF8
    Write-CaptureEvent 'finished' $verdict.state
    if ($ownsLock) { $mutex.ReleaseMutex() }; $mutex.Dispose()
}
Write-Host ("Capture: {0}; {1} bytes; stop={2}; metadata={3}" -f $verdict.state, $bytes, $stopReason, $metaPath)
if ($bytes -eq 0) { exit 2 }
if (-not $verdict.complete) { exit 4 }
exit 0
