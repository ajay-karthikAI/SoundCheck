"""Load immutable SQL statements by resource name."""

from importlib import resources


def load_sql(name: str) -> str:
    """Return a named SQL resource from the package."""
    if not name.endswith(".sql") or "/" in name or "\\" in name:
        msg = f"Invalid SQL resource name: {name!r}"
        raise ValueError(msg)
    return resources.files("soundcheck.sql").joinpath(name).read_text(encoding="utf-8")

