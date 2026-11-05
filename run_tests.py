#!/usr/bin/env python3
"""Run all tests and report which ones failed.

tests/valid/NAME.txt  a program that compiles and runs:
    NAME.ast       the AST printed by --ast (created by this script when it is missing)
    NAME.expected  exactly what the program prints (stdout, then stderr, if any)
    NAME.in        optional: the program's standard input
tests/errors/NAME.txt  a program that must be rejected:
    NAME.expected  the single error line on stderr; exit code non-zero, stdout empty, no .ll file written
    NAME.ast       optional: the program parses, so --ast must still print this AST (the error is semantic)
tests/optimizer/NAME.txt  a program that shows a transformation of --optimize:
    NAME.ast       the tree printed by --optimize --ast (checked only when this script runs with --optimize)
    NAME.expected  exactly what the program prints, with and without --optimize
    NAME.in        optional: the program's standard input

Without --optimize the compiler runs without the optimizer. With --optimize every test compiles through it
and must give the same result as without it.

The .ll files and binaries go to build/ (not committed).

usage: python3 run_tests.py [--optimize] [--native] [--update-ast] [NAME_FILTER ...]
    --optimize    compile every test with --optimize and check the trees in tests/optimizer
    --native      build with llc + clang and run the binary instead of running the .ll with lli
    --update-ast  rewrite the .ast files of the valid tests from the current --ast output
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
COMPILER = os.path.join(ROOT, "compiler.py")
BUILD = os.path.join(ROOT, "build")
LLVM_DIRS = ["/opt/homebrew/opt/llvm/bin", "/usr/local/opt/llvm/bin", "/usr/lib/llvm-18/bin", "/usr/lib/llvm-17/bin"]
RUN_TIMEOUT = 10


def find_tool(name):
    path = shutil.which(name)
    if path:
        return path
    for d in LLVM_DIRS:
        candidate = os.path.join(d, name)
        if os.access(candidate, os.X_OK):
            return candidate
    return None


def read(path):
    with open(path, "rb") as f:
        return f.read()


def text(data):
    return data.decode("utf-8", "replace").rstrip("\n")


def compiler(*args):
    return subprocess.run([sys.executable, COMPILER, *args], capture_output=True)


class Runner:
    def __init__(self, native, update_ast, optimize):
        self.native, self.update_ast = native, update_ast
        self.flags = ("--optimize",) if optimize else ()
        self.notes = []
        tools = ["llc", "clang"] if native else ["lli"]
        self.tools = {t: find_tool(t) for t in tools}
        missing = [t for t, p in self.tools.items() if p is None]
        if missing:
            sys.exit(f"cannot find {', '.join(missing)}: install LLVM or add it to PATH")

    def check_ast(self, base, must_exist):
        ast_path = base + ".ast"
        p = compiler("--ast", base + ".txt")
        if p.returncode != 0:
            return f"--ast failed: {text(p.stderr)}"
        if not os.path.exists(ast_path) or self.update_ast:
            if must_exist and not os.path.exists(ast_path):
                return None
            with open(ast_path, "wb") as f:
                f.write(p.stdout)
            self.notes.append(f"wrote {os.path.relpath(ast_path, ROOT)}")
            return None
        if p.stdout != read(ast_path):
            return "--ast output differs from NAME.ast"
        return None

    def execute(self, ll_path, stdin):
        if self.native:
            obj, exe = ll_path[:-3] + ".o", ll_path[:-3]
            for cmd in ([self.tools["llc"], "-filetype=obj", "-relocation-model=pic", ll_path, "-o", obj],
                        [self.tools["clang"], obj, "-o", exe]):
                p = subprocess.run(cmd, capture_output=True)
                if p.returncode != 0:
                    return None, f"{os.path.basename(cmd[0])} failed: {text(p.stderr)}"
            cmd = [exe]
        else:
            cmd = [self.tools["lli"], ll_path]
        try:
            return subprocess.run(cmd, input=stdin, capture_output=True, timeout=RUN_TIMEOUT), None
        except subprocess.TimeoutExpired:
            return None, f"the program did not finish in {RUN_TIMEOUT} s"

    def check_valid(self, base, name):
        problem = self.check_ast(base, must_exist=False)
        return problem or self.check_run(base, os.path.join(BUILD, "valid", name + ".ll"))

    def check_optimizer(self, base, name):
        if self.flags:
            p = compiler("--optimize", "--ast", base + ".txt")
            if p.returncode != 0:
                return f"--optimize --ast failed: {text(p.stderr)}"
            if not os.path.exists(base + ".ast"):
                return "missing NAME.ast"
            if p.stdout != read(base + ".ast"):
                return "the tree after --optimize differs from NAME.ast"
        return self.check_run(base, os.path.join(BUILD, "optimizer", name + ".ll"))

    def check_run(self, base, ll_path):
        p = compiler(*self.flags, base + ".txt", ll_path)
        if p.returncode != 0 or p.stderr:
            return f"compilation failed (exit code {p.returncode}): {text(p.stderr)}"
        if not os.path.exists(ll_path):
            return "the compiler wrote no .ll file"
        stdin = read(base + ".in") if os.path.exists(base + ".in") else b""
        run, problem = self.execute(ll_path, stdin)
        if problem:
            return problem
        if run.returncode < 0:
            return f"the program crashed (signal {-run.returncode})"
        expected = read(base + ".expected")
        actual = run.stdout + run.stderr
        if actual != expected:
            return f"output differs\n      expected: {text(expected)!r}\n      got:      {text(actual)!r}"
        return None

    def check_error(self, base, name):
        ll_path = os.path.join(BUILD, "errors", name + ".ll")
        if os.path.exists(ll_path):
            os.remove(ll_path)
        p = compiler(*self.flags, base + ".txt", ll_path)
        expected = read(base + ".expected")
        if p.returncode == 0:
            return "expected a compilation error but the program was accepted"
        if p.stdout:
            return "stdout must be empty on error"
        if p.stderr != expected:
            return f"error line differs\n      expected: {text(expected)}\n      got:      {text(p.stderr)}"
        if os.path.exists(ll_path):
            return "an output file was written although compilation failed"
        if os.path.exists(base + ".ast"):
            return self.check_ast(base, must_exist=True)
        return None


def main(argv):
    native = "--native" in argv
    update_ast = "--update-ast" in argv
    filters = [a for a in argv[1:] if not a.startswith("--")]
    optimize = "--optimize" in argv
    runner = Runner(native, update_ast, optimize)
    failed, total = [], 0
    for folder, checker in (("valid", runner.check_valid), ("errors", runner.check_error),
                            ("optimizer", runner.check_optimizer)):
        d = os.path.join(ROOT, "tests", folder)
        os.makedirs(os.path.join(BUILD, folder), exist_ok=True)
        for file in sorted(os.listdir(d)):
            if not file.endswith(".txt"):
                continue
            name = file[:-4]
            if filters and not any(f in name for f in filters):
                continue
            total += 1
            base = os.path.join(d, name)
            label = f"{folder}/{name}"
            if not os.path.exists(base + ".expected"):
                problem = "missing NAME.expected"
            else:
                problem = checker(base, name)
            if problem:
                failed.append(label)
                print(f"FAIL  {label}\n      {problem}")
            else:
                print(f"ok    {label}")
    for note in runner.notes:
        print(f"note: {note}")
    mode = ("llc + clang" if native else "lli") + (", --optimize" if optimize else "")
    print(f"\n{total - len(failed)}/{total} tests passed ({mode})")
    if failed:
        print("Failed tests:")
        for label in failed:
            print("  " + label)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
