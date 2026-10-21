"""Load only model-related iOS model settings before importing Artemis."""
import json
import os
from pathlib import Path
from dotenv import dotenv_values


def configure(provider, source=None):
    project = Path(__file__).resolve().parents[1]
    override = source or os.environ.get('APPTESTER_DIR')
    if override:
        root = Path(override)
        main = dotenv_values(root / '.env')
        gemini = dotenv_values(root / '.tools/artemis/.env')
        provider_file = root / 'config/ai-providers.json'
    else:
        main = gemini = dotenv_values(project / '.env.ios')
        provider_file = project / 'config/ios-models.json'
    if provider == 'gemini':
        key = gemini.get('GOOGLE_API_KEY') or gemini.get('GEMINI_API_KEY')
        model = gemini.get('GEMINI_MODEL') or 'gemini-3.8-flash'
        if not key:
            raise ValueError('iOS model Gemini credential is missing')
        os.environ['GOOGLE_API_KEY'] = os.environ['GEMINI_API_KEY'] = key
        for name in ('HTTP_PROXY', 'HTTPS_PROXY'):
            if gemini.get(name):
                os.environ[name] = gemini[name]
        kind = 'google'
    elif provider == 'qwen':
        spec = json.loads(provider_file.read_text())['qwen']
        def resolve(field, default=None):
            return next((main[k] for k in spec.get(field, []) if main.get(k)), default)
        key = resolve('apiKeyEnv')
        if not key:
            raise ValueError('iOS model Qwen credential is missing')
        model = resolve('modelEnv', spec['defaultModel'])
        os.environ['OPENAI_API_KEY'] = key
        os.environ['OPENAI_BASE_URL'] = resolve('baseUrlEnv', spec['baseUrl'])
        # Keep the vendor-specific body for the compatibility probe.
        os.environ['ARTEMIS_QWEN_EXTRA_BODY'] = resolve('extraBodyEnv', json.dumps(spec.get('defaultExtraBody', {})))
        kind = 'openai'
    else:
        raise ValueError('Choose gemini or qwen')
    result = {'provider': kind, 'model': model}
    if provider == 'qwen':
        result['extra_body'] = json.loads(os.environ['ARTEMIS_QWEN_EXTRA_BODY'])
    return result
