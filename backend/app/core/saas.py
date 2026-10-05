import os
from pathlib import Path

from olympus.saas.platform import SaaSPlatform


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CLOUD_DATA_DIR = Path(os.environ.get("OLYMPUS_CLOUD_DATA_DIR", _REPO_ROOT / ".olympus" / "cloud"))
PLATFORM = SaaSPlatform(_CLOUD_DATA_DIR / "saas" / "platform.sqlite3")
