"""Explicit numeric presentation contract shared by report producers."""
def chart(*, type='bar', orientation='horizontal', unit='count', precision=0,
          min=0, max=None, sort='source', negative=False, allowed_types=None):
    return dict(type=type, orientation=orientation, unit=unit, precision=precision,
                min=min, max=max, sort=sort, negative=negative,
                allowed_types=allowed_types or [type])


def number(value):
    return float(value) if value is not None else None


def row(label, value, raw, width=0):
    return dict(label=label, value=value, raw=number(raw), width=width)
