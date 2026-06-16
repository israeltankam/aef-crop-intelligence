# src/utils/progress.py
"""Human-readable progress helpers for long Streamlit tasks."""
from __future__ import annotations

from contextlib import contextmanager, nullcontext

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None


@contextmanager
def friendly_spinner(message: str, detail: str | None = None):
    """Show a plain-language spinner and optional detail line.

    The user asked for visible, non-technical explanations while algorithms run.
    Keeping this helper central makes those messages consistent and easy to
    translate later.
    """
    if st is None:
        with nullcontext():
            yield
        return
    if detail:
        st.caption(detail)
    with st.spinner(message):
        yield
