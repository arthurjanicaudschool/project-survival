"""HTML extraction and claim grounding. Never execute publisher JavaScript."""

import re
from html.parser import HTMLParser
from hashlib import sha256


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = []
        self.text = []
        self.article = []
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in (
            "script",
            "style",
            "nav",
            "header",
            "footer",
            "noscript",
            "svg",
            "form",
        ):
            self.skip.append(tag)
        if tag in ("main", "article"):
            self.depth += 1

    def handle_endtag(self, tag):
        if tag in self.skip:
            self.skip = self.skip[: self.skip.index(tag)]
        if tag in ("main", "article"):
            self.depth = max(0, self.depth - 1)

    def handle_data(self, data):
        if not self.skip:
            self.text.append(data)
            if self.depth:
                self.article.append(data)


def extract(body, content_type="text/html"):
    if "html" in content_type:
        parser = TextExtractor()
        parser.feed(body)
        primary = " ".join(parser.article)
        body = primary if len(primary) > 250 else " ".join(parser.text)
    text = re.sub(r"\s+", " ", body).strip()
    words = len(text.split())
    junk = sum(
        text.count(v)
        for v in (
            "function(",
            "function (",
            "window.",
            "webpack",
            "this.default_",
            "var ",
        )
    )
    useful = (
        words >= 35
        and junk < 5
        and not re.search(
            r'^("use strict"|enable javascript|access denied)', text, re.I
        )
    )
    return {
        "excerpt": text[:6000] if useful else "",
        "quality": "READABLE" if useful else "UNUSABLE",
        "word_count": words,
        "content_hash": sha256(text.encode()).hexdigest(),
        "error": None if useful else "NO_USABLE_CONTENT",
    }


def verify_claims(actions, trace):
    excerpts = {}
    for t in trace:
        r = t.get("result") or {}
        if t.get("ok") and r.get("quality") == "READABLE":
            excerpts[r["url"]] = r["excerpt"]
    checked = []
    for action in actions:
        for c in action.claims:
            normalized = lambda s: re.sub(r"\s+", " ", s).strip().casefold()
            grounded = c.url in excerpts and normalized(c.quote) in normalized(
                excerpts[c.url]
            )
            checked.append(
                {
                    "url": c.url,
                    "claim": c.claim,
                    "quote": c.quote,
                    "quote_verified": grounded,
                    "limitation": "Exact excerpt match; semantic entailment and causality are not automatically proven.",
                }
            )
    return checked
