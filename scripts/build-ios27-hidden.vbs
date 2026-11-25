' Build the iOS 27 image with no console window.
'
' wscript.exe //nologo scripts\build-ios27-hidden.vbs [tag]
'
' wscript.exe is a GUI-subsystem host, so it never allocates a console. When no
' tag is given the tag is read from E:\iOS Port\Work\scratch\BUILD-TAG.txt, which lets
' Task Scheduler run this file with no arguments at all.
Option Explicit
Dim sh, fso, tag, tagFile, inner, rc
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
tag = "local"
If WScript.Arguments.Count > 0 Then
  tag = WScript.Arguments(0)
Else
  tagFile = "E:\iOS Port\Work\scratch\BUILD-TAG.txt"
  If fso.FileExists(tagFile) Then
    Dim ts
    Set ts = fso.OpenTextFile(tagFile, 1)
    If Not ts.AtEndOfStream Then tag = Trim(ts.ReadLine())
    ts.Close
  End If
End If
inner = "wsl.exe -e bash -lc ""bash /mnt/e/iOS Port/Work/scratch/run-build.sh " & tag & """"
rc = sh.Run("cmd.exe /c " & inner, 0, True)
WScript.Quit rc
