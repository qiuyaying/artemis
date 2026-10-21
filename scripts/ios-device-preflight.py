"""Read-only inventory and explicit real-device WDA build plan."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/artemis-client/src"))
from dotenv import dotenv_values

p=argparse.ArgumentParser()
p.add_argument('--apptester-dir',type=Path,default=Path.home()/'Documents/APP-tester')
p.add_argument('--use-apptester',action='store_true',help='Read the configured device ID and signing team')
p.add_argument('--device-id');p.add_argument('--team-id')
a=p.parse_args()
env=dotenv_values(a.apptester_dir/'.env') if a.use_apptester else {}
udid=a.device_id or env.get('MIDSCENE_IOS_DEVICE_ID')
team=a.team_id or env.get('IOS_MEDIA_SEEDER_DEVELOPMENT_TEAM')
from artemis.drivers.ios.discovery import discover_devices
inventory = discover_devices()
devices = inventory['devices']
selected = next((d for d in devices if udid in (d['udid'], d['identifier'])), None) if udid else None
print(json.dumps({**inventory, 'selected': selected,
    'signing_team_configured': bool(team),
    'ready_for_build_plan': bool(selected and selected['usb_connected'] and team
                                 and selected['developer_mode'] != 'disabled'),
    'note': 'Physical devices only. USB presence does not prove WDA readiness. Unknown developer mode requires verification.'},
    ensure_ascii=False, indent=2))
