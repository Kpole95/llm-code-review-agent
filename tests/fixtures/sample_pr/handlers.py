"""Request handlers."""


def safe_parse_amount(raw_value):
    # BUG: bare except hides ValueError on bad input, returns None silently.
    try:
        return float(raw_value)
    except:
        return None