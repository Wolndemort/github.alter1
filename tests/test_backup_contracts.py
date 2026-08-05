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
