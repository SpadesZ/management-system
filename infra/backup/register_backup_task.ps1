param(
    [string]$TaskName = "TokenButler-Postgres-Backup-15m",
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$RunAsUser = "$env:USERDOMAIN\\$env:USERNAME"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptPath = (Resolve-Path (Join-Path $PSScriptRoot "backup_postgres.ps1")).Path
$escapedScript = $scriptPath.Replace("'", "''")

$taskCommand = "pwsh.exe -NoProfile -ExecutionPolicy Bypass -File `"$escapedScript`""

$null = & schtasks /Create /F /SC MINUTE /MO 15 /TN $TaskName /TR $taskCommand /RL LIMITED /RU $RunAsUser
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create scheduled task: $TaskName"
}

$taskInfo = & schtasks /Query /TN $TaskName /FO LIST /V
if ($LASTEXITCODE -ne 0) {
    throw "Scheduled task created but query failed: $TaskName"
}

Write-Output ("TASK_NAME={0}" -f $TaskName)
Write-Output "TASK_QUERY_BEGIN"
$taskInfo
Write-Output "TASK_QUERY_END"
