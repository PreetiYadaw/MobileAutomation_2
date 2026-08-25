"""
Turns the raw page/app into a short, LLM-friendly list of interactive
elements, instead of dumping the entire HTML/XML tree.

Each element gets a short ref tag like [E3] PLUS enough metadata - label
text, placeholder, input type, current value, dropdown options, checkbox/
radio state - that the LLM can decide what to type/select/toggle from text
alone, without ever needing a screenshot. Vision should only be needed for
genuinely unusual custom widgets that don't expose this metadata.
"""

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

WEB_INTERACTIVE_XPATH = (
    "//a | //button | //input | //select | //textarea | "
    "//*[@role='button'] | //*[@role='checkbox'] | //*[@role='combobox'] | //*[@onclick]"
)

ANDROID_INTERACTIVE_XPATH = (
    "//*[@clickable='true' or @long-clickable='true' or @checkable='true' or "
    "contains(@class,'EditText') or contains(@class,'Button') or contains(@class,'Spinner')]"
)


def _web_label_for(driver, el) -> str:
    """Find the <label> text associated with a form field, if any."""
    try:
        el_id = el.get_attribute("id")
        if el_id:
            labels = driver.find_elements(By.XPATH, f"//label[@for='{el_id}']")
            if labels and labels[0].text.strip():
                return labels[0].text.strip()
        parent_label = el.find_elements(By.XPATH, "./ancestor::label[1]")
        if parent_label and parent_label[0].text.strip():
            return parent_label[0].text.strip()
    except Exception:
        pass
    return ""


def _describe_web_element(driver, el) -> str | None:
    try:
        if not el.is_displayed():
            return None

        tag = el.tag_name
        text = (el.text or "").strip().replace("\n", " ")[:60]
        el_id = el.get_attribute("id") or ""
        name = el.get_attribute("name") or ""
        placeholder = el.get_attribute("placeholder") or ""
        aria_label = el.get_attribute("aria-label") or ""
        el_type = el.get_attribute("type") or ""
        autocomplete = el.get_attribute("autocomplete") or ""
        required = el.get_attribute("required") is not None
        label = _web_label_for(driver, el)

        extra = ""
        if tag == "select":
            try:
                sel = Select(el)
                options = [o.text.strip() for o in sel.options if o.text.strip()]
                selected = sel.first_selected_option.text.strip()
            except Exception:
                options, selected = [], ""
            extra = f" options=[{', '.join(options[:15])}] selected='{selected}'"
        elif el_type in ("checkbox", "radio"):
            try:
                checked = el.is_selected()
            except Exception:
                checked = False
            extra = f" checked={checked}"
        elif tag in ("input", "textarea"):
            try:
                current_value = el.get_attribute("value") or ""
            except Exception:
                current_value = ""
            if el_type == "password" and current_value:
                current_value = "*" * len(current_value)
            extra = f" current_value='{current_value}'"

        display_label = label or aria_label or placeholder or text or name or el_id or el_type
        if not display_label and not extra:
            return None

        meta_bits = []
        if el_type:
            meta_bits.append(f"type={el_type}")
        if placeholder and placeholder != display_label:
            meta_bits.append(f"placeholder='{placeholder}'")
        if autocomplete:
            meta_bits.append(f"autocomplete={autocomplete}")
        if required:
            meta_bits.append("required")
        meta = (" " + " ".join(meta_bits)) if meta_bits else ""

        return f"<{tag} id='{el_id}'{meta}>{display_label}</{tag}>{extra}"
    except Exception:
        return None


def get_web_state(driver, max_elements: int = 50):
    """Returns (state_text, ref_map) where ref_map maps 'E0','E1',... -> WebElement."""
    elements = driver.find_elements(By.XPATH, WEB_INTERACTIVE_XPATH)
    ref_map = {}
    lines = []
    idx = 0
    for el in elements:
        desc = _describe_web_element(driver, el)
        if not desc:
            continue
        ref = f"E{idx}"
        ref_map[ref] = el
        lines.append(f"[{ref}] {desc}")
        idx += 1
        if idx >= max_elements:
            break

    scroll_info = ""
    try:
        scroll_y = driver.execute_script("return window.scrollY")
        scroll_height = driver.execute_script("return document.body.scrollHeight")
        viewport_h = driver.execute_script("return window.innerHeight")
        remaining = max(0, scroll_height - (scroll_y + viewport_h))
        scroll_info = f"Scroll position: {scroll_y}px, viewport {viewport_h}px, ~{remaining}px of content below.\n"
    except Exception:
        pass

    state_text = (
        f"URL: {driver.current_url}\n"
        f"Title: {driver.title}\n"
        f"{scroll_info}"
        f"Interactive elements:\n" + "\n".join(lines)
    )
    return state_text, ref_map


def get_android_state(driver, max_elements: int = 50):
    """Same idea, but for an Appium/Android session using the UI hierarchy.
    Note: unlike web DOM, only elements CURRENTLY ON SCREEN appear here -
    the planner is instructed to scroll if what it needs isn't listed."""
    elements = driver.find_elements(By.XPATH, ANDROID_INTERACTIVE_XPATH)
    ref_map = {}
    lines = []
    idx = 0
    for el in elements:
        try:
            text = (el.text or "").strip()[:60]
            desc = el.get_attribute("content-desc") or ""
            resource_id = el.get_attribute("resource-id") or ""
            cls = el.get_attribute("className") or ""
            checkable = (el.get_attribute("checkable") == "true")
            checked = (el.get_attribute("checked") == "true")
            enabled = el.get_attribute("enabled")

            label = text or desc or resource_id
            if not label:
                continue

            extra = f" checkable={checkable} checked={checked}" if checkable else ""
            if enabled == "false":
                extra += " disabled"

            ref = f"E{idx}"
            ref_map[ref] = el
            lines.append(f"[{ref}] <{cls} id='{resource_id}'>{label}</{cls}>{extra}")
            idx += 1
            if idx >= max_elements:
                break
        except Exception:
            continue

    state_text = "Interactive elements (only what's currently on screen):\n" + "\n".join(lines)
    return state_text, ref_map


def get_state(driver, platform: str):
    if platform == "web":
        return get_web_state(driver)
    return get_android_state(driver)
