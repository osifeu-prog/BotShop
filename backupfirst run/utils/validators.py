import re
ADDR_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")

def is_address(v: str) -> bool:
    return bool(v and ADDR_RE.match(v))

def is_positive_float(s: str) -> bool:
    try:
        return float(s) > 0
    except:
        return False