from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "lint_docstring_examples.py"
MODULE_SPEC = importlib.util.spec_from_file_location("lint_docstring_examples", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load module from {MODULE_PATH}")
lint_docstring_examples = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = lint_docstring_examples
MODULE_SPEC.loader.exec_module(lint_docstring_examples)


class DocstringExampleLintTests(unittest.TestCase):
    def test_accepts_public_objects_with_examples(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            app = repo_root / "app"
            app.mkdir()
            (app / "sample.py").write_text(
                '''
class Parser:
    """Parse values.

    Example:
        >>> Parser().parse("value")
        'value'
    """

    def parse(self, raw_value: str) -> str:
        """Return the value.

        Example:
            >>> Parser().parse("value")
            'value'
        """
        return raw_value


def build_value() -> str:
    """Build one value.

    Example:
        >>> build_value()
        'value'
    """
    return "value"
'''.strip(),
                encoding="utf-8",
            )

            problems = lint_docstring_examples.lint_docstring_examples(repo_root)

        self.assertEqual(problems, [])

    def test_rejects_public_objects_without_examples(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            app = repo_root / "app"
            app.mkdir()
            (app / "sample.py").write_text(
                '''
class Parser:
    """Parse values."""

    def parse(self, raw_value: str) -> str:
        """Return the value."""
        return raw_value
'''.strip(),
                encoding="utf-8",
            )

            problems = lint_docstring_examples.lint_docstring_examples(repo_root)

        self.assertEqual(len(problems), 2)
        self.assertIn("`Parser` is missing an `Example:` section", problems[0])
        self.assertIn("`Parser.parse` is missing an `Example:` section", problems[1])

    def test_ignores_private_and_nested_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            app = repo_root / "app"
            app.mkdir()
            (app / "sample.py").write_text(
                '''
def public() -> str:
    """Return a value.

    Example:
        >>> public()
        'value'
    """
    def nested() -> str:
        return "nested"
    return "value"


def _private() -> str:
    return "private"
'''.strip(),
                encoding="utf-8",
            )

            problems = lint_docstring_examples.lint_docstring_examples(repo_root)

        self.assertEqual(problems, [])

    def test_repository_app_docstrings_have_examples(self) -> None:
        problems = lint_docstring_examples.lint_docstring_examples(REPO_ROOT)
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
