"""
Turns a resolved action into a real driver interaction. Covers the full
vocabulary the planner can choose from: click, type, select (dropdown),
toggle (checkbox/radio), submit, scroll (4 directions), browser back/
forward, refresh.
"""

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select

from app.automation.locator_engine import ResolvedTarget
from config import settings


def execute_click(driver, target: ResolvedTarget):
    if target.method == "ref":
        target.element.click()
    else:
        ActionChains(driver).move_by_offset(target.x_px, target.y_px).click().perform()
        ActionChains(driver).move_by_offset(-target.x_px, -target.y_px).perform()


def execute_type(driver, target: ResolvedTarget, text: str):
    if target.method == "ref":
        target.element.click()
        target.element.clear()
        target.element.send_keys(text)
    else:
        ActionChains(driver).move_by_offset(target.x_px, target.y_px).click().send_keys(text).perform()
        ActionChains(driver).move_by_offset(-target.x_px, -target.y_px).perform()


def execute_select(driver, target: ResolvedTarget, value: str):
    """Select a dropdown option by visible text (case-insensitive partial match fallback)."""
    if target.method != "ref":
        raise RuntimeError(
            "Dropdown selection needs a real element reference, not a screenshot coordinate."
        )
    select = Select(target.element)
    try:
        select.select_by_visible_text(value)
        return
    except Exception:
        pass
    for option in select.options:
        if value.strip().lower() in option.text.strip().lower():
            option.click()
            return
    raise RuntimeError(f"Could not find a dropdown option matching '{value}'.")


def execute_toggle(driver, target: ResolvedTarget):
    """Check/uncheck a checkbox, or select a radio button. Same mechanics as
    a click - kept as a separate name purely for clearer logs/history."""
    execute_click(driver, target)


def execute_submit(driver, target: ResolvedTarget = None):
    """Submit the current form. Prefers pressing Enter in the given field
    (works even for JS-driven forms with no real HTML <form>), falls back
    to calling .submit() on the element's enclosing form, then falls back
    to Enter on whatever element currently has focus."""
    if target is not None and target.method == "ref":
        try:
            target.element.send_keys(Keys.RETURN)
            return
        except Exception:
            pass
        try:
            target.element.submit()
            return
        except Exception:
            pass
    driver.switch_to.active_element.send_keys(Keys.RETURN)


def execute_scroll(driver, direction: str, platform: str):
    if platform == "android":
        size = driver.get_window_size()
        width, height = size["width"], size["height"]
        start_x, start_y, end_x, end_y = width // 2, height // 2, width // 2, height // 2

        if direction == "up":
            start_y, end_y = int(height * 0.8), int(height * 0.2)
        elif direction == "down":
            start_y, end_y = int(height * 0.2), int(height * 0.8)
        elif direction == "left":
            start_x, end_x = int(width * 0.8), int(width * 0.2)
        elif direction == "right":
            start_x, end_x = int(width * 0.2), int(width * 0.8)

        driver.swipe(start_x, start_y, end_x, end_y, 400)
    else:
        dx = dy = 0
        amount = settings.scroll_pixels
        if direction == "down":
            dy = amount
        elif direction == "up":
            dy = -amount
        elif direction == "right":
            dx = amount
        elif direction == "left":
            dx = -amount
        driver.execute_script(f"window.scrollBy({dx}, {dy});")


def execute_browser_back(driver):
    driver.back()


def execute_browser_forward(driver):
    driver.forward()


def execute_refresh(driver):
    driver.refresh()
