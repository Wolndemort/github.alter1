from utils.document_commands import document_edit_instruction, is_document_edit_request


def test_document_edit_commands_normalize_common_russian_forms():
    assert is_document_edit_request("измени статус на готово")
    assert document_edit_instruction("измени статус на готово") == "статус => готово"
    assert document_edit_instruction("убери черновик") == "черновик =>"
    assert document_edit_instruction("добавь срочно после статус") == "статус => статус срочно"


def test_explicit_replacement_syntax_is_preserved():
    assert document_edit_instruction("/edit старый => новый") == "старый => новый"
    assert document_edit_instruction("ALTER: замени старый на новый") == "старый => новый"


def test_natural_request_strips_previous_document_reference_before_replacement():
    prompt = "\u0438\u0437\u043c\u0435\u043d\u0438 \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0439 \u0441\u043e\u0437\u0434\u0430\u043d\u043d\u044b\u0439 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442: ready status => final status"
    assert document_edit_instruction(prompt) == "ready status => final status"


def test_document_edit_parser_understands_english_quotes_and_file_qualifiers():
    assert document_edit_instruction('Please replace "old status" with "ready" in the PDF') == "old status => ready"
    assert document_edit_instruction("delete черновик в документе") == "черновик =>"
    assert document_edit_instruction("insert срочно after статус") == "статус => статус срочно"
    assert is_document_edit_request("change old with new")
    assert is_document_edit_request('Please replace "old status" with "ready" in the PDF')
