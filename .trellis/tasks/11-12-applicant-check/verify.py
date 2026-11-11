"""Check the recorded pre-research hashes; only remove this task's empty temps."""
import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TASK = Path(__file__).resolve().parent
EXPECTED = {
    "demo/backend/ocr/localocr.py": "f7a0e3f26dec882bc82169aa3407ec8d14b2f329db4f6511863bf1f57220f1c1",
    "engine_v2/docs/own-ocr.md": "9ca9cc9114a0234e8dfe6f9d5f7a26d7b2f149a9525a617da3fa709e2b54cbba",
    "engine_v2/docs/own-ocr-history.md": "8d08d83860deebe4f05675776dc197be58350c16b2b2204adf4f34dd520c9b46",
    "demo/backend/tests/run_p17_own_scenarios.py": "a1b35db0155767f51f22b124e34b59ab4d33c552751b363be1c0081ce14ce8cb",
    ".trellis/tasks/11-11-own-default/implement.md": "0b93614c03344ac7b4369fcc953ae2d80dc561cc6d4cf63ef6fb403bbdbfad65",
    ".trellis/tasks/11-11-own-default/research.md": "5cc509650f79fe383bdac1857e0e12d589f18a20dbd8ae5270344b5817ad41bd",
    ".trellis/tasks/11-11-own-default/design.md": "05c099b9ba9e216803b26db9447103aed74bded69fad038a7db994c2e200d185",
    ".trellis/tasks/11-11-own-default/implement.jsonl": "6a6941ddf947a527b0e85243adebbb9420bd4a0d2982f8ca273ee401cd0005f2",
    ".trellis/tasks/11-11-own-default/prd.md": "f230f6ba93dd14b4d7b9d4511b4e56c531a04ef4d8fbbb65c779459477080557",
    ".trellis/tasks/11-11-own-default/check.jsonl": "6a6941ddf947a527b0e85243adebbb9420bd4a0d2982f8ca273ee401cd0005f2",
    ".trellis/tasks/11-11-own-default/task.json": "a46dd6e9f7843b817af83babbff1321636f06738af6f653b44040ef5d44c88ea",
    ".trellis/tasks/11-11-own-default/report.md": "9579ec03b6c83fe2b66eecca05c5d6570292703bfc609f94553c7ab9be105b6d",
}
for relative, expected in EXPECTED.items():
    actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    assert actual == expected, f"CHANGED: {relative}"
old_task = {str(p.relative_to(ROOT)) for p in (ROOT / ".trellis/tasks/11-11-own-default").rglob("*") if p.is_file()}
assert old_task == {path for path in EXPECTED if path.startswith(".trellis/")}
print(f"Baseline content unchanged: {len(EXPECTED)}/{len(EXPECTED)} files (5 original status entries).")

# ONNX created telemetry state under TMPDIR; it is unrelated to the research output.
(TASK / ".ses").unlink(missing_ok=True)
for path in TASK.glob("probe-*"):
    if path.is_dir() and not any(path.iterdir()):
        path.rmdir()
for args in (("branch", "--show-current"), ("status", "--short"), ("diff", "--stat")):
    print(subprocess.check_output(["git", *args], cwd=ROOT, text=True), end="")
print("Research artifacts:", ", ".join(sorted(path.name for path in TASK.iterdir())))
