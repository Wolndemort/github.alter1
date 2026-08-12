from utils.quality import assess_reply, has_internal_leak, has_language_mismatch, sanitize_public_reply


def test_detects_ukrainian_answer_to_russian_request():
    reply = "".join(chr(code) for code in (0x0413, 0x0430, 0x0440, 0x0430, 0x0437, 0x0434, 0x002c, 0x044f, 0x0020, 0x0434, 0x043e, 0x043f, 0x043e, 0x043c, 0x043e, 0x0436, 0x0443, 0x0020, 0x0456, 0x0437, 0x0020, 0x0446, 0x0438, 0x043c, 0x0020, 0x043f, 0x0438, 0x0442, 0x0430, 0x043d, 0x043d, 0x044f, 0x043c))
    request = "".join(chr(code) for code in (0x041f, 0x043e, 0x043c, 0x043e, 0x0433, 0x0438, 0x0020, 0x043c, 0x043d, 0x0435, 0x0020, 0x043d, 0x0430, 0x0439, 0x0442, 0x0438, 0x0020, 0x043c, 0x0430, 0x0433, 0x0430, 0x0437, 0x0438, 0x043d))
    assert has_language_mismatch(reply, request)


def test_sanitizes_service_tags_and_provider_error_details():
    assert sanitize_public_reply("Готово <answer>сделал</answer>.") == "Готово сделал."
    safe = sanitize_public_reply("Не удалось получить ответ от AI. Код запроса: abc123")
    assert "abc123" not in safe
    assert "Код запроса" not in safe


def test_detects_english_planner_leak_from_chat_screenshot():
    reply = (
        "Okay, the user just mentioned they wanted me to remember something.\n\n"
        "Looking at the memory section in the instructions, I should use the memory function.\n\n"
        "According to the rules, the tools available don't include a direct remember function."
    )
    assert has_internal_leak(reply)
    assert "internal_details" in assess_reply(reply).issues


def test_allows_normal_english_user_content():
    assert not has_internal_leak("The package arrived today and everything works.")


def test_detects_leak_after_tool_narration():
    assert has_internal_leak("But wait, the tools available don't include that function.")


def test_detects_english_reasoning_leak_from_production_benchmark():
    reply = "Okay, the user is feeling anxious. Looking at the internal response mode, I need to follow the character guidelines."
    assert has_internal_leak(reply)


def test_detects_instructional_english_reasoning_leak_from_production_benchmark():
    reply = 'The user says: "Мне тревожно". We must respond per instructions: calm, warm, supportive.'
    assert has_internal_leak(reply)


def test_detects_additional_production_planning_leaks():
    replies = (
        "We need to respond according to character rules: calm, concise, helpful.",
        "According to ALTER behavior, understand the user and ask for context.",
        "The user just says: explain this in English. Given instructions, let's craft an answer.",
    )
    assert all(has_internal_leak(reply) for reply in replies)


def test_detects_deeper_instruction_leak():
    assert has_internal_leak("We need to obey the instruction. Earlier we were told to answer in Russian.")


def test_detects_english_answer_to_russian_request():
    assert has_language_mismatch("Sure, I can help you with that.", "Помоги мне составить план")
    assert not has_language_mismatch("Конечно, помогу.", "Помоги мне составить план")
