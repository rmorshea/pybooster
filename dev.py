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


@click.group()
def dev():
    """A collection of development commands."""


@dev.group("test")
def test():
    """Test commands."""


@test.command("lib")
@click.argument("args", nargs=-1)
def test_lib(args: list[str]):
    """Run tests."""
    run(["pytest", "-v", *args])


@test.command("cov")
@click.option("--no-test", is_flag=True, help="Skip running tests.")
@click.option("--no-report", is_flag=True, help="Skip generating coverage report.")
@click.argument("args", nargs=-1)
def test_cov(no_test: bool, no_report: bool, args: list[str]):
    """Run tests with coverage."""
    if not no_test:
        run(["coverage", "run", "-m", "pytest", "-v", *args])
    if not no_report:
        run(["coverage", "combine"], check=False)
        run(["coverage", "report"])
        run(["coverage", "xml"])
        run(["diff-cover", "coverage.xml", "--config-file", "pyproject.toml"])


@dev.group("lint", chain=True)
def lint():
    """Lint commands."""


@lint.command("types")
@click.argument("args", nargs=-1)
def lint_types(args: list[str]):
    """Type check."""
    run(["pyright", *args])


@lint.command("style")
@click.option("--fix", is_flag=True, help="Fix style issues.")
def lint_style(fix: bool):
    """Style check."""
    if fix:
        run(["black", "."])
        run(["ruff", "check", "--fix"])
    else:
        run(["black", "--check", "--diff", "."])
        run(["ruff", "check"])


# build = "mkdocs build -f docs/mkdocs.yml"
# publish = "mkdocs gh-deploy -f docs/mkdocs.yml"
# fix = "pytest tests/test_docs.py {args:} --update-examples"
# serve = "mkdocs serve -f docs/mkdocs.yml"


@dev.group("docs")
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
    dev()
