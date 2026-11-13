"""Live ordinary async questions become chat choices, never native permission responses."""
import json
import time

from .sanitize import clean_text

ASYNC = {'functions.request_user_input_async', 'request_user_input_async'}


def parse(payload, at, replay_before):
    if payload.get('name') not in ASYNC:
        return None
    try:
        raw = payload.get('arguments', payload.get('input'))
        if isinstance(raw, str):
            if len(raw) > 32768:
                return None
            raw = json.loads(raw)
        questions = raw['questions']
        if not isinstance(questions, list) or not 1 <= len(questions) <= 3:
            return None
        fields = []
        for index, q in enumerate(questions, 1):
            if not isinstance(q, dict) or not isinstance(q.get('options', []), list):
                return None
            title = q.get('title', q.get('question'))
            if q.get('isSecret') or q.get('is_secret') or not isinstance(title, str):
                return None
            options = []
            for option in q.get('options') or []:
                if isinstance(option, dict):
                    option = option['label'] + ('：' + option['description'] if option.get('description') else '')
                options.append(option)
            fields.append({'id': str(q.get('id') or 'q' + str(index)), 'title': title, 'options': options})
        if not valid_fields(fields):
            return None
        return {'id': payload['call_id'], 'time': at, 'fields': fields, 'replayed': at < replay_before}
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def valid_fields(fields):
    if not isinstance(fields, list) or not 1 <= len(fields) <= 3:
        return False
    keys = []
    for field in fields:
        if not isinstance(field, dict) or set(field) != {'id', 'title', 'options'}:
            return False
        for key, maximum in (('id', 100), ('title', 300)):
            value = field[key]
            if not isinstance(value, str) or not value.strip() or len(value) > maximum or clean_text(value, maximum) != value:
                return False
        options = field['options']
        if (not isinstance(options, list) or len(options) > 8
                or any(not isinstance(v, str) or not v.strip() or len(v) > 180 or clean_text(v, 180) != v for v in options)
                or len(set(options)) != len(options)):
            return False
        keys.append(field['id'])
    return len(set(keys)) == len(keys)


def answer(choice, values):
    fields = choice.get('fields')
    if not valid_fields(fields) or not isinstance(values, dict) or set(values) != {f['id'] for f in fields}:
        raise ValueError('请按当前问题填写全部字段，不能添加或遗漏字段')
    lines = ['我对当前看板问题的回答（作为聊天回复，不代交原生表单）：']
    for field in fields:
        value = values[field['id']]
        if not isinstance(value, str) or not value.strip() or len(value) > 2000 or clean_text(value, 2000) != value:
            raise ValueError('回答为空、过长或含敏感信息')
        if field['options'] and value not in field['options']:
            raise ValueError('回答必须是当前问题提供的选项原文')
        lines.append(field['title'] + '\n回答：' + value)
    return '\n'.join(lines)


def sync(directory, prompt, thread_id):
    from .choice import choice_lock, read_choice
    from .watcher import atomic_json
    from .choice import create_choice
    marker = directory / 'question-choice-state.json'
    if json.loads((directory / 'activity-source.json').read_text()).get('thread_id') != thread_id:
        raise ValueError('会话已切换，不转换旧问题')
    current = read_choice(directory, thread_id)
    if not prompt:
        if current and current.get('source_question_id'):
            with choice_lock(directory):
                latest = read_choice(directory, thread_id)
                if latest and latest['id'] == current['id']:
                    (directory / 'choice.json').unlink(missing_ok=True)
        return
    if prompt.get('replayed') or not valid_fields(prompt.get('fields')):
        return
    try:
        seen = json.loads(marker.read_text())
        if seen.get('thread_id') == thread_id and seen.get('id') == prompt['id']:
            return
    except (OSError, ValueError, AttributeError):
        pass
    if current:
        return  # Never replace an unrelated live manual choice.
    fields = prompt['fields']
    options = fields[0]['options'] if len(fields) == 1 and 2 <= len(fields[0]['options']) <= 5 else []
    title = fields[0]['title'] if len(fields) == 1 else '请回答以下 ' + str(len(fields)) + ' 个问题'
    try:
        value = create_choice(directory, title, options, fields=fields, source_question_id=prompt['id'])
    except ValueError:
        return  # A concurrent manual publisher wins; collection must remain available.
    atomic_json(marker, {'thread_id': thread_id, 'id': prompt['id'], 'choice_id': value['id'], 'time': time.time()})
