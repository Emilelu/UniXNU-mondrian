# Pure capture classification shared by the collector and offline regression test.
function Get-K60CaptureVerdict {
    param(
        [bool]$PortSeen, [bool]$PortOpened, [long]$Bytes,
        [string]$StopReason, [bool]$DataRecent, [bool]$PanicSeen
    )
    if ($Bytes -gt 0) {
        if ($StopReason -eq 'budget' -and $DataRecent) {
            return [pscustomobject]@{ state = 'captured-truncated'; complete = $false }
        }
        if ($StopReason -eq 'collector-error') {
            return [pscustomobject]@{ state = 'captured-error'; complete = $false }
        }
        if ($StopReason -in @('port-lost', 'fastboot-return') -and -not $PanicSeen) {
            return [pscustomobject]@{ state = 'captured-disconnected'; complete = $false }
        }
        return [pscustomobject]@{ state = 'captured'; complete = $true }
    }
    if ($PortOpened) { return [pscustomobject]@{ state = 'opened-no-data'; complete = $false } }
    if ($PortSeen) { return [pscustomobject]@{ state = 'port-open-failed'; complete = $false } }
    return [pscustomobject]@{ state = 'port-not-observed'; complete = $false }
}
