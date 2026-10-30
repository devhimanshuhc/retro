"""Fallback reader for public pages a plain HTTP fetch can't use: bot checks that answer 403/429 to non-browsers,
and pages whose text only appears after JavaScript runs. Headless Chromium, no logins, no forms, no clicks; every
request the page makes goes through the same public-address check as the plain fetch."""
import asyncio
import ipaddress
import logging

log = logging.getLogger("browser")
TIMEOUT_MS = 25_000
SKIP_TYPES = {"image", "media", "font", "stylesheet"}  # text only: faster, and fewer third-party requests


async def _public(host: str, cache: dict[str, bool]) -> bool:
    if host not in cache:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(host, 443)
            cache[host] = bool(infos) and all(ipaddress.ip_address(i[4][0]).is_global for i in infos)
        except OSError:
            cache[host] = False
    return cache[host]


async def render(urls: list[str], concurrency: int = 3) -> dict[str, str | Exception]:
    """{url: rendered HTML or the error}. One browser for the batch, at most `concurrency` pages at a time."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as e:  # optional: without playwright the plain fetch result stands
        return {u: e for u in urls}
    hosts: dict[str, bool] = {}
    gate = asyncio.Semaphore(concurrency)
    out: dict[str, str | Exception] = {}

    async def guard(route):
        req = route.request
        from urllib.parse import urlsplit
        host = urlsplit(req.url).hostname or ""
        if req.resource_type in SKIP_TYPES or not await _public(host, hosts):
            await route.abort()
        else:
            await route.continue_()

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch()
        except Exception as e:  # browser binary missing: `uv run playwright install chromium`
            log.warning("browser fallback unavailable: %r", e)
            return {u: e for u in urls}
        ctx = await browser.new_context(locale="en-US", java_script_enabled=True)
        await ctx.route("**/*", guard)

        async def one(url: str):
            async with gate:
                page = await ctx.new_page()
                try:
                    resp = await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
                    if resp is None or resp.status >= 400:
                        raise ValueError(f"HTTP {resp.status if resp else 'no response'} in browser")
                    try:  # let client-side rendering finish, but never wait long
                        await page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass
                    out[url] = await page.content()
                except Exception as e:
                    out[url] = e
                finally:
                    await page.close()

        try:
            await asyncio.gather(*(one(u) for u in urls))
        finally:
            await browser.close()
    return out
