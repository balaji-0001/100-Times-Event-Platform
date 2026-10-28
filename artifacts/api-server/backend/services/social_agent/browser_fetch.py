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
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from backend.core.config import get_settings
from backend.core.ssrf_protection import validate_safe_url
from backend.services.social_agent.web_fetch import USER_AGENT

logger = logging.getLogger("social_agent.browser_fetch")

_PAGE_TIMEOUT_MS = 8_000
_NETWORK_IDLE_TIMEOUT_MS = 1_500
# Organizer lookups (`for_contacts=True`): contact blocks are often a lazily
# loaded footer or a widget filled in after load, so scroll down and give
# mailto/tel links a moment to appear.
_CONTACT_SELECTOR = 'a[href^="mailto:"], a[href^="tel:"], [data-cfemail], a[href*="email-protection"]'
_CONTACT_WAIT_MS = 2_500

# Playwright's sync API refuses to run on a thread that has an asyncio loop
# (FastAPI/scheduler threads may), so every render runs on these dedicated
# workers. Each worker thread owns its own Playwright + browser (the sync API
# is single-threaded), so at most _RENDER_WORKERS browsers exist at a time.
_RENDER_WORKERS = 2
_executor = ThreadPoolExecutor(max_workers=_RENDER_WORKERS, thread_name_prefix="browser-fetch")
_thread_state = threading.local()
_queue_lock = threading.Lock()
_queued_renders = 0


def browser_fetch_enabled() -> bool:
    return get_settings().discovery_browser_fetch


def busy() -> bool:
    """True when every render worker is busy and as many renders again are
    waiting — callers with an optional render (the organizer lookup's
    fallback) should skip it rather than queue behind them."""
    with _queue_lock:
        return _queued_renders >= 2 * _RENDER_WORKERS


def render(url: str, for_contacts: bool = False) -> str | None:
    global _queued_renders
    allow_dev = get_settings().environment.lower() != "production"
    try:
        url = validate_safe_url(url, allow_private_in_dev=allow_dev)
    except ValueError as exc:
        logger.warning("SSRF protection blocked browser render for %s: %s", url, exc)
        return None
    # Each render keeps the same per-page bound (3x the page timeout), but time
    # spent waiting behind other queued renders no longer counts against it.
    with _queue_lock:
        _queued_renders += 1
        rounds_ahead = (_queued_renders - 1) // _RENDER_WORKERS
    try:
        return _executor.submit(_render_in_browser, url, for_contacts).result(timeout=_PAGE_TIMEOUT_MS / 1000 * 3 * (rounds_ahead + 1))
    except Exception as exc:
        logger.warning("Browser render failed for %s: %s", url, str(exc).splitlines()[0] if str(exc) else type(exc).__name__)
        return None
    finally:
        with _queue_lock:
            _queued_renders -= 1


def _get_browser():
    if sys.modules.get("playwright.sync_api") is None and "playwright.sync_api" in sys.modules:
        return None
    browser = getattr(_thread_state, "browser", None)
    if browser is None or not browser.is_connected():
        try:
            from playwright.sync_api import sync_playwright
            if getattr(_thread_state, "playwright", None) is None:
                _thread_state.playwright = sync_playwright().start()
            _thread_state.browser = _thread_state.playwright.chromium.launch(headless=True)
        except Exception as exc:
            logger.info("Playwright or Chromium launch unavailable: %s", exc)
            return None
    return _thread_state.browser


def _render_in_browser(url: str, for_contacts: bool = False) -> str | None:
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
        if for_contacts:
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_selector(_CONTACT_SELECTOR, state="attached", timeout=_CONTACT_WAIT_MS)
            except Exception:
                pass  # no contact links appeared: the rendered page is still worth reading
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
