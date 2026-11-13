"""Phone-readable transport/task health, separate from the last task's UI status."""
import time

from agent_progress_card.sanitize import clean_text
from .files import read_json

COMMANDS = {'诊断', '/diagnose', '自检', '出门检查'}


def describe(store, card, health, compact=False):
    summary = store.summary()
    lines = ['手机链路诊断（不是任务执行结果）：',
             '微信发送：' + ('已暂停；本人新消息后只发当前摘要' if summary['send_paused'] else '可尝试回复；以实际收到为准')]
    labels = {'wechat': '微信收件', 'send': '微信发件', 'codex': '任务会话', 'approvals': '审批通道',
              'card': '看板采集', 'watchdog': '运行监督'}
    problems = [labels[k] + '：' + clean_text(v, 180) for k, v in health.items() if k in labels and v]
    for key, title in labels.items():
        if key in health:
            lines.append(title + '：' + clean_text(health[key] or '最近检查正常', 300))
    tasks = summary['tasks']
    queued = sum(tasks.get(key, 0) for key in ('queued', 'dispatching'))
    if queued:
        lines.append(f'有 {queued} 条本人消息待投递；通信可用不表示这些任务已执行。')
    if tasks.get('uncertain'):
        lines.append(f"有 {tasks['uncertain']} 条历史投递回执不确定，不自动重做；可请助手核验实际结果。")
    try:
        heartbeat = read_json(card / 'activity-heartbeat.json')
        age = time.time() - heartbeat['checked_at']
        matches = heartbeat.get('thread_id') == store.get('thread')
        if not matches or not 0 <= age <= 20:
            problems.append('采集心跳未更新或绑定不匹配；看板可能是最后记录')
        lines.append('采集心跳：' + ('已更新' if matches and 0 <= age <= 20 else '未更新或绑定不匹配；看板可能是最后记录'))
    except (OSError, ValueError, KeyError, TypeError):
        lines.append('采集心跳：不可读取，当前任务显示不能当作实时证据')
        problems.append('采集心跳不可读取，当前任务显示不能当作实时证据')
    if store.db.execute("SELECT 1 FROM sqlite_master WHERE name='remote_approvals'").fetchone():
        rows = store.db.execute("SELECT state,count(*) FROM remote_approvals WHERE server_live=1 GROUP BY state").fetchall()
        counts = dict(rows)
        if health.get('approval_waiting') and not any(counts.get(k) for k in ('pending', 'queued', 'sending', 'expired', 'native')):
            problems.append('任务正在等授权，但手机没有收到可用请求；发送“审批”也不能补造请求，需原客户端或预先配置的备用入口')
            lines.append(problems[-1])
        if counts.get('expired'):
            lines.append('仍有请求在等待，但手机编号过期；发送“审批”刷新编号，不会自动提交决定。')
        if counts.get('native'):
            lines.append('有请求需要原客户端/专用流程，手机数字不能完成该类型。')
    try:
        supervisor = read_json(card / 'resident.json')
        age = time.time() - supervisor['checked_at']
        own_pid = read_json(store.directory / 'service-heartbeat.json').get('pid')
        supervised = (supervisor.get('status') == 'running' and supervisor.get('child_pid') == own_pid
                      and type(own_pid) is int and 0 <= age <= 30)
        lines.append('常驻监督：' + ('本桥接由当前监督进程管理' if supervised else '未确认正在监督本桥接，不能承诺自动重启'))
        if not supervised:
            problems.append('未确认常驻监督正在管理本桥接，不能承诺自动重启')
    except (OSError, ValueError, KeyError, TypeError):
        lines.append('常驻监督：缺少当前证据，不能承诺自动重启')
        problems.append('常驻监督缺少当前证据，不能承诺自动重启')
    lines.append('电脑关机、离线或登录失效时，本通道无法自救；需事先保留可用的备用入口。')
    if compact:
        return clean_text('\n'.join(problems), 1000)
    return clean_text('\n'.join(lines), 2800)
