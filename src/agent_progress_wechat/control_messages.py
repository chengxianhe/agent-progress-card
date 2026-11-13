"""Classify control input before ordinary task capacity and FIFO delivery."""
import re

from .approval_prompt import is_approval_text
from .selection_text import approval_syntax, numbered_selection


def is_control(text):
    from .remote_health import COMMANDS
    return (text in COMMANDS or text in ('进度', '/status', '结果', '/result', '帮助', '/help', '选项', '/choice')
            or is_approval_text(text) or approval_syntax(text, 'C')
            or numbered_selection(text, 'C', bare=False) is not None
            or bool(re.match(r'^填写\s+C[0-9a-f]{10}\s+', text, re.I))
            or bool(re.fullmatch(r'[0-9]{1,2}', text)))
