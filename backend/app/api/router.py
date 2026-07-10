from fastapi import APIRouter

from app.api.routes import (
    analysis_specs,
    auth,
    cleaning,
    datasets,
    evidence,
    jobs,
    projects,
    quality,
    reports,
    runs,
    schemas,
    system,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(system.router)
api_router.include_router(projects.router)
api_router.include_router(datasets.router)
api_router.include_router(schemas.router)
api_router.include_router(quality.router)
api_router.include_router(cleaning.router)
api_router.include_router(analysis_specs.router)
api_router.include_router(runs.router)
api_router.include_router(evidence.router)
api_router.include_router(reports.router)
api_router.include_router(jobs.router)
