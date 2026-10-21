import time
import re
from fastapi.testclient import TestClient
from artemis.drivers.ios.web import make_app


def credentials(client):
    html = client.get('/').text
    return {'x-ios-token':re.search("const token='([^']+)'",html).group(1)}


def wait_done(client, headers):
    for _ in range(200):
        result=client.get('/api/task',headers=headers).json()
        if not result['active']: return result['task']
        time.sleep(.02)
    raise AssertionError('worker did not stop')


def test_auth_validation_and_success(tmp_path):
    runner=tmp_path/'runner.py'
    runner.write_text('import sys,json,time\nfrom pathlib import Path\ntime.sleep(.2)\nPath(sys.argv[sys.argv.index("--output")+1]).write_text(json.dumps({"task_status":"completed","result":{"status":"completed"}}))\n')
    with TestClient(make_app('sim','http://wda',runner_path=runner,run_dir=tmp_path)) as client:
        h=credentials(client)
        assert client.post('/api/task',json={'goal':'test'}).status_code==403
        assert client.post('/api/task',headers=h,json={'goal':'test','model':'arbitrary'}).status_code==422
        assert client.post('/api/task',headers=h,json={'goal':'  '}).status_code==422
        assert client.post('/api/task',headers=h,json={'goal':'test'}).status_code==202
        assert client.post('/api/task',headers=h,json={'goal':'other'}).status_code==409
        assert client.get('/api/screen',headers=h).status_code==409
        assert client.post('/api/action',headers=h,json={'name':'press_key'}).status_code==409
        assert wait_done(client,h)['status']=='completed'


def test_cancel_releases_worker_and_allows_next_task(tmp_path):
    runner=tmp_path/'runner.py'
    runner.write_text('import time\ntime.sleep(30)\n')
    with TestClient(make_app('sim','http://wda',runner_path=runner,run_dir=tmp_path)) as client:
        h=credentials(client)
        for _ in range(2):
            assert client.post('/api/task',headers=h,json={'goal':'test'}).status_code==202
            assert client.post('/api/task/cancel',headers=h).status_code==200
            assert wait_done(client,h)['status']=='cancelled'


def test_worker_failure_is_not_reported_success(tmp_path):
    runner=tmp_path/'runner.py';runner.write_text('raise SystemExit(1)\n')
    with TestClient(make_app('sim','http://wda',runner_path=runner,run_dir=tmp_path)) as client:
        h=credentials(client)
        client.post('/api/task',headers=h,json={'goal':'test'})
        assert wait_done(client,h)['status']=='failed'
