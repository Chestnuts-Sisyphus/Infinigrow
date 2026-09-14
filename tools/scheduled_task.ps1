# ============================================================================
# Infinigrow scheduled task registrar (install / uninstall / status)
#
# Task name defaults to `Infinigrow_tick` (override with IG_TASK_NAME); it runs
# `tools\run_tick.bat` every N minutes (default 10, override with IG_TICK_MINUTES).
# That launcher itself goes through the *version gate* and then runs the tick,
# then calls the gardener.
#
# Why a one-shot trigger with a repetition interval instead of -Daily:
#   -Once + -RepetitionInterval is the general "every N minutes from now" form,
#   and registering it under the current user (no -User argument) needs no
#   admin rights. The engine never needs elevation: it only writes its own
#   state directory.
#
# NOTE: ASCII-only on purpose. Windows PowerShell 5.1 reads .ps1 files without a
# BOM as ANSI (system code page), so UTF-8 Chinese text here would be mangled.
# Human-readable Chinese lives in docs/running.md.
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\scheduled_task.ps1 -Action install
#   (or just run tools\manage_scheduled_task.bat install)
# ============================================================================
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('install', 'uninstall', 'status')]
    [string]$Action
)

$ErrorActionPreference = 'Stop'

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$bat = Join-Path $PSScriptRoot 'run_tick.bat'
# Run through a hidden launcher: a bare .bat action flashes a console window on every
# run, which steals focus from whoever is using the machine. WSH window style 0 hides it.
$vbs = Join-Path $PSScriptRoot 'run_tick_hidden.vbs'
$wscript = Join-Path $env:SystemRoot 'System32\wscript.exe'

$taskName = $env:IG_TASK_NAME
if ([string]::IsNullOrWhiteSpace($taskName)) { $taskName = 'Infinigrow_tick' }

$minutes = 10
if (-not [string]::IsNullOrWhiteSpace($env:IG_TICK_MINUTES)) {
    $parsed = 0
    if ([int]::TryParse($env:IG_TICK_MINUTES, [ref]$parsed) -and $parsed -gt 0) {
        $minutes = $parsed
    } else {
        Write-Host "WARN: IG_TICK_MINUTES=$($env:IG_TICK_MINUTES) is not a positive integer; using 10."
    }
}

switch ($Action) {
    'install' {
        if (-not (Test-Path $bat)) {
            Write-Host "FAIL: launcher not found: $bat"
            exit 1
        }
        if (-not (Test-Path $vbs)) {
            Write-Host "FAIL: hidden launcher not found: $vbs"
            exit 1
        }
        # NOTE: do NOT name this $action - PowerShell variables are case-insensitive,
        # so it would overwrite the $Action parameter and trip its ValidateSet.
        $taskAction = New-ScheduledTaskAction -Execute $wscript `
            -Argument ('//nologo "' + $vbs + '"') -WorkingDirectory $repo
        $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
            -RepetitionInterval (New-TimeSpan -Minutes $minutes) `
            -RepetitionDuration (New-TimeSpan -Days 3650)
        $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
            -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -StartWhenAvailable `
            -DontStopOnIdleEnd
        Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $trigger `
            -Settings $settings -Force `
            -Description "Infinigrow: one tick every $minutes minutes (version gate -> tick -> gardener; hidden window)" | Out-Null
        Write-Host "OK: registered scheduled task '$taskName' (every $minutes minutes; workdir $repo)"
        Write-Host "Note: it runs as the *currently logged-on user* (active while logged on)."
        Write-Host "Check it with: tools\manage_scheduled_task.bat status"
        exit 0
    }
    'uninstall' {
        $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($null -eq $existing) {
            Write-Host "Nothing to do: task '$taskName' does not exist."
            exit 0
        }
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "OK: unregistered task '$taskName' (engine state and ledgers are untouched)."
        exit 0
    }
    'status' {
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($null -eq $task) {
            Write-Host "Status: task '$taskName' does NOT exist (not installed)."
            exit 0
        }
        $info = Get-ScheduledTaskInfo -TaskName $taskName
        Write-Host "Task: $taskName"
        Write-Host "  State: $($task.State) (Enabled=$($task.Settings.Enabled))"
        Write-Host "  Last run: $($info.LastRunTime) | Last result: $($info.LastTaskResult)"
        Write-Host "  Next run: $($info.NextRunTime)"
        exit 0
    }
}
