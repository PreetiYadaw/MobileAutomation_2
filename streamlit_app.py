import asyncio
import streamlit as st
from config import settings
from app.automation.agent import run_agent

st.set_page_config(page_title="AI UI Automation", layout="wide")

st.title("AI-driven UI Automation")
st.caption(
    "Describe your goal in one sentence. The agent plans, acts, and verifies "
    "each step itself, then stops - it will not repeat the run automatically."
)

with st.sidebar:
    st.header("Config (from .env)")
    st.text(f"Platform: {settings.platform}")
    st.text(f"Target: {settings.target_url}")
    st.text(f"Planning model: {settings.groq_model}")
    st.text(f"Vision model: {settings.groq_vision_model}")
    st.text(f"Vision fallback: {'on' if settings.enable_vision_fallback else 'off (DOM/text only)'}")
    st.text(f"Popup auto-dismiss: {'on' if settings.popup_dismiss_enabled else 'off'}")
    st.text(f"Max steps: {settings.max_steps}")
    st.caption("Change these in your .env file, then restart the app.")

if "agent_running" not in st.session_state:
    st.session_state.agent_running = False

goal = st.text_area(
    "What should the agent do?",
    placeholder="e.g. Log in with username 'standard_user' and password 'secret_sauce', "
                "then add the first product to the cart and verify the cart shows 1 item.",
    height=100,
)

run_clicked = st.button(
    "Run",
    type="primary",
    disabled=not goal.strip() or st.session_state.agent_running,
)


def _render_step(log_container, log):
    step = log["step"]
    action = log["action"]
    status = log["status"]

    icon = {"ok": "🟢", "finished": "✅", "failed": "🔴", "error": "⚠️"}.get(status, "•")
    with log_container:
        with st.expander(
            f"{icon} Step {step}: {action.get('action')} — {action.get('reasoning', '')}",
            expanded=(status != "ok"),
        ):
            st.json(action)

            if log.get("verification"):
                v = log["verification"]
                vt = "✅ Passed" if v["passed"] else "❌ Failed"
                st.write(f"**Verification ({v['method']}, score={v['score']}):** {vt}")
                st.caption(v["reasoning"])

            if log.get("error"):
                st.error(log["error"])

            if log.get("screenshot"):
                st.image(str(log["screenshot"]), width=400)

        if status == "finished":
            st.success("Goal completed. Agent has stopped.")
        elif status == "failed":
            st.error("Agent gave up — goal did not seem achievable.")


def _run_agent_once(goal: str, log_container):
    """Drive the async generator to completion in one dedicated event loop.
    Guaranteed to execute the automation exactly once per call."""

    async def _drive():
        async for log in run_agent(goal):
            _render_step(log_container, log)

    asyncio.run(_drive())


if run_clicked:
    st.session_state.agent_running = True
    log_container = st.container()
    with st.spinner("Running agent..."):
        try:
            _run_agent_once(goal, log_container)
        finally:
            st.session_state.agent_running = False
