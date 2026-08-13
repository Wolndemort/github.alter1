from utils.document_commands import document_edit_instruction, is_document_edit_request


def test_document_edit_commands_normalize_common_russian_forms():
    assert is_document_edit_request("измени статус на готово")
    assert document_edit_instruction("измени статус на готово") == "статус => готово"
    assert document_edit_instruction("убери черновик") == "черновик =>"
    assert document_edit_instruction("добавь срочно после статус") == "статус => статус срочно"


def test_explicit_replacement_syntax_is_preserved():
    assert document_edit_instruction("/edit старый => новый") == "старый => новый"
    assert document_edit_instruction("ALTER: замени старый на новый") == "старый => новый"
