$ErrorActionPreference = "Stop"

$backupDir = Join-Path $PSScriptRoot "..\backups"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$target = Join-Path $backupDir "alter-$stamp.sql"

docker compose exec -T db pg_dump -U postgres -d alter_project_db | Out-File -FilePath $target -Encoding utf8
Write-Host "Backup created: $target"
