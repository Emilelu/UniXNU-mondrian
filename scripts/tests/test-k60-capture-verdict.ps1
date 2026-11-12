#!/usr/bin/env pwsh
# Offline regression for the boot evidence classifier. No device, no COM port.
$ErrorActionPreference='Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'k60-capture-state.ps1')
$cases=@(
    @{name='empty-first-reader-is-not-kernel-proof'; want='port-not-observed';  complete=$false; a=@{PortSeen=$false;PortOpened=$false;Bytes=0;    StopReason='port-timeout';   DataRecent=$false;PanicSeen=$false}},
    @{name='port-observed-but-never-opened';         want='port-open-failed';   complete=$false; a=@{PortSeen=$true; PortOpened=$false;Bytes=0;    StopReason='port-timeout';   DataRecent=$false;PanicSeen=$false}},
    @{name='opened-without-bytes';                   want='opened-no-data';     complete=$false; a=@{PortSeen=$true; PortOpened=$true; Bytes=0;    StopReason='budget';         DataRecent=$false;PanicSeen=$false}},
    @{name='complete-normal-capture';                want='captured';           complete=$true;  a=@{PortSeen=$true; PortOpened=$true; Bytes=91673;StopReason='idle';           DataRecent=$false;PanicSeen=$false}},
    @{name='budget-truncation-is-labelled';          want='captured-truncated'; complete=$false; a=@{PortSeen=$true; PortOpened=$true; Bytes=91673;StopReason='budget';         DataRecent=$true; PanicSeen=$false}},
    @{name='fastboot-return-after-panic';            want='captured';           complete=$true;  a=@{PortSeen=$true; PortOpened=$true; Bytes=5000; StopReason='fastboot-return';DataRecent=$false;PanicSeen=$true}},
    @{name='fastboot-return-without-panic';          want='captured-disconnected';complete=$false;a=@{PortSeen=$true;PortOpened=$true;Bytes=90000;StopReason='fastboot-return';DataRecent=$false;PanicSeen=$false}},
    @{name='collector-error-with-text';              want='captured-error';     complete=$false; a=@{PortSeen=$true; PortOpened=$true; Bytes=1200; StopReason='collector-error';DataRecent=$false;PanicSeen=$false}}
)
$failed=0
foreach ($case in $cases) {
    $splat=@{}
    foreach ($key in $case.a.Keys) { $splat[$key]=$case.a[$key] }
    $v=Get-K60CaptureVerdict @splat
    if ($v.state -ne $case.want -or $v.complete -ne $case.complete) {
        Write-Host ("FAIL {0}: got {1}/{2}, want {3}/{4}" -f $case.name,$v.state,$v.complete,$case.want,$case.complete) -ForegroundColor Red
        $failed++
    } else { Write-Host ("ok   {0} -> {1}/{2}" -f $case.name,$v.state,$v.complete) }
}
if ($failed) { Write-Host "$failed case(s) failed" -ForegroundColor Red; exit 1 }
Write-Host 'All capture classifier cases passed.'
