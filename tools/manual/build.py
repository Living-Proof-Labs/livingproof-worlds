# SPDX-License-Identifier: Apache-2.0
"""Render canonical world documentation and native Task summaries.

Adapted from collaboration-guidelines v7.8.2 tools/manual/build.py (Apache-2.0).
"""

import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen

import yaml

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts/manual"
REPO = "https://github.com/Living-Proof-Labs/livingproof-worlds"
BASELINE = "v7.8.2"
BASELINE_SHA = "1470bd46deffd62d6badf568996225e56872258a"


def run(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def build():
    commit = os.environ.get("SOURCE_COMMIT") or run("git", "rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Expected an exact source commit")
    dirty_value = os.environ.get("SOURCE_DIRTY")
    if dirty_value is not None and dirty_value not in ("true", "false"):
        raise ValueError("SOURCE_DIRTY must be true or false")
    dirty = (
        dirty_value == "true"
        if dirty_value is not None
        else bool(run("git", "status", "--porcelain"))
    )
    if (OUT / "html").exists():
        shutil.rmtree(OUT / "html")
    source = OUT / "source"
    if source.exists():
        shutil.rmtree(source)
    source.mkdir(parents=True)
    paths = ["README.md", "AGENTS.md", "docs/manual.md"]
    paths += [str(p.relative_to(ROOT)) for p in sorted((ROOT / "worlds").rglob("*.md"))]
    mapping = {p: p.replace("README.md", "index.md") for p in paths}
    mapping["README.md"] = "guide.md"
    mapping["docs/manual.md"] = "index.md"
    record = {
        "source_commit": commit,
        "source_dirty": dirty,
        "guidelines_baseline": BASELINE,
        "guidelines_baseline_commit": BASELINE_SHA,
        "generator": "zensical==0.0.73",
        "workflow_run": (
            REPO + "/actions/runs/" + os.environ["GITHUB_RUN_ID"]
            if os.environ.get("GITHUB_RUN_ID")
            else None
        ),
        "sources": {},
    }
    source_link = REPO + "/tree/" + commit
    for path, destination in mapping.items():
        text = (ROOT / path).read_text()
        record["sources"][path] = hashlib.sha256(text.encode()).hexdigest()

        def rewrite(match, path=path, destination=destination):
            target = match[1]
            url = urlsplit(target)
            if url.scheme or url.netloc or not url.path or url.path.startswith("/"):
                return match[0]
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), url.path))
            if resolved in mapping:
                relative = posixpath.relpath(
                    mapping[resolved], posixpath.dirname(destination) or "."
                )
                return "](" + urlunsplit(("", "", relative, url.query, url.fragment)) + ")"
            if (
                resolved.startswith(("worlds/", "schema/"))
                and (ROOT / resolved).is_file()
                and Path(resolved).suffix in (".json", ".svg")
            ):
                relative = posixpath.relpath(resolved, posixpath.dirname(destination) or ".")
                return "](" + relative + ")"
            return (
                "]("
                + REPO
                + "/blob/"
                + commit
                + "/"
                + resolved
                + (("#" + url.fragment) if url.fragment else "")
                + ")"
            )

        text = re.sub(r"\]\(([^)\s]+)\)", rewrite, text)
        target = source / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        version = posixpath.relpath("version.md", posixpath.dirname(destination) or ".")
        license_path = REPO + "/blob/" + commit + "/LICENSE"
        text += (
            f"\n\n---\n\n[Documentation home](https://docs.livingprooflabs.com/) · "
            f"[Docs: development · {commit[:12]}]({source_link}) · "
            f"[Version and source]({version}) · [Help / report an issue]({REPO}/issues) · "
            f"[License]({license_path})\n"
        )
        target.write_text(text)
    tasks = [
        "# Contributor tasks",
        "",
        "Generated from native Task summaries; no task body is executed.",
        "",
    ]
    for taskfile, context in [
        ("Taskfile.yml", "Host: Docker and Task 3.54.0"),
        ("Taskfile.runtime.yml", "Prepared container: do not invoke host wrappers"),
    ]:
        tasks += ["## " + context, ""]
        task_data = json.loads(run("task", "-t", taskfile, "--list", "--json"))
        for task in task_data["tasks"]:
            tasks += [
                f"### {task['name']}",
                "",
                "```text",
                run("task", "-t", taskfile, "--summary", task["name"]),
                "```",
                "",
            ]
        record["sources"][taskfile] = hashlib.sha256((ROOT / taskfile).read_bytes()).hexdigest()
    (source / "tasks.md").write_text("\n".join(tasks))
    # Preserve raw contracts, world data and existing diagrams at their source paths.
    for folder in ("worlds", "schema"):
        for path in (ROOT / folder).rglob("*"):
            if path.is_file() and path.suffix in (".json", ".svg"):
                target = source / path.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
    lock = json.loads((ROOT / "docs-brand.lock.json").read_text())
    url = f"https://raw.githubusercontent.com/{lock['repository']}/{lock['commit']}/{lock['path']}"
    with urlopen(url, timeout=60) as response:
        brand = response.read()
    if hashlib.sha256(brand).hexdigest() != lock["sha256"]:
        raise ValueError("Documentation brand checksum mismatch")
    (source / "assets").mkdir()
    (source / "assets/brand.css").write_bytes(brand)
    record["brand"] = lock
    (source / "build.json").write_text(json.dumps(record, indent=2) + "\n")
    (source / "version.md").write_text(
        "# Version and source\n\nThis is development documentation, not a package release. "
        "Historical rendered manuals are not maintained; use the matching "
        f"[published source tag]({REPO}/tags) for an adopted release.\n\n"
        f"[Docs: development · {commit[:12]}]({source_link}); dirty checkout: **{str(dirty).lower()}**. "
        "A dirty preview has changes beyond that commit; source hashes below identify its inputs.\n\n"
        f"Guidelines and recipe: [{BASELINE}](https://github.com/Living-Proof-Labs/collaboration-guidelines/tree/{BASELINE}), resolved to `{BASELINE_SHA}`. "
        "This is a released guidance dependency, not the version of this development manual. "
        f"[Published world releases]({REPO}/releases) are separate.\n\n"
        "```json\n" + json.dumps(record, indent=2) + "\n```\n\n[Build record](build.json)\n"
    )
    config = yaml.safe_load((ROOT / "tools/manual/mkdocs.yml").read_text())
    config.update(
        docs_dir="source",
        site_dir="html",
        repo_url=source_link,
        repo_name=f"Source · dev {commit[:12]}",
    )
    (OUT / "mkdocs.yml").write_text(yaml.safe_dump(config, sort_keys=False))
    subprocess.run(
        [sys.executable, "-m", "zensical", "build", "--clean", "-f", str(OUT / "mkdocs.yml")],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    build()
