from services.media_quality import music_analysis_contract, parse_music_timestamps, video_context


def test_video_context_detects_insufficient_sampling():
    result = video_context(duration_seconds=120, frame_count=6, transcript="hello")
    assert result["requires_more_sampling"] is True
    assert result["transcript_chars"] == 5


def test_music_contract_does_not_invent_metadata():
    result = music_analysis_contract("[00:12] chorus")
    assert result["title"] == ""
    assert result["confidence"] == 0.0
    assert result["lyrics_excerpt"]


def test_music_timestamps_are_structured():
    assert parse_music_timestamps("[01:20] chorus")[0] == {"at_seconds": 80, "label": "chorus"}
