"""Choose the actuator from the selected device, without an Android fallback for iOS."""

def create_actuator(ctx, controller=None):
    platform = str(getattr(getattr(ctx, 'device', None), 'mobile_platform', 'android'))
    if platform == 'ios':
        from artemis.mcp.actuators.ios import IOSActuator
        return IOSActuator(ctx, controller)
    from artemis.mcp.actuators.adb import AdbActuator
    return AdbActuator(ctx, controller)
