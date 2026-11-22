# SPDX-License-Identifier: Apache-2.0
"""A workflow that reads current main at git/ref/heads/main must send the workflow token.

An anonymous call shares the runner rate limit, fails with HTTP 403, and leaves
the published site on the previous release. ``gh api`` is authenticated when
``GH_TOKEN`` or ``GITHUB_TOKEN`` is ``${{ github.token }}``. ``urllib`` must send
``Authorization: Bearer`` on the request. ``contents: read`` is enough; the
deploy job must not gain ``contents: write``.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
FRESHNESS = "git/ref/heads/main"
TOKEN_VALUE = re.compile(r"\$\{\{\s*(?:github\.token|secrets\.GITHUB_TOKEN)\s*\}\}")
DIRECT_HTTP = re.compile(
    r"urlopen|urllib\.request|requests\.(?:get|post|request)"
    r"|(?:^|[^\w])curl\s|http\.client|\bfetch\("
)
GH_API = re.compile(r"\bgh\s+api\b")
EXPECTED_SHA = "a" * 40
BLOCK_SCALARS = {"|", ">", "|-", ">-", "|+", ">+"}

UNAUTHENTICATED = """\
jobs:
  deploy:
    permissions:
      pages: write
      id-token: write
    steps:
      - name: Check current main inside deployment lock
        env:
          EXPECTED_SHA: abcdef
        run: |
          python - <<'PYCODE'
          import json, os, urllib.request
          url = 'https://api.github.com/repos/example/repo/git/ref/heads/main'
          with urllib.request.urlopen(url, timeout=30) as response:
              current = json.load(response)['object']['sha']
          PYCODE
"""

TOKEN_PRESENT_BUT_UNUSED = """\
jobs:
  deploy:
    permissions:
      contents: read
    steps:
      - name: Check current main
        env:
          GITHUB_TOKEN: ${{ github.token }}
        run: |
          python - <<'PYCODE'
          import urllib.request
          url = 'https://api.github.com/repos/example/repo/git/ref/heads/main'
          urllib.request.urlopen(url)
          PYCODE
"""

GH_WITHOUT_TOKEN = """\
permissions:
  contents: read
jobs:
  deploy:
    steps:
      - name: Require current main
        run: |
          current=$(gh api repos/example/repo/git/ref/heads/main --jq .object.sha)
          test "$current" = "$GITHUB_SHA"
"""

AUTHENTICATED_GH = """\
permissions:
  contents: read
jobs:
  deploy:
    permissions:
      contents: read
    steps:
      - name: Require current main
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          ref="repos/${GITHUB_REPOSITORY}/git/ref/heads/main"
          current=$(gh api "$ref" --jq .object.sha)
          test "$current" = "$GITHUB_SHA"
"""

AUTHENTICATED_URLLIB = """\
jobs:
  deploy:
    permissions:
      contents: read
      pages: write
      id-token: write
    steps:
      - name: Require current main
        env:
          GITHUB_TOKEN: ${{ github.token }}
        run: |
          python - <<'PYCODE'
          import json, os, urllib.request
          token = os.environ["GITHUB_TOKEN"]
          repo = os.environ["GITHUB_REPOSITORY"]
          url = f"https://api.github.com/repos/{repo}/git/ref/heads/main"
          request = urllib.request.Request(
              url,
              headers={"Authorization": f"Bearer {token}"},
          )
          with urllib.request.urlopen(request, timeout=30) as response:
              current = json.load(response)["object"]["sha"]
          PYCODE
"""

JOB_ENV_TOKEN = """\
jobs:
  deploy:
    permissions:
      contents: read
    env:
      GH_TOKEN: ${{ github.token }}
    steps:
      - name: Require current main
        run: |
          current=$(gh api repos/example/repo/git/ref/heads/main --jq .object.sha)
          test "$current" = "$GITHUB_SHA"
"""

FAKE_GH = """\
#!/bin/sh
token="${GH_TOKEN:-${GITHUB_TOKEN:-}}"
if [ -z "$token" ]; then
  echo "gh: unauthenticated" >&2
  printf 'authenticated=no\\n' > "$GH_CAPTURE"
  exit 4
fi
printf 'authenticated=yes\\nargs=%s\\n' "$*" > "$GH_CAPTURE"
if [ "${GH_STATUS:-0}" != 0 ]; then
  echo "HTTP Error ${GH_STATUS}: rate limit exceeded" >&2
  exit 1
fi
printf '%s\\n' "${REMOTE_SHA-}"
"""


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _strip_value(value: str) -> str:
    value = re.sub(r"\s+#.*$", "", value.strip())
    if value[:1] in {"'", '"'}:
        value = value[1:]
    if value[-1:] in {"'", '"'}:
        value = value[:-1]
    return value


def _envs_at(lines: list[str], env_indent: int) -> list[dict[str, str]]:
    found = []
    if env_indent == 0:
        env_re = re.compile(r"^env:\s*$")
    else:
        env_re = re.compile(rf"^ {{{env_indent}}}env:\s*$")
    for index, line in enumerate(lines):
        if not env_re.match(line):
            continue
        for inner in lines[index + 1 :]:
            if not inner.strip() or inner.lstrip().startswith("#"):
                continue
            indent = _indent(inner)
            if indent <= env_indent:
                break
            match = re.match(r"^ +([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", inner)
            if match and indent == env_indent + 2:
                found.append({"name": match.group(1), "value": _strip_value(match.group(2))})
    return found


def _permission_block(lines: list[str], block_indent: int) -> dict[str, str] | None:
    if block_indent == 0:
        pattern = re.compile(r"^permissions:\s*(.*)$")
    else:
        pattern = re.compile(rf"^ {{{block_indent}}}permissions:\s*(.*)$")
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if not match:
            continue
        inline = _strip_value(match.group(1))
        if inline and inline not in BLOCK_SCALARS:
            return {"_scalar": inline}
        block: dict[str, str] = {}
        for inner in lines[index + 1 :]:
            if not inner.strip() or inner.lstrip().startswith("#"):
                continue
            indent = _indent(inner)
            if indent <= block_indent:
                break
            key = re.match(r"^ +([\w-]+):\s*(.*)$", inner)
            if key and indent == block_indent + 2:
                block[key.group(1)] = _strip_value(key.group(2))
        return block
    return None


def _extract_jobs(text: str) -> list[dict[str, object]]:
    jobs: list[dict[str, object]] = []
    in_jobs = False
    current: dict[str, object] | None = None
    for line in text.splitlines():
        if re.match(r"^jobs:\s*$", line):
            in_jobs = True
            continue
        if not in_jobs:
            continue
        if line.strip() and _indent(line) == 0:
            break
        if re.match(r"^  [\w-]+:\s*$", line):
            if current:
                jobs.append(current)
            current = {"name": line.strip()[:-1], "lines": [line]}
            continue
        if current:
            lines = current["lines"]
            assert isinstance(lines, list)
            lines.append(line)
    if current:
        jobs.append(current)
    return jobs


def _extract_steps(job_lines: list[str]) -> list[list[str]]:
    steps: list[list[str]] = []
    in_steps = False
    current: list[str] | None = None
    for line in job_lines:
        if re.match(r"^    steps:\s*$", line):
            in_steps = True
            continue
        if not in_steps:
            continue
        if line.strip() and _indent(line) <= 4:
            break
        if re.match(r"^      - ", line):
            if current is not None:
                steps.append(current)
            current = [line]
            continue
        if current is not None:
            current.append(line)
    if current is not None:
        steps.append(current)
    return steps


def _run_script(step_lines: list[str]) -> str:
    scripts = []
    for index, line in enumerate(step_lines):
        match = re.match(r"^( +)run:\s*(.*)$", line)
        if not match:
            continue
        indent = len(match.group(1))
        rest = match.group(2).strip()
        if rest in BLOCK_SCALARS:
            body = []
            for inner in step_lines[index + 1 :]:
                if not inner.strip():
                    body.append("")
                    continue
                if _indent(inner) <= indent:
                    break
                body.append(inner)
            scripts.append("\n".join(body))
        else:
            scripts.append(_strip_value(rest))
    return "\n".join(scripts)


def _token_entries(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        entry
        for entry in entries
        if entry["name"] in {"GH_TOKEN", "GITHUB_TOKEN"} and TOKEN_VALUE.search(entry["value"])
    ]


def _sends_bearer(script: str, token_names: list[str]) -> bool:
    if "Authorization" not in script or "Bearer" not in script:
        return False
    return any(name in script for name in token_names)


def _contents(job_lines: list[str], workflow_text: str) -> str | None:
    job = _permission_block(job_lines, 4)
    if job is not None:
        return job.get("contents")
    workflow = _permission_block(workflow_text.splitlines(), 0)
    if workflow is None:
        return None
    return workflow.get("contents")


def freshness_problems(filename: str, text: str) -> list[str]:
    """Problems for one workflow. An empty list means every freshness read is authenticated."""
    problems = []
    lines = text.splitlines()
    workflow_env = _token_entries(_envs_at(lines, 0))
    for job in _extract_jobs(text):
        job_lines = job["lines"]
        assert isinstance(job_lines, list)
        job_env = _token_entries(_envs_at(job_lines, 4))
        for step in _extract_steps(job_lines):
            step_text = "\n".join(step)
            if FRESHNESS not in step_text:
                continue
            script = _run_script(step)
            tokens = _token_entries([*workflow_env, *job_env, *_envs_at(step, 8)])
            token_names = [entry["name"] for entry in tokens]
            where = f"{filename} job {job['name']}"
            if FRESHNESS not in script:
                problems.append(
                    f"{where}: {FRESHNESS} is outside the run script, "
                    "so the call is not an authenticated read"
                )
                continue
            gh_api = GH_API.search(script) is not None
            direct_http = DIRECT_HTTP.search(script) is not None
            if not gh_api and not direct_http:
                problems.append(
                    f"{where}: {FRESHNESS} is called without authentication. "
                    "Pass GH_TOKEN or GITHUB_TOKEN from github.token and use gh api, "
                    "or send Authorization: Bearer."
                )
                continue
            if gh_api and not token_names:
                problems.append(
                    f"{where}: gh api reads {FRESHNESS} without authentication. "
                    "Set GH_TOKEN or GITHUB_TOKEN to ${{ github.token }} in the step env."
                )
            if direct_http and (not token_names or not _sends_bearer(script, token_names)):
                problems.append(
                    f"{where}: {FRESHNESS} is called without authentication. "
                    "Pass GITHUB_TOKEN from github.token in the step env and send "
                    "Authorization: Bearer with that token."
                )
            if _contents(job_lines, text) != "read":
                problems.append(
                    f"{where}: the freshness read must set permissions contents: read. "
                    "That scope is enough; do not grant contents: write."
                )
    return problems


def _workflow_texts() -> list[tuple[str, str]]:
    return [
        (path.name, path.read_text()) for path in sorted(WORKFLOWS.glob("*.yml")) if path.is_file()
    ]


def _deploy_guard() -> tuple[str, dict[str, str], list[str]]:
    text = (WORKFLOWS / "verify.yml").read_text()
    deploy = next(job for job in _extract_jobs(text) if job["name"] == "deploy")
    job_lines = deploy["lines"]
    assert isinstance(job_lines, list)
    steps = _extract_steps(job_lines)
    guard = steps[0]
    script = _run_script(guard)
    env: dict[str, str] = {}
    for entry in _envs_at(guard, 8):
        if entry["name"] in {"GH_TOKEN", "GITHUB_TOKEN"} and TOKEN_VALUE.search(entry["value"]):
            env[entry["name"]] = "workflow-token"
        elif entry["name"] == "CANDIDATE":
            env[entry["name"]] = EXPECTED_SHA
    deploy_step = next(step for step in steps if "actions/deploy-pages@" in "\n".join(step))
    return script, env, deploy_step


def _run_guard(
    tmp_path: Path, *, remote_sha: str, gh_status: int
) -> tuple[subprocess.CompletedProcess[str], str]:
    script, injected, _deploy = _deploy_guard()
    fake_dir = tmp_path / "bin"
    fake_dir.mkdir()
    fake = fake_dir / "gh"
    fake.write_text(FAKE_GH)
    fake.chmod(0o755)
    capture = tmp_path / "capture.txt"
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
        env={
            "PATH": f"{fake_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "GH_CAPTURE": str(capture),
            "GH_STATUS": str(gh_status),
            "REMOTE_SHA": remote_sha,
            **injected,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    recorded = capture.read_text() if capture.is_file() else ""
    return result, recorded


def test_repository_workflows_authenticate_every_main_freshness_read():
    calls = []
    problems = []
    for name, text in _workflow_texts():
        if FRESHNESS in text:
            calls.append(name)
        problems.extend(freshness_problems(name, text))
    assert problems == [], "\n".join(problems)
    assert calls == ["verify.yml"]
    script, env, deploy_step = _deploy_guard()
    assert env["GH_TOKEN"] == "workflow-token"
    assert env["CANDIDATE"] == EXPECTED_SHA
    assert GH_API.search(script)
    assert FRESHNESS in script
    text = (WORKFLOWS / "verify.yml").read_text()
    deploy = next(job for job in _extract_jobs(text) if job["name"] == "deploy")
    job_lines = deploy["lines"]
    assert isinstance(job_lines, list)
    assert _permission_block(job_lines, 4) == {
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    }
    guard = "\n".join(_extract_steps(job_lines)[0])
    assert "Require current main inside deployment lock" in guard
    assert "continue-on-error" not in guard
    assert "actions/deploy-pages@" in "\n".join(deploy_step)


def test_unauthenticated_urllib_freshness_read_fails():
    problems = freshness_problems("sample.yml", UNAUTHENTICATED)
    assert any("without authentication" in problem for problem in problems), problems
    assert any("contents: read" in problem for problem in problems), problems
    assert any("contents: write" in problem for problem in problems), problems


def test_token_that_is_not_sent_on_the_request_still_fails():
    problems = freshness_problems("sample.yml", TOKEN_PRESENT_BUT_UNUSED)
    assert any("without authentication" in problem for problem in problems), problems


def test_gh_api_without_a_token_fails():
    problems = freshness_problems("sample.yml", GH_WITHOUT_TOKEN)
    assert any("without authentication" in problem for problem in problems), problems


def test_gh_api_with_gh_token_and_urllib_with_authorization_bearer_pass():
    assert freshness_problems("gh.yml", AUTHENTICATED_GH) == []
    assert freshness_problems("urllib.yml", AUTHENTICATED_URLLIB) == []
    assert freshness_problems("job-env.yml", JOB_ENV_TOKEN) == []


def test_contents_write_fails_even_when_the_read_sends_a_token():
    text = AUTHENTICATED_GH.replace("      contents: read", "      contents: write", 1)
    problems = freshness_problems("sample.yml", text)
    assert any("contents: read" in problem and "contents: write" in problem for problem in problems)


def test_removing_the_manual_workflow_token_fails():
    text = (WORKFLOWS / "verify.yml").read_text()
    stripped = "".join(
        line
        for line in text.splitlines(keepends=True)
        if not re.match(r"^\s+(?:GH_TOKEN|GITHUB_TOKEN):", line)
    )
    problems = freshness_problems("manual.yml", stripped)
    assert any("without authentication" in problem for problem in problems), problems


@pytest.mark.parametrize(
    ("remote_sha", "gh_status", "expected_code"),
    [
        (EXPECTED_SHA, 0, 0),
        ("b" * 40, 0, 1),
        ("", 0, 1),
        (EXPECTED_SHA, 403, 1),
    ],
)
def test_deploy_guard_still_aborts_when_main_moved_or_the_read_fails(
    tmp_path: Path, remote_sha: str, gh_status: int, expected_code: int
):
    result, recorded = _run_guard(tmp_path, remote_sha=remote_sha, gh_status=gh_status)
    assert result.returncode == expected_code, result.stderr
    assert "authenticated=yes" in recorded
    assert FRESHNESS in recorded
    assert "workflow-token" not in result.stdout
    assert "workflow-token" not in result.stderr
    assert "workflow-token" not in recorded
    if gh_status != 0:
        assert "rate limit exceeded" in result.stderr
