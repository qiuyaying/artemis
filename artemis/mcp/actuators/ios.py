"""iOS actuator for the existing Artemis MCP action contract."""
import asyncio

from artemis.controllers.unified_controller import UnifiedMobileController
from artemis.drivers.factory import get_driver
from artemis.mcp.action_types import ActionCode, ActionResult


class IOSActuator:
    from artemis.drivers.ios.policy import BLOCKED_TOOLS as unsupported_tools

    def __init__(self, ctx, controller=None):
        self.ctx = ctx
        self.driver = get_driver(ctx)
        self.controller = controller or UnifiedMobileController(ctx)

    def capabilities(self):
        return frozenset({'click_sequence', 'click', 'long_press', 'input_text', 'swipe',
                          'press_key', 'manage_app', 'wait_for_delay',
                          'observe_screen', 'take_screenshot', 'get_ui_hierarchy'})

    def extensions(self):
        return []

    async def _run(self, name, operation):
        try:
            if await operation() is False:
                return ActionResult.failure(name, f'{name} did not complete')
            return ActionResult.success(name, f'{name} executed; task outcome requires verification')
        except NotImplementedError as exc:
            return ActionResult.failure(name, str(exc), code=ActionCode.UNSUPPORTED)
        except ValueError as exc:
            return ActionResult.failure(name, str(exc), code=ActionCode.INVALID_ARGS)
        except Exception as exc:
            return ActionResult.failure(name, str(exc), detail=type(exc).__name__)

    async def click(self, nx, ny, times=1, delay_ms=100):
        return await self._run('click', lambda: self.driver.tap_normalized(nx, ny, times=times, delay_ms=delay_ms))

    async def click_sequence(self, points, delay_ms=50):
        for i, (x, y) in enumerate(points):
            result = await self.click(x, y)
            if not result.ok:
                return ActionResult.failure('click_sequence', f'Stopped at action {i + 1}: {result.message}')
            if i + 1 < len(points):
                await asyncio.sleep(max(0, delay_ms)/1000)
        return ActionResult.success('click_sequence', 'Sequence executed')

    async def long_press(self, nx, ny, duration_ms=1000):
        return await self._run('long_press', lambda: self.driver.tap_normalized(nx, ny, long_press=True, duration_ms=duration_ms))

    async def swipe(self, start, end, duration_ms=800):
        return await self._run('swipe', lambda: self.driver.swipe_normalized(list(start), list(end), duration_ms))

    async def input_text(self, text, target=None, clear_exist=True):
        async def operation():
            if target is not None:
                await self.driver.tap_normalized(*target)
            return await self.driver.input_text(text, clear_existing=clear_exist)
        return await self._run('input_text', operation)

    async def press_key(self, key):
        return await self._run('press_key', lambda: self.driver.press_key(key))

    async def manage_app(self, action, app_name):
        if action not in ('launch', 'stop'):
            return ActionResult.failure('manage_app', 'Supported actions: launch, stop; app_name must be a bundle ID')
        operation = self.driver.launch_app if action == 'launch' else self.driver.stop_app
        return await self._run('manage_app', lambda: operation(app_name))

    async def wait_for_delay(self, time_in_ms):
        if not 0 <= time_in_ms <= 30000:
            return ActionResult.failure('wait_for_delay', 'Delay must be between 0 and 30000 ms')
        return await self._run('wait_for_delay', lambda: self.driver.wait_for_delay(time_in_ms / 1000))

    async def take_screenshot(self):
        return (await self.driver.get_screen_data()).screenshot_base64

    async def get_ui_elements(self):
        return (await self.driver.get_screen_data()).ui_elements

    async def get_screen_data(self):
        return await self.controller.get_screen_data()
