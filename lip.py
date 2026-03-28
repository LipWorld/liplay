#!/usr/bin/env python3
# ============================================================
# lip.py - Main entry point (REPL and file runner)
# ============================================================
"""
Lip Language Interpreter

Usage:
    python lip.py                  # Start REPL
    python lip.py script.lip       # Run a script file
"""

import sys

from lip_interp import create_interpreter, is_pending, lip_repr
from lip_lang import parse


def run_file(filename: str):
    """Execute a Lip source file."""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            source = f.read()
    except FileNotFoundError:
        print(f"Error: File not found: {filename}", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)

    interp = create_interpreter()
    try:
        ast = parse(source)
        result = interp.eval(ast)
        if result is not None:
            print(lip_repr(result))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def is_incomplete(code: str) -> bool:
    """Check if the code appears incomplete (needs more input)."""
    stripped = code.rstrip()
    if stripped.endswith("->") or stripped.endswith(":>"):
        return True

    depth = 0
    in_string = False
    escape = False
    for ch in code:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not in_string:
            in_string = True
        elif ch == '"' and in_string:
            in_string = False
        elif not in_string:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
    return depth > 0


def run_repl():
    """Start the interactive REPL."""
    print("Lip Language REPL v0.1")
    print("Type expressions to evaluate. Ctrl+D or 'exit' to quit.\n")

    interp = create_interpreter()

    try:
        import os

        from prompt_toolkit import PromptSession
        from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
        from prompt_toolkit.history import FileHistory

        history_file = os.path.expanduser("~/.lip_history")
        session = PromptSession(
            history=FileHistory(history_file), auto_suggest=AutoSuggestFromHistory()
        )

        def get_input(prompt):
            return session.prompt(prompt)

    except ImportError:

        def get_input(prompt):
            return input(prompt)

    buffer = []
    while True:
        try:
            prompt = "... " if buffer else "lip> "
            line = get_input(prompt)

            if line.strip() == "exit":
                break

            buffer.append(line)
            code = "\n".join(buffer)

            if is_incomplete(code):
                continue

            buffer = []

            if not code.strip():
                continue

            try:
                ast = parse(code)
                result = interp.eval(ast)
                if result is not None:
                    print(f"=> {lip_repr(result)}")
            except Exception as e:
                print(f"Error: {e}")

        except EOFError:
            print("\nBye!")
            break
        except KeyboardInterrupt:
            print("\n(Interrupted)")
            buffer = []
            continue


def main():
    if len(sys.argv) > 1:
        run_file(sys.argv[1])
    else:
        run_repl()


if __name__ == "__main__":
    main()
