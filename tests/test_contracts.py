from utils.ap_logic import GOLDEN_PROMT


EXPECTED_MEMORY_CATEGORIES = {
    "identity", "health_sport", "food_drinks", "skills_career",
    "interests_hobbies", "goals_habits", "psycho_vibe", "relationships",
    "worldview", "politics", "preferences", "important_events",
}


def test_memory_contract_documents_all_categories():
    for category in EXPECTED_MEMORY_CATEGORIES:
        assert f"{category}:" in GOLDEN_PROMT


def test_memory_contract_has_privacy_rule():
    assert "только если пользователь явно сообщил их сам" in GOLDEN_PROMT
    assert "Не делай выводов и не профилируй" in GOLDEN_PROMT
