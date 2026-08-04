from data.models import ImportantEvent
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("migration_0002", Path(__file__).parents[1] / "alembic" / "versions" / "0002_important_events.py")
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def test_important_event_has_planner_contract():
    columns = ImportantEvent.__table__.columns

    assert columns["event_type"].nullable is False
    assert columns["title"].nullable is False
    assert columns["occurred_at"].nullable is False
    assert columns["importance"].nullable is False
    assert columns["details"].nullable is False
    assert columns["details"].server_default is not None


def test_important_event_supports_common_event_types():
    event_types = {"date", "career", "relationship", "sport", "injury", "purchase"}
    assert all(isinstance(event_type, str) and event_type for event_type in event_types)


def test_important_events_migration_is_after_baseline():
    assert migration.revision == "0002_important_events"
    assert migration.down_revision == "0001_baseline"
