"""Canonical freeze serialization and draw-time checks shared by cloud and bridge."""
import hashlib
import json
from datetime import datetime, time
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Shanghai')
# A conservative publication deadline, not a claim about a local outlet's cutoff.
PUBLICATION_DEADLINE = time(20, 0)


def digest(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def timestamp(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return dt.replace(tzinfo=ZoneInfo('UTC')) if dt.tzinfo is None else dt


def before_deadline(value, target):
    return timestamp(value).astimezone(TZ) < datetime.combine(target, PUBLICATION_DEADLINE, TZ)
