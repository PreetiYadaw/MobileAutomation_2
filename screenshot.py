import base64
import time
from pathlib import Path
from config import settings


def take_screenshot(driver, label: str = "step") -> Path:
    """Save a PNG screenshot to logs/screenshots and return its path."""
    filename = f"{int(time.time() * 1000)}_{label}.png"
    path = settings.screenshot_dir / filename
    driver.save_screenshot(str(path))
    return path


def screenshot_to_b64(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
