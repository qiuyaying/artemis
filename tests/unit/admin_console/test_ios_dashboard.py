from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from apps.admin_console.routers import tasks
from apps.admin_console.schemas.task_schema import RunRequest
from apps.admin_console.services.ios_device_service import IOSDeviceService, ios_device_service
from apps.admin_console.services.task_queue_service import TaskQueueService
from artemis.runtime.adb_endpoint import AdbEndpoint, AdbTarget
from artemis.runtime import DeviceExecutionLock
import httpx


@pytest.mark.asyncio
async def test_ios_submission_bypasses_adb_and_snapshots_endpoint(monkeypatch):
    monkeypatch.setattr(ios_device_service, 'platform', 'ios')
    monkeypatch.setattr(ios_device_service, 'target', {'device_id': 'phone', 'wda_url': 'http://127.0.0.1:8101'})
    monkeypatch.setattr(ios_device_service, 'check', AsyncMock(return_value={'ready': True}))
    adb_probe = AsyncMock(side_effect=AssertionError('iOS must not use ADB'))
    monkeypatch.setattr(tasks.readiness_engine, 'run_device_submission_probe', adb_probe)
    enqueue = AsyncMock(return_value={'status': 'started'})
    monkeypatch.setattr(tasks.task_queue_service, 'enqueue_tasks', enqueue)
    await tasks.run_task(RunRequest(goal='Open Settings', platform='ios', device_serial='phone'))
    assert enqueue.call_args.kwargs['platform'] == 'ios'
    assert enqueue.call_args.kwargs['wda_url'] == 'http://127.0.0.1:8101'
    assert enqueue.call_args.kwargs['device_serial'] == 'phone'
    adb_probe.assert_not_called()


@pytest.mark.asyncio
async def test_ios_submission_rejects_changed_target(monkeypatch):
    monkeypatch.setattr(ios_device_service, 'platform', 'ios')
    monkeypatch.setattr(ios_device_service, 'target', {'device_id': 'other'})
    with pytest.raises(HTTPException) as exc:
        await tasks.run_task(RunRequest(goal='Open Settings', platform='ios', device_serial='phone'))
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_selection_rejects_remote_url_and_disconnected_device(tmp_path):
    service = IOSDeviceService()
    service.path = tmp_path / 'selection.json'
    service.platform, service.target = 'android', None
    with pytest.raises(ValueError, match='local WDA'):
        await service.select('ios', 'phone', 'http://example.com:8100')
    service.inventory = AsyncMock(return_value={'devices': [{'udid': 'phone', 'usb_connected': False}]})
    with pytest.raises(ValueError, match='not connected'):
        await service.select('ios', 'phone', 'http://127.0.0.1:8101')
    assert not service.path.exists()


@pytest.mark.asyncio
async def test_failed_wda_keeps_previous_target(tmp_path):
    service = IOSDeviceService()
    service.path = tmp_path / 'selection.json'
    service.platform, service.target = 'android', None
    service.inventory = AsyncMock(return_value={'devices': [{'udid': 'phone', 'name': 'Phone', 'usb_connected': True, 'developer_mode': 'enabled'}]})
    service.check = AsyncMock(return_value={'ready': False, 'message': 'WDA offline'})
    with pytest.raises(ValueError, match='WDA offline'):
        await service.select('ios', 'phone', 'http://127.0.0.1:8101')
    assert service.platform == 'android'
    assert service.target is None


def test_ios_worker_preserves_session_and_shared_lock_scope():
    item = {'platform': 'ios', 'device_serial': 'phone', 'wda_url': 'http://127.0.0.1:8101', 'queue_ticket': 'ticket'}
    cmd, env = TaskQueueService._build_worker_invocation(item, 'run', 'session', 'Goal', 'flash', AdbTarget(AdbEndpoint.local(), 'phone'))
    assert cmd[1].endswith('ios_dashboard_run.py')
    assert cmd[cmd.index('--session-id') + 1] == 'session'
    assert cmd[cmd.index('--device-id') + 1] == 'phone'
    assert '--device-serial' not in cmd
    assert DeviceExecutionLock.LOCK_SCOPE_ENV not in env
    assert env[DeviceExecutionLock.QUEUE_TICKET_ENV] == 'ticket'


@pytest.mark.asyncio
async def test_ipad_simulator_selection_persists_type(tmp_path):
    service = IOSDeviceService()
    service.path = tmp_path / 'selection.json'
    service.inventory = AsyncMock(return_value={'devices': [{'udid': 'pad', 'name': 'iPad Pro',
        'connected': True, 'usb_connected': False, 'kind': 'simulator',
        'device_type': 'iPad', 'developer_mode': 'not_required'}]})
    service.check = AsyncMock(return_value={'ready': True, 'message': 'Ready'})
    result = await service.select('ios', 'pad', 'http://127.0.0.1:8102')
    assert result['target']['device_type'] == 'iPad'
    assert result['target']['kind'] == 'simulator'


@pytest.mark.asyncio
@pytest.mark.parametrize('kind,family,ready', [('simulator', 'iPad', True), ('physical', 'iPad', False), ('simulator', 'iPhone', False)])
async def test_wda_rejects_wrong_environment_or_device_family(monkeypatch, kind, family, ready):
    response = httpx.Response(200, json={'value': {'ready': True, 'device': 'ipad',
        'ios': {'simulatorVersion': '26.5'}}}, request=httpx.Request('GET', 'http://localhost:8102/status'))
    monkeypatch.setattr(httpx.AsyncClient, 'get', AsyncMock(return_value=response))
    service = IOSDeviceService()
    result = await service.check({'wda_url': 'http://localhost:8102', 'kind': kind, 'device_type': family})
    assert result['ready'] is ready
