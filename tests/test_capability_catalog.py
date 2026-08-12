from utils.capability_catalog import CAPABILITY_CATALOG, capability_catalog_text


def test_catalog_covers_the_major_product_surfaces():
    assert {"conversation", "agent", "documents", "vision", "video", "audio", "maps", "operations"} <= set(CAPABILITY_CATALOG)
    assert "document_edit_export" in CAPABILITY_CATALOG["documents"]
    assert "external_action_gate" in CAPABILITY_CATALOG["agent"]


def test_catalog_is_renderable_for_docs_and_ui():
    text = capability_catalog_text()
    assert "conversation:" in text
    assert "production_smoke" in text
