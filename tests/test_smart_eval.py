import asyncio
from types import SimpleNamespace

from utils import ap_logic
from utils.helpers import merge_memory
from utils.intent import is_web_request, should_search_web
from utils.quality import assess_reply


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


def test_prompt_memory_is_bounded_without_dropping_the_memory_shape():
    bounded = ap_logic._bounded_memory({"identity": {"name": "Adam"}, "open_loops": ["x" * 10000]}, max_chars=300)
    assert len(str(bounded)) < 600
    assert "identity" in bounded


def test_session_summary_uses_recent_bounded_messages(monkeypatch):
    captured = {}

    async def create(**kwargs):
        captured["messages"] = kwargs["messages"]
        return response("{}")

    monkeypatch.setattr(ap_logic.client.chat.completions, "create", create)
    result = run(ap_logic.summarize_session([
        {"role": "user", "content": "old " * 3000},
        {"role": "user", "content": "latest"},
    ]))
    assert result == {}
    payload = captured["messages"][1]["content"]
    assert len(payload) <= ap_logic.config.MEMORY_SUMMARY_MAX_CHARS + 100
    assert "latest" in payload


def test_api_prompt_has_a_hard_cost_limit():
    messages = [
        {"role": "system", "content": "system " * 5000},
        {"role": "user", "content": "latest " * 5000},
    ]
    bounded = ap_logic._bounded_api_messages(messages, max_chars=1200)
    assert sum(len(str(item.get("content", ""))) for item in bounded) <= 1200
    assert bounded[-1]["role"] == "user"


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
    assert route[0] == ap_logic.config.OPENROUTER_FREE_MODEL


def test_model_eval_does_not_route_long_assistant_history_to_reasoning():
    route = ap_logic.select_model_route([
        {"role": "assistant", "content": "history " * 2000},
        {"role": "user", "content": "Спасибо"},
    ])
    assert route[0] == ap_logic.config.OPENROUTER_FREE_MODEL


def test_tool_eval_rejects_unknown_tool_without_external_call():
    assert run(ap_logic.execute_tool("delete_database", {})) == "Неизвестный инструмент."


def test_tool_eval_marks_empty_results_for_planner_retry():
    assert ap_logic.validate_tool_result("web_search", []) == (
        "empty",
        "Инструмент web_search ничего не нашёл. Измени запрос или выбери другой инструмент.",
    )


def test_tool_eval_accepts_nonempty_results():
    assert ap_logic.validate_tool_result("web_search", [{"title": "Source"}])[0] == "ok"


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


def test_quality_eval_accepts_normal_reply():
    result = assess_reply("Короткий ответ по делу.")
    assert result.score == 100
    assert result.issues == ()


def test_quality_eval_detects_internal_leak_and_missing_sources():
    result = assess_reply('{"status":"ok"}? Второй вопрос?', has_sources=True)
    assert result.score < 100
    assert "internal_details" in result.issues
    assert "missing_source_attribution" in result.issues


def test_quality_eval_detects_russian_reasoning_leak():
    result = assess_reply(
        "Пользователь хочет понять проблему. Сначала нужно понять запрос. "
        "Следует ответить пользователю коротко."
    )
    assert "internal_details" in result.issues
