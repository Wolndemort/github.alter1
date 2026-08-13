"""Parse provider-neutral Fal options from Russian/English media prompts."""
from __future__ import annotations

import re


_RATIOS = r"21:9|16:9|4:3|3:2|1:1|2:3|3:4|9:16|9:21"


def _number(value: str) -> int | float:
    return float(value) if "." in value else int(value)


def parse_media_options(text: str, kind: str) -> dict:
    value = re.sub(r"\s+", " ", str(text or "").casefold().replace("ё", "е")).strip()
    options: dict = {}

    ratio = re.search(rf"(?<!\d)({_RATIOS})(?!\d)", value)
    if ratio:
        options["aspect_ratio"] = ratio.group(1)
    elif re.search(r"\b(?:вертикаль\w*|портрет\w*|сторис|stories|vertical|portrait)\b", value):
        options["aspect_ratio"] = "9:16"
    elif re.search(r"\b(?:горизонталь\w*|широк\w*\s+формат|альбом\w*|landscape|wide)\b", value):
        options["aspect_ratio"] = "16:9"
    elif re.search(r"\b(?:квадрат\w*|square)\b", value):
        options["aspect_ratio"] = "1:1"

    seed = re.search(r"\b(?:seed|сид|с[её]д)\s*[:=]?\s*(\d+)\b", value)
    if seed:
        options["seed"] = int(seed.group(1))

    if kind == "image":
        output = re.search(r"\b(?:формат|сохрани(?:\s+в)?|выход|format|save(?:\s+as)?)\s*[:=]?\s*(png|jpeg|jpg|webp)\b", value)
        if output:
            options["output_format"] = "jpeg" if output.group(1) == "jpg" else output.group(1)
        for key, patterns in {
            "guidance_scale": (r"guidance(?:\s+scale)?", r"гид(?:\s+)?скейл", r"сила\s+следования"),
            "image_prompt_strength": (r"image\s+prompt\s+strength", r"сила\s+промпта"),
        }.items():
            match = re.search(rf"(?:{'|'.join(patterns)})\s*[:=]?\s*(\d+(?:\.\d+)?)", value)
            if match:
                options[key] = _number(match.group(1))
        if re.search(r"\b(?:улучши\s+промпт|улучшить\s+промпт|enhance\s+prompt)\b", value):
            options["enhance_prompt"] = True

    if kind == "video":
        duration = re.search(r"\b(?:длительность|duration)?\s*[:=]?\s*(5|10)\s*(?:секунд\w*|сек\.?|s)\b", value)
        if duration:
            options["duration"] = duration.group(1)
        if re.search(r"\b(?:с|со)\s+(?:звуком|аудио)|\b(?:добавь|включи)\s+(?:звук|аудио)|\b(?:with|include)\s+audio\b", value):
            options["generate_audio"] = True
        elif re.search(r"\b(?:без\s+(?:звука|аудио)|(?:звук|аудио)\s+(?:выключи|убери)|\bwithout\s+audio)\b", value):
            options["generate_audio"] = False
        negative = re.search(r"\b(?:без|исключи|убери|negative|without)\s+(.+?)(?:[.,;]|$)", value)
        if negative:
            candidate = negative.group(1).strip()
            if candidate not in {"звука", "аудио", "audio"}:
                options["negative_prompt"] = candidate
        shot = re.search(r"\b(?:кадр|shot)\s*[:=]?\s*(customize|intelligent|настроенн\w*|умн\w*)\b", value)
        if shot:
            options["shot_type"] = "intelligent" if shot.group(1) in {"умный", "умная", "умно", "intelligent"} else "customize"
    return options
