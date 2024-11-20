from pathlib import Path

import pytest
from pytest_examples import CodeExample
from pytest_examples import EvalExample
from pytest_examples import find_examples

HERE = Path(__file__).parent
ROOT_DIR = HERE.parent
DOCS_DIR = ROOT_DIR / "docs"
SRC_DIR = ROOT_DIR / "src"


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
    if eval_example.update_examples:  # nocov
        eval_example.run_print_update(example)
    else:
        eval_example.run_print_check(example)
