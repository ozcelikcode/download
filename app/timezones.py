"""Validated IANA display zones; database and console timestamps remain UTC."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, available_timezones

TIMEZONES = frozenset(available_timezones())
TIMEZONE_CHOICES = ("UTC", "Europe/Istanbul", *sorted(TIMEZONES - {"UTC", "Europe/Istanbul"}))


def validate_timezone(value: str) -> str:
    if not isinstance(value, str) or len(value) > 64 or value not in TIMEZONES:
        raise ValueError("Unsupported time zone")
    return value


def local_datetime(value: datetime, zone: str) -> datetime:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(ZoneInfo(validate_timezone(zone)))
