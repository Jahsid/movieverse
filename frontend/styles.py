"""Cinematic theme shared by all Streamlit pages."""

import streamlit as st


CSS = """
<style>
:root { color-scheme: dark; }
.stApp { background: #0B0B0F; color: #FFFFFF; }
.block-container { max-width: 1500px; padding-top: 2.2rem; padding-bottom: 4rem; }
[data-testid="stSidebar"] { background: #111116; border-right: 1px solid #292933; }
[data-testid="stSidebar"] .block-container { padding-top: 2rem; }
[data-testid="stSidebar"] [role="radiogroup"] label {
  padding: .58rem .7rem; border-radius: 10px; margin-bottom: .25rem;
  transition: background .15s ease, color .15s ease;
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover { background: #22222B; }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
  background: #312026; border: 1px solid #87323A;
}
h1, h2, h3 { letter-spacing: -.035em; }
h1 { font-size: clamp(2.2rem, 4vw, 3.7rem) !important; font-weight: 800 !important; }
h2 { font-size: clamp(1.55rem, 2.4vw, 2.2rem) !important; font-weight: 750 !important; }
h3 { font-size: 1.12rem !important; }
p, .stCaption { color: #C7C7D0; }
.mv-brand { font-weight: 900; font-size: 1.5rem; letter-spacing: -.05em; color: white; }
.mv-brand span { color: #E50914; }
.mv-profile { background: #1C1C23; border: 1px solid #30303A; border-radius: 13px;
  padding: .8rem 1rem; color: #D9D9E0; font-size: .88rem; }
.mv-eyebrow { color: #D6A85F; text-transform: uppercase; letter-spacing: .18em;
  font-size: .74rem; font-weight: 750; margin-bottom: .5rem; }
.mv-hero { position: relative; overflow: hidden; padding: clamp(2rem, 5vw, 4.5rem);
  border-radius: 22px; border: 1px solid #3A2830;
  background: radial-gradient(circle at 79% 23%, #7B202D 0, transparent 31%),
              radial-gradient(circle at 93% 80%, #6B4A32 0, transparent 29%),
              linear-gradient(112deg, #20171C 0%, #101015 73%);
  margin-bottom: 1.2rem; }
.mv-hero::after { content: ""; position: absolute; width: 20rem; height: 20rem;
  right: -3rem; top: -4rem; border: 1px solid #FFFFFF22; border-radius: 50%;
  box-shadow: 0 0 0 3.5rem #FFFFFF08, 0 0 0 7rem #FFFFFF06; pointer-events: none; }
.mv-hero h1 { max-width: 750px; margin: 0 0 .7rem; line-height: 1.06; }
.mv-hero p { max-width: 590px; font-size: 1.08rem; color: #D2CCD1; }
.mv-section { display: flex; align-items: baseline; justify-content: space-between;
  margin: 1.8rem 0 .75rem; }
.mv-section h2 { margin: 0; }
.mv-section p { margin: 0; color: #A7A7B2; font-size: .9rem; }
.mv-poster { aspect-ratio: 2 / 3; min-height: 180px; display: flex;
  flex-direction: column; justify-content: space-between; padding: 1rem;
  border-radius: 13px; overflow: hidden; border: 1px solid #FFFFFF1C;
  background: radial-gradient(circle at 78% 20%, #46414A 0, transparent 37%),
              linear-gradient(145deg, #28262E, #14141B 72%); }
.mv-poster img { width: 100%; height: 100%; object-fit: cover; border-radius: 10px; }
.mv-poster-mark { font-size: .62rem; letter-spacing: .2em; color: #D6A85F;
  font-weight: 800; }
.mv-poster-initial { font-size: clamp(3rem, 6vw, 5rem); line-height: 1;
  font-weight: 900; color: #FFFFFF22; text-align: center; }
.mv-poster-bottom { height: 2px; width: 35%; background: #E50914; }
.mv-card-title { font-weight: 760; color: #F5F5F7; font-size: 1rem;
  line-height: 1.3; margin: .65rem 0 .25rem; min-height: 2.6rem; }
.mv-card-meta { color: #A7A7B2; font-size: .82rem; min-height: 2.2rem; }
.mv-card-note { color: #D6A85F; font-size: .79rem; font-weight: 650; margin-top: .25rem; }
.mv-empty { background: #17171D; border: 1px dashed #444450; border-radius: 14px;
  padding: 1.4rem; color: #B8B8C2; }
.mv-stat { background: #17171D; border: 1px solid #2E2E38; border-radius: 14px;
  padding: 1.1rem 1.2rem; }
.mv-stat-value { color: white; font-size: 1.65rem; font-weight: 800; }
.mv-stat-label { color: #A7A7B2; text-transform: uppercase; letter-spacing: .1em;
  font-size: .69rem; font-weight: 700; }
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
  background: #E50914; color: white; border-color: #E50914; font-weight: 750;
}
.stButton > button:hover, .stFormSubmitButton > button:hover { border-color: #D6A85F; }
[data-testid="stTextInput"] input, [data-testid="stSelectbox"] > div,
[data-testid="stNumberInput"] input { background: #22222B; color: white; }
[data-testid="stDataFrame"], [data-testid="stVegaLiteChart"] {
  border: 1px solid #2B2B35; border-radius: 12px; overflow: hidden;
}
@media (max-width: 760px) {
  .block-container { padding: 1.2rem .8rem 3rem; }
  .mv-hero { padding: 1.5rem; }
  .mv-poster { min-height: 140px; }
}
</style>
"""


def inject_theme() -> None:
    """Apply the shared theme once per Streamlit rerun."""
    st.markdown(CSS, unsafe_allow_html=True)
