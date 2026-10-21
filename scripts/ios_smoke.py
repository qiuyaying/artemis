"""Exercise the real iOS driver and Artemis MCP path on the dedicated simulator."""
import asyncio
import json
from pathlib import Path
from artemis.drivers.ios.session import ios_session

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/ios-smoke'

async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'kind': 'device_integration_not_agent_evaluation', 'steps': []}
    async with ios_session('F82C65F7-6DA6-4108-AB46-F54742E1C049', 'http://127.0.0.1:8100') as (ctx, driver, session):
        async def action(name, args):
            result = await session.call(name, args)
            report['steps'].append(result.model_dump(mode='json'))
            assert result.ok, result.message
        await action('manage_app', {'action':'launch', 'app_name':'com.apple.Preferences'})
        assert await driver.get_current_package() == 'com.apple.Preferences'
        observed = await session.observe(settle_ms=200)
        assert observed.ok and observed.hierarchy_ok
        data = await driver.get_screen_data()
        (OUT/'settings.png').write_bytes(data.screenshot_bytes)
        (OUT/'settings.xml').write_text(data.ui_hierarchy_xml)
        report['observed_elements'] = len(data.ui_elements)
        field = next(e for e in data.ui_elements if e['class'] == 'XCUIElementTypeSearchField')
        bounds = field['parsed_bounds']
        target = [round((bounds['left'] + bounds['right']) / 2 / data.width * 1000),
                  round((bounds['top'] + bounds['bottom']) / 2 / data.height * 1000)]
        await action('click', {'target': target})
        await action('input_text', {'text': 'Wi-Fi', 'clear_exist': False})
        await action('input_text', {'text': '蓝牙', 'clear_exist': True})
        typed = await driver.get_screen_data()
        assert any(e['class'] == 'XCUIElementTypeSearchField' and e['value'] == '蓝牙'
                   for e in typed.ui_elements), 'Input value did not match'
        (OUT/'typed.png').write_bytes(typed.screenshot_bytes)
        report['input_verified'] = True
        await action('swipe', {'start':[500,800], 'end':[500,300], 'duration_ms':500})
        data = await driver.get_screen_data()
        (OUT/'after-swipe.png').write_bytes(data.screenshot_bytes)
        (OUT/'after-swipe.xml').write_text(data.ui_hierarchy_xml)
        await action('press_key', {'key':'home'})
        unsupported = await session.call('press_key', {'key':'back'})
        assert not unsupported.ok
        report['unsupported_back'] = unsupported.model_dump(mode='json')
        report['status'] = 'passed'
    (OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))

asyncio.run(main())
