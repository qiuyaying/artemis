from artemis.drivers.ios.discovery import normalize_devices, normalize_simulators
import pytest
import typer
import socket
from artemis.interfaces.cli.commands import ios


def test_modern_inventory_filters_simulator_and_preserves_usb_presence():
    def device(udid, transport, state):
        return {'properties': {'hardware': {'udid': udid, 'platform': 'iOS'},
                'state': {'name': udid}, 'connection': {
                    'transportType': transport, 'state': state, 'pairingState': 'paired'}}}
    payload = {'result': {'devices': [device('sim', 'sameMachine', 'connected'),
               device('phone', 'wired', 'disconnected'),
               device('old-phone', 'localNetwork', 'disconnected')]}}
    result = normalize_devices(payload, ['phone'])
    assert [d['udid'] for d in result] == ['phone', 'old-phone']
    assert result[0]['usb_connected'] is True
    assert result[0]['tunnel'] == 'disconnected'
    assert result[0]['developer_mode'] == 'unknown'
    assert result[1]['usb_connected'] is False


def test_legacy_inventory_reports_disabled_developer_mode():
    payload = {'result': {'devices': [{'hardwareProperties': {'udid': 'real', 'platform': 'iOS'},
        'deviceProperties': {'developerModeStatus': 'disabled'},
        'connectionProperties': {'transportType': 'wired', 'tunnelState': 'connected'}}]}}
    result = normalize_devices(payload, ['real'])
    assert result[0]['developer_mode'] == 'disabled'
    assert result[0]['tunnel'] == 'connected'


def test_simulator_inventory_distinguishes_ipad_and_offline_devices():
    def entry(udid, family, state, available=True):
        return {'udid': udid, 'name': family, 'state': state, 'isAvailable': available,
                'deviceTypeIdentifier': 'com.apple.CoreSimulator.SimDeviceType.' + family}
    result = normalize_simulators({'devices': {
        'com.apple.CoreSimulator.SimRuntime.iOS-26-5': [
            entry('pad', 'iPad-Pro', 'Booted'), entry('phone', 'iPhone-17', 'Shutdown'),
            entry('unavailable', 'iPad-mini', 'Shutdown', False)],
        'com.apple.CoreSimulator.SimRuntime.tvOS-26-5': [entry('tv', 'Apple-TV', 'Booted')]}})
    assert [d['udid'] for d in result] == ['pad', 'phone']
    assert result[0]['device_type'] == 'iPad'
    assert result[0]['kind'] == 'simulator'
    assert result[0]['connected'] is True
    assert result[1]['connected'] is False


def test_usb_ui_rejects_disconnected_device(monkeypatch):
    monkeypatch.setattr(socket.socket, 'bind', lambda *args: None)
    monkeypatch.setattr('artemis.drivers.ios.discovery.discover_devices',
                        lambda: {'devices': [{'udid': 'phone', 'usb_connected': False}]})
    with pytest.raises(typer.BadParameter, match='not connected'):
        ios.usb_ui(device_id='phone', port=48122, wda_port=48123, device_port=8100)


def test_usb_ui_closes_owned_proxy_when_console_exits(monkeypatch):
    monkeypatch.setattr(socket.socket, 'bind', lambda *args: None)
    import httpx
    import subprocess
    import time
    monkeypatch.setattr('artemis.drivers.ios.discovery.discover_devices',
                        lambda: {'devices': [{'udid': 'phone', 'usb_connected': True,
                                               'developer_mode': 'enabled'}]})
    class Proxy:
        stopped = False
        def poll(self): return 0 if self.stopped else None
        def terminate(self): self.stopped = True
        def wait(self, timeout=None): return 0
    proxy = Proxy()
    commands = []
    monkeypatch.setattr(subprocess, 'Popen', lambda command: commands.append(command) or proxy)
    monkeypatch.setattr(time, 'sleep', lambda _: None)
    monkeypatch.setattr(httpx.Client, 'get', lambda self, url: httpx.Response(
        200, json={'value': {'ready': True}}, request=httpx.Request('GET', url)))
    calls = []
    monkeypatch.setattr(ios, 'ui', lambda **kwargs: calls.append(kwargs))
    ios.usb_ui(device_id='phone', port=48122, wda_port=48123, device_port=8100)
    assert commands == [['iproxy', '--udid', 'phone', '--source', '127.0.0.1', '48123:8100']]
    assert calls == [{'device_id': 'phone', 'wda_url': 'http://127.0.0.1:48123', 'port': 48122}]
    assert proxy.stopped
