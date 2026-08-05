from pathlib import Path


def test_billing_migrations_are_linear_and_include_recurring_fields():
    root = Path(__file__).parents[1]
    first = (root / "alembic" / "versions" / "0010_billing.py").read_text(encoding="utf-8")
    second = (root / "alembic" / "versions" / "0011_recurring_billing.py").read_text(encoding="utf-8")
    assert 'revision = "0010_billing"' in first
    assert 'down_revision = "0009_vector_memory"' in first
    assert 'revision = "0011_recurring_billing"' in second
    assert 'down_revision = "0010_billing"' in second
    assert 'payment_method_id' in second
    assert 'auto_renew' in second
    assert 'next_charge_at' in second


def test_recurring_monitor_is_started_by_main():
    main = (Path(__file__).parents[1] / "main.py").read_text(encoding="utf-8")
    tasks = (Path(__file__).parents[1] / "utils" / "tasks.py").read_text(encoding="utf-8")
    assert "monitor_subscription_renewals" in main
    assert "SUBSCRIPTION_RENEWAL_CHECK_SECONDS" in tasks
