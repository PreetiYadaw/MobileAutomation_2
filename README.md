# AI UI Automation (Web + Android)

Give the agent one plain-English goal ("log in and add the first item to
cart") and it plans, locates elements, acts, and verifies each step by
itself — using a hybrid of real UI locators + a screenshot/vision fallback,
and fuzzy text matching + LLM judgment for verification.

## What changed in this version

- **The agent now reasons from DOM metadata, not just element text.** Every
  element the planner sees includes its label, placeholder, input type,
  autocomplete hint, current value, dropdown options, and checkbox/radio
  state - enough to decide what to type/select without ever looking at a
  screenshot.
- **Full action vocabulary**: `click`, `type`, `select` (dropdown), `toggle`
  (checkbox/radio), `submit`, `scroll` (up/down/left/right), `browser_back`,
  `browser_forward`, `refresh`, `verify`, `wait`, `finish`, `fail`.
- **Verification now reads actual field values from the DOM**, not just
  visible page text. This matters: a typed value in an `<input>` never shows
  up in the page's rendered text, and a password field is masked even if it
  did - so "does the password field contain X" was previously unanswerable
  from text alone. Now it's read directly from the DOM with certainty,
  which removes most of the remaining reliance on vision.
- **The planner is told to scroll before falling back to vision** - on
  native mobile apps especially, only on-screen elements are visible to it,
  so scrolling often surfaces the element it needs without ever taking a
  screenshot.
- DOM/text is trusted first, always. Vision (screenshot → LLM) only fires
  when a DOM ref lookup fails, or a fuzzy-match score lands in a genuine
  grey zone — and you can kill it entirely with `ENABLE_VISION_FALLBACK=false`
  for max speed/min cost.
- **Runs exactly once.** The planner's prompt checks action history and
  calls `finish` the moment the goal is satisfied, plus a hard repetition
  guard force-stops the run if the same action is proposed twice in a row.
- **Popups are dismissed automatically**, before every single step.
- **Async end-to-end.** LLM calls use async clients; blocking Selenium/Appium
  calls run on a background thread so the event loop never stalls.
- **Three LLM providers, chosen independently for text vs. vision**: Groq,
  Azure OpenAI, DeepSeek for planning; Groq or Azure for vision (DeepSeek
  has no vision model).

## How it works (architecture)

```
streamlit_app.py          <- UI: type a goal, click Run, watch steps live
config.py                 <- Settings class, reads everything from .env

app/
  llm/groq_client.py       <- calls Groq (planning model + vision model)
  automation/
    driver_manager.py      <- starts Selenium (web) or Appium (android) driver
    page_state.py           <- condenses DOM/UI tree into a short element list
    planner.py                <- asks LLM: "what's the ONE next action?"
    locator_engine.py          <- hybrid: use given element ref, else screenshot+vision
    action_executor.py          <- actually clicks/types/swipes
    verifier.py                   <- hybrid: fuzzy text match, else LLM+screenshot judgment
    popup_handler.py                <- auto-dismisses popups/permission dialogs each step
    agent.py                          <- async loop: dismiss -> plan -> locate -> act -> verify
  utils/screenshot.py       <- screenshot save/base64 helpers
```

The loop in `agent.py` runs up to `MAX_STEPS` times: each cycle it re-reads
the screen (so it stays correct even as the UI changes), asks the LLM for
the single next action, executes it, and verifies the result — then feeds
that outcome into the next cycle's history so the LLM knows what already
happened.

## 1. Install

```bash
cd mobile-ai-automation
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

You also need Google Chrome installed (Selenium drives it via
`webdriver-manager`, which downloads the matching chromedriver
automatically — no manual driver download needed).

## 2. Configure

```bash
cp .env.example .env
```

### Choosing your LLM provider(s)

There are **two independent toggles** in `.env`:

- `LLM_PROVIDER` — powers text/planning calls (deciding the next action).
  Set to `groq`, `azure`, or `deepseek` — whichever you want.
- `VISION_LLM_PROVIDER` — powers screenshot-understanding calls (the locator
  fallback + ambiguous verification). Set to `groq` or `azure` only —
  **DeepSeek's models can't see images**, so it's not a valid choice here.

You only need to fill in credentials for the provider(s) you actually pick.
For example, `LLM_PROVIDER=deepseek` + `VISION_LLM_PROVIDER=groq` needs both
`DEEPSEEK_API_KEY` and `GROQ_API_KEY` filled in, but no Azure fields.

- **Groq** — get a key from console.groq.com. `GROQ_MODEL` defaults to
  `openai/gpt-oss-20b` (text only — cannot see images, which is why it's
  never used for vision). `GROQ_VISION_MODEL` defaults to `qwen/qwen3.6-27b`
  (confirmed working for the vision calls).
- **Azure OpenAI** — needs `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`,
  and `AZURE_OPENAI_DEPLOYMENT` (your **deployment name** from Azure
  AI/OpenAI Studio, not the model name — e.g. deployment `my-gpt41`, not
  model `gpt-4.1`). If your deployment is GPT-4.1 (natively multimodal), the
  same deployment can serve both text and vision — leave
  `AZURE_OPENAI_VISION_DEPLOYMENT` blank and it'll reuse the main one.
- **DeepSeek** — needs `DEEPSEEK_API_KEY` only (`DEEPSEEK_BASE_URL` and
  `DEEPSEEK_MODEL` already default correctly). Text/planning only.

- `TARGET_URL` — defaults to `https://www.saucedemo.com`, a public demo
  e-commerce site built specifically for testing automation tools (has a
  login form, a cart, checkout flow — perfect for phase 1).

## 3. Run (Phase 1 — website)

```bash
streamlit run streamlit_app.py
```

In the browser tab that opens, try a goal like:

> Log in with username 'standard_user' and password 'secret_sauce', then
> add the first product to the cart and verify the cart badge shows 1.

Watch the step-by-step log: each step shows the JSON action the LLM chose,
whether verification passed (and by which method — fuzzy match or vision),
and a screenshot.

## 4. Move to Android (Phase 2 — do this now)

### Connect the phone
1. Phone: Settings → About Phone → tap "Build Number" 7 times → enables
   Developer Options.
2. Settings → Developer Options → turn on **USB Debugging**.
3. Plug the phone in via USB, accept the "Trust this computer?" popup.
4. Install **Android Platform Tools** (gives you `adb`) and run
   `adb devices` — confirm it shows as `device`, not `unauthorized`.
5. Install Node.js, then:
   ```bash
   npm install -g appium
   appium driver install uiautomator2
   ```
6. Start the Appium server (leave this running in its own terminal):
   ```bash
   appium
   ```
   It listens on `http://127.0.0.1:4723` by default — matches
   `APPIUM_SERVER_URL` in `.env`.

### Pick a first test target
Two good options to validate everything end-to-end before pointing this at
your own app:

**Option A — Calculator app (simplest, no APK needed, every phone has one).**
```env
PLATFORM=android
ANDROID_APP_PACKAGE=com.google.android.calculator
ANDROID_APP_ACTIVITY=com.android.calculator2.Calculator
```
(If that activity doesn't launch, find the real package/activity with the
app open on the phone: `adb shell dumpsys window | grep mCurrentFocus`.)
Try the goal: *"Compute 7 plus 5 and verify the result shows 12."*

**Option B — Chrome on the phone (reuses the exact same web goal you already
tested).** In `driver_manager.py`'s `_start_android`, instead of setting
`app_package`/`app_activity`, set:
```python
options.browser_name = "Chrome"
```
Leave `ANDROID_APP_PACKAGE` / `ANDROID_APP_ACTIVITY` blank in `.env`. This
drives the phone's actual Chrome browser — try the same
`TARGET_URL=https://www.saucedemo.com` goal from Phase 1.

**Option C — your own app.** Set `ANDROID_APP_PACKAGE` and
`ANDROID_APP_ACTIVITY` to your app's real values (same `adb shell dumpsys
window | grep mCurrentFocus` trick works with your app open).

### Run it
```bash
streamlit run streamlit_app.py
```
Everything else — planner, hybrid locator, hybrid verifier, popup dismissal,
the Streamlit UI — is unchanged between web and Android. That's the payoff
of building it this way.

### Android-specific notes
- `ANDROID_AUTO_GRANT_PERMISSIONS=true` (default) pre-grants runtime
  permissions (camera, location, notifications) at session start, so those
  system dialogs mostly never appear.
- The popup handler additionally tries `mobile: acceptAlert` each pass as a
  catch-all for anything that slips through.
- `page_state.py`'s Android XPath (`clickable='true' or long-clickable='true'
  or class contains EditText/Button`) is a reasonable default but some apps
  use custom views that won't match — widen it if the agent can't see an
  element it should.

## Notes / known limitations (read before you rely on this)

- This is a working starting point, not a hardened production framework.
- The vision-fallback coordinate detection is inherently approximate —
  expect it to need retries on visually cluttered screens. Turn it off
  entirely (`ENABLE_VISION_FALLBACK=false`) if your target is well-structured
  and you'd rather it fail loudly than guess coordinates.
- `page_state.py`'s XPath selectors are a reasonable default but you may
  need to widen/narrow them for a specific site or app.
- The popup dismisser is a fixed English label list (`accept`, `allow`,
  `close`, `got it`, etc. — see `popup_handler.py`). Extend `DISMISS_LABELS`
  for other languages or app-specific button text.
- The repetition guard stops the run if the same action is proposed twice in
  a row — this is deliberately conservative (better to stop early than loop
  forever), but a legitimate task that requires the identical action twice
  back-to-back (rare) would need the guard loosened in `agent.py`.
- There's no retry/backoff logic yet if the LLM API call itself fails —
  add that before running long unattended sessions.
- Cost control: each step makes 1 planning call, and only sometimes a
  vision call. Keep `MAX_STEPS` sane while you're testing.
