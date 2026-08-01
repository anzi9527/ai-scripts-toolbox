#!/usr/bin/env python3
"""每周一实时成本核算 —— 读取 API 日志 + 实时余额，输出周报"""
import sys, os, json
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from api_log import get_logs, get_summary
from _finance_report import check_balance

BJT = timezone(timedelta(hours=8))
NOW = datetime.now(tz=BJT)
BASE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(BASE, "output")
WEEK_REPORT = os.path.join(OUTPUT, f"weekly_cost_{NOW.strftime('%Y-%m-%d')}.md")

def format_cost(c):
    if c < 0.01:
        return f"¥{c:.4f}"
    return f"¥{c:.2f}"

def main():
    # 本周数据（周一~周日）
    weekday_num = NOW.weekday()
    monday = (NOW - timedelta(days=weekday_num)).strftime('%Y-%m-%d')
    sunday = (NOW + timedelta(days=6 - weekday_num)).strftime('%Y-%m-%d')
    
    week_logs = get_logs(start_date=monday)
    
    # 上周数据
    last_monday = (NOW - timedelta(days=weekday_num + 7)).strftime('%Y-%m-%d')
    last_sunday = (NOW - timedelta(days=weekday_num + 1)).strftime('%Y-%m-%d')
    last_logs = get_logs(start_date=last_monday, end_date=last_sunday)
    
    # 本月数据
    first_day = NOW.strftime('%Y-%m-01')
    month_logs = get_logs(start_date=first_day)
    
    # 实时余额
    balance = check_balance()
    
    # 汇总统计
    week_cost = sum(e['cost'] for e in week_logs)
    week_calls = len(week_logs)
    week_in = sum(e['input_tokens'] for e in week_logs)
    week_out = sum(e['output_tokens'] for e in week_logs)
    
    last_cost = sum(e['cost'] for e in last_logs)
    month_cost = sum(e['cost'] for e in month_logs)
    
    # 按 pipeline 聚合
    by_pipe = {}
    for e in week_logs:
        p = e['pipeline']
        if p not in by_pipe:
            by_pipe[p] = {'calls': 0, 'cost': 0.0}
        by_pipe[p]['calls'] += 1
        by_pipe[p]['cost'] += e['cost']
    
    # 按日聚合
    by_day = {}
    for e in week_logs:
        d = e['ts'][:10]
        if d not in by_day:
            by_day[d] = {'calls': 0, 'cost': 0.0}
        by_day[d]['calls'] += 1
        by_day[d]['cost'] += e['cost']
    
    # 生成报告
    lines = []
    lines.append(f"# 📅 每周成本核算 · {monday} ~ {sunday}")
    lines.append(f"**生成时间**: {NOW.strftime('%Y-%m-%d %H:%M')} BJT")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    lines.append("## 💰 余额")
    lines.append("")
    lines.append(f"| 项目 | 金额 |")
    lines.append(f"|------|:----:|")
    lines.append(f"| 实时余额（API 查询） | ¥{balance if balance else '查询失败'} |")
    lines.append("")
    
    lines.append("## 📊 本周消耗")
    lines.append("")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|------|:----:|")
    lines.append(f"| API 调用次数 | {week_calls} |")
    lines.append(f"| 输入 tokens | {week_in:,} |")
    lines.append(f"| 输出 tokens | {week_out:,} |")
    lines.append(f"| 总 tokens | {week_in + week_out:,} |")
    lines.append(f"| **本周费用** | **{format_cost(week_cost)}** |")
    lines.append("")
    
    if last_logs:
        change = week_cost - last_cost
        pct = (change / last_cost * 100) if last_cost > 0 else 0
        direction = "↑" if change > 0 else "↓" if change < 0 else "→"
        lines.append(f"> 上周消耗 {format_cost(last_cost)} | 环比 {direction} {abs(change):.4f} ({pct:+.1f}%)")
    
    lines.append("")
    
    # 按日
    lines.append("### 每日明细")
    lines.append("")
    lines.append(f"| 日期 | 调用 | 费用 |")
    lines.append(f"|------|:---:|:----:|")
    for d in sorted(by_day.keys()):
        lines.append(f"| {d} | {by_day[d]['calls']} | {format_cost(by_day[d]['cost'])} |")
    lines.append(f"| **合计** | **{week_calls}** | **{format_cost(week_cost)}** |")
    lines.append("")
    
    # 按 pipeline
    lines.append("### 按模块")
    lines.append("")
    lines.append(f"| 模块 | 调用 | 费用 | 占比 |")
    lines.append(f"|------|:---:|:----:|:---:|")
    for pipe, info in sorted(by_pipe.items(), key=lambda x: -x[1]['cost']):
        pct = info['cost'] / week_cost * 100 if week_cost > 0 else 0
        lines.append(f"| {pipe} | {info['calls']} | {format_cost(info['cost'])} | {pct:.1f}% |")
    lines.append("")
    
    # 月度
    lines.append("### 📆 本月至今")
    lines.append("")
    days_passed = NOW.day
    avg_daily = month_cost / days_passed if days_passed > 0 else 0
    lines.append(f"| 项目 | 金额 |")
    lines.append(f"|------|:----:|")
    lines.append(f"| {NOW.strftime('%Y年%m月')} 至今 | {format_cost(month_cost)} |")
    lines.append(f"| 日均消耗 | {format_cost(avg_daily)} |")
    if avg_daily > 0:
        est_monthly = avg_daily * 30
        lines.append(f"| 预估月消耗 | {format_cost(est_monthly)} |")
        if balance:
            lines.append(f"| 余额可用 | **{balance / est_monthly:.1f} 个月**" if est_monthly > 0 else "")
    lines.append("")
    
    # 定价备注
    lines.append("---")
    lines.append("")
    lines.append("*费用基于 DeepSeek 官方定价计算*")
    lines.append("*deepseek-v4-flash: ¥1/M input + ¥2/M output*")
    lines.append("*deepseek-v4-pro: ¥3/M input + ¥6/M output*")
    lines.append("*数据来源: api_log.json（实时 API 调用日志） + /user/balance（实时余额查询）*")
    
    report = "\n".join(lines)
    
    with open(WEEK_REPORT, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"[OK] 周报已生成: weekly_cost_{NOW.strftime('%Y-%m-%d')}.md", file=sys.stderr)


if __name__ == "__main__":
    main()
