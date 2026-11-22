# SPDX-License-Identifier: Apache-2.0
"""Exercise the released manual's workflow guards without contacting GitHub."""

import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40
OTHER = "b" * 40
TAG = "v2.3.4"
RUN = "34"
ATTEMPT = "2"


def workflow(name):
    return yaml.load(
        (ROOT / ".github/workflows" / f"{name}.yml").read_text(), Loader=yaml.BaseLoader
    )


def _step(workflow_name, job, name):
    return next(s for s in workflow(workflow_name)["jobs"][job]["steps"] if s.get("name") == name)


def _run(step, path, **env):
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
        cwd=path,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=False,
    )


def test_workflow_uses_one_read_only_build_before_writer_and_not_after():
    orchestrator = workflow("verify")
    jobs = orchestrator["jobs"]
    assert set(orchestrator["on"]) == {"push", "pull_request", "workflow_dispatch"}
    assert jobs["version"]["with"]["replay-tag"] == "${{ inputs.release_tag || '' }}"
    assert set(workflow("manual")["on"]) == {"workflow_call"}
    assert set(workflow("manual")["jobs"]) == {"build"}
    assert jobs["manual"]["needs"] == "version"
    assert jobs["manual"]["with"]["version"] == "${{ needs.version.outputs.semver-version }}"
    assert jobs["manual"]["permissions"] == {"contents": "read"}
    assert set(jobs["release"]["needs"]) == {"verify", "version", "manual"}
    assert set(jobs["deploy"]["needs"]) == {"version", "manual", "release"}
    assert jobs["release"]["with"] == {
        "expected-version": "${{ needs.manual.outputs.artifact-version }}",
        "expected-commit": "${{ needs.manual.outputs.artifact-commit }}",
    }
    assert "github.event_name == 'push'" in jobs["release"]["if"]
    assert "needs.version.outputs.git-tag != ''" in jobs["release"]["if"]
    assert "needs.release.outputs.published == 'true'" in jobs["deploy"]["if"]
    assert "needs.release.result == 'success'" in jobs["deploy"]["if"]
    assert "github.event_name == 'workflow_dispatch'" in jobs["deploy"]["if"]
    assert "needs.release.result == 'skipped'" in jobs["deploy"]["if"]
    for job in ("release", "deploy"):
        assert "needs.manual.outputs.artifact-run-id == github.run_id" in jobs[job]["if"]
        assert "needs.manual.outputs.artifact-attempt == github.run_attempt" in jobs[job]["if"]
    assert all("actions/checkout" not in step.get("uses", "") for step in jobs["deploy"]["steps"])


@pytest.mark.parametrize(
    "run,attempt,commit,ok",
    [
        (RUN, ATTEMPT, SHA, True),
        ("9", ATTEMPT, SHA, False),
        (RUN, "1", SHA, False),
        (RUN, ATTEMPT, OTHER, False),
    ],
)
def test_plan_matches_event_checkout_and_attempt(tmp_path, run, attempt, commit, ok):
    git = tmp_path / "git"
    git.write_text(f'#!/bin/sh\n[ "$*" = "rev-parse HEAD" ] || exit 25\n echo {SHA}\n')
    git.chmod(0o755)
    step = _step("manual", "build", "Require the exact shared version plan for this attempt")
    result = _run(
        step,
        tmp_path,
        PATH=f"{tmp_path}:{os.environ['PATH']}",
        SOURCE_COMMIT=commit,
        MANUAL_VERSION="2.3.4",
        EVENT_COMMIT=SHA,
        GITHUB_RUN_ID=RUN,
        GITHUB_RUN_ATTEMPT=ATTEMPT,
        PLAN_RUN=run,
        PLAN_ATTEMPT=attempt,
    )
    assert (result.returncode == 0) == ok, result


@pytest.mark.parametrize(
    ("kind", "ok"),
    [
        ("lightweight", True),
        ("annotated", True),
        ("bare", False),
        ("no-tag", False),
        ("other-commit", False),
        ("other-version", False),
        ("draft", False),
        ("prerelease", False),
        ("not-published", False),
    ],
)
def test_exact_stable_release_gate(tmp_path, kind, ok):
    git, gh = tmp_path / "git", tmp_path / "gh"
    git.write_text(
        "#!/bin/bash\n"
        '[[ "$*" == "-c credential.helper= ls-remote --exit-code '
        "https://github.com/Living-Proof-Labs/livingproof-worlds.git refs/tags/v2.3.4 "
        'refs/tags/v2.3.4^{}" ]] || exit 40\n'
        '[ "$MOCK_TAGS" != "" ] || exit 2\n'
        'printf "%s\\n" "$MOCK_TAGS"\n'
    )
    gh.write_text(
        '#!/bin/sh\n[ "$*" = "api repos/Living-Proof-Labs/livingproof-worlds/releases/tags/v2.3.4" ] '
        '|| exit 41\n[ "$MOCK_RELEASE" != "" ] || exit 1\nprintf "%s\\n" "$MOCK_RELEASE"\n'
    )
    git.chmod(0o755)
    gh.chmod(0o755)
    ref = f"refs/tags/{TAG}"
    refs = f"{SHA}\t{ref}"
    release = {"tag_name": TAG, "draft": False, "prerelease": False, "published_at": "2026-11-22"}
    if kind == "annotated":
        refs = f"{OTHER}\t{ref}\n{SHA}\t{ref}^{{}}"
    elif kind in {"no-tag", "other-commit"}:
        refs = "" if kind == "no-tag" else f"{OTHER}\t{ref}"
    elif kind == "draft":
        release["draft"] = True
    elif kind == "prerelease":
        release["prerelease"] = True
    elif kind == "not-published":
        release["published_at"] = None
    result = _run(
        _step(
            "verify",
            "deploy",
            "Independently require the published stable release at the exact commit",
        ),
        tmp_path,
        PATH=f"{tmp_path}:{os.environ['PATH']}",
        CANDIDATE=SHA,
        GITHUB_SHA=SHA,
        VERSION="2.3.5" if kind == "other-version" else "2.3.4",
        RELEASE_TAG=TAG,
        MOCK_TAGS=refs,
        MOCK_RELEASE="" if kind == "bare" else json.dumps(release),
    )
    assert (result.returncode == 0) == ok, result


@pytest.mark.parametrize(
    "kind", ["verified", "changed-byte", "extra-file", "stale-attempt", "other-digest"]
)
def test_seal_then_check_transported_bytes(tmp_path, kind):
    site = tmp_path / "artifacts/manual/html"
    site.mkdir(parents=True)
    (site / "index.html").write_text("manual\n")
    (site / ".nojekyll").touch()
    (site / "build.json").write_text(
        json.dumps(
            {
                "source_commit": SHA,
                "source_dirty": False,
                "version": TAG[1:],
                "run_id": RUN,
                "run_attempt": ATTEMPT,
            }
        )
    )
    outputs = tmp_path / "outputs"
    seal = _run(
        _step("manual", "build", "Seal the verified manual bytes for this attempt"),
        tmp_path,
        SOURCE_COMMIT=SHA,
        MANUAL_VERSION=TAG[1:],
        GITHUB_RUN_ID=RUN,
        GITHUB_RUN_ATTEMPT=ATTEMPT,
        GITHUB_OUTPUT=str(outputs),
    )
    assert seal.returncode == 0, seal
    recorded = dict(row.split("=", 1) for row in outputs.read_text().splitlines())
    assert recorded | {"digest": ""} == {
        "commit": SHA,
        "version": TAG[1:],
        "run-id": RUN,
        "attempt": ATTEMPT,
        "digest": "",
    }
    shutil.copytree(site.parent, tmp_path / "verified-manual")
    delivered = tmp_path / "verified-manual/html"
    if kind == "changed-byte":
        (delivered / "index.html").write_text("different manual\n")
    elif kind == "extra-file":
        (delivered / "unexpected.html").touch()
    transport = _run(
        _step("verify", "deploy", "Verify transport and package only the sealed HTML"),
        tmp_path,
        CANDIDATE=SHA,
        VERSION=TAG[1:],
        GITHUB_RUN_ID=RUN,
        GITHUB_RUN_ATTEMPT="3" if kind == "stale-attempt" else ATTEMPT,
        RUNNER_TEMP=str(tmp_path),
        DIGEST="0" * 64 if kind == "other-digest" else recorded["digest"],
    )
    assert (transport.returncode == 0) == (kind == "verified"), transport
    if kind == "verified":
        with tarfile.open(tmp_path / "artifact.tar") as package:
            assert sorted(package.getnames()) == [
                ".",
                "./.nojekyll",
                "./build.json",
                "./index.html",
            ]
