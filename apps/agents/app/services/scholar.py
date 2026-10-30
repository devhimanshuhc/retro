"""Research papers from OpenAlex (open scholarly index, free, no key, built for automated use). Gives real papers
with their abstracts, so research has peer-reviewed sources even when publisher sites block page fetches.
The abstract is the page text: quotes from it are copied by code, like any fetched page."""
import re

import httpx

API = "https://api.openalex.org/works"
STOP = {"what", "which", "when", "where", "does", "with", "from", "that", "this", "their", "have", "were", "they",
        "about", "into", "than", "them", "these", "those", "there", "been", "being", "will", "would", "could", "should"}


def terms(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 3 and t not in STOP}


def abstract(inverted: dict[str, list[int]] | None) -> str:
    """OpenAlex stores abstracts as {word: [positions]}; rebuild the text."""
    if not inverted:
        return ""
    words = [""] * (max(p for ps in inverted.values() for p in ps) + 1)
    for w, ps in inverted.items():
        for p in ps:
            words[p] = w
    return " ".join(w for w in words if w)


async def search(question: str, client: httpx.AsyncClient, limit: int = 3, since: int = 2018) -> list[dict]:
    """Up to `limit` relevant papers for a question: [{url, title, text, year}]. A paper counts as relevant when its
    title shares at least two content words with the question (the API's own ranking is too loose). Never raises:
    no papers is a normal answer."""
    params = {"search": question[:300], "per-page": 10,
              "filter": f"has_abstract:true,from_publication_date:{since}-01-01,type:article|preprint|review",
              "select": "id,doi,title,publication_year,abstract_inverted_index,primary_location"}
    try:
        r = await client.get(API, params=params, timeout=15)
        r.raise_for_status()
        works = r.json().get("results", [])
    except (httpx.HTTPError, ValueError):
        return []
    want, out = terms(question), []
    for w in works:
        title, text = w.get("title") or "", abstract(w.get("abstract_inverted_index"))
        if len(terms(title) & want) < 2 or len(text) < 200:
            continue
        url = w.get("doi") or ((w.get("primary_location") or {}).get("landing_page_url")) or w["id"]
        out.append({"url": url, "title": title, "text": text, "year": w.get("publication_year")})
        if len(out) == limit:
            break
    return out
