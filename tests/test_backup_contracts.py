from pathlib import Path


def test_s3_backup_script_uses_verified_dump_and_yandex_endpoint():
    source = (Path(__file__).parents[1] / "scripts" / "backup-db-to-s3.sh").read_text(encoding="utf-8")
    assert "./scripts/backup-db.sh" in source
    assert "storage.yandexcloud.net" in source
    assert "aws s3 cp" in source
    assert "aws s3api head-object" in source
    assert "CLOUD_RETENTION_DAYS" in source
    assert "aws s3 rm" in source
    assert "S3_BUCKET" in source


def test_windows_backup_uses_custom_dump_and_restore_verification():
    source = (Path(__file__).parents[1] / "scripts" / "backup-db.ps1").read_text(encoding="utf-8")
    assert "format=custom" in source
    assert "pg_restore --list" in source


def test_restore_drill_refuses_production_database_and_validates_identifier():
    source = (Path(__file__).parents[1] / "scripts" / "restore-drill.sh").read_text(encoding="utf-8")
    assert "Refusing to run restore drill" in source
    assert "DRILL_DB" in source and "POSTGRES_DB" in source
    assert "alter-$stamp.dump" in source
