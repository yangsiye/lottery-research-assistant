from __future__ import annotations
import requests
from datetime import datetime

UA = "Mozilla/5.0 lottery-research-assistant/1.0"

class FetchError(RuntimeError): pass

def _ints(s):
    if isinstance(s, list): return [int(x) for x in s]
    for sep in [',',' ','+','-','|']:
        if sep in str(s):
            return [int(x) for x in str(s).replace('+',sep).split(sep) if str(x).strip().isdigit()]
    return [int(s)] if str(s).isdigit() else []

def fetch_ssq(periods=100):
    session=requests.Session(); session.headers.update({'User-Agent':UA,'Referer':'https://www.cwl.gov.cn/'})
    try:
        session.get('https://www.cwl.gov.cn/', timeout=15)
        url='https://www.cwl.gov.cn/cwl_admin/kjxx/findDrawNotice'
        r=session.get(url, params={'name':'ssq','issueCount':periods}, timeout=20); r.raise_for_status(); data=r.json()
        rows=data.get('result') or []
    except Exception as e: raise FetchError(f'SSQ official fetch failed: {e}')
    out=[]
    for row in rows:
        main=_ints(row.get('red','')); bonus=_ints(row.get('blue',''))
        if len(main)!=6 or len(set(main))!=6 or not all(1<=x<=33 for x in main): continue
        if len(bonus)!=1 or not 1<=bonus[0]<=16: continue
        out.append({'lottery':'ssq','issue':str(row.get('code')),'draw_date':str(row.get('date'))[:10],
                    'main':sorted(main),'bonus':sorted(bonus),'source':'cwl.gov.cn'})
    if not out: raise FetchError('SSQ official endpoint returned no valid rows')
    return out

def fetch_dlt(periods=100):
    url='https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry'
    headers={'User-Agent':UA,'Referer':'https://www.lottery.gov.cn/'}
    try:
        r=requests.get(url, params={'gameNo':'85','provinceId':'0','pageSize':periods,'isVerify':'1','pageNo':'1'}, headers=headers, timeout=20)
        r.raise_for_status(); data=r.json()
        rows=((data.get('value') or {}).get('list') or [])
    except Exception as e: raise FetchError(f'DLT official fetch failed: {e}')
    out=[]
    for row in rows:
        # Official payloads have varied field names over time; accept known forms conservatively.
        code=str(row.get('lotteryDrawNum') or row.get('drawNum') or row.get('issue') or '')
        date=str(row.get('lotteryDrawTime') or row.get('drawTime') or row.get('date') or '')[:10]
        raw=str(row.get('lotteryDrawResult') or row.get('drawResult') or row.get('result') or '')
        nums=[int(x) for x in raw.replace('+',' ').replace('|',' ').replace(',',' ').split() if x.isdigit()]
        if len(nums) < 7: continue
        main,bonus=nums[:5],nums[5:7]
        if len(set(main))!=5 or not all(1<=x<=35 for x in main): continue
        if len(set(bonus))!=2 or not all(1<=x<=12 for x in bonus): continue
        out.append({'lottery':'dlt','issue':code,'draw_date':date,'main':sorted(main),'bonus':sorted(bonus),'source':'sporttery.cn'})
    if not out: raise FetchError('DLT official endpoint returned no valid rows')
    return out
