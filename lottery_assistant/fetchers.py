from __future__ import annotations
import re
from datetime import date, datetime, timedelta, time
import requests
from .lifecycle import TZ

UA='Mozilla/5.0 lottery-research-assistant/1.5'

class FetchError(RuntimeError): pass


class ArchiveConflictError(FetchError):
    """A newly observed official result contradicts a persisted official signature."""
    def __init__(self,message,evidence=None):
        super().__init__(message)
        self.evidence=evidence or {}


def _ints(value):
    if isinstance(value,list): return [int(x) for x in value]
    return [int(x) for x in re.split(r'[, +|\-]+',str(value).strip()) if x]


def validate_archive(rows,lottery,periods,now=None):
    from .rules import DRAW_DAYS, CLOSURES, closure_reason
    if not isinstance(periods,int) or isinstance(periods,bool) or not 1<=periods<=5000:
        raise ValueError('invalid periods')
    today=(now or datetime.now(TZ)).astimezone(TZ).date()
    limits={'ssq':(33,16,6,1),'dlt':(35,12,5,2)}
    max_m,max_b,mp,bp=limits[lottery]
    unique={}
    for row in rows:
        try:
            issue=row['issue'];day=date.fromisoformat(row['draw_date'])
        except (KeyError,TypeError,ValueError) as e:
            raise FetchError('invalid issue/date in official archive') from e
        pattern=r'\d{7}' if lottery=='ssq' else r'\d{5}'
        year=str(day.year) if lottery=='ssq' else str(day.year)[-2:]
        if (not isinstance(issue,str) or not re.fullmatch(pattern,issue)
            or issue[:-3]!=year or int(issue[-3:])<1 or day>today):
            raise FetchError('invalid issue/date in official archive')
        if row.get('lottery',lottery)!=lottery:
            raise FetchError('wrong lottery in official archive')
        if day.weekday() not in DRAW_DAYS[lottery] or closure_reason(day):
            raise FetchError('official archive conflicts with draw calendar')
        for numbers,maximum,pick in ((row['main'],max_m,mp),(row['bonus'],max_b,bp)):
            if (len(numbers)!=pick or len(set(numbers))!=pick or
                not all(isinstance(x,int) and not isinstance(x,bool) and 1<=x<=maximum for x in numbers)):
                raise FetchError('invalid number count/range in official archive')
        if issue in unique and (sorted(unique[issue]['main'])!=sorted(row['main']) or sorted(unique[issue]['bonus'])!=sorted(row['bonus']) or unique[issue]['draw_date']!=row['draw_date']):
            raise FetchError('conflicting duplicate official issue')
        unique[issue]=row
    ordered=sorted(unique.values(),key=lambda r:(r['draw_date'],r['issue']))
    if len(ordered)<periods: raise FetchError(f'官方历史不足：要求 {periods}，仅得到 {len(ordered)}；不降级为模拟数据')
    ordered=ordered[-periods:]
    for a,b in zip(ordered,ordered[1:]):
        if a['draw_date']>=b['draw_date']: raise FetchError('duplicate/non-increasing draw dates')
        if a['issue'][:-3]==b['issue'][:-3] and int(b['issue'][-3:])-int(a['issue'][-3:])!=1:
            raise FetchError('issue gap in official archive')
        # Only apply annual closures for years whose official calendar has been verified.
        if a['draw_date'][:4]==b['draw_date'][:4] and int(a['draw_date'][:4]) in CLOSURES:
            expected=date.fromisoformat(a['draw_date'])+timedelta(days=1)
            while expected.weekday() not in DRAW_DAYS[lottery] or closure_reason(expected):
                expected+=timedelta(days=1)
            if expected.isoformat()!=b['draw_date']:
                raise FetchError('draw-date gap in official archive calendar')
    return ordered


def validate_sync_archive(rows,existing,lottery,periods,now=None):
    """Preflight the whole source batch before any persisted official result changes."""
    from .rules import previous_draw_day,draw_status
    now=(now or datetime.now(TZ)).astimezone(TZ)
    rows=validate_archive(rows,lottery,periods,now)
    allowed={'ssq':{'cwl.gov.cn','swlc.net.cn'},'dlt':{'sporttery.cn','gstc.org.cn'}}
    old={r['issue']:r for r in existing}
    for r in rows:
        if r.get('source') not in allowed[lottery]:
            raise FetchError('unverified source in official sync')
        previous=old.get(r['issue'])
        if previous and (previous['draw_date']!=r['draw_date'] or
                         sorted(previous['main_numbers'])!=sorted(r['main']) or
                         sorted(previous['bonus_numbers'])!=sorted(r['bonus'])):
            raise ArchiveConflictError(f"official source conflicts with persisted issue {r['issue']}; manual audit required",
                {'issue':r['issue'],'existing':{k:previous.get(k) for k in
                    ('draw_date','main_numbers','bonus_numbers','source')},
                 'observed':{k:r.get(k) for k in ('draw_date','main','bonus','source')}})
    latest=rows[-1]['draw_date']
    if existing and latest<max(r['draw_date'] for r in existing):
        raise FetchError('official source archive regressed behind persisted data')
    expected=previous_draw_day(lottery,now.date()).isoformat()
    if latest<expected:
        raise FetchError(f'official source stale: expected at least {expected}, got {latest}')
    if latest==now.date().isoformat():
        draw_time={'ssq':time(21,15),'dlt':time(21,10)}[lottery]
        if draw_status(lottery,now.date())['status']!='WAITING_DRAW' or now.time().replace(tzinfo=None)<draw_time:
            raise FetchError('official source contains a result before its scheduled draw')
    return rows


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
            if 'json' not in response.headers.get('Content-Type','').lower():
                raise FetchError(f'expected official JSON, received {response.headers.get("Content-Type","unknown")} at {response.url}')
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
            observed_at=datetime.now(TZ).isoformat()
            for row in rows:
                meta=row.setdefault('prize_data',{})
                meta['primary_source_error']=str(primary_error)
                meta['source_validation']='single-official-source'
                meta['source_observed_at']=observed_at
            return rows
        except Exception as fallback_error:
            raise FetchError(f'{primary_error}; provincial official fallback failed: {fallback_error}') from fallback_error


def fetch_ssq(periods=100):
    from .official_fallbacks import fetch_shanghai_ssq
    return _with_official_fallback(_fetch_ssq_primary,fetch_shanghai_ssq,periods)


def fetch_dlt(periods=100):
    from .official_fallbacks import fetch_gansu_dlt
    return _with_official_fallback(_fetch_dlt_primary,fetch_gansu_dlt,periods)
