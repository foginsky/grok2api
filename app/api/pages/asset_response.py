from pathlib import Path

from fastapi.responses import FileResponse, Response

from app.api.pages.embedded_assets import EMBEDDED_ASSETS


def serve_embedded_asset(static_dir: Path, relative_path: str, media_type: str) -> Response:
    """优先返回磁盘文件，不存在时回退到内嵌资源。"""
    file_path = static_dir / relative_path
    if file_path.exists():
        return FileResponse(file_path, media_type=media_type)

    content = EMBEDDED_ASSETS.get(relative_path)
    if content is None:
        raise RuntimeError(f"Embedded asset not found: {relative_path}")
    return Response(content=content, media_type=media_type)
