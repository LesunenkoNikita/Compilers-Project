#!/usr/bin/env python3
"""Run all tests and report which ones failed.

tests/valid/NAME.txt   + NAME.expected : stdout must equal the expected AST dump, exit code 0, empty stderr
tests/errors/NAME.txt  + NAME.expected : stderr must equal the expected error line, non-zero exit code, empty stdout
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
COMPILER = os.path.join(ROOT, "compiler.py")


def run(path):
    return subprocess.run([sys.executable, COMPILER, "--ast", path], capture_output=True)


def check_valid(path, expected):
    p = run(path)
    if p.returncode != 0:
        return f"exit code {p.returncode}, stderr: {p.stderr.decode('utf-8', 'replace').strip()}"
    if p.stderr:
        return "unexpected stderr output"
    if p.stdout != expected:
        return "AST dump differs from the expected one"
    return None


def check_error(path, expected):
    p = run(path)
    if p.returncode == 0:
        return "expected a compilation error but the program was accepted"
    if p.stdout:
        return "stdout must be empty on error"
    if p.stderr != expected:
        return (f"error line differs\n      expected: {expected.decode('utf-8', 'replace').strip()}"
                f"\n      got:      {p.stderr.decode('utf-8', 'replace').strip()}")
    return None


def main():
    failed, total = [], 0
    for folder, checker in (("valid", check_valid), ("errors", check_error)):
        d = os.path.join(ROOT, "tests", folder)
        for name in sorted(os.listdir(d)):
            if not name.endswith(".txt"):
                continue
            total += 1
            expected_path = os.path.join(d, name[:-4] + ".expected")
            with open(expected_path, "rb") as f:
                expected = f.read()
            problem = checker(os.path.join(d, name), expected)
            label = f"{folder}/{name}"
            if problem:
                failed.append(label)
                print(f"FAIL  {label}\n      {problem}")
            else:
                print(f"ok    {label}")
    print(f"\n{total - len(failed)}/{total} tests passed")
    if failed:
        print("Failed tests:")
        for label in failed:
            print("  " + label)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
