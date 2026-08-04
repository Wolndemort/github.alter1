from collections import defaultdict
from datetime import date


class DailyRequestLimit:
    def __init__(self, limit: int = 100):
        self.limit = limit
        self._usage: dict[tuple[int, date], int] = defaultdict(int)

    def allow(self, user_id: int) -> bool:
        key = (user_id, date.today())
        if self._usage[key] >= self.limit:
            return False
        self._usage[key] += 1
        return True


daily_limit = DailyRequestLimit()
