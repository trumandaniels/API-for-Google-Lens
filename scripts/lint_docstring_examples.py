#!/usr/bin/env python3

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

APP_PACKAGE = "app"
EXAMPLE_MARKER = "Example:"


@dataclass(frozen=True)
class DocumentedObject:
    """Production class or function that must carry an executable example."""

    repo_relative_path: str
    qualname: str
    line_number: int
    docstring: str | None


class DocstringExampleLintError(RuntimeError):
    """Raised when docstring example linting cannot inspect a source file."""


def main() -> int:
    """Run the docstring example lint from the repository root."""

    repo_root = Path(__file__).resolve().parent.parent
    try:
        problems = lint_docstring_examples(repo_root)
    except DocstringExampleLintError as error:
        print(f"Docstring example lint failed: {error}", file=sys.stderr)
        return 1
    if problems:
        print("Docstring example lint failed:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1
    print("Docstring example lint passed")
    return 0


def lint_docstring_examples(repo_root: Path) -> list[str]:
    """Return problems for public production objects missing examples.

    Args:
        repo_root: Repository root containing the `app/` package.

    Returns:
        Human-readable lint problems.
    """

    problems: list[str] = []
    for documented_object in iter_documented_objects(repo_root / APP_PACKAGE, repo_root):
        if not documented_object.docstring:
            problems.append(format_problem(documented_object, "is missing a docstring"))
            continue
        if EXAMPLE_MARKER not in documented_object.docstring:
            problems.append(format_problem(documented_object, "is missing an `Example:` section"))
    return problems


def iter_documented_objects(package_root: Path, repo_root: Path) -> list[DocumentedObject]:
    """Discover public top-level classes/functions and public class methods.

    Args:
        package_root: Root package to scan.
        repo_root: Repository root used for stable relative paths.

    Returns:
        Objects that are part of the production documentation surface. Private
        helpers, nested local functions, and dunder methods are intentionally
        excluded.
    """

    objects: list[DocumentedObject] = []
    for source_path in sorted(package_root.rglob("*.py")):
        if source_path.name == "__init__.py":
            continue
        try:
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
        except SyntaxError as error:
            relative_path = source_path.relative_to(repo_root).as_posix()
            raise DocstringExampleLintError(f"`{relative_path}` could not be parsed: {error}") from error
        relative_path = source_path.relative_to(repo_root).as_posix()
        objects.extend(iter_module_objects(tree, relative_path))
    return objects


def iter_module_objects(tree: ast.Module, repo_relative_path: str) -> list[DocumentedObject]:
    """Return documented objects for one parsed module.

    Args:
        tree: Parsed module AST.
        repo_relative_path: Stable path used in lint messages.

    Returns:
        Public top-level classes/functions plus public methods on public
        classes.
    """

    objects: list[DocumentedObject] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and is_public_name(node.name):
            objects.append(to_documented_object(repo_relative_path, node.name, node))
            continue
        if isinstance(node, ast.ClassDef) and is_public_name(node.name):
            objects.append(to_documented_object(repo_relative_path, node.name, node))
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and is_public_name(child.name):
                    objects.append(to_documented_object(repo_relative_path, f"{node.name}.{child.name}", child))
    return objects


def is_public_name(name: str) -> bool:
    """Return whether a class or function name belongs to the documented API."""

    return not name.startswith("_")


def to_documented_object(
    repo_relative_path: str,
    qualname: str,
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
) -> DocumentedObject:
    """Convert an AST node to a lintable documentation record."""

    return DocumentedObject(
        repo_relative_path=repo_relative_path,
        qualname=qualname,
        line_number=node.lineno,
        docstring=ast.get_docstring(node),
    )


def format_problem(documented_object: DocumentedObject, detail: str) -> str:
    """Build a stable lint message for one missing example problem."""

    return (
        f"`{documented_object.repo_relative_path}` line {documented_object.line_number} "
        f"`{documented_object.qualname}` {detail}."
    )


if __name__ == "__main__":
    raise SystemExit(main())
