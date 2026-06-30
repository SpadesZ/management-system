param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$BackupDir = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path "infra\backups"),
    [string]$DbUser = "llm_finops",
    [string]$DbName = "llm_finops",
    [int]$RetentionDays = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -Path $BackupDir)) {
    New-Item -Path $BackupDir -ItemType Directory -Force | Out-Null
}

$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmss")
$backupFile = Join-Path $BackupDir ("{0}_{1}.dump" -f $DbName, $timestamp)
$shaFile = "$backupFile.sha256"
$metaFile = "$backupFile.meta.json"

$sw = [System.Diagnostics.Stopwatch]::StartNew()

Push-Location $ProjectRoot
try {
    $dumpCmd = "docker compose exec -T postgres pg_dump -U {0} -d {1} -Fc" -f $DbUser, $DbName
    $null = & pwsh -NoProfile -Command "$dumpCmd > `"$backupFile`""
    if ($LASTEXITCODE -ne 0) {
        throw "pg_dump failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

$sw.Stop()

if (-not (Test-Path -Path $backupFile)) {
    throw "Backup file was not created: $backupFile"
}

$hash = Get-FileHash -Path $backupFile -Algorithm SHA256
"{0}  {1}" -f $hash.Hash.ToLowerInvariant(), (Split-Path $backupFile -Leaf) | Set-Content -Path $shaFile -Encoding ascii

$meta = [ordered]@{
    created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    db_name = $DbName
    backup_file = (Split-Path $backupFile -Leaf)
    sha256 = $hash.Hash.ToLowerInvariant()
    size_bytes = (Get-Item $backupFile).Length
    duration_seconds = [Math]::Round($sw.Elapsed.TotalSeconds, 3)
}
$meta | ConvertTo-Json | Set-Content -Path $metaFile -Encoding utf8

$cutoff = (Get-Date).AddDays(-$RetentionDays)
Get-ChildItem -Path $BackupDir -File -Filter "*.dump" |
    Where-Object { $_.LastWriteTime -lt $cutoff } |
    ForEach-Object {
        Remove-Item -Path $_.FullName -Force -ErrorAction SilentlyContinue
        Remove-Item -Path ("{0}.sha256" -f $_.FullName) -Force -ErrorAction SilentlyContinue
        Remove-Item -Path ("{0}.meta.json" -f $_.FullName) -Force -ErrorAction SilentlyContinue
    }

Write-Output ("BACKUP_FILE={0}" -f $backupFile)
Write-Output ("SHA256={0}" -f $hash.Hash.ToLowerInvariant())
Write-Output ("DURATION_SECONDS={0}" -f [Math]::Round($sw.Elapsed.TotalSeconds, 3))
