"""MovieVerse Streamlit entry point and shared navigation."""

import streamlit as st

try:
    from frontend import pages
    from frontend.styles import inject_theme
except ModuleNotFoundError:
    import pages
    from styles import inject_theme


st.set_page_config(page_title="MovieVerse | Discover films", page_icon="🎬",
                   layout="wide", initial_sidebar_state="expanded")
inject_theme()

st.sidebar.markdown('<div class="mv-brand">MOVIE<span>VERSE</span></div>',
                    unsafe_allow_html=True)
st.sidebar.caption("Your next great watch starts here.")
st.sidebar.divider()

PAGE_LABELS = {
    "Home": "⌂  Home",
    "Discover": "◈  Discover",
    "For You": "✦  For You",
    "My Watchlist": "♡  My Watchlist",
    "Insights": "▥  Insights",
}
LEGACY_PAGES = {"Explore Movies": "Discover", "Recommendations": "For You",
                "Watchlist": "My Watchlist", "Analytics": "Insights"}
current_page = st.session_state.get("navigation", "Home")
st.session_state.navigation = LEGACY_PAGES.get(current_page, current_page)
pending_page = st.session_state.pop("pending_page", None)
if pending_page in PAGE_LABELS:
    st.session_state.navigation = pending_page
if st.session_state.navigation not in PAGE_LABELS:
    st.session_state.navigation = "Home"
page = st.sidebar.radio("Browse", tuple(PAGE_LABELS), key="navigation",
                        format_func=PAGE_LABELS.get, label_visibility="collapsed")
st.sidebar.divider()
st.sidebar.markdown('<div class="mv-profile">◉ &nbsp; Demo profile<br>'
                    '<span style="color:#A7A7B2">Your saved films live here.</span></div>',
                    unsafe_allow_html=True)

{
    "Home": pages.home,
    "Discover": pages.discover,
    "For You": pages.for_you,
    "My Watchlist": pages.watchlist,
    "Insights": pages.insights,
}[page]()
