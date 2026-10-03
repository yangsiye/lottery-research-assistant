from __future__ import annotations
import re
from datetime import date, datetime
import requests
from .lifecycle import TZ

UA='Mozilla/5.0 lottery-research-assistant/1.5'

class FetchError(RuntimeError): pass


def _ints(value):
    if isinstance(value,list): return [int(x) for x in value]
    return [int(x) for x in re.split(r'[, +|\-]+',str(value).strip()) if x]


def validate_archive(rows,lottery,periods):
    from .rules import DRAW_DAYS, closure_reason
    limits={'ssq':(33,16,6,1),'dlt':(35,12,5,2)}
    max_m,max_b,mp,bp=limits[lottery]
    unique={}
    for row in rows:
        issue=row['issue'];day=date.fromisoformat(row['draw_date'])
        if not re.fullmatch(r'\d{5}|\d{7}',issue) or day>datetime.now(TZ).date():
            raise FetchError('invalid issue/date in official archive')
        if day.weekday() not in DRAW_DAYS[lottery] or closure_reason(day):
            raise FetchError('official archive conflicts with draw calendar')
        for numbers,maximum,pick in ((row['main'],max_m,mp),(row['bonus'],max_b,bp)):
            if len(numbers)!=pick or len(set(numbers))!=pick or not all(1<=x<=maximum for x in numbers):
                raise FetchError('invalid number count/range in official archive')
        if issue in unique and (unique[issue]['main']!=row['main'] or unique[issue]['bonus']!=row['bonus'] or unique[issue]['draw_date']!=row['draw_date']):
            raise FetchError('conflicting duplicate official issue')
        unique[issue]=row
    ordered=sorted(unique.values(),key=lambda r:(r['draw_date'],r['issue']))
    if len(ordered)<periods: raise FetchError(f'官方历史不足：要求 {periods}，仅得到 {len(ordered)}；不降级为模拟数据')
    ordered=ordered[-periods:]
    for a,b in zip(ordered,ordered[1:]):
        if a['draw_date']>=b['draw_date']: raise FetchError('duplicate/non-increasing draw dates')
        if a['issue'][:-3]==b['issue'][:-3] and int(b['issue'][-3:])-int(a['issue'][-3:])!=1:
            raise FetchError('issue gap in official archive')
    return ordered


def _fetch_ssq_primary(periods=100):
    if not 1<=periods<=5000: raise ValueError('invalid periods')
    session=requests.Session()
    session.headers.update({'User-Agent':UA,'Referer':'https://www.cwl.gov.cn/'})
    out=[]
    try:
        session.get('https://www.cwl.gov.cn/',timeout=15)
        for page in range(1,(periods+99)//100+1):
            response=session.get('https://www.cwl.gov.cn/cwl_admin/kjxx/findDrawNotice',
                params={'name':'ssq','issueCount':periods,'pageNo':page,'pageSize':100,'systemType':'PC'},timeout=20)
            response.raise_for_status()
            rows=response.json().get('result') or []
            if not rows: break
            for row in rows:
                out.append({'lottery':'ssq','issue':str(row.get('code') or ''),
                            'draw_date':str(row.get('date') or '')[:10],
                            'main':sorted(_ints(row.get('red',''))),'bonus':sorted(_ints(row.get('blue',''))),
                            'source':'cwl.gov.cn','prize_data':{'official_record':row}})
            if len({r['issue'] for r in out})>=periods: break
        return validate_archive(out,'ssq',periods)
    except Exception as e:
        raise FetchError(f'SSQ official fetch failed: {e}') from e
    finally: session.close()


def _fetch_dlt_primary(periods=100):
    if not 1<=periods<=5000: raise ValueError('invalid periods')
    out=[]
    try:
        for page in range(1,(periods+99)//100+1):
            response=requests.get('https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry',
                params={'gameNo':'85','provinceId':'0','pageSize':100,'isVerify':'1','pageNo':page},
                headers={'User-Agent':UA,'Referer':'https://www.lottery.gov.cn/'},timeout=20)
            response.raise_for_status()
            rows=(response.json().get('value') or {}).get('list') or []
            if not rows: break
            for row in rows:
                nums=_ints(row.get('lotteryDrawResult') or row.get('drawResult') or row.get('result') or '')
                if len(nums)!=7: raise FetchError('invalid DLT result field')
                out.append({'lottery':'dlt','issue':str(row.get('lotteryDrawNum') or row.get('drawNum') or row.get('issue') or ''),
                    'draw_date':str(row.get('lotteryDrawTime') or row.get('drawTime') or row.get('date') or '')[:10],
                    'main':sorted(nums[:5]),'bonus':sorted(nums[5:]),'source':'sporttery.cn',
                    'prize_data':{'official_record':row}})
            if len({r['issue'] for r in out})>=periods: break
        return validate_archive(out,'dlt',periods)
    except Exception as e: raise FetchError(f'DLT official fetch failed: {e}') from e


def _with_official_fallback(primary,fallback,periods):
    if not isinstance(periods,int) or not 1<=periods<=5000: raise ValueError('invalid periods')
    try: return primary(periods)
    except FetchError as primary_error:
        try:
            rows=fallback(periods)
            for row in rows: row['prize_data']['primary_source_error']=str(primary_error)
            return rows
        except Exception as fallback_error:
            raise FetchError(f'{primary_error}; provincial official fallback failed: {fallback_error}') from fallback_error


def fetch_ssq(periods=100):
    from .official_fallbacks import fetch_shanghai_ssq
    return _with_official_fallback(_fetch_ssq_primary,fetch_shanghai_ssq,periods)


def fetch_dlt(periods=100):
    from .official_fallbacks import fetch_gansu_dlt
    return _with_official_fallback(_fetch_dlt_primary,fetch_gansu_dlt,periods)
