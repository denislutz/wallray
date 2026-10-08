import json
from collections.abc import Callable
from pathlib import Path

_catalog_cache: dict[tuple[Path, str], dict[str, str]] = {}


def load_catalog(locales_dir: Path, locale: str) -> dict[str, str]:
    key = (locales_dir, locale)
    if key not in _catalog_cache:
        path = locales_dir / f"{locale}.json"
        _catalog_cache[key] = json.loads(path.read_text()) if path.exists() else {}
    return _catalog_cache[key]


def translator(locales_dir: Path, locale: str) -> Callable[[str], str]:
    catalog = load_catalog(locales_dir, locale)
    return lambda msg: catalog.get(msg, msg)
