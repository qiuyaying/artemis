"""Read-only Xcode inventory, with USB presence independent of developer tunnels."""
import json
import subprocess
import tempfile
from pathlib import Path


def normalize_devices(payload, usb_ids=()):
    devices = []
    for raw in payload.get('result', {}).get('devices', []):
        props = raw.get('properties') or {}
        hardware = props.get('hardware') or raw.get('hardwareProperties', {})
        state = props.get('state') or raw.get('deviceProperties', {})
        connection = props.get('connection') or raw.get('connectionProperties', {})
        transport = connection.get('transportType')
        if transport == 'sameMachine' or hardware.get('platform') != 'iOS':
            continue
        udid = hardware.get('udid')
        if not udid:
            continue
        devices.append({
            'name': state.get('name'), 'udid': udid,
            'identifier': raw.get('identifier'), 'transport': transport,
            'kind': 'physical', 'device_type': hardware.get('deviceType', 'unknown'),
            'usb_connected': udid in usb_ids,
            'developer_mode': state.get('developerModeStatus') or
                raw.get('deviceProperties', {}).get('developerModeStatus', 'unknown'),
            'tunnel': connection.get('state', connection.get('tunnelState', 'unknown')),
            'pairing': connection.get('pairingState', 'unknown'),
        })
    return devices


def normalize_simulators(payload):
    devices = []
    for runtime, entries in payload.get('devices', {}).items():
        if '.iOS-' not in runtime:
            continue
        for entry in entries:
            if not entry.get('isAvailable'):
                continue
            device_type = entry.get('deviceTypeIdentifier', '')
            family = 'iPad' if 'iPad' in device_type else 'iPhone' if 'iPhone' in device_type else None
            if family is None:
                continue
            devices.append({'udid': entry['udid'], 'identifier': entry['udid'],
                            'name': entry['name'], 'kind': 'simulator', 'device_type': family,
                            'runtime': runtime, 'state': entry['state'],
                            'connected': entry['state'] == 'Booted', 'usb_connected': False,
                            'transport': 'simulator', 'developer_mode': 'not_required',
                            'pairing': 'not_required'})
    return devices


def discover_devices(include_simulators=False):
    warnings = []
    try:
        usb = subprocess.run(['idevice_id', '-l'], capture_output=True, text=True,
                             check=True, timeout=15).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        usb = []
        warnings.append('USB presence unavailable; install libimobiledevice or check usbmuxd.')
    try:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'devices.json'
            subprocess.run(['xcrun', 'devicectl', 'list', 'devices', '--json-output', str(output)],
                           capture_output=True, text=True, check=True, timeout=30)
            devices = normalize_devices(json.loads(output.read_text()), usb)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        if not include_simulators:
            raise RuntimeError('Cannot list iOS devices; check Xcode selection and pairing.') from exc
        devices = []
        warnings.append('Physical-device inventory unavailable; check Xcode selection and pairing.')
    known = {d['udid'] for d in devices}
    for udid in usb:
        if udid not in known:
            devices.append({'udid': udid, 'name': None, 'usb_connected': True,
                            'pairing': 'unknown', 'developer_mode': 'unknown',
                            'tunnel': 'unknown', 'transport': 'wired', 'identifier': None})
    for device in devices:
        device['kind'] = 'physical'
        device['connected'] = device['usb_connected']
    if include_simulators:
        try:
            result = subprocess.run(['xcrun', 'simctl', 'list', 'devices', 'available', '-j'],
                                    capture_output=True, text=True, check=True, timeout=30)
            devices.extend(normalize_simulators(json.loads(result.stdout)))
        except (OSError, ValueError, subprocess.SubprocessError):
            warnings.append('Simulator inventory unavailable; check Xcode and installed iOS runtimes.')
    return {'devices': devices, 'warnings': warnings}
