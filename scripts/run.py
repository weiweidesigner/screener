"""Standalone, read-only TradingView stock screener Skill and JSON CLI."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from typing import Literal
from urllib.parse import quote, urlparse
from pathlib import Path

import requests
from pydantic import BaseModel, ConfigDict, Field, model_validator

FIELD_PATTERN = r'^[A-Za-z0-9_.|%\-]{1,100}$'
TV_FIELDS = {
    'name':'交易代码', 'description':'证券名称', 'exchange':'交易所', 'currency':'原币',
    'close':'价格', 'change':'涨跌幅(%)', 'volume':'成交量(股)',
    'relative_volume_10d_calc':'相对成交量', 'market_cap_basic':'总市值(原币)',
    'price_earnings_ttm':'滚动市盈率', 'price_book_fq':'市净率',
    'earnings_per_share_diluted_yoy_growth_ttm':'EPS同比增速(%)',
    'SMA20':'20期均线', 'SMA60':'60期均线', 'RSI':'RSI',
    'sector':'行业板块', 'industry':'行业', 'update_mode':'源标注的行情更新模式',
}

class ScreenerFilter(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    field: str = Field(pattern=FIELD_PATTERN)
    operator: Literal['greater','egreater','less','eless','equal','nequal','in_range','not_in_range','in','not_in','match','nmatch','crosses','crosses_above','crosses_below','empty','nempty']
    value: float | str | list[float | str] | None = None

    @model_validator(mode='after')
    def operand(self):
        if self.operator in {'in_range','not_in_range'} and (not isinstance(self.value,list) or len(self.value)!=2):
            raise ValueError('范围筛选需要两个边界')
        if self.operator in {'in','not_in'} and (not isinstance(self.value,list) or not self.value):
            raise ValueError('集合筛选需要非空数组')
        if isinstance(self.value,list) and len(self.value)>100:raise ValueError('筛选数组最多100项')
        if self.operator not in {'empty','nempty'} and self.value is None:raise ValueError('筛选缺少value')
        return self

class TradingViewInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operation: Literal['describe','screen']='screen'
    market: Literal['china','hongkong','america']='china'
    columns: list[str] = Field(default_factory=lambda:['name','description','close','change','volume'],min_length=1,max_length=30)
    filters: list[ScreenerFilter] = Field(default_factory=list,max_length=20)
    match: Literal['all','any']='all'
    sortBy: str | None = None
    ascending: bool = False
    limit: int = Field(default=30,ge=1,le=100)
    offset: int = Field(default=0,ge=0,le=10000)

    @model_validator(mode='after')
    def fields(self):
        for field in [*self.columns,*([self.sortBy] if self.sortBy else [])]:
            if not re.fullmatch(FIELD_PATTERN,field):raise ValueError('字段名称无效')
        return self


def timestamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def availability():
    return {'screener':{'configured':True,'sessionConfigured':bool(os.getenv('TRADINGVIEW_SESSION_ID','').strip()),'transport':'relay' if os.getenv('TRADINGVIEW_SCREENER_RELAY_URL','').strip() else 'direct','note':'行情时效以每行update_mode为准'}}

def normalize_ticker(ticker):
    exchange,sep,code=ticker.partition(':')
    suffix={'SSE':'SH','SZSE':'SZ','BSE':'BJ','HKEX':'HK'}.get(exchange)
    if suffix:return (code.zfill(5) if suffix=='HK' else code)+'.'+suffix
    return code if sep else ticker

def tradingview_screen(payload):
    p=TradingViewInput.model_validate(payload)
    if p.operation=='describe':
        return dict(provider='tradingview',status='ok',markets=['china','hongkong','america'],fields=TV_FIELDS,
                    fieldReference='https://shner-elmo.github.io/TradingView-Screener/fields/stocks.html',
                    note='字段不局限于示例。可选SMA20|1W等周期字段；value可引用其他字段，例如close greater SMA20。筛选和排序由agent决定。',availability=availability()['screener'])
    relay=os.getenv('TRADINGVIEW_SCREENER_RELAY_URL','').strip().rstrip('/')
    if relay:
        endpoint=urlparse(relay)
        if endpoint.scheme!='http' or endpoint.hostname not in {'127.0.0.1','localhost'}:
            raise RuntimeError('TradingView转发必须使用SSH隧道的本地回环地址')
        try:
            token=Path(os.environ['TRADINGVIEW_SCREENER_TOKEN_FILE']).read_text().strip()
            response=requests.post(relay+'/screen',json=p.model_dump(),headers={'Authorization':'Bearer '+token},timeout=25)
            response.raise_for_status();result=response.json()
            if result.get('provider')!='tradingview' or result.get('status')!='ok' or not isinstance(result.get('rows'),list):raise ValueError('invalid relay response')
            return dict(result,transport='relay')
        except (OSError,KeyError,ValueError,requests.RequestException):
            raise RuntimeError('TradingView查询节点不可用，请确认查询节点在线；本轮未取得筛选数据') from None
    from tradingview_screener import Query,Or
    columns=list(dict.fromkeys([*p.columns,'name','description','exchange','currency','update_mode']))
    query=Query().set_markets(p.market).select(*columns).offset(p.offset).limit(p.offset+p.limit)
    query.query.setdefault('options',{})['lang']='zh'
    expressions=[dict(left=f.field,operation=f.operator,right=f.value) for f in p.filters]
    if expressions:
        query=query.where(*expressions) if p.match=='all' else query.where2(Or(*expressions))
    if p.sortBy:query=query.order_by(p.sortBy,ascending=p.ascending)
    session=os.getenv('TRADINGVIEW_SESSION_ID','').strip()
    try:
        count,frame=query.get_scanner_data(timeout=20,**({'cookies':{'sessionid':session}} if session else {}))
        rows=json.loads(frame.to_json(orient='records',force_ascii=False))
    except (requests.RequestException,ValueError,KeyError,TypeError):
        raise RuntimeError('TradingView筛选请求失败，请检查市场、字段和筛选参数或稍后重试；未返回候选') from None
    for row in rows:
        ticker=row['ticker'];row['symbol']=normalize_ticker(ticker);row['code']=row.get('name')
        row['name']=row.get('description') or row.get('name') or row['symbol']
        row['tradingViewUrl']='https://www.tradingview.com/chart/?symbol='+quote(ticker,safe='')
    return dict(provider='tradingview',status='ok',market=p.market,source='TradingView Screener',sourceUrl='https://www.tradingview.com/screener/',
                fetchedAt=timestamp(),rows=rows,totalMatched=count,returned=len(rows),nextOffset=p.offset+len(rows) if p.offset+len(rows)<count else None,
                query=p.model_dump(),note='筛选快照用于候选研究，不是成交报价。update_mode保留实际更新模式；fetchedAt是抓取时间，不是行情时间。')




Input = TradingViewInput


def execute(service=None, owner=None, payload=None):
    """Compatibility entry point; the screener never reads account identity."""
    return tradingview_screen(payload if payload is not None else {})


def main(argv=None):
    import argparse
    import sys
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--schema',action='store_true',help='Print the JSON input schema without network access')
    mode.add_argument('--describe',action='store_true',help='Describe markets, field examples and availability')
    mode.add_argument('--input',type=Path,help='Read arguments from a JSON file')
    mode.add_argument('--input-json',help='Read arguments as a JSON object')
    parser.add_argument('--output',type=Path,help='Write the result to a JSON file as well as stdout')
    args=parser.parse_args(argv)
    try:
        if args.schema:result=Input.model_json_schema()
        elif args.describe:result=tradingview_screen({'operation':'describe'})
        else:
            if args.input:payload=json.loads(args.input.read_text())
            elif args.input_json is not None:payload=json.loads(args.input_json)
            elif not sys.stdin.isatty():payload=json.load(sys.stdin)
            else:parser.error('Pass --input, --input-json, --describe, --schema, or pipe a JSON object')
            result=tradingview_screen(payload)
        output=json.dumps(result,ensure_ascii=False,allow_nan=False)
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(output+'\n')
        print(output)
        return 0
    except Exception:
        # Never echo a session cookie, relay token or request body in CLI errors.
        print(json.dumps({'status':'error','reason':'Screener request failed. Check input schema, field availability and network or relay connectivity.'}),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
