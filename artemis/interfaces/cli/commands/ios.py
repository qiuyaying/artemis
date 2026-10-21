"""iOS integration commands; existing Android run bootstrap is unchanged."""
import asyncio
import json
from pathlib import Path
import typer
from artemis.drivers.ios.session import ios_session

ios_app = typer.Typer(help='Connect an explicit iOS device to its running WebDriverAgent.')


@ios_app.command('devices')
def devices():
    """List physical iOS devices and distinguish USB presence from WDA readiness."""
    from artemis.drivers.ios.discovery import discover_devices
    try:
        typer.echo(json.dumps(discover_devices(), ensure_ascii=False, indent=2))
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc


@ios_app.command('usb-ui')
def usb_ui(device_id: str = typer.Option(...), port: int = 8012,
           wda_port: int = 8101, device_port: int = 8100):
    """Forward a selected physical device's running WDA and open its console."""
    import subprocess
    import socket
    import time
    import httpx
    from artemis.drivers.ios.discovery import discover_devices
    if not all(1 <= p <= 65535 for p in (port, wda_port, device_port)) or port == wda_port:
        raise typer.BadParameter('Use distinct valid console and local WDA ports.')
    for local_port in (port, wda_port):
        with socket.socket() as probe:
            try:
                probe.bind(('127.0.0.1', local_port))
            except OSError as exc:
                raise typer.BadParameter(f'Cannot bind local port {local_port}: {exc}') from exc
    selected = next((d for d in discover_devices()['devices'] if d['udid'] == device_id), None)
    if not selected or not selected['usb_connected']:
        raise typer.BadParameter('Selected iPhone is not connected over USB. Connect and unlock it first.')
    if selected['developer_mode'] == 'disabled':
        raise typer.BadParameter('Enable Developer Mode on the selected iPhone first.')
    try:
        proxy = subprocess.Popen(['iproxy', '--udid', device_id, '--source', '127.0.0.1',
                                  f'{wda_port}:{device_port}'])
    except OSError as exc:
        raise typer.BadParameter('Install iproxy (libusbmuxd) first.') from exc
    url = f'http://127.0.0.1:{wda_port}'
    try:
        ready = False
        with httpx.Client(timeout=2, trust_env=False) as client:
            for _ in range(10):
                time.sleep(0.3)
                if proxy.poll() is not None:
                    raise typer.BadParameter('USB forwarding failed; check the local port and device.')
                try:
                    response = client.get(url + '/status')
                    response.raise_for_status()
                    ready = response.json().get('value', {}).get('ready') is True
                    if ready:
                        break
                except (httpx.HTTPError, ValueError):
                    pass
        if not ready:
            raise typer.BadParameter('WDA is not ready on this iPhone. Start scripts/ios-wda-device.sh with its UDID and signing team first.')
        typer.echo(f'iOS console: http://127.0.0.1:{port} (USB device {device_id})')
        ui(device_id=device_id, wda_url=url, port=port)
    finally:
        if proxy.poll() is None:
            proxy.terminate()
            try:
                proxy.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proxy.kill()
                proxy.wait()


@ios_app.command('inspect')
def inspect_device(device_id: str = typer.Option(...), wda_url: str = typer.Option(...),
                   output: Path = typer.Option(Path('ios-observation'))):
    """Save a screenshot, hierarchy and observation without a model call."""
    async def run():
        async with ios_session(device_id, wda_url) as (ctx, driver, session):
            data = await driver.get_screen_data()
            output.mkdir(parents=True, exist_ok=True)
            (output / 'screen.png').write_bytes(data.screenshot_bytes)
            (output / 'hierarchy.xml').write_text(data.ui_hierarchy_xml or '')
            observation = await session.observe(settle_ms=0)
            (output / 'observation.json').write_text(observation.model_dump_json(indent=2))
            if not observation.ok or not observation.hierarchy_ok:
                raise RuntimeError(observation.message)
            typer.echo(json.dumps({'platform': 'ios', 'size': driver.screen_size,
                                   'elements': len(data.ui_elements), 'output': str(output.resolve())}))
    asyncio.run(run())


@ios_app.command('ui')
def ui(device_id: str = typer.Option(...), wda_url: str = typer.Option(...), port: int = 8011):
    """Open the loopback iOS console; workspace launcher enables SDK task controls."""
    import uvicorn
    from artemis.drivers.ios.web import make_app
    uvicorn.run(make_app(device_id, wda_url), host='127.0.0.1', port=port)
