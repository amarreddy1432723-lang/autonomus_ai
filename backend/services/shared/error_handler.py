import uuid
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

def register_error_handlers(app: FastAPI):
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        request_id = str(uuid.uuid4())
        # Infer title from HTTP status
        title = exc.detail if isinstance(exc.detail, str) else "An error occurred"
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            title = "Resource Not Found"
        elif exc.status_code == status.HTTP_401_UNAUTHORIZED:
            title = "Unauthorized access"
        elif exc.status_code == status.HTTP_403_FORBIDDEN:
            title = "Forbidden action"
        elif exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            title = "Rate Limit Exceeded"
            
        error_type = f"https://api.my-ai.com/errors/{exc.status_code}"
        
        headers = getattr(exc, "headers", {}) or {}
        
        return JSONResponse(
            status_code=exc.status_code,
            headers={**headers, "Content-Type": "application/problem+json"},
            content={
                "type": error_type,
                "title": title,
                "status": exc.status_code,
                "detail": str(exc.detail),
                "instance": request.url.path,
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        request_id = str(uuid.uuid4())
        details = exc.errors()
        detail_msg = "; ".join([f"{'.'.join(str(p) for p in d['loc'])}: {d['msg']}" for d in details])
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            headers={"Content-Type": "application/problem+json"},
            content={
                "type": "https://api.my-ai.com/errors/422",
                "title": "Validation Error",
                "status": 422,
                "detail": detail_msg,
                "instance": request.url.path,
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        request_id = str(uuid.uuid4())
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            headers={"Content-Type": "application/problem+json"},
            content={
                "type": "https://api.my-ai.com/errors/500",
                "title": "Internal Server Error",
                "status": 500,
                "detail": "An unexpected error occurred. Please contact support.",
                "instance": request.url.path,
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        )
