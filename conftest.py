import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Each service directory (auth-api, movie_api, reservation_api) is put on
# sys.path via that service's own ini file's `pythonpath` setting, not
# hardcoded here — every service defines an identically-named `core`
# package, so only one can safely be importable in a given pytest process.
# Keeping this file service-agnostic avoids one service's path silently
# shadowing another's when running a different service's test suite.

# Must be set before any service's main (and its OTel setup) is ever
# imported — a root conftest.py is guaranteed by pytest to load before any
# test module.
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
