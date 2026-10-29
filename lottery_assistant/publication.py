"""Deterministic eligibility for an immutable recommendation, independent of liveness.

READY means eligible for a frontend to publish after checking its delivery history.
It never means delivered, and a review row is never a delivery receipt.
"""
import json
from datetime import datetime

from .lifecycle import TZ, PUBLICATION_DEADLINE, digest, timestamp
from .rules import draw_status, previous_draw_day

POOLS = {'ssq': (6, 33, 1, 16), 'dlt': (5, 35, 2, 12)}


def delivery_history_status(publication, delivered_records):
    """Use actual recommendation deliveries, never payout reviews, as input.

    None means history was not available; [] means it was checked and empty.
    This helper is side-effect free and cannot claim an output was delivered.
    """
    if delivered_records is None:
        return 'UNKNOWN'
    for record in delivered_records:
        if record.get('lottery') != publication['lottery']:
            continue
        if (record.get('dedupe_key') == publication.get('dedupe_key')
            or record.get('prediction_id') == publication.get('prediction_id')
            or (record.get('target_draw_date') == publication.get('target_draw_date')
                and record.get('target_issue_key') == publication.get('target_issue_key'))):
            return 'ALREADY_DELIVERED'
    return 'NOT_DELIVERED'


def publication_decision(db, lottery, now, state=None):
    now = now.astimezone(TZ)
    target = now.date().isoformat()
    deadline = datetime.combine(now.date(), PUBLICATION_DEADLINE, TZ)
    result = {'status': 'WITHHELD', 'reason': None, 'lottery': lottery, 'evaluated_at': now.isoformat(),
              'target_draw_date': target, 'valid_until': deadline.isoformat(),
              'checks': {}, 'warnings': [], 'dedupe_status': 'REQUIRES_DELIVERY_HISTORY',
              'delivered': False}

    def reject(reason):
        result['reason'] = reason
        return result

    calendar = draw_status(lottery, now.date())
    if calendar['status'] != 'WAITING_DRAW':
        return reject(calendar['status'])
    try:
        rec = db.get_frozen_recommendation(lottery, target)
        if rec is not None and not isinstance(rec, dict):
            return reject('FREEZE_INVALID')
    except (KeyError, TypeError, ValueError):
        return reject('FREEZE_INVALID')
    result['frozen_record_present'] = rec is not None
    if rec:
        result['prediction_id'] = rec.get('prediction_id')
    if now >= deadline:
        return reject('PUBLICATION_CLOSED')
    draws = db.get_draws(lottery)
    if any(d['draw_date'] == target for d in draws):
        return reject('DRAW_COMPLETED')
    if state and state['status'] == 'DRAW_COMPLETED':
        return reject('DRAW_COMPLETED')
    if not rec:
        return reject('RECOMMENDATION_MISSING')
    quality = db.get_data_quality_flag(lottery)
    if quality and quality['status'] == 'BLOCKED':
        result['data_quality_conflict'] = quality
        return reject('DATA_QUALITY_CONFLICT')
    try:
        pid = rec['prediction_id']
        freeze = db.get_prediction_freeze(pid)
        prediction = db.conn.execute('SELECT * FROM predictions WHERE id=?', (pid,)).fetchone()
        count = db.conn.execute('''SELECT COUNT(*) FROM prediction_freezes f
            JOIN predictions p ON p.id=f.prediction_id
            WHERE p.lottery=? AND f.target_draw_date=?''', (lottery, target)).fetchone()[0]
        frozen_at = timestamp(rec['frozen_at']).astimezone(TZ)
        fields = ('frozen_at', 'target_draw_date', 'basis_issue')
        integrity = (type(pid) is int and pid > 0 and freeze is not None and prediction is not None
                     and count == 1 and digest(rec) == freeze['payload_sha256']
                     and all(rec.get(k) == freeze[k] for k in fields)
                     and rec['lottery'] == prediction['lottery'] == lottery
                     and rec['main'] == json.loads(prediction['main_numbers'])
                     and rec['bonus'] == json.loads(prediction['bonus_numbers'])
                     and bool(rec['model_version']) and rec['model_version'] == prediction['model_version']
                     and prediction['issue'] == f"NEXT_AFTER_{rec['basis_issue']}")
        result['checks']['freeze_integrity'] = bool(integrity)
        if not integrity:
            return reject('FREEZE_INVALID')
        result.update(prediction_id=pid, basis_issue=rec['basis_issue'],
                      target_issue_key=f"NEXT_AFTER_{rec['basis_issue']}",
                      frozen_at=rec['frozen_at'], freeze_sha256=freeze['payload_sha256'])
        result['dedupe_key'] = f"{lottery}:{result['target_issue_key']}:{target}:{pid}"
        result['checks']['freeze_time'] = frozen_at.date() == now.date() and frozen_at <= now and frozen_at < deadline
        if not result['checks']['freeze_time']:
            return reject('FREEZE_TIME_INVALID')
        mp, mm, bp, bm = POOLS[lottery]
        def valid_numbers(values, pick, maximum):
            return (isinstance(values, list) and len(values) == pick
                    and all(type(n) is int and 1 <= n <= maximum for n in values)
                    and values == sorted(set(values)))
        result['checks']['numbers'] = valid_numbers(rec['main'], mp, mm) and valid_numbers(rec['bonus'], bp, bm)
        if not result['checks']['numbers']:
            return reject('NUMBERS_INVALID')
        expected = previous_draw_day(lottery, now.date()).isoformat()
        latest = draws[-1] if draws else None
        result['checks']['basis_current'] = bool(latest and latest['draw_date'] == expected
                                                 and latest['issue'] == rec['basis_issue'])
        if not result['checks']['basis_current']:
            return reject('BASIS_DATA_INVALID')
        sources = sorted({d['source'] for d in draws})
        if len(sources) == 1:
            result['warnings'].append('SINGLE_OFFICIAL_SOURCE')
        if latest['prize_data'].get('primary_source_error'):
            result['warnings'].append('PRIMARY_SOURCE_UNAVAILABLE')
    except (KeyError, TypeError, ValueError, OverflowError):
        return reject('FREEZE_INVALID')
    result.update(status='READY', reason='VERIFIED_CURRENT_DRAW_FREEZE')
    return result
