"""Headless-browser page fetch (Playwright + Chromium) for pages that only
show their content after JavaScript runs — event listings and organizer
sites built as single-page apps return an empty shell to a plain HTTP GET.

Used only as a fallback by `web_fetch.fetch(url, render_js=True)`, which
the Event Discovery Agent opts into. Returns the rendered HTML so the
existing JSON-LD / contact / AI extraction runs on it unchanged — this
module never extracts or invents anything itself.

Degrades gracefully: if Playwright or its Chromium build isn't installed,
or the page fails to load, `render` returns `None` and the caller keeps
whatever the plain fetch got.
"""

import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from backend.core.config import get_settings
from backend.core.ssrf_protection import validate_safe_url
from backend.services.social_agent.web_fetch import USER_AGENT

logger = logging.getLogger("social_agent.browser_fetch")

_PAGE_TIMEOUT_MS = 8_000
_NETWORK_IDLE_TIMEOUT_MS = 1_500

# Playwright's sync API refuses to run on a thread that has an asyncio loop
# (FastAPI/scheduler threads may), so every render runs on this dedicated
# worker. One worker also caps the agent at a single browser at a time.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="browser-fetch")
_playwright_instance = None
_browser_instance = None


def browser_fetch_enabled() -> bool:
    return get_settings().discovery_browser_fetch


def render(url: str) -> str | None:
    allow_dev = get_settings().environment.lower() != "production"
    try:
        url = validate_safe_url(url, allow_private_in_dev=allow_dev)
    except ValueError as exc:
        logger.warning("SSRF protection blocked browser render for %s: %s", url, exc)
        return None
    try:
        return _executor.submit(_render_in_browser, url).result(timeout=_PAGE_TIMEOUT_MS / 1000 * 3)
    except Exception as exc:
        logger.warning("Browser render failed for %s: %s", url, str(exc).splitlines()[0] if str(exc) else type(exc).__name__)
        return None


def _get_browser():
    global _playwright_instance, _browser_instance
    if sys.modules.get("playwright.sync_api") is None and "playwright.sync_api" in sys.modules:
        return None
    if _browser_instance is None or not _browser_instance.is_connected():
        try:
            from playwright.sync_api import sync_playwright
            if _playwright_instance is None:
                _playwright_instance = sync_playwright().start()
            _browser_instance = _playwright_instance.chromium.launch(headless=True)
        except Exception as exc:
            logger.info("Playwright or Chromium launch unavailable: %s", exc)
            return None
    return _browser_instance


def _render_in_browser(url: str) -> str | None:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    except (ImportError, AttributeError, TypeError):
        return None

    browser = _get_browser()
    if browser is None:
        return None

    context = None
    try:
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=_PAGE_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            return None
        except Exception:
            return None

        if response is None or response.status != 200:
            return None
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            return None
        try:
            page.wait_for_load_state("networkidle", timeout=_NETWORK_IDLE_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            pass  # pages with polling/analytics never go idle; use what has rendered
        return page.content()
    except Exception as exc:
        logger.warning("Browser render error for %s: %s", url, exc)
        return None
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
