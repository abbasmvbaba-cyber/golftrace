from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from .config import settings, is_dev_auth_allowed
from .db import init_db
from .api.v1.projects import router as projects_router
from .api.v1.uploads import router as uploads_router
from .api.v1.videos import router as videos_router
from .api.v1.annotations import router as annotations_router
from .api.v1.analyses import router as analyses_router
from .api.v1.jobs import router as jobs_router
from .api.v1.tracks import router as tracks_router
from .api.v1.renders import router as renders_router

app = FastAPI(
    title="GolfTrace API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(projects_router, prefix="/api/v1/projects", tags=["projects"])
app.include_router(uploads_router, prefix="/api/v1", tags=["uploads"])
app.include_router(videos_router, prefix="/api/v1/videos", tags=["videos"])
app.include_router(annotations_router, prefix="/api/v1", tags=["annotations"])
app.include_router(analyses_router, prefix="/api/v1", tags=["analyses"])
app.include_router(jobs_router, prefix="/api/v1/jobs", tags=["jobs"])
app.include_router(tracks_router, prefix="/api/v1", tags=["tracks"])
app.include_router(renders_router, prefix="/api/v1", tags=["renders"])

# Health checks
@app.get("/api/v1/health")
def health():
    return {"status": "ok", "version": "0.1.0"}

@app.get("/api/health")
def health_alt():
    return {"status": "ok"}

@app.get("/health")
def health_root():
    return {"status": "ok"}

# Startup checks
@app.on_event("startup")
def startup():
    # Check dev auth config
    try:
        is_dev_auth_allowed()
    except RuntimeError as e:
        if settings.ENV == "production":
            raise e

    # Init DB
    try:
        init_db()
        print("Database initialized")
    except Exception as e:
        print(f"DB init failed: {e}")

    # Check S3 bucket exists? For MinIO, we try to create
    try:
        from .core.storage import storage_service
        if storage_service.use_s3 and storage_service.s3_client:
            try:
                storage_service.s3_client.head_bucket(Bucket=settings.S3_BUCKET)
            except:
                try:
                    storage_service.s3_client.create_bucket(Bucket=settings.S3_BUCKET)
                    print(f"Created bucket {settings.S3_BUCKET}")
                except Exception as be:
                    print(f"Bucket creation failed: {be}")
    except Exception as e:
        print(f"S3 check failed: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)
