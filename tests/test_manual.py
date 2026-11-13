# SPDX-License-Identifier: Apache-2.0
"""Checks for an explicitly built manual; ordinary world tests need no site."""

import importlib.util
import json
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
