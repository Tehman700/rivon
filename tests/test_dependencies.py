"""Everything the application imports has to exist in the production image.

The image is built with `uv sync --no-dev`, so a package that is only a dev
dependency is simply absent there. Nothing in the test suite notices, because
the test environment has both — which is exactly how `httpx` reached production
as an unhandled 500 on the first real connect: the import sat inside a function,
so even importing the module looked fine.

This walks what `rivon/` actually imports and checks each third-party package is
declared as a runtime dependency.
"""

import ast
import sys
import tomllib
from importlib.metadata import packages_distributions
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = REPO_ROOT / "rivon"


def _declared_runtime_dependencies() -> set[str]:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    names = set()
    for spec in data["project"]["dependencies"]:
        # "sqlalchemy[asyncio]>=2.0.36" -> "sqlalchemy"
        name = spec.split("[")[0].split(">")[0].split("<")[0].split("=")[0].split(";")[0]
        names.add(name.strip().lower().replace("_", "-"))
    return names


def _imported_modules() -> dict[str, set[Path]]:
    """Top-level module names imported anywhere under `rivon/`, and by whom.

    Imports inside functions count: they are the ones that survive a module
    import and fail later, in front of a customer.
    """
    found: dict[str, set[Path]] = {}
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module] if node.module and node.level == 0 else []
            else:
                continue
            for name in names:
                found.setdefault(name.split(".")[0], set()).add(path.relative_to(REPO_ROOT))
    return found


def test_every_third_party_import_is_a_runtime_dependency() -> None:
    declared = _declared_runtime_dependencies()
    distributions = packages_distributions()
    offenders: list[str] = []

    for module, users in sorted(_imported_modules().items()):
        if module == "rivon" or module in sys.stdlib_module_names:
            continue
        # A module can come from a differently named distribution: `redis` from
        # "redis", but `jwt` from "pyjwt".
        provided_by = {d.lower().replace("_", "-") for d in distributions.get(module, [])}
        if not provided_by:
            offenders.append(f"{module} (not installed at all) — imported by {sorted(users)[0]}")
        elif not provided_by & declared:
            offenders.append(
                f"{module} comes from {sorted(provided_by)} which is not in "
                f"[project.dependencies] — imported by {sorted(users)[0]}"
            )

    assert offenders == [], (
        "these would be missing from the production image:\n  " + "\n  ".join(offenders)
    )


def test_the_check_would_notice_a_dev_only_dependency() -> None:
    """Guard the guard: prove the comparison is doing real work."""
    declared = _declared_runtime_dependencies()
    assert "httpx" in declared, "the outbound HTTP client must ship with the app"
    assert "pytest" not in declared, "test tooling must not be a runtime dependency"


@pytest.mark.parametrize("module", ["httpx", "cryptography"])
def test_the_packages_the_channels_need_are_declared(module: str) -> None:
    # Both are reached only from inside functions — httpx when a message is
    # sent, cryptography when a credential is sealed — so neither shows up as a
    # broken import at start-up.
    declared = _declared_runtime_dependencies()
    provided_by = {d.lower() for d in packages_distributions().get(module, [])}
    assert provided_by & declared, f"{module} is imported by rivon but not declared"
