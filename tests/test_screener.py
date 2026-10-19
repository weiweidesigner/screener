import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from scripts.run import Input,execute,tradingview_screen

ROOT=Path(__file__).resolve().parents[1]


def test_agent_filters_pagination_and_delayed_quote_metadata_are_preserved(monkeypatch):
    seen={}
    def post(url,**kwargs):
        seen.update(url=url,**kwargs)
        row={'name':'600519','description':'贵州茅台','close':1500,'currency':'CNY','exchange':'SSE','update_mode':'delayed_streaming_900'}
        return SimpleNamespace(ok=True,json=lambda:{'totalCount':40,'data':[
            {'s':'SSE:600519','d':[row.get(c) for c in kwargs['json']['columns']]}]})
    monkeypatch.setattr('requests.post',post)
    result=execute(payload={'market':'china','columns':['close'],'filters':[{'field':'close','operator':'greater','value':'SMA20'}],
                            'sortBy':'volume','ascending':False,'offset':10,'limit':5})
    assert seen['url']=='https://scanner.tradingview.com/china/scan'
    assert seen['json']['range']==[10,15]
    assert seen['json']['filter']==[{'left':'close','operation':'greater','right':'SMA20'}]
    assert result['rows'][0]['symbol']=='600519.SH' and result['rows'][0]['name']=='贵州茅台'
    assert result['rows'][0]['update_mode']=='delayed_streaming_900'
    assert result['rows'][0]['tradingViewUrl'].endswith('SSE%3A600519')
    assert result['nextOffset']==11


def test_any_conditions_and_session_credentials_do_not_leak_to_results(monkeypatch):
    monkeypatch.setenv('TRADINGVIEW_SESSION_ID','test-private-session')
    seen={}
    def post(url,**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(ok=True,json=lambda:{'totalCount':0,'data':[]})
    monkeypatch.setattr('requests.post',post)
    result=tradingview_screen({'market':'america','match':'any','filters':[
        {'field':'change','operator':'greater','value':3},{'field':'volume','operator':'greater','value':100000}]})
    assert 'filter2' in seen['json']
    assert seen['cookies']=={'sessionid':'test-private-session'}
    assert result['status']=='ok' and result['returned']==0
    assert 'test-private-session' not in json.dumps(result)


def test_invalid_arguments_cannot_reach_the_network(monkeypatch):
    monkeypatch.setattr('requests.post',lambda *a,**kw:pytest.fail('must validate first'))
    for args in ({'limit':999},{'filters':[{'field':'close','operator':'in_range','value':[1]}]},
                 {'market':'other'},{'url':'https://arbitrary.example'},{'token':'secret'}):
        with pytest.raises(ValidationError):execute(payload=args)


def test_relay_auth_stays_server_side_and_destination_is_loopback(tmp_path,monkeypatch):
    token=tmp_path/'secret';token.write_text('test-private-relay-token')
    monkeypatch.setenv('TRADINGVIEW_SCREENER_RELAY_URL','http://127.0.0.1:18767')
    monkeypatch.setenv('TRADINGVIEW_SCREENER_TOKEN_FILE',str(token))
    seen={}
    def post(url,**kwargs):
        seen.update(url=url,**kwargs)
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'provider':'tradingview','status':'ok','rows':[]})
    monkeypatch.setattr('requests.post',post)
    result=execute(payload={'market':'hongkong'})
    assert seen['headers']['Authorization']=='Bearer test-private-relay-token'
    assert result['transport']=='relay'
    assert 'test-private-relay-token' not in json.dumps(result)
    monkeypatch.setenv('TRADINGVIEW_SCREENER_RELAY_URL','https://arbitrary.example')
    with pytest.raises(RuntimeError):execute(payload={})


def test_cli_works_as_a_copied_skill_without_the_host_repository(tmp_path):
    copied=tmp_path/'installed-skill'
    shutil.copytree(ROOT/'scripts',copied/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
    env=dict(os.environ);env.pop('PYTHONPATH',None)
    script=str(copied/'scripts/run.py')
    schema=subprocess.run([sys.executable,script,'--schema'],cwd=tmp_path,env=env,capture_output=True,text=True,check=True)
    assert json.loads(schema.stdout)['properties']['market']['enum']==['china','hongkong','america']
    output=tmp_path/'result.json'
    result=subprocess.run([sys.executable,script,'--input-json','{"operation":"describe"}','--output',str(output)],cwd=tmp_path,env=env,capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)==json.loads(output.read_text())
    assert json.loads(result.stdout)['provider']=='tradingview'
    piped=subprocess.run([sys.executable,script],input='{"operation":"describe"}',cwd=tmp_path,env=env,capture_output=True,text=True,check=True)
    assert json.loads(piped.stdout)['status']=='ok'


def test_cli_rejects_invalid_payload_without_echoing_credentials():
    result=subprocess.run([sys.executable,str(ROOT/'scripts/run.py'),'--input-json','{"session":"test-private-value"}'],capture_output=True,text=True)
    assert result.returncode==2 and not result.stdout
    assert json.loads(result.stderr)['status']=='error'
    assert 'test-private-value' not in result.stderr
