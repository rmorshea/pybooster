from pathlib import Path
from typing import Any

import pytest
from pytest_examples import CodeExample
from pytest_examples import EvalExample
from pytest_examples import find_examples

HERE = Path(__file__).parent
ROOT_DIR = HERE.parent
DOCS_DIR = ROOT_DIR / "docs"
SRC_DIR = ROOT_DIR / "src"

module_globals_by_ex: dict[Path, dict[str, Any]] = {}


@pytest.mark.parametrize(
    "example",
    [
        ex
        for ex in find_examples(DOCS_DIR, SRC_DIR)
        if ex.prefix_settings().get("test", "").lower() != "false"
    ],
    ids=str,
)
def test_docstrings(example: CodeExample, eval_example: EvalExample):
    mod_globals = module_globals_by_ex.setdefault(example.path, {})
    if eval_example.update_examples:  # nocov
        mod_globals.update(eval_example.run_print_update(example, module_globals=mod_globals))
    else:
        mod_globals.update(eval_example.run_print_check(example, module_globals=mod_globals))
