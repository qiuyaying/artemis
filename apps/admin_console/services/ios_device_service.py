"""Native dashboard iOS target selection and read-only WDA preview."""
import asyncio
import base64
import json
from urllib.parse import urlparse

import httpx
from artemis.config import WORKSPACE_ROOT
from artemis.drivers.ios.discovery import discover_devices


class IOSDeviceService:
    def __init__(self):
        self.path = WORKSPACE_ROOT / '.cache' / 'dashboard-device.json'
        self.platform = 'android'
        self.target = None
        try:
            saved = json.loads(self.path.read_text())
            self.platform = saved['platform']
            self.target = saved.get('target')
        except (OSError, ValueError, KeyError):
            pass

    async def inventory(self):
        return await asyncio.to_thread(discover_devices, include_simulators=True)

    async def check(self, target=None):
        target = target or self.target
        if not target:
            return {'ready': False, 'message': 'Select an iPhone or iPad and connect its WebDriverAgent.'}
        try:
            async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
                response = await client.get(target['wda_url'] + '/status')
                response.raise_for_status()
                value = response.json().get('value', {})
                if value.get('ready') is not True:
                    raise ValueError('WebDriverAgent is not ready')
                is_simulator = bool((value.get('ios') or {}).get('simulatorVersion'))
                if is_simulator != (target.get('kind', 'physical') == 'simulator'):
                    raise ValueError('WDA endpoint type does not match the selected physical device or simulator.')
                family = target.get('device_type', '').lower()
                if family in ('iphone', 'ipad') and value.get('device', '').lower() != family:
                    raise ValueError('WDA device family does not match the selected iPhone or iPad.')
            return {'ready': True, 'message': f'{target.get("device_type", "iOS")} WebDriverAgent connected'}
        except (httpx.HTTPError, ValueError) as exc:
            return {'ready': False, 'message': f'WDA connection failed: {exc}'}

    async def select(self, platform, device_id=None, wda_url=None):
        target = self.target
        if platform == 'ios':
            parsed = urlparse(wda_url or '')
            if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
                raise ValueError('Use a local WDA URL, for example http://127.0.0.1:8101')
            inventory = await self.inventory()
            device = next((d for d in inventory['devices'] if d['udid'] == device_id), None)
            if not device or not device.get('connected', device.get('usb_connected')):
                raise ValueError('Selected device is not connected. Connect USB or boot the simulator first.')
            if device['developer_mode'] == 'disabled':
                raise ValueError('Enable Developer Mode on this iPhone or iPad first.')
            target = {'device_id': device_id, 'name': device['name'], 'wda_url': wda_url.rstrip('/'),
                      'kind': device.get('kind', 'physical'), 'device_type': device.get('device_type', 'unknown')}
            status = await self.check(target)
            if not status['ready']:
                raise ValueError(status['message'])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'platform': platform, 'target': target}))
        temporary.replace(self.path)
        self.platform, self.target = platform, target
        return await self.status()

    async def status(self):
        status = await self.check() if self.platform == 'ios' else {'ready': False, 'message': ''}
        return {'platform': self.platform, 'target': self.target, **status}

    async def frames(self):
        target = dict(self.target or {})
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            while self.platform == 'ios' and self.target == target:
                try:
                    response = await client.get(target['wda_url'] + '/screenshot')
                    response.raise_for_status()
                    data = base64.b64decode(response.json()['value'], validate=True)
                    yield b'--frame\r\nContent-Type: image/png\r\nContent-Length: ' + str(len(data)).encode() + b'\r\n\r\n' + data + b'\r\n'
                except (httpx.HTTPError, ValueError, KeyError):
                    break
                await asyncio.sleep(0.6)


ios_device_service = IOSDeviceService()
