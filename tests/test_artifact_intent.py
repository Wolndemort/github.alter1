from utils.artifact_intent import reuses_previous_artifact


def test_previous_artifact_reference_requires_an_edit_action():
    assert reuses_previous_artifact("измени последний созданный результат")
    assert reuses_previous_artifact("edit the previous generated image")
    assert not reuses_previous_artifact("покажи последний результат")
    assert not reuses_previous_artifact("создай новое изображение")
    russian = "измени последний созданный документ: ready status => final status"
    assert reuses_previous_artifact(russian.encode("utf-8").decode("latin1"))
