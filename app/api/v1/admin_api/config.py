import os

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import verify_app_key
from app.core.config import config
from app.services.cf_refresh.scheduler import refresh_once
from app.core.storage import (
    get_storage as get_storage_backend,
    LocalStorage,
    RedisStorage,
    SQLStorage,
)

router = APIRouter()


@router.get("/verify", dependencies=[Depends(verify_app_key)])
async def admin_verify():
    """验证后台访问密钥（app_key）"""
    return {"status": "success"}


@router.get("/config", dependencies=[Depends(verify_app_key)])
async def get_config():
    """获取当前配置"""
    # 暴露原始配置字典
    return config._config


@router.post("/config", dependencies=[Depends(verify_app_key)])
async def update_config(data: dict):
    """更新配置"""
    try:
        await config.update(data)
        return {"status": "success", "message": "配置已更新"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/cf-refresh", dependencies=[Depends(verify_app_key)])
async def trigger_cf_refresh():
    """手动触发一次 CF 刷新。"""
    try:
        result = await refresh_once()
        return {
            "status": "success",
            "message": "CF 刷新完成",
            "result": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/storage", dependencies=[Depends(verify_app_key)])
async def admin_get_storage():
    """获取当前存储模式"""
    storage_type = os.getenv("SERVER_STORAGE_TYPE", "").lower()
    if not storage_type:
        storage = get_storage_backend()
        if isinstance(storage, LocalStorage):
            storage_type = "local"
        elif isinstance(storage, RedisStorage):
            storage_type = "redis"
        elif isinstance(storage, SQLStorage):
            storage_type = {
                "mysql": "mysql",
                "mariadb": "mysql",
                "postgres": "pgsql",
                "postgresql": "pgsql",
                "pgsql": "pgsql",
            }.get(storage.dialect, storage.dialect)
    return {"type": storage_type or "local"}
