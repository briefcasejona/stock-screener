"""Cached reads: a file is read again only after it changed."""
import streamlit as st

import core


@st.cache_data(show_spinner=False)
def _dashboard(stamp):
    return core.load_dashboard()


@st.cache_data(show_spinner=False)
def _screen(stamp):
    return core.load_screen()


def dashboard():
    return _dashboard(core.data_stamp())


def screen():
    return _screen(core.mtime(f'{core.SCREENER}/dashboard/screen.json'))


def changed():
    """After the program changed data itself."""
    st.cache_data.clear()
