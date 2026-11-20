# SPDX-License-Identifier: Apache-2.0
"""Checks for an explicitly built manual; ordinary world tests need no site."""

import importlib.util
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "artifacts/manual/html"
pytestmark = pytest.mark.skipif(not SITE.exists(), reason="Build with task manual:verify first")
spec = importlib.util.spec_from_file_location("manual_links", ROOT / "tools/manual/links.py")
links = importlib.util.module_from_spec(spec)
spec.loader.exec_module(links)


def test_local_links_and_fragments():
    links.check_links(SITE)


def test_brand_on_every_page():
    pages = list(SITE.rglob("*.html"))
    assert len(pages) >= 7
    for page in pages:
        text = page.read_text()
        assert "assets/brand.css" in text, page
        assert 'data-md-color-primary="indigo"' not in text, page


def test_source_identity_and_task_reference():
    record = json.loads((SITE / "build.json").read_text())
    assert len(record["source_commit"]) == 40
    assert record["brand"] == json.loads((ROOT / "docs-brand.lock.json").read_text())
    assert record["source_commit"] in (SITE / "version.html").read_text()
    tasks = (SITE / "tasks.html").read_text()
    assert "manual:verify" in tasks
    assert "Prepared container" in tasks


def test_released_assets_are_preserved():
    for folder in ("worlds", "schema"):
        for path in (ROOT / folder).rglob("*"):
            if path.is_file() and path.suffix in (".svg", ".json"):
                assert (SITE / path.relative_to(ROOT)).read_bytes() == path.read_bytes()


class VisibleHTMLParser(HTMLParser):
    """Ignore non-rendered HTML; CSS visibility is checked in the browser tests."""

    VOID_TAGS = (
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    )

    def __init__(self):
        super().__init__()
        self.hidden_elements = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        style = re.sub(r"\s+", "", attrs.get("style", "").lower())
        hidden = (
            tag in ("script", "style", "template")
            or "hidden" in attrs
            or "display:none" in style
            or "visibility:hidden" in style
        )
        if tag not in self.VOID_TAGS:
            self.hidden_elements.append((tag, hidden))

    def handle_endtag(self, tag):
        for index in range(len(self.hidden_elements) - 1, -1, -1):
            if self.hidden_elements[index][0] == tag:
                del self.hidden_elements[index:]
                break


def commit_pattern(commit):
    """Match this build's full or abbreviated identity, not arbitrary hex words."""
    prefixes = "|".join(re.escape(commit[:length]) for length in range(7, 41))
    return re.compile(r"\b(?:" + prefixes + r")\b", re.IGNORECASE)


class HeaderFooterInspector(VisibleHTMLParser):
    def __init__(self):
        super().__init__()
        self.in_source_repo = 0
        self.in_footer = 0
        self.in_link = False
        self.link_attrs = {}
        self.link_text = []
        self.source_repos = []
        self.source_links = []
        self.docs_links = []
        self.footer_text = []
        self.visible_text = []

    def handle_starttag(self, tag, attrs):
        super().handle_starttag(tag, attrs)
        attr_dict = dict(attrs)
        classes = set(attr_dict.get("class", "").split())
        if tag not in self.VOID_TAGS and (
            "md-source__repository" in classes or self.in_source_repo
        ):
            self.in_source_repo += 1
        if tag not in self.VOID_TAGS and (tag == "footer" or self.in_footer):
            self.in_footer += 1
        if tag == "a" and "md-source" in classes:
            self.source_links.append(attr_dict.get("href", ""))
        if tag == "a":
            self.in_link = True
            self.link_attrs = attr_dict
            self.link_text = []

    def handle_endtag(self, tag):
        if tag in self.VOID_TAGS:
            return
        super().handle_endtag(tag)
        if self.in_source_repo:
            self.in_source_repo -= 1
        if self.in_footer:
            self.in_footer -= 1
        if tag == "a" and self.in_link:
            text = "".join(self.link_text).strip()
            if text.startswith("Docs: development"):
                self.docs_links.append(
                    (text, self.link_attrs.get("href", ""), self.link_attrs.get("title", ""))
                )
            self.in_link = False

    def handle_data(self, data):
        if any(hidden for _, hidden in self.hidden_elements):
            return
        self.visible_text.append(data)
        if self.in_source_repo:
            self.source_repos.append(data)
        if self.in_footer:
            self.footer_text.append(data)
        if self.in_link:
            self.link_text.append(data)


def test_no_sha_in_header_or_footer_visible_text():
    record = json.loads((SITE / "build.json").read_text())
    commit = record["source_commit"]
    sha_pattern = commit_pattern(commit)
    for path in SITE.rglob("*.html"):
        inspector = HeaderFooterInspector()
        inspector.feed(path.read_text())
        repo_text = "".join(inspector.source_repos).strip()
        assert "Source · development" in repo_text, path
        assert not sha_pattern.search(repo_text), (path, repo_text)
        assert any(commit in href for href in inspector.source_links), path
        footer_text = " ".join(inspector.footer_text)
        assert not sha_pattern.search(footer_text), (path, footer_text)
        for text, href, title in inspector.docs_links:
            assert text == "Docs: development", (path, text)
            assert not sha_pattern.search(text), (path, text)
            assert commit in href, (path, href)
            assert commit in title, (path, title)
        if path.name != "version.html":
            visible = " ".join(inspector.visible_text)
            assert not sha_pattern.search(visible), (path, visible)


@pytest.mark.parametrize("length", [7, 12, 40])
def test_visible_commit_identity_is_detected(length):
    commit = "a1b2c3d4e5f6789012345678901234567890abcdef"
    inspector = HeaderFooterInspector()
    inspector.feed(f"<footer>Docs: development · {commit[:length]}</footer>")
    assert commit_pattern(commit).search(" ".join(inspector.footer_text))


@pytest.mark.parametrize(
    "wrapper",
    [
        "<span hidden><em>{sha}</em><br></span>",
        '<span style="display: none">{sha}</span>',
        '<span style="visibility: hidden">{sha}</span>',
        "<script>{sha}</script>",
        "<style>{sha}</style>",
        "<template>{sha}</template>",
    ],
)
def test_hidden_provenance_and_ordinary_words_are_not_commit_identity(wrapper):
    commit = "a1b2c3d4e5f6789012345678901234567890abcdef"
    inspector = HeaderFooterInspector()
    inspector.feed(
        "<footer>defaced "
        + wrapper.format(sha=commit)
        + f'<a href="https://github.com/example/repo/tree/{commit}" title="{commit}">'
        + "Docs: development</a> after</footer>"
    )
    visible = " ".join(inspector.visible_text)
    assert "defaced" in visible and "after" in visible
    assert not commit_pattern(commit).search(visible)
    assert inspector.docs_links == [
        ("Docs: development", f"https://github.com/example/repo/tree/{commit}", commit)
    ]
