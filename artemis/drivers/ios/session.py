"""Owned iOS connection: per-device lease and shared Artemis action session."""
import asyncio
from contextlib import asynccontextmanager
from artemis.context import ArtemisContext, DeviceContext, DevicePlatform
from artemis.drivers.factory import get_driver
from artemis.mcp.action_session import get_action_session
from artemis.mcp.actuators.factory import create_actuator
from artemis.runtime.device_lock import DeviceExecutionLock


@asynccontextmanager
async def ios_session(device_id: str, wda_url: str):
    lease = DeviceExecutionLock(device_id=device_id, description='iOS WDA connection',
                                concurrency_mode='per_device', ingress='ios')
    lease.acquire(blocking=False)
    driver = None
    try:
        ctx = ArtemisContext(trace_id='ios', device=DeviceContext(
            device_id=device_id, mobile_platform=DevicePlatform.IOS,
            host_platform='DARWIN', wda_url=wda_url))
        driver = get_driver(ctx)
        await driver.connect()
        ctx.device.device_width, ctx.device.device_height = driver.screen_size
        ctx.actuator = create_actuator(ctx)
        async with ctx:
            session = await get_action_session(ctx)
            yield ctx, driver, session
    finally:
        try:
            if driver is not None:
                await driver.disconnect()
        finally:
            lease.release()
