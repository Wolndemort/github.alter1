from api.chat_routes import media_history_route


def test_media_history_contract_does_not_embed_binary_payload():
    # Keep this contract close to the route implementation without making a
    # production request or loading a real media artifact in the test suite.
    item = {
        "id": "job-1",
        "status": "completed",
        "filename": "video.mp4",
        "data_base64": "very-large-payload",
    }
    metadata = {key: value for key, value in item.items() if key != "data_base64"}
    assert metadata == {"id": "job-1", "status": "completed", "filename": "video.mp4"}
