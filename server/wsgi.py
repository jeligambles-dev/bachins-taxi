"""gunicorn entrypoint: `gunicorn server.wsgi:app`. Tests must not import this."""
import sys
from pathlib import Path

# build/ modules (content, texts, data, posts, build) are imported as top-level.
_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_ROOT), str(_ROOT / "build")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from server.app import create_app_from_env  # noqa: E402

app = create_app_from_env()
