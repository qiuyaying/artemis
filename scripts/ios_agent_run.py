"""Bounded iOS SDK run using local model credentials."""
import argparse, asyncio, json
from pathlib import Path
from artemis_model_config import configure

async def main():
    p=argparse.ArgumentParser()
    p.add_argument('--model',choices=['gemini','qwen'],default='gemini')
    p.add_argument('--profile',choices=['flash','pro'],default='flash')
    p.add_argument('--device-id',required=True);p.add_argument('--wda-url',required=True)
    p.add_argument('--goal',required=True);p.add_argument('--max-steps',type=int,default=12)
    p.add_argument('--timeout',type=int,default=240)
    p.add_argument('--output',type=Path)
    p.add_argument('--session-id')
    args=p.parse_args()
    if args.max_steps<1 or args.timeout<1: p.error('Bounds must be positive')
    selected=configure(args.model)
    from artemis.config import LLMConfig
    from artemis.config.llm import _expand_default_into_nodes
    from artemis.sdk.agent import Agent
    from artemis.sdk.builders.agent_config_builder import AgentConfigBuilder
    from third_party.mobile_use.sdk.types.task import AgentProfile,TaskRequestCommon
    node={**selected,'fallback':selected.copy()}
    cfg=LLMConfig.model_validate(_expand_default_into_nodes({'default':node}))
    # Also set optional judges so they cannot silently use another provider.
    for field in ('history_analyzer','validator_pixel_safety_net','planner_validation','output_analyzer'):
        setattr(cfg,field,cfg.operator.model_copy(deep=True))
    profile=AgentProfile(name=args.profile,llm_config=cfg)
    config=(AgentConfigBuilder().for_ios_device(args.device_id,args.wda_url)
            .add_profile(profile,validate=True).with_default_profile(profile)
            .with_default_task_config(TaskRequestCommon(max_steps=args.max_steps)).build())
    agent=Agent(config=config, session_id=args.session_id)
    from artemis.drivers.ios.policy import PLATFORM_GUIDANCE
    try:
        await agent.init()
        result=await asyncio.wait_for(agent.run_task(goal=args.goal+'\n'+PLATFORM_GUIDANCE,profile=args.profile),args.timeout)
        report={'model':selected['model'],'profile':args.profile,'result':result,
                'task_status':agent._tasks[-1].status if agent._tasks else None}
    except Exception as exc:
        report={'model':selected['model'],'profile':args.profile,
                'task_status':'timeout' if isinstance(exc,TimeoutError) else 'failed',
                'error_type':type(exc).__name__}
    except asyncio.CancelledError:
        report={'model':selected['model'],'profile':args.profile,'task_status':'cancelled'}
    finally:
        await agent.clean()
    report['device_id']=args.device_id
    report['goal']=args.goal
    report['max_steps']=args.max_steps
    report['timeout_seconds']=args.timeout
    out=Path('benchmark');out.mkdir(exist_ok=True)
    destination=args.output or out/f'ios-agent-{args.model}-{args.profile}.json'
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,default=str,indent=2,ensure_ascii=False))
    print(json.dumps(report,default=str,ensure_ascii=False))
    if report['task_status'] != 'completed': raise SystemExit(1)

asyncio.run(main())
