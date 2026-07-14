import redis
import time
import math
import os
from dataclasses import dataclass
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Configure Redis connection
try:
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
    else:
        redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=0,
            decode_responses=True,
        )
except Exception:
    redis_client = None

LUA_RATE_LIMITER = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local requested = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

local state = redis.call('HMGET', key, 'tokens', 'last_updated')
local tokens = tonumber(state[1])
local last_updated = tonumber(state[2])

if not tokens then
    tokens = capacity
    last_updated = now
else
    local elapsed = math.max(0, now - last_updated)
    tokens = math.min(capacity, tokens + elapsed * rate)
    last_updated = now
end

local allowed = false
if tokens >= requested then
    tokens = tokens - requested
    allowed = true
end

redis.call('HMSET', key, 'tokens', tokens, 'last_updated', last_updated)
redis.call('EXPIRE', key, 3600)

return {allowed and 1 or 0, tokens}
"""

class RateLimiter:
    def __init__(self, limit_key_prefix: str, rate: float, capacity: float):
        """
        rate: tokens generated per second
        capacity: max burst capacity in bucket
        """
        self.prefix = limit_key_prefix
        self.rate = rate
        self.capacity = capacity

    async def __call__(self, request: Request):
        # Allow disabling rate limiter if Redis is unavailable or during certain environments
        if redis_client is None:
            return
            
        try:
            # Ping to verify connection
            redis_client.ping()
        except Exception:
            return # Fail-open if Redis is down
            
        # Get identifier (X-User-Id header or IP)
        user_id = request.headers.get("x-user-id") or request.headers.get("X-User-Id")
        if not user_id:
            user_id = request.client.host if request.client else "unknown"
            
        key = f"rate_limit:{self.prefix}:{user_id}"
        now = time.time()
        
        try:
            res = redis_client.eval(LUA_RATE_LIMITER, 1, key, self.capacity, self.rate, 1, now)
            allowed, tokens = int(res[0]), float(res[1])
        except Exception as e:
            print(f"Rate Limiter Script Error: {e}")
            return # Fail-open
            
        remaining = int(tokens)
        reset_time = int(now + (self.capacity - tokens) / self.rate)
        
        if allowed == 0:
            wait_time = math.ceil((1.0 - tokens) / self.rate)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later.",
                headers={
                    "X-RateLimit-Limit": str(int(self.capacity)),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                    "Retry-After": str(max(1, wait_time))
                }
            )
            
        # Store on request state for response headers injection
        request.state.rate_limit_limit = int(self.capacity)
        request.state.rate_limit_remaining = remaining
        request.state.rate_limit_reset = reset_time


@dataclass(frozen=True)
class RouteLimitProfile:
    name: str
    capacity: float
    rate: float


ROUTE_LIMITS = {
    "auth": RouteLimitProfile("auth", float(os.getenv("RATE_LIMIT_AUTH_BURST", "30")), float(os.getenv("RATE_LIMIT_AUTH_PER_SEC", "0.2"))),
    "model": RouteLimitProfile("model", float(os.getenv("RATE_LIMIT_MODEL_BURST", "20")), float(os.getenv("RATE_LIMIT_MODEL_PER_SEC", "0.05"))),
    "upload": RouteLimitProfile("upload", float(os.getenv("RATE_LIMIT_UPLOAD_BURST", "15")), float(os.getenv("RATE_LIMIT_UPLOAD_PER_SEC", "0.03"))),
    "code_runtime": RouteLimitProfile("code_runtime", float(os.getenv("RATE_LIMIT_CODE_RUNTIME_BURST", "20")), float(os.getenv("RATE_LIMIT_CODE_RUNTIME_PER_SEC", "0.05"))),
    "pa": RouteLimitProfile("pa", float(os.getenv("RATE_LIMIT_PA_BURST", "30")), float(os.getenv("RATE_LIMIT_PA_PER_SEC", "0.08"))),
    "interview": RouteLimitProfile("interview", float(os.getenv("RATE_LIMIT_INTERVIEW_BURST", "25")), float(os.getenv("RATE_LIMIT_INTERVIEW_PER_SEC", "0.05"))),
    "admin": RouteLimitProfile("admin", float(os.getenv("RATE_LIMIT_ADMIN_BURST", "120")), float(os.getenv("RATE_LIMIT_ADMIN_PER_SEC", "0.5"))),
    "default": RouteLimitProfile("default", float(os.getenv("RATE_LIMIT_DEFAULT_BURST", "120")), float(os.getenv("RATE_LIMIT_DEFAULT_PER_SEC", "1.0"))),
}

ROUTE_LIMIT_EXAMPLES = {
    "auth": ["/api/v1/auth/login", "/sign-in"],
    "model": ["/api/v1/agents/chat", "/api/v1/code/sessions/{id}/stream", "/api/v1/code/sessions/{id}/suggest-next"],
    "upload": ["/api/v1/files", "/api/v1/files/upload"],
    "code_runtime": ["/api/v1/code/terminal/{id}/input", "/api/v1/jobs/{id}/stream", "/api/v1/github/sessions/{id}/create-pr"],
    "pa": ["/api/v1/pa/command", "/api/v1/pa/reminders"],
    "interview": ["/api/v1/interview/answer", "/api/v1/billing/interview/access"],
    "admin": ["/api/v1/admin/summary", "/api/v1/admin/rate-limits"],
    "default": ["/api/v1/health", "/api/v1/settings"],
}


def rate_limit_policy_report() -> dict:
    redis_ok = False
    redis_error = None
    if redis_client is not None:
        try:
            redis_client.ping()
            redis_ok = True
        except Exception as exc:  # pragma: no cover - runtime dependency
            redis_error = str(exc)
    enabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() not in {"0", "false", "no"}
    fail_closed = os.getenv("RATE_LIMIT_FAIL_CLOSED", "false").lower() in {"1", "true", "yes"}
    return {
        "enabled": enabled,
        "enforcing": enabled and redis_ok,
        "mode": "enforced" if enabled and redis_ok else "disabled" if not enabled else "fail_open_no_redis",
        "fail_closed": fail_closed,
        "redis": {
            "configured": bool(os.getenv("REDIS_URL") or os.getenv("REDIS_HOST")),
            "available": redis_ok,
            "error": redis_error,
        },
        "profiles": [
            {
                "name": name,
                "burst": int(profile.capacity),
                "rate_per_second": profile.rate,
                "refill_per_minute": round(profile.rate * 60, 2),
                "env": {
                    "burst": f"RATE_LIMIT_{name.upper()}_BURST",
                    "per_second": f"RATE_LIMIT_{name.upper()}_PER_SEC",
                },
                "examples": ROUTE_LIMIT_EXAMPLES.get(name, []),
            }
            for name, profile in ROUTE_LIMITS.items()
        ],
    }


def route_limit_profile(path: str) -> RouteLimitProfile:
    if path.startswith("/api/v1/auth") or path.startswith("/sign-in") or path.startswith("/sign-up"):
        return ROUTE_LIMITS["auth"]
    if path.startswith("/api/v1/admin"):
        return ROUTE_LIMITS["admin"]
    if path.startswith("/api/v1/files") or "/upload" in path:
        return ROUTE_LIMITS["upload"]
    if path.startswith("/api/v1/pa"):
        return ROUTE_LIMITS["pa"]
    if path.startswith("/api/v1/billing/interview") or path.startswith("/api/v1/interview"):
        return ROUTE_LIMITS["interview"]
    if (
        path.startswith("/api/v1/agents")
        or path.startswith("/api/v1/models")
        or path.startswith("/api/v1/code/complete")
        or path.startswith("/api/v1/code/generate")
        or path.startswith("/api/v1/code/sessions") and any(part in path for part in ["/stream", "/suggest-next", "/tasks"])
    ):
        return ROUTE_LIMITS["model"]
    if (
        path.startswith("/api/v1/code")
        or path.startswith("/api/v1/jobs")
        or path.startswith("/api/v1/terminal")
        or path.startswith("/api/v1/github")
    ):
        return ROUTE_LIMITS["code_runtime"]
    return ROUTE_LIMITS["default"]


def request_identifier(request: Request) -> str:
    return (
        request.headers.get("x-user-id")
        or request.headers.get("X-User-Id")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )

class RateLimitHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if os.getenv("RATE_LIMIT_ENABLED", "true").lower() not in {"0", "false", "no"} and redis_client is not None:
            try:
                redis_client.ping()
                profile = route_limit_profile(request.url.path)
                key = f"rate_limit:{profile.name}:{request_identifier(request)}"
                now = time.time()
                res = redis_client.eval(LUA_RATE_LIMITER, 1, key, profile.capacity, profile.rate, 1, now)
                allowed, tokens = int(res[0]), float(res[1])
                remaining = int(tokens)
                reset_time = int(now + (profile.capacity - tokens) / max(profile.rate, 0.001))
                request.state.rate_limit_limit = int(profile.capacity)
                request.state.rate_limit_remaining = remaining
                request.state.rate_limit_reset = reset_time
                request.state.rate_limit_policy = profile.name
                if allowed == 0:
                    wait_time = math.ceil((1.0 - tokens) / max(profile.rate, 0.001))
                    headers = {
                        "X-RateLimit-Limit": str(int(profile.capacity)),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset_time),
                        "X-RateLimit-Policy": profile.name,
                        "Retry-After": str(max(1, wait_time)),
                    }
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={
                            "code": "RATE_LIMITED",
                            "message": "Rate limit exceeded. Please try again later.",
                            "route_class": profile.name,
                        },
                        headers=headers,
                    )
            except HTTPException:
                raise
            except Exception as exc:
                if os.getenv("RATE_LIMIT_FAIL_CLOSED", "false").lower() in {"1", "true", "yes"}:
                    raise HTTPException(status_code=503, detail={"code": "RATE_LIMIT_UNAVAILABLE", "message": str(exc)})
        response = await call_next(request)
        if hasattr(request.state, "rate_limit_limit"):
            response.headers["X-RateLimit-Limit"] = str(request.state.rate_limit_limit)
            response.headers["X-RateLimit-Remaining"] = str(request.state.rate_limit_remaining)
            response.headers["X-RateLimit-Reset"] = str(request.state.rate_limit_reset)
            response.headers["X-RateLimit-Policy"] = getattr(request.state, "rate_limit_policy", "default")
        return response
