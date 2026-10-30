import httpx
import pytest

from app.services import sources

PAGE = b"""<html><head><script>var q = "Revenue for the quarter was $9 trillion";</script></head><body>
<nav>Home | Investors | Careers</nav>
<p>NVIDIA today reported revenue for the third quarter ended October 27, 2024, of $35.1&nbsp;billion,
up 17% from the previous quarter.</p></body></html>"""


def test_page_text_skips_scripts_and_navigation():
    text = sources.page_text(PAGE, "text/html")
    assert "$35.1" in text and "trillion" not in text and "Careers" not in text


def test_passages_keep_whole_sentences_within_quote_limits():
    text = " ".join(f"Sentence number {i} says something useful about batteries." for i in range(40))
    ps = sources.passages(text + " " + "x" * 1000)
    assert all(80 <= len(p) <= 480 for p in ps)
    assert all(p.endswith(".") for p in ps[:-3]) and " ".join(ps).count("Sentence number") == 40


def test_rank_puts_the_relevant_passage_first_and_skips_unrelated():
    docs = ["The weather in Paris was mild and sunny all week.",
            "Data center revenue grew 112% year over year to $30.8 billion.",
            "Gaming revenue fell 5% in the quarter."]
    assert sources.rank("How fast did data center revenue grow?", docs)[:2] == [1, 2]
    assert 0 not in sources.rank("data center revenue", docs)
    assert sources.rank("revenue", docs, [1, 1, 3])[0] == 2  # weight breaks near-ties toward stronger sources


async def test_fetch_returns_text_and_reasons():
    def serve(req):
        if req.url.path == "/gone":
            return httpx.Response(404)
        return httpx.Response(200, content=PAGE, headers={"content-type": "text/html"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
        texts, dropped = await sources.fetch(["https://a.com/ok", "https://a.com/gone", "https://a.com/ok"], client)
    assert list(texts) == ["https://a.com/ok"] and "$35.1" in texts["https://a.com/ok"]
    assert dropped == ["https://a.com/gone: HTTP 404"]


@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "http://localhost:27017/", "http://169.254.169.254/latest",
                                 "http://10.0.0.5/"])
async def test_internal_addresses_are_blocked(url):
    texts, dropped = await sources.fetch([url])
    assert texts == {} and dropped == [f"{url}: unreachable (Blocked)"]


def test_reference_lists_are_not_passages():
    refs = ('Smith, J. (2020). "Gene editing". Nature. 34 (8): 600-611. doi:10.1016/j.tig.2018.05.004. PMID 29908711. '
            'Retrieved 2026-05-20.')
    fact = "In October 2020, Charpentier and Doudna were awarded the Nobel Prize in Chemistry for their work."
    assert sources.passages(f"{fact} {refs}", target=60) == [fact]


LONG = b"<html><body><p>" + b"Data Center revenue was $89.0 billion, up 117% from a year ago. " * 20 + b"</p></body></html>"


@pytest.fixture
def rendered(monkeypatch):
    seen = []

    async def render(urls):
        seen.append(list(urls))
        return {u: LONG.decode() if "blocked" in u or "spa" in u else ValueError("HTTP 403 in browser") for u in urls}
    monkeypatch.setattr(sources.browser, "render", render)
    monkeypatch.setattr(sources.config, "BROWSER_FALLBACK", True)
    return seen


async def test_browser_rereads_refused_and_script_only_pages(rendered):
    def serve(req):
        path = req.url.path
        if path in ("/blocked", "/wall"):
            return httpx.Response(403)
        if path == "/gone":
            return httpx.Response(404)
        body = b"<html><body><div id=app></div></body></html>" if path == "/spa" else LONG
        return httpx.Response(200, content=body, headers={"content-type": "text/html"})

    urls = [f"https://a.com/{p}" for p in ("ok", "blocked", "wall", "gone", "spa")]
    async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
        texts, dropped = await sources.fetch(urls, client)
    assert sorted(rendered[0]) == ["https://a.com/blocked", "https://a.com/spa", "https://a.com/wall"]  # never 404s or good pages
    assert "$89.0" in texts["https://a.com/blocked"] and "$89.0" in texts["https://a.com/spa"]
    assert dropped == ["https://a.com/wall: HTTP 403; browser: HTTP 403 in browser", "https://a.com/gone: HTTP 404"]


async def test_no_browser_when_turned_off(rendered, monkeypatch):
    monkeypatch.setattr(sources.config, "BROWSER_FALLBACK", False)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(403))) as client:
        texts, dropped = await sources.fetch(["https://a.com/x"], client)
    assert rendered == [] and dropped == ["https://a.com/x: HTTP 403"]
