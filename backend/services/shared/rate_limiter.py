import redis
import time
import math
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware

# Configure Redis connection
try:
    redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
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

class RateLimitHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if hasattr(request.state, "rate_limit_limit"):
            response.headers["X-RateLimit-Limit"] = str(request.state.rate_limit_limit)
            response.headers["X-RateLimit-Remaining"] = str(request.state.rate_limit_remaining)
            response.headers["X-RateLimit-Reset"] = str(request.state.rate_limit_reset)
        return response
