"""Render complete bounded command approvals; unsafe/incomplete previews stay native."""
import json
from pathlib import Path
import re
import unicodedata

from agent_progress_card.sanitize import clean_text, PROTECTED
from .selection_text import numbered_selection, literal_selection, approval_syntax

METHOD = 'item/commandExecution/requestApproval'


def request_key(identity):
    if isinstance(identity, bool) or not isinstance(identity, (str, int)):
        raise ValueError('Invalid request identity')
    if isinstance(identity, str) and (not identity or len(identity) > 300):
        raise ValueError('Invalid request identity')
    return json.dumps(identity, ensure_ascii=True)


def rejection_reason(params):
    """Explain display limits without echoing potentially sensitive request values."""
    if params.get('kind', 'command') not in ('command', 'humanCommand', 'writeStdin'):
        return '这类操作暂不支持微信审批'
    if params.get('additionalPermissions'):
        return '请求包含额外权限，需使用原生权限界面'
    network = params.get('networkApprovalContext')
    if network is not None:
        if (not isinstance(network, dict) or set(network) != {'host', 'protocol'}
                or not isinstance(network['host'], str) or not 1 <= len(network['host']) <= 253
                or network['protocol'] not in ('http', 'https', 'socks5Tcp', 'socks5Udp')):
            return '网络权限上下文不完整或尚未支持'
        value = json.dumps(network, ensure_ascii=False)
        if PROTECTED.search(value) or clean_text(value, 1000) != value:
            return '网络权限上下文无法完整安全展示'
    environment = params.get('environmentId')
    if environment is not None and (not isinstance(environment, str) or len(environment) > 200
                                    or clean_text(environment, 200) != environment):
        return '执行环境无法完整安全展示'
    choices = params.get('availableDecisions')
    if choices is not None and (not isinstance(choices, list) or len(choices) > 8 or ('accept' not in choices or not any(x in choices for x in ('decline', 'cancel')))):
        return '服务端提供的审批选项暂不支持'
    command, cwd, reason = params.get('command'), params.get('cwd'), params.get('reason') or '执行此命令需要你的确认'
    if not isinstance(command, str) or not command.strip() or not isinstance(cwd, str) or not cwd or not isinstance(reason, str):
        return '请求缺少完整的命令、目录或原因'
    values = (command, cwd, reason)
    for value, limit, label in zip(values, (60000, 300, 400), ('命令正文', '目录', '原因')):
        if len(value) > limit:
            return f'{label}超过微信审批的 {limit} 字符展示上限'
    for value in values:
        if any(unicodedata.category(c).startswith('C') and c not in '\n\t' for c in value):
            return '请求含不能安全展示的控制字符'
        if PROTECTED.search(value) or clean_text(value, 64000) != value.replace(str(Path.home()), '~'):
            return '请求涉及敏感内容，脱敏后无法完整核对授权内容'
    return None


def display(params):
    if rejection_reason(params):
        return None
    values = (params['command'], params['cwd'], params.get('reason') or '执行此命令需要你的确认')
    command, cwd, reason = (clean_text(v, 64000) for v in values)
    text = (f'终端输入（写入现有进程）：\n{command}' if params.get('kind') == 'writeStdin'
            else f'命令：\n{command}')
    text += f'\n目录：{cwd}\n原因：{reason}'
    if params.get('environmentId'):
        text += '\n执行环境：' + params['environmentId']
    if params.get('networkApprovalContext'):
        text += '\n本次网络目标：' + json.dumps(params['networkApprovalContext'], ensure_ascii=False)
    return text


def ordered_choices(params):
    offered = params.get('availableDecisions')
    if offered is None:
        offered = ['accept', 'decline', 'cancel']
    if not isinstance(offered, list) or len(offered) > 8:
        return []
    labels = {'accept': '仅此次允许', 'decline': '拒绝本次命令，任务可继续',
              'cancel': '拒绝并结束本轮', 'acceptForSession': '本会话内允许（请在电脑端操作）'}
    result = []
    for option in offered:
        decision = option if isinstance(option, str) and option in ('accept', 'decline', 'cancel') else None
        if isinstance(option, str):
            label = labels.get(option, '其他权限选项（请在电脑端操作）')
        elif isinstance(option, dict) and 'acceptWithExecpolicyAmendment' in option:
            label = '允许同类命令以后执行（请在电脑端操作）'
        else:
            label = '其他权限选项（请在电脑端操作）'
        result.append({'label': label, 'decision': decision})
    return result


def numbered_reply(text):
    return numbered_selection(text)


def parse_reply(text):
    match = re.fullmatch(r'(批准|拒绝)\s+(A[0-9A-Fa-f]{10})', text.strip(), re.I)
    if not match:
        return None
    return match[2].upper(), 'accept' if match[1] == '批准' else 'decline'


def label_reply(text):
    literal = literal_selection(text)
    label, code = literal if literal else (text.strip(), None)
    match = re.fullmatch(r'(allow|accept|允许|仅此次允许|cancel|取消)', label, re.I)
    if not match:
        return None
    action = 'accept' if match[1].lower() in ('allow', 'accept', '允许', '仅此次允许') else 'cancel'
    return action, code


def is_approval_text(text):
    return (bool(label_reply(text)) or bool(literal_selection(text)) or approval_syntax(text)
            or text in ('审批', '/approvals') or text.startswith(('批准', '拒绝', '填写', '审批 ', '/approvals ')))
