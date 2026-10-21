"""Native dashboard worker: shared model config, tracing, IPC and cancellation."""
import argparse
import asyncio

from artemis.config import settings
from artemis.drivers.ios.policy import PLATFORM_GUIDANCE
from artemis.sdk.agent import Agent
from third_party.mobile_use.main import new_default_config_builder


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--device-id', required=True)
    parser.add_argument('--wda-url', required=True)
    parser.add_argument('--session-id', required=True)
    parser.add_argument('--profile', choices=['flash', 'pro'], default='flash')
    parser.add_argument('--goal', required=True)
    parser.add_argument('--expected-output')
    parser.add_argument('--verification-level')
    parser.add_argument('--explorer-mode')
    parser.add_argument('--enable-outputter', dest='outputter', action='store_true', default=None)
    parser.add_argument('--disable-outputter', dest='outputter', action='store_false')
    args = parser.parse_args()
    builder = new_default_config_builder().for_ios_device(args.device_id, args.wda_url)
    if args.verification_level:
        builder.with_verification_level(args.verification_level)
    if args.explorer_mode:
        builder.with_explorer(pro_mode=args.explorer_mode)
    if args.outputter is not None:
        builder.with_outputter(enabled=args.outputter)
    agent = Agent(config=builder.build(), session_id=args.session_id)
    try:
        await agent.init()
        task = agent.new_task(args.goal + '\n' + PLATFORM_GUIDANCE)
        task.using_profile(args.profile).with_name('web_ios_' + args.session_id)
        task.with_trace_recording(path=str(settings.TRACES_PATH))
        if args.expected_output:
            task.with_output_description(args.expected_output)
        await agent.run_task(request=task.build())
        if not agent._tasks or agent._tasks[-1].status != 'completed':
            raise SystemExit(1)
    finally:
        await agent.clean()


if __name__ == '__main__':
    asyncio.run(main())
