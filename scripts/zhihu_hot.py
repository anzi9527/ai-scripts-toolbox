#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知乎热榜采集器 v3 — 使用 playwright + JSON cookie
首次使用前先运行 playwright launch 手动登录一次导出 cookie
"""

import sys, io, os, json, time
from datetime import datetime, timezone, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BJT = timezone(timedelta(hours=8))
NOW = datetime.now(tz=BJT)
BASE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(BASE, "output")
COOKIE_JSON = os.path.join(BASE, ".zhihu_cookies.json")
os.makedirs(OUTPUT, exist_ok=True)

def fetch_hot(max_items=50):
    """用 cookie 采集热榜"""
    from playwright.sync_api import sync_playwright
    
    if not os.path.exists(COOKIE_JSON):
        print("Cookie 文件不存在，请先导出 cookie", file=sys.stderr)
        return []
    
    with open(COOKIE_JSON, 'r', encoding='utf-8') as f:
        cookies_list = json.load(f)
    
    # 补全字段
    for c in cookies_list:
        c.setdefault('path', '/')
        c.setdefault('secure', False)
        c.setdefault('httpOnly', False)
    
    results = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        context.add_cookies(cookies_list)
        page = context.new_page()
        
        # 打开热榜，等待页面加载完成
        page.goto('https://www.zhihu.com/hot')
        page.wait_for_load_state('networkidle')
        time.sleep(2)
        
        # 检查是否跳转到登录页
        if 'signup' in page.url or 'login' in page.url:
            print("Cookie 已过期，请重新导出", file=sys.stderr)
            browser.close()
            return []
        
        # 采取稳定策略：先等待热门内容出现
        try:
            page.wait_for_selector('.HotItem-title', timeout=10000)
        except:
            print("热榜内容未加载", file=sys.stderr)
            browser.close()
            return []
        
        # 采集
        items = page.query_selector_all('.HotItem')
        print(f"找到 {len(items)} 条热榜条目", file=sys.stderr)
        
        for i, item in enumerate(items[:max_items]):
            try:
                title_el = item.query_selector('.HotItem-title')
                excerpt_el = item.query_selector('.HotItem-excerpt')
                metrics_el = item.query_selector('.HotItem-metrics')
                
                title = title_el.inner_text().strip() if title_el else ""
                excerpt = excerpt_el.inner_text().strip()[:200] if excerpt_el else ""
                metrics = metrics_el.inner_text().strip() if metrics_el else ""
                
                if title:
                    results.append({
                        "rank": i + 1,
                        "title": title,
                        "excerpt": excerpt,
                        "metrics": metrics,
                    })
            except:
                pass
        
        browser.close()
    
    # 保存
    date_str = NOW.strftime('%Y-%m-%d')
    output_file = os.path.join(OUTPUT, f"zhihu_hot_{date_str}.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"已保存: {output_file}", file=sys.stderr)
    return results

if __name__ == "__main__":
    results = fetch_hot()
    if results:
        print(f"\n热榜采集完成: {len(results)} 条")
        for r in results[:15]:
            print(f"  {r['rank']}. {r['title']}")
    else:
        print("采集失败")
