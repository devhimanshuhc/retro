"""Retrieval for research (RAG without embeddings): fetch candidate pages, split them into passages, and rank the
passages against each question with BM25. The LLM then sees only the top passages, and every quote in a report is
a passage copied by code from a page we fetched, so a source can't be invented or misquoted.
"""
import asyncio
import io
import ipaddress
import math
import re
import unicodedata
from collections import Counter
from html.parser import HTMLParser

import httpx
from pypdf import PdfReader

import config
from app.services import browser

MAX_BYTES = 15_000_000
MIN_TEXT = 600  # less text than this from a page usually means it renders in JavaScript
BROWSER_RETRY = ("HTTP 403", "HTTP 429")  # refusals a real browser often gets past (bot checks)
HEADERS = {"User-Agent": config.FETCH_USER_AGENT, "Accept-Language": "en"}


class Blocked(httpx.RequestError):
    pass


async def _public_only(request: httpx.Request) -> None:
    """URLs come from an LLM that reads untrusted pages: never let one point the worker at an internal address.
    Runs on every hop, so redirects are checked too. shortcut: DNS rebinding isn't covered; pin IPs if exposed."""
    infos = await asyncio.get_running_loop().getaddrinfo(request.url.host, request.url.port or 443)
    if not infos or any(not ipaddress.ip_address(i[4][0]).is_global for i in infos):
        raise Blocked(f"non-public address {request.url.host}", request=request)


IDENTIFY = ("sec.gov",)  # hosts that require a contact address from automated clients


async def _identify(request: httpx.Request) -> None:
    """SEC EDGAR blocks anonymous automated requests and asks for "<name> <email>". Only those hosts get the
    contact address; every other site sees the ordinary user agent."""
    host = request.url.host
    if config.CONTACT_EMAIL and any(host == h or host.endswith("." + h) for h in IDENTIFY):
        request.headers["User-Agent"] = f"Retro {config.CONTACT_EMAIL}"


# Source kinds decided by the site, not by the LLM's guess: official hosts are primary, scholarly hosts are papers,
# and aggregators that repackage others' numbers are news even when they look official.
PRIMARY = re.compile(r"(\.gov|\.gov\.\w\w|\.mil|europa\.eu|\.int)$|^(investors?|ir|newsroom|press)\.")
PAPER = re.compile(r"(^|\.)(arxiv\.org|doi\.org|nature\.com|science\.org|sciencedirect\.com|springer\.com|"
                   r"wiley\.com|ieee\.org|acm\.org|ncbi\.nlm\.nih\.gov|ssrn\.com|biorxiv\.org|medrxiv\.org|"
                   r"openalex\.org|zenodo\.org|acs\.org|rsc\.org|cell\.com|thelancet\.com|nejm\.org|"
                   r"jamanetwork\.com|plos\.org|frontiersin\.org|mdpi\.com)$")
AGGREGATOR = re.compile(r"(^|\.)(marketbeat|yahoo|seekingalpha|investing|fool|zacks|benzinga|stocktitan|tipranks|"
                        r"macrotrends|wikipedia|medium|substack)\.")


def kind_of(url: str, guess: str) -> str:
    """The kind of a source by its site; the LLM's guess only where the site says nothing."""
    host = (httpx.URL(url).host or "").removeprefix("www.")
    if PAPER.search(host):
        return "paper"
    if PRIMARY.search(host):
        return "primary"
    if AGGREGATOR.search(host + ".") and guess in ("primary", "paper"):
        return "news"
    return guess


class _Text(HTMLParser):
    SKIP = ("script", "style", "noscript", "template", "nav", "header", "footer")

    def __init__(self):
        super().__init__()
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        self._skip += tag in self.SKIP

    def handle_endtag(self, tag):
        self._skip -= tag in self.SKIP and self._skip > 0

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def page_text(body: bytes, content_type: str, pages: int = 60) -> str:
    if "pdf" in content_type or body[:5] == b"%PDF-":
        return " ".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(body)).pages[:pages])
    parser = _Text()
    parser.feed(body.decode("utf-8", errors="replace"))
    return " ".join(parser.parts)


async def _fetch_one(client: httpx.AsyncClient, url: str) -> str:
    """The page's text, or raises ValueError with why it can't be used."""
    try:
        r = await client.get(url)
    except (httpx.HTTPError, OSError) as e:  # OSError: DNS failure in the address check
        raise ValueError(f"unreachable ({type(e).__name__})") from e
    if r.status_code >= 400:
        raise ValueError(f"HTTP {r.status_code}")
    if len(r.content) > MAX_BYTES:
        raise ValueError("too large")
    try:
        return page_text(r.content, r.headers.get("content-type", ""))
    except Exception as e:  # corrupt PDF, odd encoding
        raise ValueError(f"unreadable ({type(e).__name__})") from e


async def fetch(urls, client: httpx.AsyncClient | None = None) -> tuple[dict[str, str], list[str]]:
    """Fetch pages concurrently. Returns ({url: text}, ["<url>: <why it was dropped>"])."""
    own = client is None
    client = client or httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=20,
                                         event_hooks={"request": [_public_only, _identify]})
    urls = list(dict.fromkeys(urls))
    try:
        results = await asyncio.gather(*(_fetch_one(client, u) for u in urls), return_exceptions=True)
        # one retry for pages that couldn't be reached at all: a brief network blip once dropped 13 of 14 pages
        again = [i for i, r in enumerate(results) if isinstance(r, ValueError) and str(r).startswith("unreachable")]
        if again:
            await asyncio.sleep(1)
            for i, r in zip(again, await asyncio.gather(*(_fetch_one(client, urls[i]) for i in again), return_exceptions=True)):
                results[i] = r
    finally:
        if own:
            await client.aclose()
    for r in results:
        if isinstance(r, BaseException) and not isinstance(r, ValueError):
            raise r  # a bug, not a bad page
    texts = {u: r for u, r in zip(urls, results) if isinstance(r, str)}
    failed = {u: str(r) for u, r in zip(urls, results) if isinstance(r, ValueError)}
    # Second chance in a real browser: pages refused to a plain fetch, and pages with almost no text (JS-rendered)
    refused = [u for u, why in failed.items() if why in BROWSER_RETRY]
    thin = [u for u, t in texts.items() if len(t.strip()) < MIN_TEXT]
    if config.BROWSER_FALLBACK and (refused or thin):
        for u, html in (await browser.render(refused + thin)).items():
            text = page_text(html.encode(), "text/html").strip() if isinstance(html, str) else ""
            if u in failed:
                if len(text) >= 200:
                    texts[u] = text
                    del failed[u]
                else:
                    failed[u] += f"; browser: {html if isinstance(html, Exception) else 'too little text'}"[:200]
            elif len(text) > len(texts[u].strip()):  # keep whichever read found more
                texts[u] = text
    return texts, [f"{u}: {why}" for u, why in failed.items()]


# Bibliography and page-chrome markers: reference lists are full of topic words but state no facts.
_REFS = re.compile(r"\b(?:doi:?\s*10\.|pmid|isbn|issn|s2cid|bibcode|archived from|retrieved \d|skip to main content)", re.I)


def passages(text: str, target: int = 240, limit: int = 480) -> list[str]:
    """Split page text into passages of whole sentences, about `target` chars, never over `limit`
    (so each fits Source.quote). Short scraps (menus, captions) are dropped."""
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip())
    out, cur = [], ""
    for s in sentences:
        while len(s) > limit:  # no sentence breaks (tables, lists): cut on a word boundary
            cut = s.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            out.append(s[:cut])
            s = s[cut:].strip()
        if cur and len(cur) + 1 + len(s) > limit:
            out.append(cur)
            cur = ""
        cur = f"{cur} {s}".strip()
        if len(cur) >= target:
            out.append(cur)
            cur = ""
    out.append(cur)
    return [p for p in out if len(p) >= 80 and not _REFS.search(p)]


def _terms(text: str) -> list[str]:
    return re.sub(r"[^\w%$]+", " ", unicodedata.normalize("NFKC", text).lower()).split()


def rank(query: str, docs: list[str], weights: list[float] | None = None, k1: float = 1.5, b: float = 0.75) -> list[int]:
    """Indexes of `docs` by BM25 relevance to `query` (times each doc's weight), best first;
    docs sharing no term with it are left out."""
    toks = [_terms(d) for d in docs]
    if not toks:
        return []
    avg = sum(map(len, toks)) / len(toks) or 1
    df = Counter(t for ts in toks for t in set(ts))
    q = set(_terms(query))
    scores = []
    for i, ts in enumerate(toks):
        tf = Counter(ts)
        s = sum(math.log(1 + (len(toks) - df[t] + 0.5) / (df[t] + 0.5))
                * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(ts) / avg)) for t in q if tf[t])
        if s > 0:
            scores.append((s * (weights[i] if weights else 1), i))
    return [i for _, i in sorted(scores, key=lambda x: -x[0])]
