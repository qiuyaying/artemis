from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from apps.admin_console.services.ios_device_service import ios_device_service

router = APIRouter(prefix='/api/ios', tags=['ios'])


class DeviceSelection(BaseModel):
    platform: Literal['android', 'ios']
    device_id: str | None = None
    wda_url: str | None = None


@router.get('/devices')
async def devices():
    try:
        return await ios_device_service.inventory()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get('/status')
async def status():
    return await ios_device_service.status()


@router.post('/select')
async def select(body: DeviceSelection):
    try:
        from admin_console.core.state import state
    except ImportError:
        from apps.admin_console.core.state import state
    if state.active_runs or state.queue_items:
        raise HTTPException(409, 'Wait for queued/running tasks to finish before changing devices.')
    try:
        return await ios_device_service.select(body.platform, body.device_id, body.wda_url)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc
