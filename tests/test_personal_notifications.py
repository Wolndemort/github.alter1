from utils.personal_notifications import quota_reminder_text, subscription_reminder_text
from data.models import User


def test_subscription_reminder_is_personal_and_mentions_site_when_manual():
    user = User(id=42, first_name="Адам", memory={}, tech_stack={})
    text = subscription_reminder_text(user, 3)
    assert "Адам" in text
    assert "через 3 дней" in text
    assert "личном кабинете ALTER" in text


def test_quota_reminder_has_a_distinct_depleted_message():
    user = User(id=42, first_name="Адам", memory={}, tech_stack={})
    text = quota_reminder_text(user, 0, 3500, "depleted")
    assert "Адам" in text
    assert "0 AI-кредитов из 3500" in text
    assert "докупить пакет" in text
