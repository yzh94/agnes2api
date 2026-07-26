import os
from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

router = APIRouter(tags=["Frontend"])

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
DIST_DIR = os.path.join(FRONTEND_DIR, "dist")


# 挂载静态资源目录（assets/ 下的 JS/CSS 文件）
if os.path.exists(DIST_DIR):
    router.mount("/assets", StaticFiles(directory=os.path.join(DIST_DIR, "assets")), name="assets")


@router.get("/")
async def serve_frontend():
    """提供前端界面（优先新构建，回退到旧版）。"""
    dist_path = os.path.join(DIST_DIR, "index.html")
    if os.path.exists(dist_path):
        return FileResponse(dist_path)

    legacy_path = os.path.join(FRONTEND_DIR, "legacy.html")
    if os.path.exists(legacy_path):
        return FileResponse(legacy_path)

    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)

    return JSONResponse(
        status_code=404,
        content={"status": "error", "message": "Frontend not found"}
    )


@router.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """SPA 路由回退：所有非 API 请求都返回 index.html。"""
    excluded_prefixes = ("api/", "v1/", "proxy/", "health", "assets/")
    if any(full_path.startswith(p) for p in excluded_prefixes):
        return JSONResponse(status_code=404, content={"message": "Not found"})

    dist_path = os.path.join(DIST_DIR, "index.html")
    if os.path.exists(dist_path):
        return FileResponse(dist_path)

    legacy_path = os.path.join(FRONTEND_DIR, "legacy.html")
    if os.path.exists(legacy_path):
        return FileResponse(legacy_path)

    return JSONResponse(status_code=404, content={"message": "Frontend not found"})


@router.get("/frontend")
async def serve_frontend_redirect():
    """重定向到前端界面。"""
    return RedirectResponse(url="/")
