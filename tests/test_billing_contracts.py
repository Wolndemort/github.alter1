from pathlib import Path


def test_billing_migrations_are_linear_and_include_recurring_fields():
    root = Path(__file__).parents[1]
    first = (root / "alembic" / "versions" / "0010_billing.py").read_text(encoding="utf-8")
    second = (root / "alembic" / "versions" / "0011_recurring_billing.py").read_text(encoding="utf-8")
    third = (root / "alembic" / "versions" / "0012_subscription_reminders.py").read_text(encoding="utf-8")
    assert 'revision = "0010_billing"' in first
    assert 'down_revision = "0009_vector_memory"' in first
    assert 'revision = "0011_recurring_billing"' in second
    assert 'down_revision = "0010_billing"' in second
    assert 'payment_method_id' in second
    assert 'auto_renew' in second
    assert 'next_charge_at' in second
    assert 'revision = "0012_subscription_reminders"' in third
    assert 'down_revision = "0011_recurring_billing"' in third
    assert 'subscription_reminders' in third


def test_recurring_monitor_is_started_by_main():
    main = (Path(__file__).parents[1] / "main.py").read_text(encoding="utf-8")
    tasks = (Path(__file__).parents[1] / "utils" / "tasks.py").read_text(encoding="utf-8")
    assert "monitor_subscription_renewals" in main
    assert "SUBSCRIPTION_RENEWAL_CHECK_SECONDS" in tasks
    assert "monitor_subscription_expiry_reminders" in main


def test_subscription_reminder_copy_mentions_auto_renew_and_alter():
    from utils.tasks import subscription_expiry_reminder

    text = subscription_expiry_reminder(5, "Адам", False)
    assert "Адам" in text
    assert "через 5 дней" in text
    assert "автопродление" in text.lower()
    assert "ALTER не забудет" in text

    enabled = subscription_expiry_reminder(1, "Адам", True)
    assert "завтра" in enabled
    assert "уже включено" in enabled
