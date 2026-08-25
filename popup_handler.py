"""
Best-effort automatic popup/consent-banner/permission-dialog dismissal.

Called before every planning step (and right after the driver starts), so
the LLM never has to reason about "close this popup first" - by the time
it sees the screen, common popups are already gone. This is intentionally
NOT LLM-based: it's a fast, cheap, deterministic pass using plain locators.
"""

from selenium.webdriver.common.by import By
from config import settings

DISMISS_LABELS = {
    "accept all", "accept", "agree", "i agree", "allow", "allow all",
    "allow while using app", "while using the app", "got it", "ok", "okay",
    "close", "dismiss", "no thanks", "not now", "continue", "×", "x",
    "i understand", "understood",
}

WEB_CANDIDATE_XPATH = (
    "//button | //a[@role='button'] | //*[@role='button'] | //*[@aria-label]"
)

ANDROID_CANDIDATE_XPATH = "//*[@clickable='true']"


def _matches_dismiss_label(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in DISMISS_LABELS


def _dismiss_web(driver, max_dismissals: int) -> int:
    closed = 0
    for _ in range(max_dismissals):
        try:
            candidates = driver.find_elements(By.XPATH, WEB_CANDIDATE_XPATH)
        except Exception:
            break

        clicked_this_pass = False
        for el in candidates:
            try:
                if not el.is_displayed():
                    continue
                label = el.text or el.get_attribute("aria-label") or ""
                if _matches_dismiss_label(label):
                    el.click()
                    closed += 1
                    clicked_this_pass = True
                    break
            except Exception:
                continue

        if not clicked_this_pass:
            break
    return closed


def _dismiss_android(driver, max_dismissals: int) -> int:
    closed = 0

    # Android runtime-permission dialogs are OS-level, not part of the app's
    # own UI tree - try the alert-style dismissal first (harmless if there's
    # no alert; with ANDROID_AUTO_GRANT_PERMISSIONS=true these mostly won't
    # appear at all since the driver pre-grants permissions at session start).
    try:
        driver.execute_script("mobile: acceptAlert")
        closed += 1
    except Exception:
        pass

    for _ in range(max_dismissals):
        try:
            candidates = driver.find_elements(By.XPATH, ANDROID_CANDIDATE_XPATH)
        except Exception:
            break

        clicked_this_pass = False
        for el in candidates:
            try:
                label = el.get_attribute("text") or el.get_attribute("content-desc") or ""
                if _matches_dismiss_label(label):
                    el.click()
                    closed += 1
                    clicked_this_pass = True
                    break
            except Exception:
                continue

        if not clicked_this_pass:
            break
    return closed


def dismiss_popups(driver, platform: str, max_dismissals: int = 3) -> int:
    """Try to close up to `max_dismissals` popups. Returns how many were closed.
    Never raises - a failed dismissal attempt should never break the agent run."""
    if not settings.popup_dismiss_enabled:
        return 0
    try:
        if platform == "web":
            return _dismiss_web(driver, max_dismissals)
        return _dismiss_android(driver, max_dismissals)
    except Exception:
        return 0
