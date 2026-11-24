' Build the iOS 27 image with no console window at all.
'
' wscript.exe //nologo scripts\build-ios27-hidden.vbs <tag>
'
' wscript.exe is a GUI-subsystem host, so no console is ever allocated. The
' cmd.exe child is started with window style 0 (hidden), and the WSL command
' writes its own log under E:\k60-work\scratch\build-<tag>.log.
Option Explicit
Dim sh, tag, inner, rc
Set sh = CreateObject("WScript.Shell")
tag = "local"
If WScript.Arguments.Count > 0 Then tag = WScript.Arguments(0)
inner = "wsl.exe -e bash -lc ""bash /mnt/e/k60-work/scratch/run-build.sh " & tag & """"
rc = sh.Run("cmd.exe /c " & inner, 0, True)
WScript.Quit rc
