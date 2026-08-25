"""
The loop: dismiss popups -> Plan -> Locate -> Act -> Verify -> repeat, until
the LLM says "finish"/"fail", a repetition guard trips, or we hit max_steps.

Async so the LLM calls (network-bound) don't block; blocking Selenium/Appium
driver calls are pushed onto a thread via asyncio.to_thread so they don't
stall the event loop either. This is an async GENERATOR - it yields exactly
once per step and then stops for good; it never re-runs the whole automation
after finishing.
"""

import asyncio

from app.automation.driver_manager import DriverManager
from app.automation.page_state import get_state
from app.automation.planner import aplan_next_step
from app.automation.locator_engine import aresolve_target
from app.automation.action_executor import (
    execute_click, execute_type, execute_select, execute_toggle,
    execute_submit, execute_scroll, execute_browser_back,
    execute_browser_forward, execute_refresh,
)
from app.automation.verifier import averify
from app.automation.popup_handler import dismiss_popups
from app.utils.screenshot import take_screenshot
from config import settings


def _fingerprint(action: dict) -> tuple:
    return (
        action.get("action"), action.get("ref"), action.get("text"),
        action.get("select_value"), action.get("direction"),
    )


async def run_agent(goal: str):
    """Async generator: yields a dict per step, e.g.
    {"step": 1, "action": {...}, "verification": {...}, "screenshot": Path, "status": "ok"}
    Runs the goal exactly once and stops - status "finished"/"failed" is terminal.
    """
    dm = DriverManager()
    driver = await asyncio.to_thread(dm.start)
    history: list[str] = []
    last_fingerprint = None
    repeat_count = 0

    try:
        # Cookie/consent banners often appear immediately on load.
        await asyncio.to_thread(dismiss_popups, driver, settings.platform)

        for step_num in range(1, settings.max_steps + 1):
            await asyncio.to_thread(dismiss_popups, driver, settings.platform)

            state_text, ref_map = await asyncio.to_thread(get_state, driver, settings.platform)

            action = await aplan_next_step(goal, history, state_text)
            act_type = action.get("action")

            log = {"step": step_num, "action": action, "verification": None,
                   "screenshot": None, "status": "ok"}

            if act_type == "finish":
                log["status"] = "finished"
                yield log
                break

            if act_type == "fail":
                log["status"] = "failed"
                yield log
                break

            # Safety net: if the model proposes the exact same action twice
            # in a row, it's stuck - almost always because the goal was
            # already achieved but the model didn't say "finish". Stop
            # rather than churn through the remaining steps doing nothing new.
            fp = _fingerprint(action)
            repeat_count = repeat_count + 1 if fp == last_fingerprint else 0
            last_fingerprint = fp
            if repeat_count >= 2:
                log["status"] = "finished"
                log["action"] = {
                    **action,
                    "reasoning": (
                        "Stopped automatically: the same action was proposed "
                        "repeatedly, which usually means the goal was already achieved."
                    ),
                }
                yield log
                break

            description = action.get("expected_result") or action.get("reasoning") or goal
            ref = action.get("ref")

            try:
                if act_type in ("click", "type", "select", "toggle"):
                    target = await aresolve_target(driver, ref, ref_map, description)
                    if target is None:
                        raise RuntimeError(f"Could not locate element for: {description}")
                    if act_type == "click":
                        await asyncio.to_thread(execute_click, driver, target)
                    elif act_type == "type":
                        await asyncio.to_thread(execute_type, driver, target, action.get("text") or "")
                    elif act_type == "select":
                        await asyncio.to_thread(execute_select, driver, target, action.get("select_value") or "")
                    elif act_type == "toggle":
                        await asyncio.to_thread(execute_toggle, driver, target)

                elif act_type == "submit":
                    target = None
                    if ref:
                        target = await aresolve_target(driver, ref, ref_map, description)
                    await asyncio.to_thread(execute_submit, driver, target)

                elif act_type == "scroll":
                    await asyncio.to_thread(
                        execute_scroll, driver, action.get("direction") or "down", settings.platform
                    )

                elif act_type == "browser_back":
                    await asyncio.to_thread(execute_browser_back, driver)

                elif act_type == "browser_forward":
                    await asyncio.to_thread(execute_browser_forward, driver)

                elif act_type == "refresh":
                    await asyncio.to_thread(execute_refresh, driver)

                elif act_type == "wait":
                    await asyncio.sleep(2)

                elif act_type == "verify":
                    pass  # verification always happens below regardless

                else:
                    raise RuntimeError(f"Unknown action type: {act_type}")

            except Exception as e:
                log["status"] = "error"
                log["error"] = str(e)
                history.append(f"Step {step_num}: {act_type} on {ref} -> ERROR: {e}")
                log["screenshot"] = await asyncio.to_thread(take_screenshot, driver, f"step{step_num}_error")
                yield log
                continue

            verification = await averify(driver, action.get("expected_result", ""), settings.platform)
            log["verification"] = verification
            log["screenshot"] = await asyncio.to_thread(take_screenshot, driver, f"step{step_num}")

            history.append(
                f"Step {step_num}: {act_type} (ref={ref}) -> "
                f"{'PASSED' if verification['passed'] else 'FAILED'} "
                f"({verification['method']}): {verification['reasoning']}"
            )

            yield log

    finally:
        await asyncio.to_thread(dm.quit)
