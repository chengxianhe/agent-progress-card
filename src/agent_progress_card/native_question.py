"""Mirror public input forms as notices, never as remote approval/answer controls."""
import json

from .sanitize import clean_text

NAMES = {'request_user_input', 'request_user_input_async',
         'functions.request_user_input', 'functions.request_user_input_async'}
FOOTER = '请在原客户端回答此表单；微信编号不能提交原生表单。此处为最近提问记录，可能已回答。'


def _question(payload, at, replay_before):
    if payload.get('name') not in NAMES:
        return None
    identity = payload.get('call_id')
    if not isinstance(identity, str) or not identity or len(identity) > 180:
        return None
    raw = payload.get('arguments', payload.get('input'))
    if isinstance(raw, str):
        if len(raw) > 32768:
            return None
        try:
            raw = json.loads(raw)
        except ValueError:
            return None
    questions = raw.get('questions') if isinstance(raw, dict) else None
    if not isinstance(questions, list) or not questions:
        return None
    lines = []
    for question in questions[:3]:
        if not isinstance(question, dict):
            return None
        title = question.get('title', question.get('question'))
        if not isinstance(title, str) or not title.strip():
            return None
        lines.append(clean_text(title, 300))
        options = question.get('options', [])
        if not isinstance(options, list):
            return None
        for index, option in enumerate(options[:5], 1):
            if isinstance(option, dict):
                label, detail = option.get('label'), option.get('description', '')
                if not isinstance(label, str) or not isinstance(detail, str):
                    return None
                option = label + ('：' + detail if detail else '')
            if not isinstance(option, str) or not option.strip():
                return None
            lines.append(str(index) + '. ' + clean_text(option, 180))
        if len(options) > 5:
            lines.append('其余选项请查看原客户端。')
    if len(questions) > 3:
        lines.append('其余问题请查看原客户端。')
    text = clean_text('\n'.join(lines), 2700) + '\n\n' + FOOTER
    return {'id': 'native:' + identity, 'time': at, 'text': text,
            'kind': 'question', 'replayed': at < replay_before}


def native_question(payload, at, replay_before):
    if payload.get('name') not in NAMES:
        return None
    identity = payload.get('call_id')
    if not isinstance(identity, str) or not identity or len(identity) > 180:
        return None
    result = _question(payload, at, replay_before)
    if result is not None:
        return result
    return {'id': 'native:' + identity, 'time': at,
            'text': '客户端提问结构暂不支持，未生成手机答复；请在原客户端核对。没有提交任何决定。',
            'kind': 'question', 'replayed': at < replay_before}
