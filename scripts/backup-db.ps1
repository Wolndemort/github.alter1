$ErrorActionPreference = "Stop"

$backupDir = Join-Path $PSScriptRoot "..\backups"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$target = Join-Path $backupDir "alter-$stamp.dump"
$dbUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "postgres" }
$dbName = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "alter_project_db" }

docker compose exec -T db pg_dump -U $dbUser -d $dbName --format=custom --no-owner | Set-Content -Path $target -Encoding Byte
if (-not (Test-Path $target) -or (Get-Item $target).Length -eq 0) { Remove-Item $target -Force; throw "Backup is empty" }
Get-Content -Path $target -Encoding Byte | docker compose exec -T db pg_restore --list | Out-Null
Write-Host "Backup created and verified: $target"
