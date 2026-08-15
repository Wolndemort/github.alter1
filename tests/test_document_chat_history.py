import pytest

from data.models import Session
from services.chat_service import record_document_turn


class Result:
    def __init__(self, session):
        self.session = session

    def scalar_one_or_none(self):
        return self.session


class Db:
    def __init__(self):
        self.session = Session(id=17, user_id=7, raw_messages=[])
        self.commits = 0

    async def execute(self, query):
        return Result(self.session)

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_document_turns_stay_in_one_session_and_keep_latest_artifact():
    db = Db()
    first = await record_document_turn(
        db, 7, "Прочитай документ", "В документе статус draft.",
        filename="status.txt", media_type="text/plain", operation="analysis",
        artifact_id="source-1", observation="status: draft",
    )
    second = await record_document_turn(
        db, 7, "Замени draft на ready", "Готово — изменённый файл возвращён.",
        filename="status.txt", media_type="text/plain", operation="document_edit",
        artifact_id="edited-2",
    )

    assert first == second == 17
    assert [item["role"] for item in db.session.raw_messages] == [
        "user", "assistant", "assistant", "user", "assistant", "assistant",
    ]
    assert '"id":"edited-2"' in db.session.raw_messages[-1]["content"]
    assert db.commits == 2
