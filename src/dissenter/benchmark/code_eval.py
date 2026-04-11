"""Sandboxed code execution for HumanEval-style benchmarks.

Runs candidate code against test cases in a subprocess with a timeout.
We use subprocess isolation rather than exec() in-process so:
  - A hanging candidate doesn't freeze the benchmark runner
  - A crashing candidate doesn't crash the runner
  - Basic resource limits can be applied

This is NOT a security sandbox. It's fine for grading trusted model
output (your own runs), but don't use it on adversarial input.

The HumanEval test format looks like:

    def check(candidate):
        assert candidate(1, 2) == 3
        ...

    check(entry_point_name)

We exec the candidate code, then exec the test code (which defines
check()), then call check(entry_point).
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CodeEvalResult:
    passed: bool
    error: str | None = None
    stdout: str = ""
    stderr: str = ""


# Template for the subprocess runner. The candidate code and the test
# code are interpolated as string literals via json.dumps so we don't
# have to worry about indentation or quoting games.
_RUNNER_TEMPLATE = """\
import sys
import json

candidate_code = {candidate_json}
test_code = {test_json}
entry_point = {entry_point_json}

ns = {{}}
try:
    exec(candidate_code, ns)
except Exception as e:
    print(json.dumps({{"ok": False, "error": f"candidate exec failed: {{type(e).__name__}}: {{e}}"}}))
    sys.exit(0)

try:
    exec(test_code, ns)
except Exception as e:
    print(json.dumps({{"ok": False, "error": f"test code exec failed: {{type(e).__name__}}: {{e}}"}}))
    sys.exit(0)

check = ns.get("check")
fn = ns.get(entry_point)
if check is None:
    print(json.dumps({{"ok": False, "error": "test code defined no check() function"}}))
    sys.exit(0)
if fn is None:
    print(json.dumps({{"ok": False, "error": f"candidate defined no {{entry_point!r}} function"}}))
    sys.exit(0)

try:
    check(fn)
except AssertionError as e:
    print(json.dumps({{"ok": False, "error": f"assertion failed: {{e}}"}}))
    sys.exit(0)
except Exception as e:
    print(json.dumps({{"ok": False, "error": f"check raised: {{type(e).__name__}}: {{e}}"}}))
    sys.exit(0)

print(json.dumps({{"ok": True}}))
"""


def eval_humaneval(
    candidate_code: str,
    test_code: str,
    entry_point: str,
    timeout: int = 10,
) -> CodeEvalResult:
    """Run a candidate solution against its HumanEval test cases.

    Returns CodeEvalResult(passed=True) if all assertions pass, else
    passed=False with a human-readable error.
    """
    import json

    runner_source = _RUNNER_TEMPLATE.format(
        candidate_json=json.dumps(candidate_code),
        test_json=json.dumps(test_code),
        entry_point_json=json.dumps(entry_point),
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(runner_source)
        runner_path = f.name

    try:
        proc = subprocess.run(
            [sys.executable, runner_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return CodeEvalResult(
            passed=False,
            error=f"timeout after {timeout}s",
        )
    finally:
        try:
            Path(runner_path).unlink()
        except Exception:
            pass

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()

    if not stdout:
        return CodeEvalResult(
            passed=False,
            error=f"runner produced no output (stderr: {stderr[:200]})",
            stderr=stderr,
        )

    try:
        # The runner prints a single JSON line on its last line
        last_line = stdout.splitlines()[-1]
        result = json.loads(last_line)
    except Exception as e:
        return CodeEvalResult(
            passed=False,
            error=f"could not parse runner output: {e}",
            stdout=stdout,
            stderr=stderr,
        )

    if result.get("ok"):
        return CodeEvalResult(passed=True, stdout=stdout, stderr=stderr)
    else:
        return CodeEvalResult(
            passed=False,
            error=result.get("error", "unknown"),
            stdout=stdout,
            stderr=stderr,
        )
