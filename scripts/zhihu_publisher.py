#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知乎日报发布器 — 自动生成日报并发布到知乎专栏

每日调用：
  1. 读取当天的行业日报 final
  2. 生成知乎风格文章（标题+正文+热榜引用）
  3. 用 playwright 自动发布

依赖：
  - .zhihu_cookies.json（已保存的登录 cookie）
  - 行业日报 output/industry_daily_YYYY-MM-DD_final.md
"""

import sys, os, json, io, time, glob, re
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(BASE, "output")
BJT = timezone(timedelta(hours=8))
NOW = datetime.now(tz=BJT)
DATE = NOW.strftime('%Y-%m-%d')

COOKIE_JSON = os.path.join(BASE, ".zhihu_cookies.json")


def load_latest_report():
    """加载最新一篇日报的 final 文件"""
    files = sorted(glob.glob(os.path.join(OUTPUT, "industry_daily_*_final.md")), reverse=True)
    if not files:
        # 试试 output 里的
        files = sorted(glob.glob(os.path.join(OUTPUT, "industry_daily_*.md")), reverse=True)
    if not files:
        return None, None
    
    path = files[0]
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 提取日期
    m = re.search(r'industry_daily_(\d{4}-\d{2}-\d{2})', os.path.basename(path))
    date_str = m.group(1) if m else DATE
    
    return date_str, content


def format_zhihu_article(date_str, content):
    """把日报格式化为知乎文章风格"""
    lines = content.split('\n')
    
    # 提取标题
    title = f"AI应用行业日报 · {date_str}"
    for line in lines:
        if line.startswith('# ') and not line.startswith('## '):
            title = line.strip('# ').strip()
            break
    
    # 提取市场概览（如果有）
    overview = ""
    market_section = ""
    risk_section = ""
    opportunity_section = ""
    
    current_section = None
    for line in lines:
        if line.startswith('## '):
            section_name = line.strip('# ').strip()
            if '市场' in section_name or '概览' in section_name or '概况' in section_name or '趋势' in section_name:
                current_section = 'market'
            elif '机会' in section_name or '机遇' in section_name or '推荐' in section_name:
                current_section = 'opportunity'
            elif '风险' in section_name or '警告' in section_name or '困难' in section_name:
                current_section = 'risk'
            else:
                current_section = 'other'
        elif current_section == 'market' and line.strip():
            market_section += line.strip() + '\n\n'
        elif current_section == 'opportunity' and line.strip():
            opportunity_section += line.strip() + '\n\n'
        elif current_section == 'risk' and line.strip():
            risk_section += line.strip() + '\n\n'
    
    # 构建知乎文章
    body = f"""# {title}

## 📊 今日市场概况

{market_section[:800] if market_section else '今日AI应用市场持续活跃，多个领域出现显著进展。'}

## 🎯 重点机会

{opportunity_section[:600] if opportunity_section else '市场机会持续显现，建议重点关注AI与垂直行业结合的应用场景。'}

## ⚠️ 风险提示

{risk_section[:400] if risk_section else '投资有风险，入场需谨慎。建议分散布局，避免重仓单一赛道。'}

---

> 本日报由 AI 自动生成，仅供参考，不构成投资建议。
> 数据来源：综合行业报告、新闻资讯、知乎热榜等多方信息。
"""
    
    return title, body


def publish_article(title, body):
    """用 playwright 把文章发布到知乎"""
    with open(COOKIE_JSON, 'r', encoding='utf-8') as f:
        cookies_list = json.load(f)
    for c in cookies_list:
        c.setdefault('path', '/')
        c.setdefault('secure', False)
        c.setdefault('httpOnly', False)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(cookies_list)
        page = context.new_page()
        
        # 打开写文章页面
        page.goto('https://zhuanlan.zhihu.com/write', wait_until='networkidle', timeout=30000)
        time.sleep(3)
        
        # 检查是否跳转到登录
        if 'login' in page.url or 'signup' in page.url:
            print("Cookie 已过期，请重新导出", file=sys.stderr)
            browser.close()
            return False
        
        # 找编辑框 — 标题通常是一个单行 contenteditable
        editors = page.query_selector_all('div[contenteditable]')
        print(f"找到 {len(editors)} 个编辑框", file=sys.stderr)
        
        # 第一个编辑框是标题
        if len(editors) >= 1:
            editors[0].fill(title)
            print(f"标题已填写: {title[:50]}...", file=sys.stderr)
        
        # 第二个编辑框是正文
        if len(editors) >= 2:
            editors[1].fill(body)
            print(f"正文已填写: {len(body)} 字符", file=sys.stderr)
        else:
            # 试试粘贴
            page.evaluate(f"document.querySelector('div[contenteditable]').innerText = {json.dumps(body)}")
            print("正文已通过 JS 填写", file=sys.stderr)
        
        time.sleep(2)
        
        # 找发布按钮
        buttons = page.query_selector_all('button')
        publish_btn = None
        for btn in buttons:
            txt = btn.inner_text().strip()
            if txt == '发布' or txt == '发布文章':
                publish_btn = btn
                break
        
        if publish_btn:
            print(f"找到发布按钮: {publish_btn.inner_text().strip()}", file=sys.stderr)
            # 自动发布
            publish_btn.click()
            time.sleep(3)
            print("已发布！", file=sys.stderr)
        else:
            print("未找到发布按钮", file=sys.stderr)
            # 保存截图看看页面状态
            page.screenshot(path=os.path.join(OUTPUT, f"zhihu_publish_fail_{DATE}.png"))
        
        browser.close()
        return True


def main():
    print(f"== 知乎日报发布器 v1 ==", file=sys.stderr)
    
    date_str, content = load_latest_report()
    if not content:
        print("未找到日报文件", file=sys.stderr)
        return
    
    print(f"最新日报: {date_str} ({len(content)} 字符)", file=sys.stderr)
    
    title, body = format_zhihu_article(date_str, content)
    
    # 保存为预览
    preview_path = os.path.join(OUTPUT, f"zhihu_article_{date_str}.md")
    with open(preview_path, 'w', encoding='utf-8') as f:
        f.write(f"# {title}\n{body}")
    print(f"预览已保存: {preview_path}", file=sys.stderr)
    
    # 发布
    success = publish_article(title, body)
    if success:
        print(f"发布流程完成（需确认发布按钮）", file=sys.stderr)
    
    print(json.dumps({"status": "ok", "date": date_str, "title": title[:30]}))


if __name__ == "__main__":
    main()
