"""Validate explicit phone answers against bounded, supported native form schemas."""
import datetime
import json
import re
from urllib.parse import urlparse


def validate_schema(schema):
    if not isinstance(schema, dict) or schema.get('type') != 'object':
        raise ValueError('表单不是可支持的对象结构')
    if set(schema) - {'type', 'properties', 'required', '$schema', 'title', 'description', 'additionalProperties'}:
        raise ValueError('表单包含未支持的约束')
    properties = schema.get('properties', {})
    if not isinstance(properties, dict) or len(properties) > 12:
        raise ValueError('表单字段过多')
    required = schema.get('required', [])
    if not isinstance(required, list) or any(not isinstance(k, str) or k not in properties for k in required):
        raise ValueError('表单必填字段无效')
    for key, field in properties.items():
        if not isinstance(key, str) or not key or len(key) > 100 or not isinstance(field, dict):
            raise ValueError('表单字段无效')
        if set(field) - {'type', 'title', 'description', 'default', 'enum', 'enumNames', 'oneOf',
                         'minLength', 'maxLength', 'minimum', 'maximum', 'format'}:
            raise ValueError('表单字段包含未支持的约束')
        if field.get('type') not in ('string', 'boolean', 'integer', 'number'):
            raise ValueError('表单字段类型暂不支持')
        if field.get('format') not in (None, 'email', 'uri', 'date', 'date-time'):
            raise ValueError('表单格式暂不支持')
        enum_values(field)
    return properties


def enum_values(field):
    if 'oneOf' in field:
        options = field['oneOf']
        if not isinstance(options, list) or any(not isinstance(o, dict) or 'const' not in o or set(o) - {'const', 'title'} for o in options):
            raise ValueError('表单枚举无效')
        values = [o['const'] for o in options]
    else:
        values = field.get('enum')
    if values is not None and (not isinstance(values, list) or not 1 <= len(values) <= 8):
        raise ValueError('表单枚举数量无效')
    return values


def validate_content(schema, content):
    fields = validate_schema(schema)
    if not isinstance(content, dict) or set(content) - set(fields) or any(k not in content for k in schema.get('required', [])):
        raise ValueError('请填写全部必填字段，不要添加其他字段')
    for key, value in content.items():
        field = fields[key]
        kind = field['type']
        if ((kind == 'string' and not isinstance(value, str)) or
                (kind == 'boolean' and type(value) is not bool) or
                (kind == 'integer' and type(value) is not int) or
                (kind == 'number' and type(value) not in (int, float))):
            raise ValueError('字段类型不符合表单要求')
        values = enum_values(field)
        if values is not None and not any(type(value) is type(v) and value == v for v in values):
            raise ValueError('请选择表单提供的值')
        if isinstance(value, str):
            if not field.get('minLength', 0) <= len(value) <= field.get('maxLength', 2000):
                raise ValueError('字段长度不符合要求')
            fmt = field.get('format')
            try:
                if fmt == 'date':
                    datetime.date.fromisoformat(value)
                elif fmt == 'date-time':
                    datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
                elif fmt == 'email' and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
                    raise ValueError()
                elif fmt == 'uri' and not urlparse(value).scheme:
                    raise ValueError()
            except ValueError:
                raise ValueError('字段格式不符合要求') from None
        elif type(value) in (int, float):
            if not field.get('minimum', float('-inf')) <= value <= field.get('maximum', float('inf')):
                raise ValueError('字段数值不符合要求')
    return content


def native_answers(questions, content):
    if not isinstance(content, dict) or set(content) != {q['id'] for q in questions}:
        raise ValueError('请按问题 ID 回答全部问题')
    answers = {}
    for question in questions:
        value = content[question['id']]
        options = question.get('options') or []
        if type(value) is int and 1 <= value <= len(options):
            value = options[value - 1]['label']
        if not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise ValueError('答案必须是有效编号或非空文字')
        if options and not question.get('isOther') and value not in [x['label'] for x in options]:
            raise ValueError('请使用问题提供的选项')
        answers[question['id']] = {'answers': [value]}
    return {'answers': answers}


def form_reply(text):
    match = re.fullmatch(r'填写\s+(A[0-9A-Fa-f]{10})\s+(.+)', text.strip(), re.S | re.I)
    if not match:
        return None
    try:
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('字段重复')
                result[key] = value
            return result
        content = json.loads(match[2], object_pairs_hook=unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError('数值无效')))
    except (ValueError, TypeError):
        raise ValueError('填写内容须为有效 JSON 对象，且字段不能重复') from None
    return match[1].upper(), content
