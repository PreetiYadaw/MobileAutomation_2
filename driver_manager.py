"""
Creates and owns the underlying driver.

Phase 1 (now): PLATFORM=web -> Selenium Chrome driver.
Phase 2 (later): PLATFORM=android -> Appium driver talking to your phone.

Both drivers speak (mostly) the same WebDriver API, which is why the rest
of the app (locator_engine, action_executor) can stay almost identical
between web and mobile.
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

from config import settings


class DriverManager:
    def __init__(self):
        self.driver = None

    def start(self):
        if settings.platform == "web":
            self.driver = self._start_web()
        elif settings.platform == "android":
            self.driver = self._start_android()
        else:
            raise ValueError(f"Unsupported platform: {settings.platform}")
        return self.driver

    def _start_web(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        # Uncomment for headless runs:
        # options.add_argument("--headless=new")
        driver = webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()),
            options=options,
        )
        driver.get(settings.target_url)
        return driver

    def _start_android(self):
        # Imported lazily so Appium-Python-Client isn't required for web-only runs.
        from appium import webdriver as appium_webdriver
        from appium.options.android import UiAutomator2Options

        options = UiAutomator2Options()
        options.device_name = settings.android_device_name
        options.automation_name = "UiAutomator2"
        options.platform_name = "Android"
        options.auto_grant_permissions = settings.android_auto_grant_permissions
        if settings.android_app_package:
            options.app_package = settings.android_app_package
        if settings.android_app_activity:
            options.app_activity = settings.android_app_activity
        # If you'd rather launch the phone's Chrome browser instead of a native
        # app, set options.browser_name = "Chrome" and skip app_package/activity.

        driver = appium_webdriver.Remote(settings.appium_server_url, options=options)
        return driver

    def quit(self):
        if self.driver:
            self.driver.quit()
