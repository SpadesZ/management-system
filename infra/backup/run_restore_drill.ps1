param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$DbUser = "llm_finops",
    [string]$DbName = "llm_finops",
    [string]$DrillDb = "llm_finops_restore_drill",
    [string]$BackupDir = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path "infra\backups")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$startAt = Get-Date

$backupOutput = & (Join-Path $PSScriptRoot "backup_postgres.ps1") -ProjectRoot $ProjectRoot -BackupDir $BackupDir -DbUser $DbUser -DbName $DbName
if ($LASTEXITCODE -ne 0) {
    throw "backup_postgres.ps1 failed"
}

$backupPathLine = $backupOutput | Where-Object { $_ -like "BACKUP_FILE=*" } | Select-Object -First 1
if (-not $backupPathLine) {
    throw "Unable to parse backup output"
}
$backupFile = $backupPathLine.Substring("BACKUP_FILE=".Length)

$restoreStart = Get-Date
$restoreOutput = & (Join-Path $PSScriptRoot "restore_postgres.ps1") -BackupFile $backupFile -ProjectRoot $ProjectRoot -DbUser $DbUser -TargetDb $DrillDb -DropIfExists
if ($LASTEXITCODE -ne 0) {
    throw "restore_postgres.ps1 failed"
}
$restoreEnd = Get-Date

$restoreMinutes = [Math]::Round((New-TimeSpan -Start $restoreStart -End $restoreEnd).TotalMinutes, 3)
$rpoMinutes = [Math]::Round((New-TimeSpan -Start (Get-Item $backupFile).LastWriteTimeUtc -End (Get-Date).ToUniversalTime()).TotalMinutes, 3)

$status = "PASS"
if ($restoreMinutes -gt 240 -or $rpoMinutes -gt 15) {
    $status = "FAIL"
}

$summary = [ordered]@{
    drill_started_at_utc = $startAt.ToUniversalTime().ToString("o")
    drill_finished_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    backup_file = (Split-Path $backupFile -Leaf)
    restore_db = $DrillDb
    restore_minutes = $restoreMinutes
    rpo_minutes = $rpoMinutes
    target_rto_minutes = 240
    target_rpo_minutes = 15
    status = $status
    restore_output = $restoreOutput
}

$summaryJson = $summary | ConvertTo-Json -Depth 6
Write-Output $summaryJson
