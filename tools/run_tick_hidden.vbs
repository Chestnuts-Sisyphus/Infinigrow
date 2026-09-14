' ============================================================================
' Infinigrow one-click launcher - HIDDEN start (register THIS in the scheduler)
'
' Why: making the scheduler run a .bat / cmd / bare python flashes a console
' window on every run - it steals focus and covers whatever the user is doing.
' Window style 0 = fully hidden. NOTE: New-ScheduledTaskSettingsSet -Hidden only
' hides the entry in the task list, NOT the window; do not confuse the two.
'
' Usage: scheduled task action =
'        wscript.exe //nologo "<repo>\tools\run_tick_hidden.vbs"
' It does one thing: launch run_tick.bat with a hidden window, without waiting
' (the task's IgnoreNew setting prevents overlapping runs).
'
' ASCII-only on purpose: cmd/wscript read scripts in the system code page, so
' non-ASCII characters here get mangled (same lesson as the .bat files).
' ============================================================================
Option Explicit
Dim fso, sh, here, bat
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
here = fso.GetParentFolderName(WScript.ScriptFullName)
bat = fso.BuildPath(here, "run_tick.bat")
If Not fso.FileExists(bat) Then
    WScript.Quit 2
End If
' 0 = hidden window, False = do not wait
sh.Run """" & bat & """", 0, False
WScript.Quit 0
