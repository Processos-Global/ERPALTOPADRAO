"""Local, inclusive calendar ranges without database timezone conversion."""
from datetime import date, datetime, time, timedelta
from django.utils import timezone


def range_dt(qs, field, filters):
    start, end = filters.get('inicio'), filters.get('fim')
    # Boundary dates cover the entire representable domain. Avoid UTC overflow.
    if start and start != date.min:
        qs = qs.filter(**{field + '__gte': timezone.make_aware(datetime.combine(start, time.min))})
    if end and end != date.max:
        qs = qs.filter(**{field + '__lt': timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min))})
    return qs
