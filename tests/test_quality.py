from utils.quality import assess_reply, has_internal_leak, has_language_mismatch


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


def test_detects_english_answer_to_russian_request():
    assert has_language_mismatch("Sure, I can help you with that.", "Помоги мне составить план")
    assert not has_language_mismatch("Конечно, помогу.", "Помоги мне составить план")
