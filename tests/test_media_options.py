from utils.media_options import parse_media_options


def test_image_options_are_parsed_from_caption():
    result = parse_media_options("Сделай вертикальный формат, seed 42, сохрани в png", "image")
    assert result == {"aspect_ratio": "9:16", "seed": 42, "output_format": "png"}


def test_video_options_are_parsed_from_caption():
    result = parse_media_options("Оживи на 10 секунд, 16:9, с звуком, без людей", "video")
    assert result["duration"] == "10"
    assert result["aspect_ratio"] == "16:9"
    assert result["generate_audio"] is True
    assert result["negative_prompt"] == "людей"
