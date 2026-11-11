"""Typed mobile request adapters; each option carries its exact protocol response."""
import json
from pathlib import Path
import unicodedata

from agent_progress_card.sanitize import clean_text, PROTECTED
from .approval_forms import validate_schema, enum_values, native_answers, validate_content
from .approval_prompt import METHOD, display, ordered_choices, rejection_reason

FILE = 'item/fileChange/requestApproval'
PERMISSIONS = 'item/permissions/requestApproval'
INPUT = 'item/tool/requestUserInput'
MCP = 'mcpServer/elicitation/request'
REQUEST_METHODS = {METHOD, FILE, PERMISSIONS, INPUT, MCP}


def visible(value, limit=64000):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    if (len(text) > limit or any(unicodedata.category(c).startswith('C') and c not in '\n\t' for c in text)
            or PROTECTED.search(text) or clean_text(text, limit) != text.replace(str(Path.home()), '~')):
        raise ValueError('内容含敏感信息、控制字符或超过完整展示上限')
    return clean_text(text, limit)


def option(label, result=None):
    return {'label': label, 'response': result}


def mcp_result(action, content=None):
    return {'action': action, 'content': content, '_meta': None}


def describe(method, params, changes=None):
    if method == METHOD:
        preview = display(params)
        if preview is None:
            raise ValueError(rejection_reason(params))
        return preview, ordered_choices(params), {}
    if method == INPUT:
        return input_form(params)
    if method == MCP:
        return mcp_form(params)
    if method == PERMISSIONS:
        permissions = params.get('permissions')
        if not isinstance(permissions, dict) or set(permissions) - {'network', 'fileSystem'}:
            raise ValueError('权限请求结构不受支持')
        granted = {key: value for key, value in permissions.items() if value is not None}
        if not granted:
            raise ValueError('权限请求为空')
        preview = '权限申请（仅本轮）\n目录：' + visible(params.get('cwd', '')) + '\n原因：' + visible(params.get('reason') or '未提供')
        preview += '\n完整权限：\n' + visible(granted)
        return preview, [option('允许所列权限，仅本轮', {'permissions': granted, 'scope': 'turn'}),
                         option('拒绝权限', {'permissions': {}, 'scope': 'turn'})], {}
    if method == FILE:
        if not isinstance(changes, list) or not changes:
            raise ValueError('尚未收到该请求的完整文件差异')
        if params.get('grantRoot'):
            raise ValueError('请求包含会话写入目录授权，暂不能按单次文件修改处理')
        preview = '文件修改\n原因：' + visible(params.get('reason') or '未提供') + '\n完整差异：\n' + visible(changes)
        return preview, [option('仅此次允许', {'decision': 'accept'}),
                         option('拒绝本次修改', {'decision': 'decline'}),
                         option('取消本轮', {'decision': 'cancel'})], {}
    raise ValueError('尚未支持的请求类型：' + method)


def input_form(params):
    questions = params.get('questions')
    if not isinstance(questions, list) or not 1 <= len(questions) <= 3:
        raise ValueError('原生问题格式不受支持')
    ids, lines = set(), ['客户端提问']
    for q in questions:
        if not isinstance(q, dict) or q.get('isSecret'):
            raise ValueError('私密输入不能经微信普通消息提交')
        key = q.get('id')
        if not isinstance(key, str) or not key or key in ids:
            raise ValueError('问题 ID 无效或重复')
        ids.add(key)
        options = q.get('options') or []
        if not isinstance(options, list) or len(options) > 8:
            raise ValueError('问题选项超过支持范围')
        lines.append(visible(key + '：' + q['question']))
        for i, item in enumerate(options, 1):
            if not isinstance(item, dict) or not isinstance(item.get('label'), str) or not 1 <= len(item['label']) <= 300:
                raise ValueError('问题选项无效')
            lines.append(f'{i}. ' + visible(item['label'] + '：' + (item.get('description') or '')))
    choices = []
    if len(questions) == 1:
        q = questions[0]
        for item in q.get('options') or []:
            choices.append(option(item['label'], native_answers(questions, {q['id']: item['label']})))
    preview = '\n'.join(lines)
    return preview, choices, {'type': 'native', 'questions': questions}


def mcp_form(params):
    mode = params.get('mode')
    if mode not in ('form', 'openai/form', 'openaiForm'):
        raise ValueError('该请求需要专用身份验证或网页流程，不能伪装成普通 Allow')
    schema = params.get('requestedSchema')
    fields = validate_schema(schema)
    meta = params.get('_meta') or {}
    if not isinstance(meta, dict):
        raise ValueError('MCP 请求元数据格式无效')
    preview = '工具：' + visible(params.get('serverName', '未提供')) + '\n' + visible(params.get('message', ''))
    if meta.get('codex_approval_kind') == 'mcp_tool_call':
        preview += '\n调用：' + visible(meta.get('tool_name', '未提供'))
        if 'tool_params' in meta:
            preview += '\n参数：\n' + visible(meta['tool_params'])
        elif meta.get('tool_params_display'):
            preview += '\n参数：\n' + visible(meta['tool_params_display'])
        if fields:
            raise ValueError('工具授权使用了未识别的附加输入字段')
        choices = [option('Allow · 仅此次允许', mcp_result('accept', {}))]
        persist = meta.get('persist', [])
        persist = [persist] if isinstance(persist, str) else persist
        if not isinstance(persist, list):
            raise ValueError('工具授权选项格式无效')
        for value in persist:
            if value in ('session', 'always'):
                label = '本会话允许' if value == 'session' else '长期允许'
                choices.append(option(label + '（未开启；执行本次请选择 Allow）'))
        choices.append(option('Cancel · 取消本次调用', mcp_result('cancel')))
        return preview, choices, {}
    if meta.get('codex_approval_kind'):
        raise ValueError('该授权类别需要专用处理：' + str(meta['codex_approval_kind']))
    choices = []
    if not fields:
        choices.append(option('Allow · 确认', mcp_result('accept', {})))
    elif len(fields) == 1:
        key, field = next(iter(fields.items()))
        values = enum_values(field)
        if values is None and field.get('type') == 'boolean':
            values = [True, False]
        for value in values or []:
            content = validate_content(schema, {key: value})
            choices.append(option(visible(value), mcp_result('accept', content)))
    if fields:
        preview += '\n表单字段及约束：\n' + visible(schema)
    choices.extend([option('拒绝', mcp_result('decline')), option('取消', mcp_result('cancel'))])
    return preview, choices, {'type': 'mcp', 'schema': schema} if fields else {}


def typed_answer(form, content):
    if form.get('type') == 'native':
        return native_answers(form['questions'], content)
    if form.get('type') == 'mcp':
        return mcp_result('accept', validate_content(form['schema'], content))
    raise ValueError('这项请求不接受填写内容，请回复选项号')


def request_event(event):
    if not isinstance(event, dict):
        return False
    method = event.get('method', '')
    return method in REQUEST_METHODS or (isinstance(method, str) and method.endswith('/requestApproval'))


def retained_event(event):
    method = event.get('method', '') if isinstance(event, dict) else ''
    if request_event(event) or method == 'serverRequest/resolved':
        return True
    params = event.get('params', {}) if isinstance(event, dict) else {}
    item = params.get('item') if isinstance(params, dict) else None
    return method in ('item/started', 'item/completed') and isinstance(item, dict) and item.get('type') == 'fileChange'
