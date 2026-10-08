from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# Disabled whenever settings.debug is true — same convention used for E2E fake-AI and skipped
# new-user notifications: debug=true means local/test, never prod, so CI/e2e hammering an
# endpoint repeatedly (multiple pushes/day against the shared test deploy) can't trip its own
# rate limit. Real per-IP enforcement only turns on where settings.debug=false, i.e. prod.
limiter = Limiter(key_func=get_remote_address, enabled=not settings.debug)
