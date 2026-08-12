from services.vision_quality import compare_documents, extract_chart_data, layout_edit_plan, normalize_findings, object_geometry, quality_gate, video_events


def test_layout_plan_is_safe_and_reviewable():
    result = layout_edit_plan("Name: Alter", [{"old": "Alter", "new": "ALTER"}])
    assert result["operations"][0]["safe"] is True


def test_document_diff_finds_contract_changes():
    result = compare_documents("Срок: 1 год\nЦена: 100", "Срок: 2 года\nЦена: 100")
    assert result["changed"] is True
    assert result["change_count"] == 2


def test_geometry_is_normalized():
    assert object_geometry(50, 25, 100, 50, 200, 100) == {"x": .25, "y": .25, "width": .5, "height": .5}


def test_chart_data_and_video_events_are_structured():
    assert extract_chart_data("Январь: 12,5\nФевраль: 15")[0]["value"] == 12.5
    assert video_events("[01:20] человек вошёл")[0]["at_seconds"] == 80


def test_low_confidence_findings_are_not_presented_as_facts():
    findings = normalize_findings([{"text": "неясно", "confidence": .2}, {"text": "точно", "confidence": .9}])
    result = quality_gate(findings)
    assert result["accepted"] == ["точно"]
    assert result["requires_confirmation"] is True
