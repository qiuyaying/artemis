from unittest.mock import AsyncMock
from types import SimpleNamespace
import pytest
from artemis.context import ArtemisContext, DevicePlatform
from artemis.sdk.agent import Agent
from artemis.sdk.builders.agent_config_builder import AgentConfigBuilder
from artemis.mcp.actuators.ios import IOSActuator
from artemis.mcp.action_manifest import filter_declarations
from artemis.core.tool_declaration import ToolDeclaration


def config():
    return AgentConfigBuilder().for_ios_device('sim', 'http://localhost:8100').build(validate_profiles=False)


@pytest.mark.asyncio
async def test_ios_init_never_initializes_adb(monkeypatch):
    agent = Agent(config=config(), device_id='sim2')
    monkeypatch.setattr(agent, '_init_clients', lambda **kw: pytest.fail('ADB initialized'))
    await agent.init(device_id='sim3')
    assert agent._device_context.mobile_platform == DevicePlatform.IOS
    assert agent._device_context.device_id == 'sim3'
    assert agent._adb_client is None
    assert not agent._config.video_recording_tools_enabled
    assert agent._config.disable_device_probes
    await agent._ensure_device_unlocked()
    await agent.clean()


@pytest.mark.asyncio
async def test_ios_connection_cleanup_and_unsupported_setup(monkeypatch):
    agent = Agent(config=config()); await agent.init()
    ctx = ArtemisContext(device=agent._device_context)
    driver = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock(), screen_size=(100,200))
    ctx._active_driver = driver
    monkeypatch.setattr('artemis.mcp.action_session.get_action_session', AsyncMock())
    await agent._prepare_device_connection(ctx)
    assert (ctx.device.device_width,ctx.device.device_height)==(100,200)
    assert isinstance(ctx.actuator, IOSActuator)
    await agent._cleanup_device_connection(ctx)
    driver.disconnect.assert_awaited_once()
    assert ctx._active_driver is None
    task=SimpleNamespace(request=SimpleNamespace(app_path='test.apk',locked_app_package='com.test'))
    with pytest.raises(ValueError,match='APK'):
        await agent._prepare_app_installation(task)
    with pytest.raises(ValueError,match='locking'):
        await agent._prepare_app_lock(task,ctx)


def test_ios_filters_android_tools():
    actuator=SimpleNamespace(capabilities=lambda: IOSActuator.capabilities(None), extensions=lambda: [], unsupported_tools=IOSActuator.unsupported_tools)
    names=['click','run_adb_command','ask_diagnoser','video_analyzer','report_task_status']
    declarations=[ToolDeclaration(n,n,{}) for n in names]
    assert [d.name for d in filter_declarations(declarations,actuator,'flash')]==['click','report_task_status']


def test_qwen_endpoint_preserves_extra_body_and_cache_identity(monkeypatch):
    from artemis.llm.router import ModelEndpoint, ModelFactory
    import langchain_openai
    seen = {}
    def model(**kwargs):
        seen.update(kwargs)
        return object()
    monkeypatch.setattr(langchain_openai, 'ChatOpenAI', model)
    endpoint = ModelEndpoint(provider='openai', model_name='qwen-test', api_key='test', extra_body={'enable_thinking':False})
    ModelFactory.create_model(endpoint)
    assert seen['extra_body'] == {'enable_thinking':False}
    assert endpoint.cache_key() != endpoint.model_copy(update={'extra_body':{'enable_thinking':True}}).cache_key()


def test_non_google_memory_does_not_construct_google_client(monkeypatch):
    from artemis.agents.flash import summarizer as module
    from unittest.mock import MagicMock
    ctx = MagicMock()
    ctx.llm_config.summarizer.provider = 'openai'
    model = MagicMock()
    resolver = MagicMock(return_value=model)
    monkeypatch.setattr(module, 'get_llm', resolver)
    monkeypatch.setattr(module, 'get_google_llm', lambda **kw: pytest.fail('Hidden Google client'))
    service = module.VisualStepSummarizer(ctx, model_name='gemini-default')
    assert service._llm is model
    resolver.assert_called_once_with(ctx, name='summarizer', is_utils=False)
