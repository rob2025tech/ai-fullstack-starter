"""Validate that requirements-lock.txt exactly pins every dependency declared in pyproject.toml.

Requires Python 3.11+ (tomllib stdlib). The backend declares requires-python >= 3.12.
"""

import re
from pathlib import Path

try:
    import tomllib  # stdlib: Python 3.11+
except ImportError:  # pragma: no cover — Python 3.10 fallback (CI only)
    import tomli as tomllib  # type: ignore[no-redef]

_BACKEND_DIR = Path(__file__).parent.parent
_PYPROJECT = _BACKEND_DIR / "pyproject.toml"
_LOCK = _BACKEND_DIR / "requirements-lock.txt"

# Dev-only packages intentionally excluded from lock validation.
# Add entries here (normalized names) with a brief inline explanation if a
# declared dev dependency is a meta-package or alias that resolves differently.
_DEV_EXCLUSIONS: frozenset[str] = frozenset()

# Packages named in the acceptance criteria that must appear with exact == pins.
_REQUIRED_PINNED: tuple[str, ...] = (
    "fastapi",
    "uvicorn",
    "pydantic",
    "pydantic-settings",
    "httpx",
    "pytest",
    "pytest-asyncio",
    "ruff",
    "pyyaml",
)


def _normalize(name: str) -> str:
    """PEP 503 name normalization: lowercase, collapse runs of [-_.] to a single hyphen."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _pinned_in_lock(lock_path: Path) -> dict[str, str]:
    """Return {normalized_name: version} for every exactly-pinned line in the lock file.

    Handles:
    - Comment lines (start with #) and blank lines — skipped
    - Environment markers (``; python_version >= "3.8"``) — stripped before parsing
    - Extras in package name (``package[extra]``) — extras stripped from name
    - Only ``==`` pins are returned; ``>=``, ``~=``, ``>``, ``<`` are not included
    """
    pinned: dict[str, str] = {}
    for raw_line in lock_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Strip environment marker (everything after `;`)
        line = line.split(";")[0].strip()
        # Strip inline hash options (``--hash=...``)
        line = line.split("--")[0].strip()
        if "==" not in line:
            continue
        name_part, version_part = line.split("==", 1)
        # Strip extras: ``package[extra]`` → ``package``
        bare_name = name_part.split("[")[0].strip()
        if not bare_name:
            continue
        normalized = _normalize(bare_name)
        pinned[normalized] = version_part.strip()
    return pinned


def _declared_names(pyproject_path: Path) -> tuple[list[str], list[str]]:
    """Return (runtime_names, dev_names) as normalized package name strings."""
    with pyproject_path.open("rb") as fh:
        data = tomllib.load(fh)

    def _extract_name(specifier: str) -> str:
        # Split on first PEP 508 version operator or whitespace
        raw = re.split(r"[>=<!~\s\[]", specifier, maxsplit=1)[0]
        return _normalize(raw)

    runtime = [
        _extract_name(s) for s in data["project"].get("dependencies", [])
    ]
    dev = [
        _extract_name(s)
        for s in data["project"].get("optional-dependencies", {}).get("dev", [])
    ]
    return runtime, dev


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_lock_file_exists() -> None:
    assert _LOCK.exists(), f"Lock file not found: {_LOCK}"
    assert _PYPROJECT.exists(), f"pyproject.toml not found: {_PYPROJECT}"


def test_runtime_deps_exactly_pinned() -> None:
    """Every runtime dependency in pyproject.toml must have an exact == pin in the lock."""
    pinned = _pinned_in_lock(_LOCK)
    runtime_names, _ = _declared_names(_PYPROJECT)

    missing = [n for n in runtime_names if n not in pinned]
    assert not missing, (
        f"Runtime dependencies declared in {_PYPROJECT} are not exactly pinned "
        f"in {_LOCK}: {missing}"
    )


def test_dev_deps_exactly_pinned_or_excluded() -> None:
    """Every dev dependency in pyproject.toml must have an exact == pin in the lock
    unless listed in _DEV_EXCLUSIONS."""
    pinned = _pinned_in_lock(_LOCK)
    _, dev_names = _declared_names(_PYPROJECT)

    missing = [
        n for n in dev_names if n not in pinned and n not in _DEV_EXCLUSIONS
    ]
    assert not missing, (
        f"Dev dependencies declared in {_PYPROJECT} are not exactly pinned "
        f"in {_LOCK} (add to _DEV_EXCLUSIONS if intentionally excluded): {missing}"
    )


def test_required_packages_pinned_exactly() -> None:
    """Spot-check: the acceptance-criteria packages must each have an exact == pin."""
    pinned = _pinned_in_lock(_LOCK)
    missing = [pkg for pkg in _REQUIRED_PINNED if pkg not in pinned]
    assert not missing, (
        f"Required packages are not exactly pinned in {_LOCK}: {missing}"
    )


def test_no_unpinned_runtime_deps() -> None:
    """No declared runtime dep is represented by a range (>=, ~=, >, <) in the lock."""
    lock_text = _LOCK.read_text(encoding="utf-8")
    runtime_names, _ = _declared_names(_PYPROJECT)
    bad: list[str] = []
    for line in lock_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for name in runtime_names:
            # Check for range pins using the un-normalized lock line
            if re.match(rf"{re.escape(name)}\s*[><!~]", stripped, re.IGNORECASE):
                bad.append(stripped)
    assert not bad, (
        f"Runtime dependencies found with non-exact pins in {_LOCK}: {bad}"
    )


def test_no_editable_installs_in_lock() -> None:
    """The lock file must not contain editable installs (-e) or absolute paths."""
    lock_text = _LOCK.read_text(encoding="utf-8")
    for line in lock_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        assert not stripped.startswith("-e "), (
            f"Editable install found in {_LOCK}: {stripped!r}"
        )
        assert not stripped.startswith("/"), (
            f"Absolute path found in {_LOCK}: {stripped!r}"
        )


def test_pinned_versions_satisfy_lower_bounds() -> None:
    """Pinned versions must satisfy the declared lower-bound constraints."""
    from packaging.version import Version

    with _PYPROJECT.open("rb") as fh:
        data = tomllib.load(fh)

    pinned = _pinned_in_lock(_LOCK)
    all_deps = data["project"].get("dependencies", []) + data["project"].get(
        "optional-dependencies", {}
    ).get("dev", [])

    violations: list[str] = []
    for spec in all_deps:
        # Extract name and lower bound from specifier like "fastapi>=0.115"
        m = re.match(r"^([A-Za-z0-9_./-]+)\s*>=\s*([^\s,]+)", spec)
        if not m:
            continue
        name = _normalize(m.group(1))
        lower = m.group(2)
        if name not in pinned:
            continue
        if Version(pinned[name]) < Version(lower):
            violations.append(
                f"{name}: pinned {pinned[name]} < declared lower bound {lower}"
            )

    assert not violations, (
        f"Pinned versions below declared lower bounds in {_LOCK}: {violations}"
    )
