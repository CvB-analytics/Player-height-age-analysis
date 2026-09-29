from __future__ import annotations

from collections.abc import MutableMapping, Sequence
from typing import Any

import streamlit as st

NAVIGATION_KEY = "navigation_page"
PENDING_NAVIGATION_KEY = "pending_navigation_page"


def queue_navigation(page: str, state: MutableMapping[str, Any] | None = None) -> None:
    target = st.session_state if state is None else state
    target[PENDING_NAVIGATION_KEY] = page


def apply_pending_navigation(
    pages: Sequence[str], state: MutableMapping[str, Any] | None = None
) -> None:
    target = st.session_state if state is None else state
    pending = target.pop(PENDING_NAVIGATION_KEY, None)
    if pending in pages:
        target[NAVIGATION_KEY] = pending
