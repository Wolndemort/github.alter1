from utils.memory_view import format_memory, memory_sections


def test_memory_projection_hides_storage_keys_and_uses_human_labels():
    sections = memory_sections({"skills_career": {"job": "разработчик"}, "open_loops": [{"title": "проект"}]})
    assert sections[0]["title"] == "Навыки и работа"
    assert sections[0]["items"] == [{"label": "Работа", "value": "разработчик"}]
    assert "skills_career" not in format_memory({"skills_career": {"job": "разработчик"}})


def test_memory_projection_supports_new_categories():
    assert memory_sections({"education": {"course": "Python"}})[0]["title"] == "Учёба и развитие"
