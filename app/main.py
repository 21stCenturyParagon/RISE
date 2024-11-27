from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from app.routers import questions, auth, progress
from app.core.logging_config import setup_logging, OperationLogger
import time
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware


logger = setup_logging()

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        start_time = time.time()
        response = None
        with OperationLogger(
            "http_request",
            method=request.method,
            url=str(request.url),
            client_host=request.client.host if request.client else None,
        ):
            try:
                response = await call_next(request)
                return response
            finally:
                process_time = (time.time() - start_time) * 1000
                status_code = response.status_code if response else 500
                logger.info(
                    "Request processed",
                    process_time_ms=round(process_time, 2),
                    status_code=status_code,
                    method=request.method,
                    url=str(request.url),
                )

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application")
    try:
        yield
    finally:
        logger.info("Shutting down application")

# Create the root app
app = FastAPI(
    title="TMUA Guide API",
    description="TMUA Guide API",
    version="1.0.0",
    lifespan=lifespan
)

# Create v1 sub-application
v1 = FastAPI(
    title="TMUA Guide API",
    description="Version 1 of TMUA Guide API",
    version="1.0.0"
)

# Add middleware to v1
v1.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add routers to v1

# Mount v1 to main app
app.mount("/api/v1", v1)

# Add middleware to main app
app.add_middleware(RequestLoggingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

v1.include_router(auth.router, prefix="/auth", tags=["Authentication"])
v1.include_router(questions.router, prefix="/questions", tags=["Questions"])
v1.include_router(progress.router, prefix="/progress", tags=["Progress"])

# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        f"Global exception handler caught: {str(exc)}",
        exc_info=True,
        url=str(request.url),
        method=request.method,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

@v1.exception_handler(Exception)
async def v1_global_exception_handler(request: Request, exc: Exception):
    logger.error(
        f"V1 API - Global exception handler caught: {str(exc)}",
        exc_info=True,
        url=str(request.url),
        method=request.method,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

# Health check endpoints
@app.get("/health")
async def health_check():
    logger.info("Health check endpoint called")
    return {"status": "healthy", "version": app.version}