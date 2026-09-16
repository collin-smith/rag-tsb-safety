"""This sandbox's system clock is ~11 hours behind real UTC (no NTP, no
sudo to fix it) — every SigV4 request otherwise fails with
SignatureDoesNotMatch / Signature expired. Compute the real offset from an
external HTTPS server's Date header (independent of AWS's own error format)
and monkeypatch botocore's timestamp source so every AWS call in this
process signs with the corrected time. Import this before any boto3 client
is created.

The clock doesn't just start offset -- it drifts at a noticeable rate (a
320-report run, ~35-45 min, was enough to push a one-time offset far
enough out to hit RequestTimeTooSkewed partway through). Re-measure
periodically rather than once at import time.
"""
import datetime
import subprocess
import time

import botocore.auth
import botocore.compat

_REFRESH_SECONDS = 120


def _external_utc_now():
    out = subprocess.run(
        ["curl", "-sI", "--max-time", "10", "https://www.tsb.gc.ca"],
        capture_output=True, text=True,
    ).stdout
    for line in out.splitlines():
        if line.lower().startswith("date:"):
            date_str = line.split(":", 1)[1].strip()
            return datetime.datetime.strptime(
                date_str, "%a, %d %b %Y %H:%M:%S %Z"
            )
    raise RuntimeError(f"no Date header in response: {out!r}")


def _measure_offset():
    external_now = _external_utc_now()
    system_now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    return external_now - system_now


_OFFSET = _measure_offset()
_LAST_MEASURED = time.monotonic()
print(f"[clock_fix] system clock offset from real UTC: {_OFFSET}")


def get_current_datetime_corrected(remove_tzinfo=True):
    global _OFFSET, _LAST_MEASURED
    if time.monotonic() - _LAST_MEASURED > _REFRESH_SECONDS:
        try:
            new_offset = _measure_offset()
            if abs((new_offset - _OFFSET).total_seconds()) > 1:
                print(f"[clock_fix] offset drifted: {_OFFSET} -> {new_offset}")
            _OFFSET = new_offset
        except Exception as e:
            print(f"[clock_fix] refresh failed, keeping stale offset: {e}")
        _LAST_MEASURED = time.monotonic()
    now = datetime.datetime.now(datetime.timezone.utc) + _OFFSET
    if remove_tzinfo:
        now = now.replace(tzinfo=None)
    return now


botocore.auth.get_current_datetime = get_current_datetime_corrected
botocore.compat.get_current_datetime = get_current_datetime_corrected
