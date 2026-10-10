import streamlit as st

NAVY = "#21295C"
DEEP = "#065A82"
TEAL = "#1C7293"
ICE = "#EAF4F8"
MUTED = "#5C6B73"

# key -> (icon, glow colour, animation, tagline)
CARDS = {
    "flights":     ("✈️", "#2E86AB", "mmtFly",    "Fares & timings"),
    "trains":      ("🚆", "#7B61FF", "mmtSlide",  "Schedules & fares"),
    "buses":       ("🚌", "#F59E0B", "mmtBounce", "Operators & seats"),
    "cabs":        ("🚕", "#EAB308", "mmtDrive",  "Outstation rides"),
    "hotels":      ("🏨", "#EF4444", "mmtPulse",  "Stays per night"),
    "villas":      ("🏡", "#10B981", "mmtSway",   "Villas & homestays"),
    "attractions": ("🎟️", "#EC4899", "mmtWiggle", "Tours & activities"),
    "packages":    ("🧳", "#06B6D4", "mmtSwing",  "Holiday packages"),
    "cruises":     ("🚢", "#3B82F6", "mmtRock",   "Cruise packages"),
}

BASE_CSS = """
<style>
:root { --navy: __NAVY__; --deep: __DEEP__; --teal: __TEAL__; --ice: __ICE__; }

/* ---------- page background + content card ---------- */
.stApp { background: linear-gradient(160deg, #EAF4F8 0%, #D4E9F5 45%, #BCDCEF 100%); background-attachment: fixed; }
[data-testid="stHeader"] { background: transparent; }
.block-container {
    max-width: 1100px; padding: 2.5rem 2.5rem 3rem 2.5rem; margin-top: 1.2rem;
    background: rgba(255,255,255,.82); border-radius: 20px;
    box-shadow: 0 10px 40px rgba(33,41,92,.12); backdrop-filter: blur(6px);
}
h1 { color: var(--navy) !important; font-weight: 800 !important; letter-spacing: -.5px;
     padding-bottom: .3rem; border-bottom: 3px solid var(--teal); display: inline-block; margin-bottom: 1.3rem !important; }
h2, h3, h4 { color: var(--navy) !important; font-weight: 700 !important; }

/* ---------- keyframes ---------- */
@keyframes mmtArrow  { 0%,100% { transform: translateY(0); opacity: .55; } 50% { transform: translateY(5px); opacity: 1; } }
@keyframes mmtDropDown { from { opacity: 0; transform: translateY(-20px) scaleY(.82); } to { opacity: 1; transform: none; } }
@keyframes mmtFadeUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: none; } }
@keyframes mmtStepIn { from { opacity: 0; transform: translateY(18px) scale(.98); } to { opacity: 1; transform: none; } }
@keyframes mmtFly    { 0%,100% { transform: translate(-7px, 7px) rotate(-4deg); } 50% { transform: translate(9px,-9px) rotate(5deg); } }
@keyframes mmtSlide  { 0%,100% { transform: translateX(-9px); } 50% { transform: translateX(9px); } }
@keyframes mmtBounce { 0%,100% { transform: translateY(0); } 40% { transform: translateY(-11px); } 60% { transform: translateY(-4px); } }
@keyframes mmtDrive  { 0%,100% { transform: translateX(-10px) rotate(-2deg); } 25% { transform: translateX(-2px) rotate(1deg); } 50% { transform: translateX(10px) rotate(-1deg); } 75% { transform: translateX(2px) rotate(2deg); } }
@keyframes mmtPulse  { 0%,100% { transform: scale(1); } 50% { transform: scale(1.18); } }
@keyframes mmtSway   { 0%,100% { transform: rotate(-7deg); } 50% { transform: rotate(7deg); } }
@keyframes mmtWiggle { 0%,100% { transform: rotate(-12deg); } 50% { transform: rotate(12deg); } }
@keyframes mmtSwing  { 0%,100% { transform: rotate(-11deg); } 50% { transform: rotate(11deg); } }
@keyframes mmtRock   { 0%,100% { transform: rotate(-5deg) translateY(2px); } 50% { transform: rotate(5deg) translateY(-4px); } }
@keyframes mmtGlow {
    0%,100% { box-shadow: 0 0 0 2px var(--glow), 0 0 18px 4px color-mix(in srgb, var(--glow) 45%, transparent); }
    50%     { box-shadow: 0 0 0 2px var(--glow), 0 0 36px 12px color-mix(in srgb, var(--glow) 65%, transparent); }
}
@keyframes mmtSearchGlow {
    0%,100% { box-shadow: 0 0 0 2px rgba(255,255,255,.7), 0 0 16px 4px rgba(28,114,147,.55); }
    50%     { box-shadow: 0 0 0 2px rgba(255,255,255,.9), 0 0 32px 10px rgba(28,114,147,.8); }
}

/* ---------- page transitions + step-by-step reveal ---------- */
[class*="st-key-flow_"] {
    position: relative; margin-top: 20px; padding: 1.1rem 1.5rem 1.4rem; border: 1px solid #D4E3EC; border-radius: 18px;
    background: linear-gradient(180deg, #EDF5F9, #F6FAFC); transform-origin: top center;
    box-shadow: 0 10px 28px rgba(33, 41, 92, .10); animation: mmtDropDown .55s cubic-bezier(.2,.8,.2,1) both;
}
[class*="st-key-flow_"]::before {            /* little pointer to the card that was clicked */
    content: ""; position: absolute; top: -10px; left: var(--caret-left, 16.6%); width: 18px; height: 18px;
    background: #EDF5F9; border-left: 1px solid #D4E3EC; border-top: 1px solid #D4E3EC;
    transform: translateX(-50%) rotate(45deg);
}
.flow-title { font-size: 1.7rem; font-weight: 800; color: var(--navy); padding-bottom: .35rem;
              margin-bottom: .6rem; border-bottom: 2px solid #C9DCE6; }
.step-arrow { color: var(--teal); font-size: 1.15rem; line-height: 1; padding-left: 10px; margin: -4px 0 -2px;
              animation: mmtArrow 1.1s ease-in-out infinite; }
.step-label { display: flex; align-items: center; gap: 10px; font-weight: 700; color: var(--navy); font-size: 1.02rem; margin: 2px 0 4px; }
.step-label b { width: 26px; height: 26px; border-radius: 50%; color: #FFFFFF; font-size: .82rem;
                background: linear-gradient(135deg, var(--deep), var(--teal)); display: inline-flex;
                align-items: center; justify-content: center; }
[class*="st-key-step_"] { animation: mmtStepIn .55s cubic-bezier(.2,.8,.2,1) both; }

/* ---------- 3x3 service cards ---------- */
[class*="st-key-svc_"] { --glow: #2E86AB; width: 100% !important; }
[class*="st-key-svc_"] [data-testid="stButton"] { width: 100% !important; }
[class*="st-key-svc_"] button {
    height: 168px !important; width: 100% !important;
    display: flex !important; flex-direction: column !important; align-items: center !important; justify-content: center !important;
    gap: 6px !important; padding: 12px !important;
    background: #FFFFFF !important; border: 1px solid #D4E3EC !important; border-radius: 20px !important;
    box-shadow: 0 4px 14px rgba(33,41,92,.08);
    transition: transform .22s ease, border-color .22s ease !important;
}
[class*="st-key-svc_"] button::before { font-size: 3rem; line-height: 1; display: block; transform-origin: 50% 80%; }
[class*="st-key-svc_"] button::after  { font-size: .78rem; font-weight: 500; color: __MUTED__; }
[class*="st-key-svc_"] button p { font-size: 1.12rem; font-weight: 800; color: var(--navy) !important; margin: 0; }
[class*="st-key-svc_"] button:hover {
    transform: translateY(-7px) scale(1.035) !important; border-color: var(--glow) !important;
    animation: mmtGlow 1.4s ease-in-out infinite;
}
[class*="st-key-svc_"] button:hover::before { animation-duration: .85s !important; }
[class*="st-key-svc_"] button:active { transform: translateY(-2px) scale(.99) !important; }

/* ---------- search buttons ---------- */
[class*="st-key-search_"] button {
    background: linear-gradient(135deg, var(--deep), var(--teal)) !important; color: #FFFFFF !important;
    border: none !important; border-radius: 12px !important; padding: .6rem 1.8rem !important; font-weight: 700 !important;
    box-shadow: 0 4px 12px rgba(6,90,130,.25) !important; transition: transform .15s ease !important;
}
[class*="st-key-search_"] button p { color: #FFFFFF !important; }
[class*="st-key-search_"] button:hover { transform: translateY(-2px);
    box-shadow: 0 0 0 3px rgba(28,114,147,.40), 0 0 32px 8px rgba(6,90,130,.70) !important; }

/* ---------- inputs: compact width, wrapping labels ---------- */
[data-testid="stTextInput"], [data-testid="stTextArea"], [data-testid="stDateInput"], [data-testid="stNumberInput"] { max-width: 300px; }
[data-testid="stTextArea"] textarea { resize: none; line-height: 1.3; border-radius: 10px; }
[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label {
    white-space: normal !important; overflow-wrap: anywhere; word-break: break-word; line-height: 1.25;
}
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"] { background: #FFFFFF !important; border-radius: 10px !important; }
[data-baseweb="input"], [data-baseweb="textarea"] { border: 1px solid #C9DCE6 !important; }
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within { border-color: var(--teal) !important; box-shadow: 0 0 0 2px rgba(28,114,147,.2); }
[data-testid="stCaptionContainer"] { overflow-wrap: anywhere; }

/* ---------- mode buttons ---------- */
[class*="st-key-mode_"], [class*="st-key-mode_"] [data-testid="stButton"] { width: 100% !important; }
[class*="st-key-mode_"] button {
    width: 100% !important; height: auto !important; min-height: 48px; padding: .55rem 1.1rem !important;
    background: #FFFFFF !important; border: 1px solid #C9DCE6 !important; border-radius: 999px !important;
    box-shadow: 0 2px 8px rgba(33,41,92,.07) !important;
    transition: transform .18s ease, box-shadow .25s ease, border-color .25s ease !important;
}
[class*="st-key-mode_"] button p {
    color: var(--navy) !important; font-weight: 700; font-size: .95rem; line-height: 1.2; text-align: center;
    white-space: normal !important; overflow: visible !important; text-overflow: clip !important;
}
[class*="st-key-mode_"] button:hover {
    border-color: var(--teal) !important; transform: translateY(-2px);
    box-shadow: 0 0 0 2px rgba(28,114,147,.35), 0 0 24px 6px rgba(28,114,147,.55) !important;
}

/* ---------- result tables / alerts ---------- */
[data-testid="stTable"] table { border-collapse: separate; border-spacing: 0; border-radius: 12px; overflow: hidden; border: 1px solid #D8E2E8; width: 100%; }
[data-testid="stTable"] thead tr th { background: var(--deep) !important; color: #FFFFFF !important; font-weight: 700; padding: 10px 14px; }
[data-testid="stTable"] tbody tr:nth-child(even) td { background: var(--ice); }
[data-testid="stTable"] tbody tr td { padding: 9px 14px; }
[data-testid="stAlert"] { border-radius: 12px; }

[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] style) { display: none; }

@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
</style>
"""


def _card_css() -> str:
    out = []
    for key, (icon, glow, anim, tag) in CARDS.items():
        out.append(
            f'.st-key-svc_{key} {{ --glow: {glow}; }}\n'
            f'.st-key-svc_{key} button::before {{ content: "{icon}"; animation: {anim} 2.6s ease-in-out infinite; }}\n'
            f'.st-key-svc_{key} button::after {{ content: "{tag}"; }}\n'
        )
    return "<style>\n" + "".join(out) + "</style>"


def apply_theme():
    css = (BASE_CSS.replace("__NAVY__", NAVY).replace("__DEEP__", DEEP)
           .replace("__TEAL__", TEAL).replace("__ICE__", ICE).replace("__MUTED__", MUTED))
    st.markdown(css + _card_css(), unsafe_allow_html=True)


def highlight_active(active, col=0):
    """Keep the selected service card glowing + point the dropdown panel's caret at its column."""
    if not active:
        return
    st.markdown(
        f"<style>.st-key-svc_{active} button {{ border-color: var(--glow) !important; "
        f"box-shadow: 0 0 0 2px var(--glow), 0 0 26px 6px color-mix(in srgb, var(--glow) 55%, transparent) !important; "
        f"transform: translateY(-4px); }}"
        f"[class*=\"st-key-flow_\"] {{ --caret-left: calc({(col + 0.5) * 100 / 3:.2f}% - 4px); }}</style>",
        unsafe_allow_html=True,
    )


def highlight_mode(sid, idx):
    """Selected mode button: filled gradient with white text."""
    st.markdown(
        f"<style>.st-key-mode_{sid}_{idx} button {{ background: linear-gradient(135deg, var(--deep), var(--teal)) !important; "
        f"border-color: var(--deep) !important; "
        f"box-shadow: 0 0 0 2px rgba(6,90,130,.45), 0 0 22px 5px rgba(6,90,130,.5) !important; }}"
        f".st-key-mode_{sid}_{idx} button p {{ color: #FFFFFF !important; }}</style>",
        unsafe_allow_html=True,
    )
