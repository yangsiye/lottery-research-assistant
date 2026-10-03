"""Public provincial official channels; no WAF challenges or unofficial substitutions."""
import re
import json
from pathlib import Path
from html.parser import HTMLParser
from datetime import datetime
import requests
from .lifecycle import TZ


def apply_audited_correction(draw):
    """Correct only an independently verified, exact source record; preserve provenance."""
    corrections=json.loads((Path(__file__).resolve().parents[1]/'config/data_corrections.json').read_text())
    for correction in corrections:
        if (draw['source'],draw['lottery'],draw['issue']) != (correction['source'],correction['lottery'],correction['issue']):
            continue
        if draw['draw_date']==correction['corrected_date']:
            continue
        if (draw['draw_date']!=correction['original_date'] or
            draw['main']!=correction['main'] or draw['bonus']!=correction['bonus']):
            raise ValueError('audited correction source signature mismatch')
        draw['prize_data']['date_correction']=correction
        draw['draw_date']=correction['corrected_date']
    return draw


class TableRows(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[];self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='tr': self.row=[]
        elif tag=='td' and self.row is not None: self.cell=[]
        elif tag=='i' and self.cell is not None: self.cell.append(' ')
    def handle_data(self,data):
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self,tag):
        if tag=='td' and self.cell is not None:
            self.row.append(''.join(self.cell).strip());self.cell=None
        elif tag=='tr' and self.row is not None:
            self.rows.append(self.row);self.row=None


def parse_shanghai_ssq(html):
    parser=TableRows();parser.feed(html)
    out=[]
    for cells in parser.rows:
        if len(cells)<8 or not re.fullmatch(r'\d{7}',cells[0]): continue
        main=[int(n) for n in cells[2].split()];bonus=[int(n) for n in cells[3].split()]
        # This summary publishes only first-prize amounts: never imply a complete prize table.
        record={'prizegrades':[{'type':1,'typemoney':cells[6]}],
                'prize_table_complete':False,'pool_after_draw':cells[7]}
        out.append({'lottery':'ssq','issue':cells[0],'draw_date':cells[1][:10],
                    'main':main,'bonus':bonus,'source':'swlc.net.cn',
                    'prize_data':{'official_record':record}})
    return out


def fetch_shanghai_ssq(periods):
    from .fetchers import validate_archive, FetchError,UA
    out=[]; end=None; seen=set()
    with requests.Session() as session:
        session.headers.update({'User-Agent':UA})
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        session.mount('https://',HTTPAdapter(max_retries=Retry(total=2,backoff_factor=.5,status_forcelist=[502,503,504])))
        for _ in range((periods+99)//100+1):
            params={'view':'previous','limit':100}
            if end: params['end_issue']=end
            r=session.get('https://www.swlc.net.cn/lottery/ssq.html',params=params,timeout=20)
            r.raise_for_status();r.encoding='utf-8'
            batch=parse_shanghai_ssq(r.text)
            if not batch: raise FetchError('上海福彩未返回可识别官方历史表格')
            new=[row for row in batch if row['issue'] not in seen]
            if not new: raise FetchError('上海福彩分页未前进')
            out.extend(new);seen.update(row['issue'] for row in new)
            if len(seen)>=periods: break
            end=str(int(min(row['issue'] for row in new))-1)
    return validate_archive(out,'ssq',periods)


def fetch_gansu_dlt(periods):
    from .fetchers import validate_archive, FetchError,UA
    out=[]
    with requests.Session() as session:
        session.headers.update({'User-Agent':UA,'Referer':'https://www.gstc.org.cn/wanfa/dlt_history'})
        for page in range(1,(periods+99)//100+1):
            # Endpoint and field names are published by the official site's frontend.
            r=session.post('https://www.gstc.org.cn/workapi/prize_history_list',
                           json={'type_id':'001','page_no':page,'page_size':'100'},timeout=20)
            r.raise_for_status();data=r.json()
            if data.get('code')!='000000': raise FetchError('甘肃体彩历史接口未返回成功状态')
            for row in (data.get('data') or {}).get('prize_history_list') or []:
                nums=[int(n) for n in row['prize_num']]
                if len(nums)!=7: raise FetchError('甘肃体彩号码字段不完整')
                out.append(apply_audited_correction({'lottery':'dlt','issue':str(row['issue_num']),'draw_date':row['prize_time'][:10],
                            'main':nums[:5],'bonus':nums[5:],'source':'gstc.org.cn',
                            'prize_data':{'official_record':row}}))
    return validate_archive(out,'dlt',periods)
