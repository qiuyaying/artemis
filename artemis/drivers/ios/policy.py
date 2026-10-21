"""Platform tool policy shared by SDK agents and direct declarations."""
BLOCKED_TOOLS = frozenset({
    'run_adb_command', 'ask_diagnoser', 'video_analyzer',
    'start_video_recording', 'stop_video_recording',
})
PLATFORM_GUIDANCE = '''\nDevice platform: iOS via WebDriverAgent. Use screenshot/UI observations.
App identifiers are iOS bundle IDs (for example com.apple.Preferences).
press_key supports HOME and ENTER only; use visible UI controls for back navigation.
ADB, Android intents, APK installation, shell commands and video recording are unavailable.
Verify task outcomes from fresh observations; tool execution alone is not success.
'''


def guidance(ctx):
    return PLATFORM_GUIDANCE if str(getattr(ctx.device, 'mobile_platform', '')) == 'ios' else ''
