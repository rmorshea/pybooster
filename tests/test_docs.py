import tomllib
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
PYPROJECT_TOML_FILE = ROOT_DIR / "pyproject.toml"
LINE_LENGTH = 80
EXAMPLES = [
    ex
    for ex in find_examples(DOCS_DIR, SRC_DIR)
    if ex.prefix_settings().get("test", "").lower() != "false"
]


def get_dict_path(data: dict, path: str) -> Any:
    for key in path.split("."):
        data = data[key]
    return data


@pytest.fixture(scope="module")
def ruff_ignore() -> list[str]:
    data = tomllib.loads(PYPROJECT_TOML_FILE.read_text())
    per_file_ignores = get_dict_path(data, "tool.ruff.lint.per-file-ignores")
    ignores = get_dict_path(data, "tool.ruff.lint.ignore")
    return per_file_ignores["**.md"] + ignores


@pytest.mark.parametrize("example", EXAMPLES, ids=str)
def test_docstrings(
    example: CodeExample, eval_example: EvalExample, ruff_ignore: list[str]
):
    eval_example.set_config(
        ruff_ignore=ruff_ignore,
        quotes="double",
        ruff_select=["ALL"],
        line_length=LINE_LENGTH,
    )
    if eval_example.update_examples:  # nocov
        eval_example.run_print_update(example)
        eval_example.format_black(example)
        eval_example.format_ruff(example)
    else:
        eval_example.run_print_check(example)
        eval_example.lint(example)
