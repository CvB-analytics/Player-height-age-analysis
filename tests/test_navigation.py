from src.ui.navigation import NAVIGATION_KEY, PENDING_NAVIGATION_KEY, apply_pending_navigation, queue_navigation


def test_completed_step_can_queue_and_apply_next_page():
    state = {}

    queue_navigation("Resultaten", state)
    assert state[PENDING_NAVIGATION_KEY] == "Resultaten"

    apply_pending_navigation(["Nieuw toernooi", "Import controleren", "Resultaten", "Rapportage"], state)
    assert state[NAVIGATION_KEY] == "Resultaten"
    assert PENDING_NAVIGATION_KEY not in state


def test_unknown_pending_page_is_discarded():
    state = {PENDING_NAVIGATION_KEY: "Onbekend", NAVIGATION_KEY: "Nieuw toernooi"}

    apply_pending_navigation(["Nieuw toernooi", "Import controleren"], state)

    assert state[NAVIGATION_KEY] == "Nieuw toernooi"
    assert PENDING_NAVIGATION_KEY not in state
