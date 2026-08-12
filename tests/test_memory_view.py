from utils.memory_view import format_memory, memory_audit, memory_sections


def test_memory_projection_hides_nested_internal_fields():
    sections = memory_sections({"identity": {"name": "Ada", "_meta": {"name": {"confidence": 0.9}}, "source": "internal"}})
    assert len(sections) == 1
    assert sections[0]["items"] == [{"label": "Имя", "value": "Ada"}]


def test_memory_audit_keeps_raw_keys_for_confirm_api():
    audit = memory_audit({"_meta": {"skills_career": {"job": {"confirmed": False, "history": []}}}})
    assert audit == [{"category": "skills_career", "key": "job", "confirmed": False, "first_seen": None, "last_seen": None, "replacements": 0}]


def test_memory_projection_hides_storage_keys_and_uses_human_labels():
    sections = memory_sections({"skills_career": {"job": "разработчик"}, "open_loops": [{"title": "проект"}]})
    assert sections[0]["title"] == "Навыки и работа"
    assert sections[0]["items"] == [{"label": "Работа", "value": "разработчик"}]
    assert "skills_career" not in format_memory({"skills_career": {"job": "разработчик"}})


def test_memory_projection_supports_new_categories():
    assert memory_sections({"education": {"course": "Python"}})[0]["title"] == "Учёба и развитие"
