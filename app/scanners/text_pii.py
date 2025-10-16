import re
from typing import List, Tuple
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b")
ADDRESS_RE = re.compile(r"\b\d{1,5}\s+[A-Za-z0-9.'-]+\s+(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Lane|Ln|Drive|Dr|Court|Ct)\b", re.I)
def scan_caption(caption: str) -> List[Tuple[str, str]]:
    outs: List[Tuple[str, str]] = []
    for m in EMAIL_RE.findall(caption or ""): outs.append(("email", m))
    for m in PHONE_RE.findall(caption or ""): outs.append(("phone", m))
    for m in ADDRESS_RE.findall(caption or ""): outs.append(("address", m))
    return outs
