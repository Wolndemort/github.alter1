import copy


def deep_merge(base: dict, nxt: dict) -> dict:
    """Рекурсивно объединяет два словаря, чтобы не затирать вложенные ключи."""
    for key, value in nxt.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def merge_memory(base: dict | None, incoming: dict | None) -> dict:
    """Merge structured memory without losing existing facts or list items."""
    result = copy.deepcopy(base) if isinstance(base, dict) else {}
    for key, value in (incoming or {}).items():
        current = result.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            result[key] = merge_memory(current, value)
        elif isinstance(current, list) and isinstance(value, list):
            for item in value:
                if item not in current:
                    current.append(copy.deepcopy(item))
        else:
            result[key] = copy.deepcopy(value)
    return result
