"""Stage the read-only FastAPI service and immutable DuckDB for Vercel."""

from __future__ import annotations

import shutil
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = Path(__file__).with_name("vercel_api_template")
STAGING_ROOT = REPOSITORY_ROOT / ".vercel-api"
DATABASE_PATH = REPOSITORY_ROOT / "data" / "soundcheck.duckdb"


def prepare_vercel_api() -> Path:
    """Create a minimal, reproducible Vercel deployment directory."""
    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(
            "data/soundcheck.duckdb is required before preparing the API deployment"
        )
    if STAGING_ROOT.parent != REPOSITORY_ROOT or STAGING_ROOT.name != ".vercel-api":
        raise RuntimeError("refusing to replace an unexpected staging directory")

    if STAGING_ROOT.exists():
        shutil.rmtree(STAGING_ROOT)
    shutil.copytree(TEMPLATE_ROOT, STAGING_ROOT)

    package_root = STAGING_ROOT / "soundcheck"
    package_root.mkdir()
    shutil.copy2(REPOSITORY_ROOT / "soundcheck" / "__init__.py", package_root)
    shutil.copy2(REPOSITORY_ROOT / "soundcheck" / "taxonomy.py", package_root)
    _copy_python_package(
        REPOSITORY_ROOT / "soundcheck" / "api",
        package_root / "api",
    )
    _copy_sql_package(
        REPOSITORY_ROOT / "soundcheck" / "sql",
        package_root / "sql",
    )

    staged_config = STAGING_ROOT / "config"
    staged_config.mkdir()
    shutil.copy2(
        REPOSITORY_ROOT / "config" / "genre_canonical.yml",
        staged_config / "genre_canonical.yml",
    )

    staged_data = STAGING_ROOT / "data"
    staged_data.mkdir()
    shutil.copy2(DATABASE_PATH, staged_data / DATABASE_PATH.name)
    return STAGING_ROOT


def _copy_python_package(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def _copy_sql_package(source: Path, destination: Path) -> None:
    destination.mkdir()
    shutil.copy2(source / "__init__.py", destination)
    shutil.copy2(source / "loader.py", destination)
    for sql_path in sorted(source.glob("api_*.sql")):
        shutil.copy2(sql_path, destination)


def main() -> None:
    staged_path = prepare_vercel_api()
    print(staged_path)


if __name__ == "__main__":
    main()
