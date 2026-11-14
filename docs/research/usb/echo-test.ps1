<#
.SYNOPSIS
Host-side check for the 0410 vendor loopback, k60_usbvend=2 (CDC data pair).

.DESCRIPTION
In mode 2 the device echoes every byte it receives on EP2 straight back on
EP3, so a plain COM port proves the loopback without libusb. This script
opens the port the device enumerated as, writes a random pattern, and reads
until the same number of bytes comes back or the timeout expires.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File docs/research/usb/echo-test.ps1 -Port COM5 -Bytes 64

.NOTES
Criteria (docs/research/usb/RESEARCH.md section 23.3): every byte written must
come back unchanged, and the device log must show
"K60 USBLOG: echo <n> bytes on ep<k> (total <m>)".
#>
param(
    [Parameter(Mandatory = $true)][string]$Port,
    [int]$Bytes = 64,
    [int]$Baud = 115200,
    [int]$TimeoutMs = 3000
)

$payload = New-Object byte[] $Bytes
$rng = [System.Random]::new(20261114)
$rng.NextBytes($payload)

$sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, 'None', 8, 'One'
$sp.ReadTimeout = $TimeoutMs
$sp.WriteTimeout = $TimeoutMs
$sp.DtrEnable = $true
$sp.RtsEnable = $true
try {
    $sp.Open()
} catch {
    Write-Error "cannot open $Port : $($_.Exception.Message)"
    exit 2
}

$received = New-Object System.Collections.Generic.List[byte]
try {
    $sp.DiscardInBuffer()
    $sp.Write($payload, 0, $payload.Length)
    $deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMs)
    while ($received.Count -lt $Bytes -and [DateTime]::UtcNow -lt $deadline) {
        try {
            $b = $sp.ReadByte()
            if ($b -ge 0) { $received.Add([byte]$b) }
        } catch [System.TimeoutException] {
            break
        }
    }
} finally {
    $sp.Close()
    $sp.Dispose()
}

$got = $received.ToArray()
$same = $got.Length -eq $payload.Length
if ($same) {
    for ($i = 0; $i -lt $payload.Length; $i++) {
        if ($got[$i] -ne $payload[$i]) { $same = $false; break }
    }
}
Write-Output ("port={0} sent={1} received={2}" -f $Port, $payload.Length, $got.Length)
if ($same) {
    Write-Output "RESULT: PASS (echo matched byte for byte)"
    exit 0
}
Write-Output "RESULT: FAIL (echo mismatch or short read)"
exit 1
