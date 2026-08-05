import asyncio
from types import SimpleNamespace

from utils import ap_logic
from utils.helpers import merge_memory
from utils.intent import is_web_request, should_search_web


def run(coro):
    return asyncio.run(coro)


def response(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_memory_eval_keeps_only_supported_categories_and_normalizes_keys():
    result = ap_logic.normalize_memory({
        "identity": {"Имя": "Адам", "город": "Москва"},
        "guessing": {"mood": "happy"},
        "open_loops": [{"title": "Закончить проект"}],
    })
    assert result == {
        "identity": {"name": "Адам", "city": "Москва"},
        "open_loops": [{"title": "Закончить проект"}],
    }


def test_memory_eval_correction_overwrites_scalar_but_preserves_other_facts():
    result = merge_memory(
        {"identity": {"city": "Москва", "name": "Адам"}},
        {"identity": {"city": "Казань"}},
    )
    assert result["identity"] == {"city": "Казань", "name": "Адам"}


def test_open_loop_eval_is_supported_by_memory_contract(monkeypatch):
    async def create(**kwargs):
        return response('{"open_loops": [{"title": "Закончить проект", "follow_up_question": "Как продвигается?"}]}')

    monkeypatch.setattr(ap_logic.client.chat.completions, "create", create)
    result = run(ap_logic.summarize_session([{"role": "user", "content": "Вернусь к проекту завтра"}]))
    assert result["open_loops"][0]["title"] == "Закончить проект"


def test_intent_eval_does_not_search_for_small_talk():
    assert not should_search_web("Мне сегодня грустно, побудь со мной")
    assert not is_web_request("Расскажи, как ты понимаешь дружбу")


def test_intent_eval_searches_current_facts_only_when_requested():
    assert should_search_web("Проверь актуальную цену телефона")
    assert should_search_web("Какая сегодня погода в Москве?")


def test_model_eval_routes_long_user_task_to_reasoning():
    route = ap_logic.select_model_route([{"role": "user", "content": "Составь подробный пошаговый план миграции базы данных"}])
    assert route[0] == ap_logic.config.OPENROUTER_REASONING_MODEL


def test_model_eval_does_not_route_long_assistant_history_to_reasoning():
    route = ap_logic.select_model_route([
        {"role": "assistant", "content": "history " * 2000},
        {"role": "user", "content": "Спасибо"},
    ])
    assert route[0] == ap_logic.config.OPENROUTER_MODEL


def test_tool_eval_rejects_unknown_tool_without_external_call():
    assert run(ap_logic.execute_tool("delete_database", {})) == "Неизвестный инструмент."


def test_audio_eval_uses_semantic_plan_for_explicit_action(monkeypatch):
    async def create(**kwargs):
        return response('{"download_audio": true, "query": "Nirvana Come As You Are"}')

    monkeypatch.setattr(ap_logic.client.chat.completions, "create", create)
    result = run(ap_logic.plan_audio_request("Поставь мне Come As You Are группы Nirvana"))
    assert result == {"download_audio": True, "query": "Nirvana Come As You Are"}


def test_audio_eval_does_not_download_for_music_discussion(monkeypatch):
    async def create(**kwargs):
        return response('{"download_audio": false, "query": ""}')

    monkeypatch.setattr(ap_logic.client.chat.completions, "create", create)
    result = run(ap_logic.plan_audio_request("Почему у Nirvana такой узнаваемый звук?"))
    assert result["download_audio"] is False
