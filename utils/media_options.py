"""Parse common Fal.ai options from natural-language media prompts."""
from __future__ import annotations

import re


def parse_media_options(text: str, kind: str) -> dict:
    value = (text or "").casefold().replace("ё", "е")
    options: dict = {}
    ratio = re.search(r"\b(21:9|16:9|4:3|3:2|1:1|2:3|3:4|9:16|9:21)\b", value)
    if ratio:
        options["aspect_ratio"] = ratio.group(1)
    elif any(word in value for word in ("вертикаль", "портрет", "сторис")):
        options["aspect_ratio"] = "9:16"
    elif any(word in value for word in ("горизонталь", "широкий формат", "альбом")):
        options["aspect_ratio"] = "16:9"
    elif "квадрат" in value:
        options["aspect_ratio"] = "1:1"
    seed = re.search(r"\bseed\s*[:=]?\s*(\d+)\b|\bсид\s*[:=]?\s*(\d+)\b", value)
    if seed:
        options["seed"] = int(seed.group(1) or seed.group(2))
    output = re.search(r"\b(?:формат|сохрани(?:\s+в)?|выход)\s*[:=]?\s*(png|jpeg|webp)\b", value)
    if output and kind == "image":
        options["output_format"] = output.group(1)
    if kind == "video":
        duration = re.search(r"\b(5|10)\s*(?:секунд|сек|s)\b", value)
        if duration:
            options["duration"] = duration.group(1)
        if any(phrase in value for phrase in ("с звуком", "со звуком", "добавь звук", "звук включи")):
            options["generate_audio"] = True
        elif any(phrase in value for phrase in ("без звука", "без аудио", "звук выключи")):
            options["generate_audio"] = False
        negative = re.search(r"\b(?:без|исключи|убери)\s+(.+?)(?:\.|,|$)", value)
        if negative:
            options["negative_prompt"] = negative.group(1).strip()
    return options
