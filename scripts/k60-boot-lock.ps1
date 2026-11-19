#!/usr/bin/env pwsh
<# Machine-wide single-writer claim for the one physical K60 device.
   The exclusive FileShare.None handle is the lock; owner JSON is diagnostic only. #>
function Enter-K60BootLock {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$false)][AllowEmptyString()][string]$Actor,
        [Parameter(Mandatory=$true)][string]$Serial,
        [Parameter(Mandatory=$true)][string]$Image
    )
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    if ([string]::IsNullOrWhiteSpace($Actor)) {
        throw 'K60_BOOT_ACTOR_REQUIRED: an anonymous claim cannot be attributed; pass the actor name'
    }
    $parent = [System.IO.Path]::GetDirectoryName($fullPath)
    if (-not [System.IO.Directory]::Exists($parent)) {
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    try {
        $stream = [System.IO.File]::Open($fullPath,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None)
    } catch [System.IO.IOException] {
        $ownerPath = $fullPath + '.owner.json'
        $owner = 'owner metadata unavailable'
        if ([System.IO.File]::Exists($ownerPath)) {
            try { $owner = [System.IO.File]::ReadAllText($ownerPath) } catch { }
        }
        throw "K60_BOOT_BUSY: device $Serial is already claimed; first claimant wins; $owner"
    }
    try {
        $ownerPath = $fullPath + '.owner.json'
        $record = [pscustomobject]@{
            actor = $Actor
            pid = $PID
            serial = $Serial
            image = $Image
            startedAt = (Get-Date).ToString('o')
            releasedAt = $null
        }
        $json = ConvertTo-Json -InputObject $record -Compress
        $utf8 = [System.Text.UTF8Encoding]::new($false)
        [System.IO.File]::WriteAllText($ownerPath, $json, $utf8)
        return [pscustomobject]@{ Stream = $stream; OwnerPath = $ownerPath; Record = $record }
    } catch {
        $stream.Dispose()
        throw
    }
}

function Exit-K60BootLock {
    param([Parameter(Mandatory=$true)]$Claim)
    if (-not $Claim) { return }
    try {
        $Claim.Record.releasedAt = (Get-Date).ToString('o')
        $json = ConvertTo-Json -InputObject $Claim.Record -Compress
        $utf8 = [System.Text.UTF8Encoding]::new($false)
        [System.IO.File]::WriteAllText($Claim.OwnerPath, $json, $utf8)
    } finally {
        $Claim.Stream.Dispose()
    }
}
