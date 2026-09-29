from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import get_settings
from .db import Base, engine
from .routes.enrollments import router as enrollments_router
from .routes.organizations import router as organizations_router
from .routes.users import router as users_router
from .schemas import HealthRead


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.app_env == "development":
        from . import models  # noqa: F401

        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(organizations_router, prefix="/v1")
app.include_router(enrollments_router, prefix="/v1")
app.include_router(users_router, prefix="/v1")


@app.get("/health", response_model=HealthRead, tags=["system"])
def health() -> HealthRead:
    return HealthRead(status="ok", service=settings.app_name)
