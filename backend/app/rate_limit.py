"""Rate limits, kept in memory. That suits one server process; running several would need
shared storage such as Redis, because each process would otherwise count on its own."""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.auth import bearer_token
from app.config import get_settings
from app.security import read_token

LOGIN_LIMIT = "10/minute"
REGISTER_LIMIT = "5/minute"
# These use shared_limit. A plain limit is counted per URL, so a user would get a fresh
# allowance on every article.
COMMENT_LIMIT = "10/minute"
VOTE_LIMIT = "60/minute"


def user_or_ip(request: Request) -> str:
    """The logged-in user, or the IP address if the token can't be read. Protected routes have
    already rejected bad tokens by the time this runs, so IP is only a fallback."""
    user_id = read_token(bearer_token(request) or "")
    return f"user:{user_id}" if user_id else f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=get_remote_address,
    strategy="moving-window",
    enabled=get_settings().rate_limits_enabled,
)
