"""WebDriverAgent driver for iOS simulators and real devices.

Public coordinates are screenshot pixels; WDA coordinates are logical points.
The endpoint must already be running on the explicitly selected device.
No Android shell fallback and no automatic retries of mutating requests.
"""
import asyncio
import base64
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse, quote
import xml.etree.ElementTree as ET

import httpx
from PIL import Image

from artemis.drivers.base import BaseDeviceDriver, ScreenData, SwipeDirection


class WdaError(RuntimeError):
    pass


class IOSWdaDriver(BaseDeviceDriver):
    def __init__(self, device_id: str, endpoint: str, *, transport=None, timeout=30.0):
        if not device_id or urlparse(endpoint).scheme not in ('http', 'https'):
            raise ValueError('An explicit device ID and HTTP(S) WDA endpoint are required')
        self._device_id = device_id
        self._client = httpx.AsyncClient(base_url=endpoint.rstrip('/'), timeout=timeout,
                                        transport=transport, trust_env=False)
        self._session = None
        self._size = (0, 0)
        self._points = (0.0, 0.0)

    @property
    def device_id(self):
        return self._device_id

    @property
    def screen_size(self):
        return self._size

    async def _request(self, method, path, payload=None, *, session=True):
        if session:
            if not self._session:
                raise WdaError('Driver is not connected')
            path = f'/session/{quote(self._session, safe="")}{path}'
        response = await self._client.request(method, path, json=payload)
        try:
            body = response.json()
        except ValueError as exc:
            raise WdaError(f'WDA returned non-JSON HTTP {response.status_code}') from exc
        value = body.get('value')
        if response.is_error or (isinstance(value, dict) and value.get('error')):
            raise WdaError(f'{method} {path}: {value}')
        return body

    async def connect(self):
        if self._session:
            return
        await self._request('GET', '/status', session=False)
        result = await self._request('POST', '/session',
                                     {'capabilities': {'alwaysMatch': {}}}, session=False)
        self._session = result.get('sessionId') or (result.get('value') or {}).get('sessionId')
        if not self._session:
            raise WdaError('WDA did not return a session ID')
        try:
            await self._geometry()
        except BaseException:
            await self.disconnect()
            raise

    async def disconnect(self):
        try:
            if self._session:
                await self._request('DELETE', '')
        finally:
            self._session = None
            await self._client.aclose()

    async def _geometry(self):
        encoded = (await self._request('GET', '/screenshot'))['value']
        raw = base64.b64decode(encoded, validate=True)
        with Image.open(BytesIO(raw)) as image:
            self._size = image.size
        window = (await self._request('GET', '/window/size'))['value']
        self._points = (float(window['width']), float(window['height']))
        if min(*self._size, *self._points) <= 0:
            raise WdaError('Invalid screen geometry')
        return raw, encoded

    async def _action_geometry(self):
        previous = self._size
        await self._geometry()
        if previous != self._size:
            raise WdaError('Screen geometry changed; observe again before acting')

    def _point(self, x, y):
        w, h = self._size
        if not 0 <= x < w or not 0 <= y < h:
            raise ValueError(f'Coordinate outside screenshot: {(x, y)}, size={self._size}')
        return x * self._points[0] / w, y * self._points[1] / h

    async def get_screen_data(self, skip_settling=False):
        if not skip_settling:
            await asyncio.sleep(0.5)
        raw, encoded = await self._geometry()
        xml = (await self._request('GET', '/source?format=xml'))['value']
        elements = []
        sx, sy = self._size[0] / self._points[0], self._size[1] / self._points[1]
        for node in ET.fromstring(xml).iter():
            a = node.attrib
            if 'x' not in a or a.get('visible') == 'false':
                continue
            x, y = float(a['x']), float(a['y'])
            w, h = float(a.get('width', 0)), float(a.get('height', 0))
            left, top, right, bottom = round(x*sx), round(y*sy), round((x+w)*sx), round((y+h)*sy)
            if w <= 0 or h <= 0:
                continue
            elements.append({
                'resource-id': a.get('name', ''), 'text': a.get('label') or a.get('value', ''),
                'content-desc': a.get('label', ''), 'class': a.get('type', node.tag),
                'value': a.get('value', ''), 'enabled': a.get('enabled', 'true'),
                'clickable': a.get('enabled', 'true'),
                'bounds': f'[{left},{top}][{right},{bottom}]',
                'parsed_bounds': dict(left=left, top=top, right=right, bottom=bottom),
            })
        return ScreenData(screenshot_bytes=raw, screenshot_base64=encoded,
                          ui_hierarchy_xml=xml, ui_elements=elements,
                          width=self._size[0], height=self._size[1], platform='ios')

    async def tap(self, x, y, duration_ms=100, times=1, delay_ms=100):
        if not 1 <= times <= 10 or delay_ms < 0:
            raise ValueError('Invalid tap count or delay')
        await self._action_geometry()
        px, py = self._point(x, y)
        for index in range(times):
            await self._request('POST', '/wda/tap', {'x': px, 'y': py})
            if index + 1 < times:
                await asyncio.sleep(delay_ms / 1000)
        return True

    async def long_press(self, x, y, duration_ms=1000):
        if duration_ms <= 0:
            raise ValueError('Duration must be positive')
        await self._action_geometry()
        px, py = self._point(x, y)
        await self._request('POST', '/wda/touchAndHold', {'x': px, 'y': py, 'duration': duration_ms/1000})
        return True

    async def swipe(self, start_x, start_y, end_x, end_y, duration_ms=800):
        if duration_ms <= 0:
            raise ValueError('Duration must be positive')
        await self._action_geometry()
        x1, y1 = self._point(start_x, start_y)
        x2, y2 = self._point(end_x, end_y)
        await self._request('POST', '/actions', {'actions': [{
            'type': 'pointer', 'id': 'finger', 'parameters': {'pointerType': 'touch'},
            'actions': [
                {'type': 'pointerMove', 'duration': 0, 'x': round(x1), 'y': round(y1), 'origin': 'viewport'},
                {'type': 'pointerDown', 'button': 0},
                {'type': 'pointerMove', 'duration': duration_ms, 'x': round(x2), 'y': round(y2), 'origin': 'viewport'},
                {'type': 'pointerUp', 'button': 0},
            ]}]})
        return True

    async def swipe_direction(self, direction, duration_ms=800):
        await self._geometry()
        w, h = self._size
        coords = {'up': (.5,.8,.5,.2), 'down': (.5,.2,.5,.8),
                  'left': (.8,.5,.2,.5), 'right': (.2,.5,.8,.5)}[SwipeDirection(direction).value]
        return await self.swipe(*(round(n * (w if i % 2 == 0 else h)) for i,n in enumerate(coords)), duration_ms)

    async def input_text(self, text, clear_existing=True):
        if clear_existing:
            result = (await self._request('GET', '/element/active'))['value']
            element = result.get('ELEMENT') or result.get('element-6066-11e4-a52e-4f735466cecf')
            if not element:
                raise WdaError('Cannot identify the focused field; refusing to guess what to clear')
            await self._request('POST', f'/element/{quote(element, safe="")}/clear', {})
        await self._request('POST', '/wda/keys', {'value': [text]})
        return True

    async def press_key(self, key):
        name = str(key).lower()
        if name == 'home':
            await self._request('POST', '/wda/homescreen', {}, session=False)
        elif name in ('enter', 'delete'):
            await self._request('POST', '/wda/keys', {'value': ['\n' if name == 'enter' else '\u0008']})
        else:
            raise NotImplementedError(f'iOS key is not supported: {name}; use a visible UI control')
        return True

    async def launch_app(self, package_name):
        await self._request('POST', '/wda/apps/launch', {'bundleId': package_name})
        return True

    async def stop_app(self, package_name):
        result = (await self._request('POST', '/wda/apps/terminate', {'bundleId': package_name}))['value']
        return bool(result)

    async def get_current_package(self):
        return (await self._request('GET', '/wda/activeAppInfo'))['value'].get('bundleId')

    async def execute_shell(self, command, timeout_seconds=15.0):
        raise NotImplementedError('Arbitrary device shell is not supported on iOS')

    async def start_video_recording(self, output_dir: Path | None = None):
        raise NotImplementedError('iOS recording is not implemented in this adapter')

    async def stop_video_recording(self):
        raise NotImplementedError('iOS recording is not implemented in this adapter')
