from pathlib import Path


def test_billing_migrations_are_linear_and_include_recurring_fields():
    root = Path(__file__).parents[1]
    first = (root / "alembic" / "versions" / "0010_billing.py").read_text(encoding="utf-8")
    second = (root / "alembic" / "versions" / "0011_recurring_billing.py").read_text(encoding="utf-8")
    third = (root / "alembic" / "versions" / "0012_subscription_reminders.py").read_text(encoding="utf-8")
    fourth = (root / "alembic" / "versions" / "0013_legal_consent.py").read_text(encoding="utf-8")
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
    assert 'revision = "0013_legal_consent"' in fourth
    assert 'down_revision = "0012_subscription_reminders"' in fourth
    assert 'legal_accepted_at' in fourth


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


def test_legal_documents_are_present_and_reference_alter():
    root = Path(__file__).parents[1] / "legal"
    for name in ("privacy.html", "consent.html", "offer.html", "refund.html"):
        text = (root / name).read_text(encoding="utf-8")
        assert "ALTER" in text
        assert "заполнить" not in text.lower()


def test_legal_start_flow_and_callback_middleware_are_wired():
    root = Path(__file__).parents[1]
    handlers = (root / "handlers" / "user_handlers.py").read_text(encoding="utf-8")
    main = (root / "main.py").read_text(encoding="utf-8")
    guard = (root / "middleware" / "guard_middleware.py").read_text(encoding="utf-8")
    assert 'callback_data="accept_legal"' in handlers
    assert "legal_consent_text" in handlers
    assert "legal_accepted_at" in handlers
    assert "dispatcher.callback_query.middleware" in main
    assert "_legal_exempt" in guard


def test_yookassa_webhook_is_publicly_wired_and_verified():
    root = Path(__file__).parents[1]
    webhook = (root / "utils" / "payment_webhook.py").read_text(encoding="utf-8")
    main = (root / "main.py").read_text(encoding="utf-8")
    nginx = (root / "nginx.alter.conf").read_text(encoding="utf-8")
    assert "payment.succeeded" in webhook
    assert "check_and_activate" in webhook
    assert "PAYMENT_WEBHOOK_PATH" in main
    assert "/webhooks/yookassa" in nginx
    assert "alter_bot:8080" in nginx


def test_payment_safety_controls_are_present():
    root = Path(__file__).parents[1]
    billing = (root / "utils" / "billing.py").read_text(encoding="utf-8")
    guard = (root / "middleware" / "guard_middleware.py").read_text(encoding="utf-8")
    assert "with_for_update" in billing
    assert "payment_method_data" in billing
    assert "save_payment_method" in billing
    assert "spam_allowed" in guard and "billing_allowed" in guard


def test_memory_lifecycle_migration_is_after_legal_consent():
    root = Path(__file__).parents[1]
    migration = (root / "alembic" / "versions" / "0014_memory_lifecycle.py").read_text(encoding="utf-8")
    assert 'revision = "0014_memory_lifecycle"' in migration
    assert 'down_revision = "0013_legal_consent"' in migration
    assert "content_hash" in migration
    assert "vector_cosine_ops" in migration


def test_telegram_link_migration_and_shared_api_contract_are_present():
    root = Path(__file__).parents[1]
    migration = (root / "alembic" / "versions" / "0017_telegram_account_link.py").read_text(encoding="utf-8")
    models = (root / "data" / "models.py").read_text(encoding="utf-8")
    routes = (root / "api" / "auth_routes.py").read_text(encoding="utf-8")
    assert 'revision = "0017_telegram_account_link"' in migration
    assert 'down_revision = "0016_email_verification"' in migration
    assert "telegram_user_id" in models
    for endpoint in ("/api/v1/account", "/api/v1/memory", "/api/v1/subscription", "/api/v1/telegram/link"):
        assert endpoint in routes


def test_background_workers_use_row_locks_and_ai_has_request_diagnostics():
    root = Path(__file__).parents[1]
    tasks = (root / "utils" / "tasks.py").read_text(encoding="utf-8")
    logic = (root / "utils" / "ap_logic.py").read_text(encoding="utf-8")
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    assert tasks.count("with_for_update(skip_locked=True)") >= 5
    assert "request_id" in logic
    assert "prompt_chars" in logic
    assert "- .:/app" not in compose
