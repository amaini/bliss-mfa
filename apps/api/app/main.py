from fastapi import FastAPI

from .config import get_settings
from .schemas import HealthRead


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")


@app.get("/health", response_model=HealthRead, tags=["system"])
def health() -> HealthRead:
    return HealthRead(status="ok", service=settings.app_name)
