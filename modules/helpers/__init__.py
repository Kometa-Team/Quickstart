"""helpers package — decomposed from the original monolithic helpers.py.

This package re-exports all functions that were previously available
via ``from modules import helpers``.  Submodules are loaded on demand;
``helpers.foo()`` works exactly as before regardless of which submodule
``foo`` lives in.
"""

from __future__ import annotations

# Import everything from the legacy module first (backward compat).
from ._legacy import *  # noqa: F403

# Private helpers used by tests and other modules.
from ._zip_update import (  # noqa: F401
    _get_upstream_sha,
    _download_zip,
    _extract_zip_bytes,
    _backup_kometa_runtime_assets,
    _restore_kometa_runtime_assets,
    _cleanup_kometa_backup,
    _ensure_venv,
    _pip_install,
)

# Private helpers from other submodules (not re-exported via `*` due to underscore prefix).
from ._file_utils import _directory_tree_signature  # noqa: F401

# Then import from smaller, focused submodules.  Any names they export
# will override legacy definitions (in case of a future rename).
from ._cli import *  # noqa: F403
from ._templates import *  # noqa: F403
from ._fonts import *  # noqa: F403
from ._overlays import *  # noqa: F403
from ._artifacts import *  # noqa: F403
from ._plex_cache import *  # noqa: F403
from ._misc import *  # noqa: F403
from ._restart import *  # noqa: F403
from ._redact import *  # noqa: F403
from ._file_utils import *  # noqa: F403
from ._settings import *  # noqa: F403
from ._git import *  # noqa: F403
from ._forms import *  # noqa: F403
from ._os import *  # noqa: F403
from ._schema import *  # noqa: F403
from ._version import *  # noqa: F403
from ._qs_update import *  # noqa: F403
from ._update_cache import *  # noqa: F403
from ._install_mode import *  # noqa: F403
from ._kometa_version import *  # noqa: F403
from ._pid import *  # noqa: F403
from ._paths import *  # noqa: F403
from ._zip_update import *  # noqa: F403
