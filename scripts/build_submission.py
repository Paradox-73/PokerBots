"""Build the upload file and check it the way the contest server will run it.

    python scripts/build_submission.py              # build + all checks
    python scripts/build_submission.py --no-docker  # skip the Python 3.11 sandbox run

Writes dist/submission.zip (bot.py at the top level + the pokerbots package,
no engine/runner code) and dist/submission/ (the same files, unzipped).

Checks (rulebook 5.x):
  1. zip size <= 5 MB
  2. imports: only stdlib, numpy, scipy and our own package; no file, socket or
     process access in the shipped code
  3. 400-hand match of the unzipped bot.py vs the organisers' starter bot,
     run isolated (python -I, its own folder): no forfeit, no illegal replies
  4. same match inside Docker: python:3.11 + numpy + scipy, 1 CPU, 1 GB RAM,
     no network, read-only filesystem (scripts/sandbox.Dockerfile)
"""

import argparse
import ast
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pokerbots.engine.match import play_match  # noqa: E402

DIST = os.path.join(ROOT, "dist")
OUT_DIR = os.path.join(DIST, "submission")
OUT_ZIP = os.path.join(DIST, "submission.zip")
STARTER = os.path.join(ROOT, "tests", "fixtures", "starter_bot.py")
IMAGE = "pokerbots-sandbox:3.11"
MAX_BYTES = 5 * 1024 * 1024

# shipped files: the bot side only (engine/game.py and match.py stay home)
SHIP_DIRS = ("pokerbots", "pokerbots/core", "pokerbots/bots")
SHIP_FILES = ("bot.py", "pokerbots/engine/__init__.py", "pokerbots/engine/protocol.py")
BANNED_MODULES = {"subprocess", "socket", "multiprocessing", "ctypes", "urllib", "http",
                  "ftplib", "smtplib", "asyncio", "shutil", "tempfile", "pathlib"}
BANNED_CALLS = {"open", "eval", "exec", "compile", "__import__", "system", "popen"}


def shipped_files():
    files = list(SHIP_FILES)
    for d in SHIP_DIRS:
        files += ["%s/%s" % (d, f) for f in sorted(os.listdir(os.path.join(ROOT, d)))
                  if f.endswith(".py")]
    return files


def build():
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    os.makedirs(DIST, exist_ok=True)
    files = shipped_files()
    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            src = os.path.join(ROOT, f)
            z.write(src, f)
            dst = os.path.join(OUT_DIR, f)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
    return files


def check_size():
    size = os.path.getsize(OUT_ZIP)
    assert size <= MAX_BYTES, "zip is %d bytes (> 5 MB)" % size
    return "zip %.1f KB" % (size / 1024)


def check_imports(files):
    allowed = set(sys.stdlib_module_names) | {"numpy", "scipy", "pokerbots"}
    problems = []
    for f in files:
        tree = ast.parse(open(os.path.join(ROOT, f), encoding="utf-8").read(), f)
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                mods = [node.module]
            for m in mods:
                top = m.split(".")[0]
                if top not in allowed or top in BANNED_MODULES:
                    problems.append("%s:%d imports %s" % (f, node.lineno, m))
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
                if name in BANNED_CALLS:
                    problems.append("%s:%d calls %s()" % (f, node.lineno, name))
    assert not problems, "\n".join(problems)
    return "imports ok (%d files)" % len(files)


def run_match(spec, label, deals):
    res = play_match(spec, STARTER, deals=deals, seed=11, names=[label, "starter"])
    print(res.summary())
    assert res.forfeit is None, res.forfeit_reason
    assert res.illegal == [0, 0], res.illegal
    return "%s: %d hands, bank used %.1fs of 60, slowest reply %.0f ms" % (
        label, res.hands_played, res.time_used[0], res.max_decision[0] * 1000)


def docker_spec():
    if subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode:
        subprocess.run(["docker", "build", "-t", IMAGE, "-f",
                        os.path.join(ROOT, "scripts", "sandbox.Dockerfile"),
                        os.path.join(ROOT, "scripts")], check=True)
    mount = OUT_DIR.replace("\\", "/")
    return ("cmd:docker run -i --rm --network none --read-only --cpus 1 --memory 1g "
            "--memory-swap 1g -v \"%s:/bot:ro\" -w /bot %s python -u bot.py" % (mount, IMAGE))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-docker", action="store_true")
    ap.add_argument("--deals", type=int, default=200, help="duplicate deals per check match")
    args = ap.parse_args()
    files = build()
    report = [check_size(), check_imports(files),
              run_match(os.path.join(OUT_DIR, "bot.py"), "local -I", args.deals)]
    if not args.no_docker:
        report.append(run_match(docker_spec(), "docker 3.11", args.deals))
    print("\nBuilt %s" % OUT_ZIP)
    for line in report:
        print("  ok  " + line)


if __name__ == "__main__":
    main()
