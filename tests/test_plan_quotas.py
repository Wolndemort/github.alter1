import asyncio

from data.models import User
from utils.billing import credits_limit
from utils.quota import charge_user_id_credits
from config import config
from utils.redis_store import charge_credits, credits_used


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def incrby(self, key, amount):
        self.values[key] = self.values.get(key, 0) + amount
        return self.values[key]

    async def decrby(self, key, amount):
        self.values[key] = self.values.get(key, 0) - amount

    async def get(self, key):
        return str(self.values.get(key, 0))

    async def expire(self, key, seconds):
        return True


def run(coro):
    return asyncio.run(coro)


def test_plan_limits_are_personal_1000_and_ego_5000():
    personal = User(id=1, first_name="Personal", memory={}, tech_stack={})
    ego = User(id=2, first_name="Ego", memory={}, tech_stack={"subscription_plan": "ego"})
    assert credits_limit(personal) == 1000
    assert credits_limit(ego) == 5000


def test_personal_is_rejected_after_1000_credits():
    redis = FakeRedis()
    assert run(charge_credits(redis, 1, 1000, 1000)) is True
    assert run(charge_credits(redis, 1, 1, 1000)) is False
    assert run(credits_used(redis, 1)) == 1000


def test_ego_can_use_5000_credits_and_is_rejected_after_that():
    redis = FakeRedis()
    assert run(charge_credits(redis, 2, 5000, 5000)) is True
    assert run(charge_credits(redis, 2, 1, 5000)) is False
    assert run(credits_used(redis, 2)) == 5000


def test_owner_generation_is_free_and_does_not_need_redis():
    assert run(charge_user_id_credits(None, int(config.OWNER_TELEGRAM_IDS.split(",")[0]), 250)) is True


def test_generation_costs_are_higher_for_text_to_media():
    assert config.MEDIA_GENERATION_CREDITS == 40
    assert config.FAL_TEXT_IMAGE_CREDITS == 100
    assert config.FAL_TEXT_VIDEO_CREDITS == 250
    assert config.FAL_TEXT_VIDEO_CREDITS > config.FAL_TEXT_IMAGE_CREDITS > config.MEDIA_GENERATION_CREDITS
