import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.logging import CorrelationIDMiddleware, logger
from db.session import init_db
from api import resume as legacy_resume_router
from api.v1 import auth, health, resumes

# Initialize Production FastAPI Application
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Production-grade AI Faculty Resume Screening & Academic Scoring Platform for Vishwakarma Group",
    version=settings.VERSION,
    openapi_url="/api/v1/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Startup DB Initialization
@app.on_event("startup")
def on_startup():
    logger.info("Initializing database and production configuration...")
    init_db()

# Middlewares
app.add_middleware(CorrelationIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "Content-Disposition",
        "X-Request-ID",
        "X-Process-Time-Ms",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
    ],
)

# Mount Static File Directory
app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")

# Include v1 Production API Routers
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(health.router, prefix=settings.API_V1_STR)
app.include_router(resumes.router, prefix=settings.API_V1_STR)

# Include Legacy Compatibility Router
app.include_router(legacy_resume_router.router)


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main frontend UI build."""
    index_path = os.path.join(settings.STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(
        content="<h1>Vishwakarma Group Faculty Resume Screening API Active</h1><p>Visit <a href='/docs'>/docs</a> for OpenAPI documentation.</p>"
    )


if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Vishwakarma Production Server on port 8000...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)