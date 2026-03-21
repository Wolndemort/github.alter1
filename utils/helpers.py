def deep_merge(base: dict, nxt: dict) -> dict:
    """Рекурсивно объединяет два словаря, чтобы не затирать вложенные ключи."""
    for key, value in nxt.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base
