"""SearXNG-local TLS trust compatibility for the host SSL-inspection CA.

Norton Web/Mail Shield's generated local root is trusted by Windows, but Python
3.14/OpenSSL rejects it under VERIFY_X509_STRICT because Basic Constraints are
not marked critical. Keep verification enabled and trust only the mounted CA
bundle; relax just that strict encoding flag for this local container.
"""

from __future__ import annotations

import os
import ssl
from typing import Any


_create_default_context = ssl.create_default_context


def _porter_create_default_context(*args: Any, **kwargs: Any) -> ssl.SSLContext:
    context = _create_default_context(*args, **kwargs)
    if os.environ.get("PORTER_SEARXNG_RELAX_LOCAL_CA_STRICT") == "1":
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return context


ssl.create_default_context = _porter_create_default_context
