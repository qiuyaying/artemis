import base64
from io import BytesIO
from types import SimpleNamespace
import json
import httpx
from PIL import Image
import pytest
from artemis.drivers.ios.wda_driver import IOSWdaDriver, WdaError
from artemis.drivers.factory import create_driver
from artemis.mcp.actuators.ios import IOSActuator
from artemis.context import DeviceContext, DevicePlatform


def backend(error_path=None):
    buf = BytesIO()
    Image.new('RGB', (1200, 2400)).save(buf, 'PNG')
    encoded = base64.b64encode(buf.getvalue()).decode()
    calls = []
    def handler(request):
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, path, body))
        if error_path and path.endswith(error_path):
            return httpx.Response(200, json={'value': {'error': 'invalid element state', 'message': 'no keyboard'}})
        if path == '/session':
            return httpx.Response(200, json={'sessionId': 'test', 'value': {}})
        if path.endswith('/screenshot'):
            value = encoded
        elif path.endswith('/window/size'):
            value = {'width': 400, 'height': 800}
        elif path.endswith('/source'):
            value = '<root><XCUIElementTypeButton name="save" label="保存" x="10" y="20" width="100" height="40" enabled="true" visible="true"/></root>'
        elif path.endswith('/element/active'):
            value = {'element-6066-11e4-a52e-4f735466cecf': 'input'}
        else:
            value = {}
        return httpx.Response(200, json={'value': value})
    return httpx.MockTransport(handler), calls


@pytest.mark.asyncio
async def test_screen_and_touch_share_pixel_coordinate_space():
    transport, calls = backend()
    driver = IOSWdaDriver('sim', 'http://wda', transport=transport)
    await driver.connect()
    try:
        data = await driver.get_screen_data(skip_settling=True)
        assert (data.width, data.height) == (1200, 2400)
        assert data.ui_elements[0]['bounds'] == '[30,60][330,180]'
        await driver.tap(600, 1200)
        assert calls[-1] == ('POST', '/session/test/wda/tap', {'x': 200, 'y': 400})
        await driver.swipe(600, 1800, 600, 600, 450)
        actions = calls[-1][2]['actions'][0]['actions']
        assert (actions[0]['x'], actions[0]['y']) == (200, 600)
        assert (actions[2]['x'], actions[2]['y'], actions[2]['duration']) == (200, 200, 450)
        with pytest.raises(ValueError):
            await driver.tap(1200, 1)
    finally:
        await driver.disconnect()
    assert calls[-1][:2] == ('DELETE', '/session/test')


@pytest.mark.asyncio
async def test_input_clear_and_unicode_and_semantic_error():
    transport, calls = backend('/wda/keys')
    driver = IOSWdaDriver('sim', 'http://wda', transport=transport)
    await driver.connect()
    try:
        with pytest.raises(WdaError, match='no keyboard'):
            await driver.input_text('你好🙂')
        assert any(path.endswith('/element/input/clear') for _,path,_ in calls)
        assert calls[-1][2] == {'value': ['你好🙂']}
        with pytest.raises(NotImplementedError):
            await driver.execute_shell('echo test')
        with pytest.raises(NotImplementedError):
            await driver.press_key('back')
    finally:
        await driver.disconnect()


@pytest.mark.asyncio
async def test_ios_factory_and_failure_propagation():
    device = DeviceContext(device_id='sim', mobile_platform=DevicePlatform.IOS, wda_url='http://wda')
    ctx = SimpleNamespace(device=device)
    driver = create_driver(ctx)
    assert isinstance(driver, IOSWdaDriver)
    await driver.disconnect()
    transport, calls = backend('/wda/tap')
    ctx._active_driver = IOSWdaDriver('sim', 'http://wda', transport=transport)
    await ctx._active_driver.connect()
    try:
        actuator = IOSActuator(ctx, controller=object())
        result = await actuator.click_sequence([(500,500), (600,600)])
        assert not result.ok
        assert len([p for _,p,_ in calls if p.endswith('/wda/tap')]) == 1
        assert 'open_link' not in actuator.capabilities()
    finally:
        await ctx._active_driver.disconnect()


def test_ios_requires_explicit_endpoint(monkeypatch):
    monkeypatch.delenv('ARTEMIS_IOS_WDA_URL', raising=False)
    ctx = SimpleNamespace(device=DeviceContext(device_id='sim', mobile_platform=DevicePlatform.IOS))
    with pytest.raises(ValueError, match='explicit'):
        create_driver(ctx)
