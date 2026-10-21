"""Verify vision and tool calling together, using a synthetic image only."""
import argparse, asyncio, base64, io, json, os
from pathlib import Path
from PIL import Image
from artemis_model_config import configure

async def main():
    p=argparse.ArgumentParser(); p.add_argument('--model',choices=['gemini','qwen'],required=True)
    args=p.parse_args(); cfg=configure(args.model)
    from langchain_core.messages import HumanMessage
    if args.model=='gemini':
        from langchain_google_genai import ChatGoogleGenerativeAI
        model=ChatGoogleGenerativeAI(model=cfg['model'],api_key=os.environ['GOOGLE_API_KEY'],timeout=45,max_retries=0)
    else:
        from langchain_openai import ChatOpenAI
        model=ChatOpenAI(model=cfg['model'],api_key=os.environ['OPENAI_API_KEY'],base_url=os.environ['OPENAI_BASE_URL'],timeout=45,max_retries=0,extra_body=json.loads(os.environ['ARTEMIS_QWEN_EXTRA_BODY']))
    raw=io.BytesIO(); Image.new('RGB',(64,64),'red').save(raw,format='PNG')
    tool={'type':'function','function':{'name':'report_color','description':'Report the visible image color','parameters':{'type':'object','properties':{'color':{'type':'string'}},'required':['color']}}}
    report={'provider':args.model,'model':cfg['model'],'test':'synthetic image + function call'}
    try:
        result=await asyncio.wait_for(model.bind_tools([tool]).ainvoke([HumanMessage(content=[{'type':'text','text':'Inspect the image. Call report_color with its dominant color in English.'},{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode()}}])]),60)
        calls=result.tool_calls
        report['passed']=any(c['name']=='report_color' and c['args'].get('color','').lower()=='red' for c in calls)
        report['tool_calls']=calls
    except Exception as e:
        detail=str(e)
        for name in ('GOOGLE_API_KEY','GEMINI_API_KEY','OPENAI_API_KEY'):
            if os.getenv(name): detail=detail.replace(os.environ[name],'<redacted>')
        report.update(passed=False,error_type=type(e).__name__,detail=detail[:800])
    out=Path('benchmark');out.mkdir(exist_ok=True)
    (out/f'ios-model-probe-{args.model}.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,ensure_ascii=False))

asyncio.run(main())
