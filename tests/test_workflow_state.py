from utils.workflow_state import advance_workflow, start_workflow, suggest_steps, workflow_view


def test_workflow_tracks_goal_progress_and_current_step():
    settings = start_workflow({}, "finish_task", "Запустить лендинг", ["Собрать требования", "Сделать прототип", "Проверить запуск"])
    assert workflow_view(settings)["current_step_title"] == "Собрать требования"
    settings = advance_workflow(settings)
    view = workflow_view(settings)
    assert view["current_step"] == 1
    assert view["completed_steps"] == 1
    assert view["goal"] == "Запустить лендинг"


def test_workflow_can_be_completed_explicitly():
    settings = start_workflow({}, "finish_task", "Цель")
    settings = advance_workflow(settings, complete=True)
    assert workflow_view(settings)["status"] == "completed"


def test_goal_type_selects_specific_steps_without_model_round_trip():
    assert suggest_steps("Подготовить разговор", "hard_conversation")[0] == "Определить цель разговора"
    assert len(suggest_steps("Запуск проекта", "finish_task")) == 4
