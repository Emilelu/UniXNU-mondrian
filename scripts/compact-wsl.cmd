@echo off
rem One-shot WSL virtual-disk compaction. Double-click, or run with a distro name:
rem   compact-wsl.cmd [Distro] [VhdxPath]
rem The diskpart half raises a UAC prompt; everything else stays in this window.
setlocal
set "DISTRO=%~1"
set "VHDX=%~2"
set "PS=powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0compact-wsl.ps1""
if "%DISTRO%"=="" (set "DISTRO=Ubuntu-24.04")
if "%VHDX%"=="" (
  %PS% -Distro "%DISTRO%"
) else (
  %PS% -Distro "%DISTRO%" -Vhdx "%VHDX%"
)
echo.
pause
