# ruff: noqa: S607,S603,S404,FBT001,D401,D103

import subprocess
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    run = subprocess.run
else:

    def run(*args, **kwargs):
        kwargs.setdefault("check", True)
        click.echo(click.style(" ".join(args[0]), bold=True))
        try:
            subprocess.run(*args, **kwargs)
        except subprocess.CalledProcessError as e:
            msg = f"Command failed with exit code {e.returncode}."
            raise click.Abort(msg) from None
        except FileNotFoundError as e:
            msg = f"File not found {e}"
            raise click.Abort(msg) from None


@click.group()
def main():
    """A collection of dev utilities."""


@main.command("test")
@click.option("--cov/--no-cov", default=True, help="Do not run tests with coverage.")
@click.option("--only-cov-report", is_flag=True, help="Only run coverage report.")
@click.argument("args", nargs=-1)
def test(args: list[str], cov: bool, only_cov_report: bool):
    """Test commands."""
    if only_cov_report:
        _cov_report()
        return
    if cov:
        run(["coverage", "run", "-m", "pytest", "-v", *args])
        _cov_report()
    else:
        run(["pytest", "-v", *args])


def _cov_report():
    run(["coverage", "combine"], check=False)
    run(["coverage", "report"])
    run(["coverage", "xml"])
    run(["diff-cover", "coverage.xml", "--config-file", "pyproject.toml"])


@main.command("lint")
@click.option("--check", is_flag=True, help="Check for linting issues without fixing.")
@click.option("--no-py-types", is_flag=True, help="Type check Python files.")
@click.option("--no-py-style", is_flag=True, help="Style check Python files.")
@click.option("--no-md-style", is_flag=True, help="Style check Markdown files.")
@click.option("--no-yml-style", is_flag=True, help="Style check YAML files.")
def lint(check: bool, no_py_types: bool, no_py_style: bool, no_md_style: bool, no_yml_style: bool):
    """Linting commands."""
    if not no_py_types:
        run(["pyright"])
    if not no_py_style:
        if check:
            run(["ruff", "format", "--check", "--diff"])
            run(["ruff", "check"])
        else:
            run(["ruff", "format"])
            run(["ruff", "check", "--fix"])
    if not no_md_style:
        if check:
            run(["mdformat", "--ignore-missing-references", "--check", "."])
        else:
            run(["mdformat", "--ignore-missing-references", "."])
    if not no_yml_style:
        if check:
            run(["yamlfix", "--check", "."])
        else:
            run(["yamlfix", "."])


@main.group("docs")
def docs():
    """Documentation commands."""


@docs.command("build")
def docs_build():
    """Build documentation."""
    run(["mkdocs", "build", "-f", "docs/mkdocs.yml"])


@docs.command("publish")
def docs_publish():
    """Publish documentation."""
    run(["mkdocs", "gh-deploy", "-f", "docs/mkdocs.yml"])


@docs.command("serve")
def docs_serve():
    """Serve documentation."""
    run(["mkdocs", "serve", "-f", "docs/mkdocs.yml"])


@docs.command("fix")
def fix():
    """Fix style issues."""
    run(["pytest", "tests/test_docs.py", "--update-examples"])


if __name__ == "__main__":
    main()
