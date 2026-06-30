param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile,
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$DbUser = "llm_finops",
    [string]$TargetDb = "llm_finops_restore_drill",
    [switch]$DropIfExists
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$resolvedBackup = (Resolve-Path $BackupFile).Path
if (-not (Test-Path -Path $resolvedBackup)) {
    throw "Backup file not found: $BackupFile"
}

$shaFile = "$resolvedBackup.sha256"
if (Test-Path -Path $shaFile) {
    $raw = (Get-Content -Path $shaFile -Raw).Trim()
    $expected = ($raw -split "\s+")[0].ToLowerInvariant()
    $actual = (Get-FileHash -Path $resolvedBackup -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($expected -ne $actual) {
        throw "Checksum mismatch. expected=$expected actual=$actual"
    }
}

$containerFile = "/tmp/restore_{0}.dump" -f [guid]::NewGuid().ToString("N")

Push-Location $ProjectRoot
try {
    & docker cp $resolvedBackup ("llm-finops-postgres:{0}" -f $containerFile)
    if ($LASTEXITCODE -ne 0) {
        throw "docker cp failed with exit code $LASTEXITCODE"
    }

    $dbExistsRaw = & docker compose exec -T postgres psql -U $DbUser -d postgres -tAc ("SELECT 1 FROM pg_database WHERE datname = '{0}'" -f $TargetDb)
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to query target database existence"
    }
    $dbExists = ((($dbExistsRaw | Out-String).Trim()) -eq "1")

    if ($dbExists -and $DropIfExists.IsPresent) {
        & docker compose exec -T postgres dropdb -U $DbUser $TargetDb
        if ($LASTEXITCODE -ne 0) {
            throw "dropdb failed with exit code $LASTEXITCODE"
        }
        $dbExists = $false
    }

    if (-not $dbExists) {
        & docker compose exec -T postgres createdb -U $DbUser $TargetDb
        if ($LASTEXITCODE -ne 0) {
            throw "createdb failed with exit code $LASTEXITCODE"
        }
    }

    & docker compose exec -T postgres pg_restore -U $DbUser -d $TargetDb --clean --if-exists --no-owner --no-privileges $containerFile
    if ($LASTEXITCODE -ne 0) {
        throw "pg_restore failed with exit code $LASTEXITCODE"
    }

    $usageCount = & docker compose exec -T postgres psql -U $DbUser -d $TargetDb -tAc "SELECT COUNT(*) FROM usage_events"
    $successUsageCount = & docker compose exec -T postgres psql -U $DbUser -d $TargetDb -tAc "SELECT COUNT(*) FROM usage_events WHERE status = 'SUCCESS'"
    $ledgerCount = & docker compose exec -T postgres psql -U $DbUser -d $TargetDb -tAc "SELECT COUNT(*) FROM cost_ledger"
    $missingPair = & docker compose exec -T postgres psql -U $DbUser -d $TargetDb -tAc "SELECT COUNT(*) FROM usage_events ue LEFT JOIN cost_ledger cl ON cl.request_id = ue.request_id WHERE ue.status = 'SUCCESS' AND cl.request_id IS NULL"

    if ($LASTEXITCODE -ne 0) {
        throw "Post-restore validation query failed"
    }

    Write-Output ("RESTORE_DB={0}" -f $TargetDb)
    Write-Output ("USAGE_EVENTS={0}" -f (($usageCount | Out-String).Trim()))
    Write-Output ("SUCCESS_USAGE_EVENTS={0}" -f (($successUsageCount | Out-String).Trim()))
    Write-Output ("COST_LEDGER={0}" -f (($ledgerCount | Out-String).Trim()))
    Write-Output ("MISSING_LEDGER_PAIRS_FOR_SUCCESS={0}" -f (($missingPair | Out-String).Trim()))
} finally {
    & docker compose exec -T postgres rm -f $containerFile | Out-Null
    Pop-Location
}
