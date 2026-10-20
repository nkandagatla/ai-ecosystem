"""Locate bundled data (core/, profiles/) and the ai-cloud-skills vendor checkout."""
import os
from pathlib import Path

PKG = Path(__file__).resolve().parent
# pipx/pip installs ship data under ai_ecosystem/_data; a git checkout uses the repo root.
ROOT = PKG / "_data" if (PKG / "_data" / "core").is_dir() else PKG.parent
CORE = ROOT / "core"
PROFILES = ROOT / "profiles"
LOCK = ROOT / "vendor.lock"
STATE_HOME = Path(os.environ.get("AI_ECOSYSTEM_HOME", Path.home() / ".ai-ecosystem"))


def vendor_dirs():
    """Candidate ai-cloud-skills checkouts, most specific first."""
    env = os.environ.get("AI_CLOUD_SKILLS_DIR")
    out = [Path(env)] if env else []
    return out + [ROOT / "vendor" / "ai-cloud-skills", STATE_HOME / "vendor" / "ai-cloud-skills"]


def vendor_dir():
    for d in vendor_dirs():
        if (d / "skills").is_dir():
            return d
    return None


def default_vendor_target():
    d = ROOT / "vendor"
    try:
        d.mkdir(parents=True, exist_ok=True)
        if os.access(d, os.W_OK):
            return d / "ai-cloud-skills"
    except OSError:
        pass
    return STATE_HOME / "vendor" / "ai-cloud-skills"
