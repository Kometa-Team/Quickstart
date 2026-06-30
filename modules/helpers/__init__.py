"""helpers package — decomposed from the original monolithic helpers.py.

This package re-exports all functions that were previously available
via ``from modules import helpers``.  Submodules are loaded on demand;
``helpers.foo()`` works exactly as before regardless of which submodule
``foo`` lives in.
"""

from __future__ import annotations

# Import everything from the legacy module first (backward compat).
from ._legacy import *  # noqa: F403

# Then import from smaller, focused submodules.  Any names they export
# will override legacy definitions (in case of a future rename).
from ._paths import *  # noqa: F403
