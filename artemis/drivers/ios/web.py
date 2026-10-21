"""Loopback console with serialized manual control and bounded SDK tasks."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import os
import secrets
import signal
import sys
import uuid
from typing import Literal
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from artemis.drivers.ios.session import ios_session


class ActionRequest(BaseModel):
    name: str
    arguments: dict = Field(default_factory=dict)


class TaskRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=8000)
    model: Literal['gemini', 'qwen'] = 'gemini'
    profile: Literal['flash', 'pro'] = 'flash'
    max_steps: int = Field(default=12, ge=1, le=100)
    timeout: int = Field(default=240, ge=10, le=1800)


def make_app(device_id, wda_url, *, runner_path=None, run_dir=None):
    token = secrets.token_urlsafe(32)
    lock = asyncio.Lock()
    runner = Path(runner_path or os.environ.get('ARTEMIS_IOS_TASK_RUNNER', ''))
    enabled = runner.is_file()
    runs = Path(run_dir or os.environ.get('ARTEMIS_APP_DIR', '.cache/artemis-ios')) / 'web-runs'
    current = None
    worker = None
    cancel = asyncio.Event()

    def active():
        return worker is not None and not worker.done()

    async def stop_process(proc):
        if proc.returncode is None:
            try:
                proc.send_signal(signal.SIGINT)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), 25)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return False
        return True

    async def execute(body, record):
        import json
        proc = None
        try:
            async with lock:
                if cancel.is_set():
                    record['status'] = 'cancelled'
                    return
                runs.mkdir(parents=True, exist_ok=True)
                output = runs / (record['id'] + '.json')
                logfile = runs / (record['id'] + '.log')
                record['status'] = 'running'
                with logfile.open('w') as log:
                    proc = await asyncio.create_subprocess_exec(
                        sys.executable, str(runner.resolve()), '--model', body.model,
                        '--profile', body.profile, '--device-id', device_id,
                        '--wda-url', wda_url, '--goal', body.goal,
                        '--max-steps', str(body.max_steps), '--timeout', str(body.timeout),
                        '--output', str(output.resolve()), '--session-id', record['id'],
                        stdout=log, stderr=log)
                    wait = asyncio.create_task(proc.wait())
                    cancellation = asyncio.create_task(cancel.wait())
                    try:
                        done, _ = await asyncio.wait(
                            [wait, cancellation], timeout=body.timeout + 45,
                            return_when=asyncio.FIRST_COMPLETED)
                        if wait not in done:
                            graceful = await stop_process(proc)
                            record['status'] = ('cancelled' if cancel.is_set() else 'timeout') if graceful else 'failed'
                            if not graceful:
                                record['error'] = 'Worker required forced termination; inspect device before retrying.'
                        elif output.exists():
                            result = json.loads(output.read_text())
                            record['status'] = result.get('task_status', 'failed')
                            record['result'] = result.get('result')
                            if result.get('error_type'):
                                record['error'] = result['error_type']
                        else:
                            record['status'] = 'failed'
                            record['error'] = 'Worker exited without a result; inspect local run log.'
                    finally:
                        cancellation.cancel()
                        await asyncio.gather(cancellation, return_exceptions=True)
                        if proc.returncode is None:
                            await stop_process(proc)
                        await wait
        except Exception as exc:
            record['status'] = 'failed'
            record['error'] = type(exc).__name__
        finally:
            if proc is not None and proc.returncode is None:
                await stop_process(proc)
            record['finished'] = True

    @asynccontextmanager
    async def lifespan(app):
        yield
        cancel.set()
        if worker is not None:
            await worker

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', 'testserver'])

    def authorize(request):
        if not secrets.compare_digest(request.headers.get('x-ios-token', ''), token):
            raise HTTPException(403)

    def require_manual():
        if active():
            raise HTTPException(409, 'Agent owns the device; cancel or wait for completion.')

    @app.get('/', response_class=HTMLResponse)
    async def index():
        return Path(__file__).with_name('console.html').read_text().replace('__TOKEN__', token)

    @app.get('/api/task')
    async def task_status(request: Request):
        authorize(request)
        return {'enabled': enabled, 'active': active(), 'task': current, 'device': device_id}

    @app.post('/api/task', status_code=202)
    async def submit(body: TaskRequest, request: Request):
        nonlocal worker, current
        authorize(request)
        if not enabled:
            raise HTTPException(503, 'Start with the workspace launcher to enable the SDK task runner.')
        if not body.goal.strip():
            raise HTTPException(422, 'Goal must not be blank')
        if active():
            raise HTTPException(409, 'A task is already running')
        cancel.clear()
        current = {'id': str(uuid.uuid4()), 'status': 'queued', 'goal': body.goal,
                   'model': body.model, 'profile': body.profile, 'finished': False}
        worker = asyncio.create_task(execute(body, current))
        return current

    @app.post('/api/task/cancel')
    async def cancel_task(request: Request):
        authorize(request)
        if active():
            cancel.set()
            current['status'] = 'cancelling'
        return {'requested': active()}

    @app.get('/api/screen')
    async def screen(request: Request):
        authorize(request)
        require_manual()
        async with lock:
            require_manual()
            async with ios_session(device_id, wda_url) as (_, driver, _session):
                data = await driver.get_screen_data()
                return {'image': data.screenshot_base64, 'width': data.width, 'height': data.height,
                        'device': device_id, 'app': await driver.get_current_package()}

    @app.post('/api/action')
    async def action(body: ActionRequest, request: Request):
        authorize(request)
        require_manual()
        async with lock:
            require_manual()
            async with ios_session(device_id, wda_url) as (ctx, driver, session):
                if body.name not in ctx.actuator.capabilities() or body.name in {
                    'observe_screen', 'take_screenshot', 'get_ui_hierarchy'}:
                    raise HTTPException(400, 'Unsupported action')
                return (await session.call(body.name, body.arguments)).model_dump(mode='json')
    return app
