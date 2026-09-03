# language/executor.py
from __future__ import annotations

import re
import sys
import types
import importlib.util
from pathlib import Path

LANGUAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = LANGUAGE_DIR.parent
BASE_PY = LANGUAGE_DIR / "base.py"

BLOCK_HEADER = re.compile(
    r"^(?:async\s+)?"
    r"(?:function|def|class|if|elif|else|for|while|try|except|finally|with|match|case)\b"
)
CONTINUATION = re.compile(r"^(?:else|elif|except|finally)\b")

# from simplelang import functions  →  from simplelang.functions import *
SIMPLELANG_FUNCTIONS_IMPORT = re.compile(
    r"^\s*from\s+simplelang\s+import\s+functions\s*(?:#.*)?$",
    re.MULTILINE,
)


def _register_simplelang_package() -> None:
    """Make `simplelang` / `simplelang.functions` importable from language/base.py."""
    if "simplelang.functions" in sys.modules:
        return

    # load language/base.py as simplelang.functions
    spec = importlib.util.spec_from_file_location("simplelang.functions", BASE_PY)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load SimpleLang base: {BASE_PY}")

    functions_mod = importlib.util.module_from_spec(spec)
    sys.modules["simplelang.functions"] = functions_mod
    spec.loader.exec_module(functions_mod)

    pkg = types.ModuleType("simplelang")
    pkg.__path__ = [str(LANGUAGE_DIR)]  # type: ignore[attr-defined]
    pkg.functions = functions_mod
    pkg.__all__ = list(getattr(functions_mod, "__all__", [])) or [
        n for n in dir(functions_mod) if not n.startswith("_")
    ]
    # star-import from package also dumps helpers
    for name in dir(functions_mod):
        if not name.startswith("_"):
            setattr(pkg, name, getattr(functions_mod, name))

    sys.modules["simplelang"] = pkg


def transpile(source: str) -> str:
    """SimpleLang → Python: func→def, {}→indent, special simplelang import."""
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    if not source.endswith("\n"):
        source += "\n"

    # magic import: brings encrypt() etc. straight into the file namespace
    source = SIMPLELANG_FUNCTIONS_IMPORT.sub(
        "from simplelang.functions import *",
        source,
    )

    out: list[str] = []
    stack: list[str] = []
    i = 0
    n = len(source)
    line_code = ""

    def block_depth() -> int:
        return sum(1 for s in stack if s == "block")

    def emit_indent() -> None:
        out.append("    " * block_depth())

    def at_line_start() -> bool:
        return not out or out[-1] == "\n"

    def skip_original_indent() -> None:
        nonlocal i
        while i < n and source[i] in " \t":
            i += 1

    def read_string() -> str:
        nonlocal i
        start = i
        q = source[i]
        if source[i : i + 3] == q * 3:
            i += 3
            while i < n and source[i : i + 3] != q * 3:
                if source[i] == "\\" and i + 1 < n:
                    i += 2
                else:
                    i += 1
            i = min(i + 3, n)
        else:
            i += 1
            while i < n and source[i] != q:
                if source[i] == "\\" and i + 1 < n:
                    i += 2
                else:
                    i += 1
            if i < n:
                i += 1
        return source[start:i]

    def peek_nonspace(pos: int) -> str:
        while pos < n and source[pos] in " \t":
            pos += 1
        return source[pos] if pos < n else ""

    def rest_of_line_stripped(pos: int) -> str:
        end = source.find("\n", pos)
        if end < 0:
            end = n
        return source[pos:end].strip()

    while i < n:
        c = source[i]

        if c == "\n":
            out.append("\n")
            line_code = ""
            i += 1
            continue

        if at_line_start() and c in " \t":
            skip_original_indent()
            continue

        if c in "\"'":
            if at_line_start():
                emit_indent()
            s = read_string()
            out.append(s)
            line_code += s
            continue

        if c == "#":
            if at_line_start():
                emit_indent()
            start = i
            while i < n and source[i] != "\n":
                i += 1
            out.append(source[start:i])
            continue

        # words — function → def
        if c.isalpha() or c == "_":
            start = i
            while i < n and (source[i].isalnum() or source[i] == "_"):
                i += 1
            word = source[start:i]
            if word == "function":
                word = "def"
            if at_line_start():
                emit_indent()
            out.append(word)
            line_code += word
            continue

        if c == "{":
            header = line_code.strip()
            is_block = False

            if header and BLOCK_HEADER.match(header) and not header.endswith(":"):
                is_block = True
            elif header == "" and out:
                prev = ""
                j = len(out) - 1
                if j >= 0 and out[j] == "\n":
                    j -= 1
                while j >= 0 and out[j] != "\n":
                    prev = out[j] + prev
                    j -= 1
                prev = prev.strip()
                if prev and not prev.endswith(":") and BLOCK_HEADER.match(prev):
                    is_block = True

            if is_block:
                if line_code.strip() == "":
                    while out and out[-1] == "\n":
                        out.pop()
                    if out:
                        out[-1] = out[-1].rstrip()
                    out.append(":\n")
                    line_code = ""
                else:
                    while out and out[-1] in " \t":
                        out.pop()
                    out.append(":")
                    line_code += ":"
                stack.append("block")
                i += 1
                if peek_nonspace(i) not in ("", "\n", "}"):
                    out.append("\n")
                    line_code = ""
                    emit_indent()
                continue
            else:
                if at_line_start():
                    emit_indent()
                out.append("{")
                line_code += "{"
                stack.append("dict")
                i += 1
                continue

        if c == "}":
            kind = stack.pop() if stack else "block"
            i += 1

            if kind == "dict":
                if at_line_start():
                    emit_indent()
                out.append("}")
                line_code += "}"
                continue

            while i < n and source[i] in " \t":
                i += 1

            if i < n and source[i] != "\n":
                after = rest_of_line_stripped(i)
                if CONTINUATION.match(after):
                    if line_code.strip() or not at_line_start():
                        out.append("\n")
                    line_code = ""
                    emit_indent()
                    continue

            if i < n and source[i] == "\n":
                line_code = ""
            elif i < n:
                if line_code.strip():
                    out.append("\n")
                line_code = ""
            continue

        if at_line_start():
            emit_indent()
        out.append(c)
        line_code += c
        i += 1

    return "".join(out)


def _prepare_sys_path(filename: str | None) -> list[str]:
    added: list[str] = []
    paths = [str(PROJECT_ROOT), str(LANGUAGE_DIR), str(Path.cwd())]

    if filename and filename != "<simplelang>":
        paths.insert(0, str(Path(filename).resolve().parent))

    for p in paths:
        if p not in sys.path:
            sys.path.insert(0, p)
            added.append(p)
    return added


def execute(source: str, filename: str = "<simplelang>", show_transpile: bool = False) -> None:
    _register_simplelang_package()
    python_code = transpile(source)

    if show_transpile:
        print("----- transpiled python -----")
        print(python_code, end="" if python_code.endswith("\n") else "\n")
        print("-----------------------------\n")

    added = _prepare_sys_path(filename)
    module_globals = {
        "__name__": "__main__",
        "__file__": str(Path(filename).resolve()) if filename != "<simplelang>" else filename,
        "__package__": None,
        "__builtins__": __builtins__,
    }

    try:
        code_obj = compile(python_code, filename, "exec")
        exec(code_obj, module_globals)
    finally:
        for p in added:
            try:
                sys.path.remove(p)
            except ValueError:
                pass


def run_file(path: str | Path, show_transpile: bool = False) -> None:
    path = Path(path).resolve()
    source = path.read_text(encoding="utf-8")
    execute(source, filename=str(path), show_transpile=show_transpile)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: sl <file.sl>")
        print("   or: python3 language/executor.py <file.sl>")
        sys.exit(1)
    run_file(sys.argv[1])