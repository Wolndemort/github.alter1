"""Intent helpers for reusing the latest generated/edit artifact."""
from __future__ import annotations

import re


def reuses_previous_artifact(text: str) -> bool:
    value = str(text or "")
    try:
        value = value.encode("latin1").decode("utf-8") if any(marker in value for marker in ("Р", "Ð")) else value
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    value = value.casefold()
    has_reference = bool(re.search(r"\b(?:последн\w*|предыдущ\w*|созданн\w*|полученн\w*|результат\w*|last|previous|created|generated|that result)\b", value)) or any(marker in value for marker in ("РїРѕСЃР»", "РїСЂРµРґ", "РіРµРЅРµСЂ"))
    has_edit = bool(re.search(r"\b(?:измени\w*|редактир\w*|передел\w*|преобраз\w*|замени\w*|добав\w*|убер\w*|edit|change|transform|replace|stylize|add|remove)\b", value)) or any(marker in value for marker in ("Рё", "РїРµСЂРµРґ", "Р·Р°РјРµРЅ"))
    return has_reference and has_edit
