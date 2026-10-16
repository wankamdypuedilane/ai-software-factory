"""A compact index of what each workspace module exports.

The workspace snapshot is budgeted, so with many files most of them are
cut from the prompt. A real run then imported `prepareTestDatabase` from
`tests/helpers/test-database.mjs`, which does not export it (another
helper does), and repeated the same mistake on retry because neither
helper was visible. The index costs one line per module and is never
dropped, so the model always knows which module exports which name.
"""

from __future__ import annotations

import re


SCRIPT_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")
PYTHON_SUFFIXES = (".py",)

MAX_NAMES_PER_MODULE = 40
MAX_INDEX_CHARS = 20000
MAX_SIGNATURE_CHARS = 200

_JS_DECLARATION = re.compile(
    r"^\s*export\s+(?:declare\s+)?(?:abstract\s+)?"
    r"(?:async\s+)?(?:function\*?|class|const|let|var|interface|type|enum)"
    r"\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)
_JS_DEFAULT = re.compile(r"^\s*export\s+default\b", re.MULTILINE)
_JS_LIST = re.compile(
    r"^\s*export\s+(?:type\s+)?\{([^}]*)\}(?:\s*from\s*['\"]([^'\"]+)['\"])?",
    re.MULTILINE,
)
_JS_STAR = re.compile(
    r"^\s*export\s+\*\s+(?:as\s+([A-Za-z_$][\w$]*)\s+)?from\s*['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)
_CJS = re.compile(r"\b(?:module\.)?exports\.([A-Za-z_$][\w$]*)\s*=")
_PY = re.compile(r"^(?:async\s+def|def|class)\s+([A-Za-z_]\w*)", re.MULTILINE)
_PY_ASSIGN = re.compile(r"^([A-Z_][A-Z0-9_]*)\s*(?::[^=\n]+)?=", re.MULTILINE)


_JS_FUNCTION = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:declare\s+)?(?:async\s+)?function\*?\s+"
    r"([A-Za-z_$][\w$]*)\s*(?:<[^>]*>)?\s*\(",
    re.MULTILINE,
)
_JS_ARROW = re.compile(
    r"^\s*export\s+const\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:async\s+)?\(",
    re.MULTILINE,
)
_PY_DEF = re.compile(r"^(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(", re.MULTILINE)


def _parameters(content: str, open_index: int) -> str | None:
    """Return the balanced parameter list starting at `(`, collapsed.

    A real unit called createBookingService with five positional
    arguments while it takes four, the last an options object: names
    alone did not say how to call a function.
    """

    depth = 0

    for index in range(open_index, min(len(content), open_index + 2000)):
        char = content[index]

        if char in "([{<":
            depth += 1
        elif char in ")]}>" and not (char == ">" and content[index - 1] == "="):
            depth -= 1

            if depth == 0:
                text = re.sub(r"\s+", " ", content[open_index:index + 1])
                text = text.replace("( ", "(").replace(" )", ")")

                if len(text) > MAX_SIGNATURE_CHARS:
                    text = text[: MAX_SIGNATURE_CHARS - 2] + "…)"

                return text

    return None


def _signatures(content: str, pattern: re.Pattern[str]) -> dict[str, str]:
    signatures: dict[str, str] = {}

    for match in pattern.finditer(content):
        params = _parameters(content, match.end() - 1)

        if params is not None:
            signatures.setdefault(match.group(1), params)

    return signatures


def _with_signatures(names: list[str], signatures: dict[str, str]) -> list[str]:
    return [f"{name}{signatures[name]}" if name in signatures else name for name in names]


def _js_exports(content: str) -> list[str]:
    names: list[str] = []

    names.extend(
        _with_signatures(
            _JS_DECLARATION.findall(content),
            {**_signatures(content, _JS_ARROW), **_signatures(content, _JS_FUNCTION)},
        )
    )

    for body, source in _JS_LIST.findall(content):
        for item in body.split(","):
            item = item.strip()

            if not item:
                continue

            exported = re.split(r"\s+as\s+", item)[-1].strip()
            exported = exported.removeprefix("type ").strip()

            if exported:
                names.append(
                    f"{exported} (re-exported from {source})"
                    if source
                    else exported
                )

    for alias, source in _JS_STAR.findall(content):
        names.append(
            f"{alias} (namespace of {source})"
            if alias
            else f"* (everything from {source})"
        )

    names.extend(_CJS.findall(content))

    if _JS_DEFAULT.search(content):
        names.append("default")

    return names


def _python_exports(content: str) -> list[str]:
    names = _with_signatures(_PY.findall(content), _signatures(content, _PY_DEF))
    names += _PY_ASSIGN.findall(content)
    return [name for name in names if not name.startswith("_")]


def module_exports(path: str, content: str) -> list[str] | None:
    """Return the names a module exports, or None for non-code files."""

    lowered = path.lower()

    if lowered.endswith(SCRIPT_SUFFIXES):
        names = _js_exports(content)
    elif lowered.endswith(PYTHON_SUFFIXES):
        names = _python_exports(content)
    else:
        return None

    return list(dict.fromkeys(names))


def build_export_index(files: dict[str, str]) -> list[str]:
    """Return one line per code module: its path and exported names."""

    lines: list[str] = []
    used = 0

    for path in sorted(files):
        names = module_exports(path, files[path])

        if names is None:
            continue

        if not names:
            shown = "(no exports)"
        else:
            shown = ", ".join(names[:MAX_NAMES_PER_MODULE])

            if len(names) > MAX_NAMES_PER_MODULE:
                shown += f", … (+{len(names) - MAX_NAMES_PER_MODULE} more)"

        line = f"- {path}: {shown}"

        if used + len(line) > MAX_INDEX_CHARS:
            lines.append("- [further modules omitted to stay within the context budget]")
            break

        lines.append(line)
        used += len(line)

    return lines
