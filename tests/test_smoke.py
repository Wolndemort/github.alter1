from sqlalchemy import ForeignKeyConstraint, inspect

from data.models import ImportantEvent, Session, User


def test_models_import_and_have_expected_tables():
    assert User.__tablename__ == "users"
    assert Session.__tablename__ == "session"
    assert {"memory", "tech_stack"} <= set(User.__table__.columns.keys())
    assert {"raw_messages", "is_processed"} <= set(Session.__table__.columns.keys())
    assert ImportantEvent.__tablename__ == "important_events"
    assert {"event_type", "title", "occurred_at", "details"} <= set(ImportantEvent.__table__.columns.keys())
    assert any(
        isinstance(constraint, ForeignKeyConstraint)
        and {str(column) for column in constraint.columns} == {"important_events.user_id"}
        and {str(element.column) for element in constraint.elements} == {"users.id"}
        for constraint in ImportantEvent.__table__.foreign_key_constraints
    )
