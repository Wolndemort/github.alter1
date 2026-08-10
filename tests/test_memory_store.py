from datetime import datetime, timedelta, timezone

from utils.memory_store import merge_memory_facts, purge_expired_memory


NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)


def test_merge_records_provenance_and_replacement_history():
    first = merge_memory_facts({}, {"identity": {"city": "Москва"}}, now=NOW)
    second = merge_memory_facts(first, {"identity": {"city": "Казань"}}, now=NOW + timedelta(days=2))
    assert second["identity"]["city"] == "Казань"
    assert second["_meta"]["identity"]["city"]["confidence"] == 0.9
    assert second["_meta"]["identity"]["city"]["history"][0]["value"] == "Москва"


def test_temporary_mood_expires_but_stable_identity_does_not():
    memory = merge_memory_facts({}, {"psycho_vibe": {"current_mood": "устал"}, "identity": {"city": "Москва"}}, now=NOW)
    expired = purge_expired_memory(memory, now=NOW + timedelta(days=31))
    assert "current_mood" not in expired.get("psycho_vibe", {})
    assert expired["identity"]["city"] == "Москва"


def test_explicit_fact_lists_are_merged_without_stringifying():
    memory = merge_memory_facts({}, {"preferences": {"explicit_facts": ["любит кофе"]}}, now=NOW)
    memory = merge_memory_facts(memory, {"preferences": {"explicit_facts": ["любит музыку"]}}, now=NOW)
    assert memory["preferences"]["explicit_facts"] == ["любит кофе", "любит музыку"]
