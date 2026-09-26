"""
Region registry + locale profile.

Geography that used to be hard-coded (German Bundesländer, the `germany`
basemap, Aken as default centre, PEGELONLINE/DWD providers) lives in
backend/data/regions.json.  Deployments can add extracts or change defaults
in data/regions.local.json (merged on top) and pick a profile / override
individual keys under settings.region in data/settings.json.

Effective locale config (see effective_locale()):

    profile defaults  <-  settings["region"] overrides

With no settings the "de" profile is used, so existing installs behave as
before.
"""
import json
from pathlib import Path
from typing import Optional

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_REGISTRY_FILE = _DATA_DIR / "regions.json"
_LOCAL_FILE = _DATA_DIR / "regions.local.json"
_SETTINGS_FILE = _DATA_DIR / "settings.json"

DEFAULT_PROFILE = "de"

_registry: Optional[dict] = None


def _load_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"⚠️ regions: cannot read {path.name}: {e}")
        return {}


def registry(reload: bool = False) -> dict:
    """{'profiles': {...}, 'regions': [...]} — base file merged with local overrides."""
    global _registry
    if _registry is not None and not reload:
        return _registry
    base = _load_json(_REGISTRY_FILE)
    local = _load_json(_LOCAL_FILE)
    profiles = {**base.get("profiles", {}), **local.get("profiles", {})}
    by_id = {r["id"]: r for r in base.get("regions", []) if "id" in r}
    for r in local.get("regions", []):
        if "id" in r:
            by_id[r["id"]] = {**by_id.get(r["id"], {}), **r}
    _registry = {"profiles": profiles, "regions": list(by_id.values())}
    return _registry


def list_regions(profile: Optional[str] = None) -> list:
    regs = registry()["regions"]
    if profile:
        regs = [r for r in regs if r.get("profile") == profile]
    return regs


def get_region(region_id: str) -> Optional[dict]:
    for r in registry()["regions"]:
        if r["id"] == region_id:
            return r
    return None


def region_name(region_id: str) -> str:
    """Display name for a Geofabrik extract id; falls back to a prettified id."""
    r = get_region(region_id)
    if r and r.get("name"):
        return r["name"]
    return region_id.replace("-", " ").replace("_", " ").title()


def _region_settings() -> dict:
    s = _load_json(_SETTINGS_FILE).get("region", {})
    return s if isinstance(s, dict) else {}


def effective_locale() -> dict:
    """Profile defaults overlaid with settings.region."""
    profiles = registry()["profiles"]
    overrides = _region_settings()
    profile_id = overrides.get("profile") or DEFAULT_PROFILE
    profile = profiles.get(profile_id) or profiles.get(DEFAULT_PROFILE) or {}
    merged = {**profile, **{k: v for k, v in overrides.items() if k != "profile"}}
    merged["profile"] = profile_id
    merged.setdefault("language", "de")
    merged.setdefault("units", "metric")
    merged.setdefault("defaultBasemap", "germany")
    merged.setdefault("defaultCenter", {"lat": 51.855, "lon": 12.046})
    merged.setdefault("defaultZoom", 13)
    return merged


def default_basemap() -> str:
    return effective_locale()["defaultBasemap"]


def save_region_settings(update: dict) -> dict:
    """Merge `update` into settings.region and return the new effective locale."""
    settings = _load_json(_SETTINGS_FILE)
    region = settings.get("region", {})
    if not isinstance(region, dict):
        region = {}
    region.update({k: v for k, v in update.items() if v is not None})
    settings["region"] = region
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
    return effective_locale()
