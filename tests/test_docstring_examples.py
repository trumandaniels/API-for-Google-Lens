from __future__ import annotations

import doctest
import importlib
import pkgutil
import unittest
from pathlib import Path

import app

REPO_ROOT = Path(__file__).resolve().parent.parent


def iter_app_module_names() -> list[str]:
    """Return importable production modules whose docstrings contain examples."""

    module_names: list[str] = []
    for module_info in pkgutil.walk_packages(app.__path__, prefix="app."):
        if module_info.ispkg:
            continue
        source_path = REPO_ROOT / Path(*module_info.name.split(".")).with_suffix(".py")
        if "Example:" in source_path.read_text(encoding="utf-8"):
            module_names.append(module_info.name)
    return sorted(module_names)


class DocstringExampleTests(unittest.TestCase):
    def test_app_docstring_examples_execute(self) -> None:
        failures: list[str] = []
        for module_name in iter_app_module_names():
            module = importlib.import_module(module_name)
            result = doctest.testmod(module, optionflags=doctest.ELLIPSIS)
            if result.failed:
                failures.append(f"{module_name}: {result.failed} failed out of {result.attempted}")

        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
