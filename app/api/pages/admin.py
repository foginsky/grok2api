import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

router = APIRouter()


def _resolve_static_dir() -> Path:
    """Resolve static directory across local and serverless layouts."""

    candidates = []
    candidates.append(Path(__file__).resolve().parents[2] / "static")
    candidates.append(Path.cwd() / "app" / "static")
    candidates.append(Path.cwd() / "_vendor" / "app" / "static")
    task_root = os.getenv("LAMBDA_TASK_ROOT")
    if task_root:
        candidates.append(Path(task_root) / "app" / "static")

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


STATIC_DIR = _resolve_static_dir()


def _admin_page_response(relative_path: str) -> FileResponse:
    file_path = STATIC_DIR / relative_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Page not found")
    return FileResponse(file_path)


@router.get("/admin", include_in_schema=False)
async def admin_root():
    return RedirectResponse(url="/admin/login")


@router.get("/admin/login", include_in_schema=False)
async def admin_login():
    return _admin_page_response("admin/pages/login.html")


@router.get("/admin/config", include_in_schema=False)
async def admin_config():
    return _admin_page_response("admin/pages/config.html")


@router.get("/admin/cache", include_in_schema=False)
async def admin_cache():
    return _admin_page_response("admin/pages/cache.html")


@router.get("/admin/token", include_in_schema=False)
async def admin_token():
    return _admin_page_response("admin/pages/token.html")
