"""
Hybrid verification.

Step 1 (cheap, deterministic, always runs, no LLM): fuzzy string match
(thefuzz) between the "expected_result" the planner gave us and BOTH
(a) the page's visible text, and (b) the actual current VALUES held in
form fields (inputs, textareas, selects) pulled straight from the DOM.

(b) matters a lot: a typed value in an <input> never appears in the page's
rendered text (and a password field is masked even if it did) - so without
reading the DOM value directly, "does the password field contain X" is
genuinely unanswerable from text alone. Reading it directly answers it with
certainty and skips the LLM/vision call entirely.

Step 2 (only if the fuzzy score lands in a genuine grey zone, AND
settings.enable_vision_fallback is True): ask the vision model to look at
a screenshot and judge whether the expected result actually happened. If
vision fallback is disabled, a grey-zone score is treated as a fail rather
than guessed at - DOM/text is the source of truth.
"""

import asyncio
from thefuzz import fuzz
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

from app.llm.model_client import achat_vision_json
from app.utils.screenshot import take_screenshot, screenshot_to_b64
from config import settings

VERIFY_SYSTEM_PROMPT = """You are verifying whether a UI automation step
succeeded. You'll be given the expected result and a screenshot. Respond
with ONLY JSON, no reasoning, no <think> tags, no explanation outside the
JSON: {"passed": true|false, "reasoning": "short reason"}
"""

GREY_ZONE_LOW = 40


def _page_visible_text(driver) -> str:
    try:
        return driver.find_element("tag name", "body").text
    except Exception:
        return ""


def _web_field_values(driver) -> str:
    """Actual current values of every visible input/textarea/select, straight
    from the DOM - this is what lets us confirm a field's content with
    certainty even when it's masked (password) or otherwise not rendered
    as visible text."""
    parts = []
    try:
        for el in driver.find_elements(By.XPATH, "//input | //textarea | //select"):
            try:
                if not el.is_displayed():
                    continue
                name = el.get_attribute("name") or el.get_attribute("id") or el.tag_name
                if el.tag_name == "select":
                    val = Select(el).first_selected_option.text
                else:
                    val = el.get_attribute("value") or ""
                if val:
                    parts.append(f"{name}={val}")
            except Exception:
                continue
    except Exception:
        pass
    return "; ".join(parts)


def _android_field_values(driver) -> str:
    parts = []
    try:
        for el in driver.find_elements(By.XPATH, "//*[contains(@class,'EditText')]"):
            try:
                val = el.get_attribute("text") or ""
                rid = el.get_attribute("resource-id") or ""
                if val:
                    parts.append(f"{rid}={val}")
            except Exception:
                continue
    except Exception:
        pass
    return "; ".join(parts)


def _combined_state_text(driver, platform: str) -> str:
    visible_text = _page_visible_text(driver)
    field_values = _web_field_values(driver) if platform == "web" else _android_field_values(driver)
    return f"{visible_text}\nField values: {field_values}"


async def averify(driver, expected_result: str, platform: str) -> dict:
    """Returns {"passed": bool, "method": "fuzzy"|"vision"|"skipped", "score": int|None, "reasoning": str}"""
    if not expected_result:
        return {"passed": True, "method": "skipped", "score": None, "reasoning": "No expectation given."}

    combined_text = await asyncio.to_thread(_combined_state_text, driver, platform)
    score = fuzz.partial_ratio(expected_result.lower(), combined_text.lower())
    threshold = settings.fuzzy_match_threshold

    if score >= threshold:
        return {
            "passed": True,
            "method": "fuzzy",
            "score": score,
            "reasoning": f"Fuzzy match score {score} >= threshold {threshold} (text + field values).",
        }

    if score <= GREY_ZONE_LOW or not settings.enable_vision_fallback:
        return {
            "passed": False,
            "method": "fuzzy",
            "score": score,
            "reasoning": f"Fuzzy match score {score} below threshold {threshold} (text + field values).",
        }

    # Grey zone AND vision fallback enabled: ask the vision model to judge.
    screenshot_path = await asyncio.to_thread(take_screenshot, driver, "verify")
    b64 = await asyncio.to_thread(screenshot_to_b64, screenshot_path)
    result = await achat_vision_json(
        VERIFY_SYSTEM_PROMPT,
        f"Expected result: {expected_result}\nDid this happen?",
        b64,
    )
    return {
        "passed": bool(result.get("passed")),
        "method": "vision",
        "score": score,
        "reasoning": result.get("reasoning", ""),
    }
