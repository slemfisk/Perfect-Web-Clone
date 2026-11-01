"""CLI contract for the public Perfect Web Clone core.

These tests describe the user-facing `pwc` commands. They must fail until
`pwc.cli` exists. Gates never call an LLM.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image


REPO = Path(__file__).resolve().parents[1]


def _run(args: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pwc", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        **kwargs,
    )


def test_no_args_exits_nonzero_and_lists_commands():
    result = _run([])
    assert result.returncode != 0
    combined = (result.stdout + result.stderr).lower()
    for name in ("extract", "plan", "section", "assemble", "score", "fingerprints", "weight"):
        assert name in combined


def test_fingerprints_reports_shopify_in_json(tmp_path):
    (tmp_path / "bad.css").write_text(".shopify-section { display:block }")
    result = _run(["fingerprints", str(tmp_path)])
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["total"] >= 1


def test_fingerprints_clean_tree_ok(tmp_path):
    (tmp_path / "ok.css").write_text(".hero { color: #111 }")
    result = _run(["fingerprints", str(tmp_path)])
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["total"] == 0


def test_weight_tiny_dir_passes(tmp_path):
    (tmp_path / "index.html").write_text("<html><body>hi</body></html>")
    result = _run(["weight", str(tmp_path)])
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True


def test_score_identical_images_is_one(tmp_path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    Image.new("RGB", (64, 64), (40, 80, 160)).save(a)
    Image.new("RGB", (64, 64), (40, 80, 160)).save(b)
    result = _run(["score", "--ref", str(a), "--cand", str(b)])
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["score"] == 1.0


def test_plan_unknown_source_id_is_json_error():
    result = _run(["plan", "does-not-exist-source"])
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "source" in payload["error"].lower() or "unknown" in payload["error"].lower()


def test_build_without_sandbox_is_json_error(tmp_path):
    env = {**os.environ, "PWC_SANDBOX_DIR": str(tmp_path / "sandboxes")}
    result = _run(["build"], env=env)
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "sandbox" in payload["error"].lower()


def test_assemble_resumes_sandbox_across_processes(tmp_path):
    # Each `pwc` call is a fresh process; the second assemble must find the
    # section the agent wrote into the first one's work_dir.
    sources = tmp_path / "sources"
    src = sources / "example-1-abc123"
    src.mkdir(parents=True)
    (src / "manifest.json").write_text('{"success": true}', encoding="utf-8")
    comp = "src/components/sections/hero/Hero.jsx"
    plan = {
        "source_url": "https://example.com",
        "section_count": 1,
        "sections": [{"name": "hero", "namespace": "hero", "component_path": comp}],
        "assembly_template": {"component_order": [{
            "order": 0, "import_name": "Hero", "namespace": "hero",
            "import_path": "./components/sections/hero/Hero",
        }]},
    }
    (src / "sections.json").write_text(json.dumps(plan), encoding="utf-8")
    env = {
        **os.environ,
        "PWC_SOURCES_DIR": str(sources),
        "PWC_SANDBOX_DIR": str(tmp_path / "sandboxes"),
    }

    first = json.loads(_run(["assemble", src.name], env=env).stdout)
    assert first["missing_section_files"] == [comp]
    work_dir = Path(first["work_dir"])
    (work_dir / comp).parent.mkdir(parents=True)
    (work_dir / comp).write_text("export default () => <h1>hi</h1>;\n", encoding="utf-8")

    second = json.loads(_run(["assemble", src.name], env=env).stdout)
    assert second["ok"] is True
    assert second["work_dir"] == first["work_dir"]
    assert second["run_ledger_created"] is False


def test_section_unknown_source_id_is_json_error():
    result = _run(["section", "does-not-exist-source", "hero"])
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "source" in payload["error"].lower() or "unknown" in payload["error"].lower()
