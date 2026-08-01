#!/usr/bin/env python3
"""
CSDN 自动发文脚本
先验证登录，然后发布 markdown 文章
"""

import sys, os, json, re, time, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import requests

BASE = os.path.dirname(__file__)
ACCOUNTS_FILE = os.path.join(BASE, 'output', 'accounts.json')
ARTICLES_DIR = os.path.join(BASE, 'output', 'articles')
LOG_FILE = os.path.join(BASE, 'output', 'publish_log.json')

def get_cookies(platform):
    if not os.path.exists(ACCOUNTS_FILE):
        print('❌ accounts.json 未找到')
        return None, None
    with open(ACCOUNTS_FILE, encoding='utf-8') as f:
        data = json.load(f)
    accounts = data.get(platform, [])
    if not accounts:
        print('❌ 未找到 %s 账号' % platform)
        return None, None
    acc = accounts[-1]
    cookies = {}
    for c in acc.get('cookies', []):
        cookies[c['name']] = c['value']
    return cookies, acc.get('phone', '')

def login_csdn():
    cookies, phone = get_cookies('csdn')
    if not cookies:
        return None
    
    s = requests.Session()
    s.cookies.update(cookies)
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
        'Referer': 'https://www.csdn.net/',
    })
    
    # 验证登录
    r = s.get('https://me.csdn.net/api/user/getUserInfo')
    try:
        user = r.json().get('data', {})
        name = user.get('userNick', user.get('userName', ''))
        print('  ✅ 登录: %s' % name)
        return s
    except:
        print('  ❌ 登录验证失败')
        print('  Response:', r.text[:200])
        return None

def publish_csdn(session, article):
    title = article['title']
    content = article['content']
    
    # CSDN 博客 API
    url = 'https://blog.csdn.net/phoenix/web/blog/saveBlog'
    
    # 提取标签
    tags = article.get('tags', ['默认'])
    
    payload = {
        'title': title,
        'content': content,
        'markdowncontent': content,
        'tags': ','.join(tags[:3]),
        'categories': 'Python',
        'type': 'original',
        'status': 'publish',
        'format': 'markdown',
        'channel': '',
        'description': content[:200].replace('#', '').replace('\n', ' ').strip(),
    }
    
    print('\n  ---')
    print('  标题: %s' % title)
    print('  标签: %s' % ', '.join(tags[:3]))
    print('  字数: %d' % len(content))
    
    r = session.post(url, json=payload)
    resp = r.json()
    
    if r.status_code == 200 and resp.get('status') == 'true':
        code = resp.get('data', {}).get('code', '')
        print('  ✅ 发布成功! Code: %s' % code)
        return True, code
    else:
        err = resp.get('msg', resp.get('message', '发布失败'))
        print('  ❌ %s' % err)
        print('  raw:', r.text[:200])
        return False, err

def main():
    print('=== CSDN 自动发文 ===')
    print('时间: %s\n' % time.strftime('%Y-%m-%d %H:%M'))
    
    # 检查账号
    cookies, phone = get_cookies('csdn')
    if not cookies:
        print('\n📢 请先运行: python3 save_login.py csdn')
        print('   浏览器弹出后手动登录CSDN，然后按 Enter 保存cookies\n')
        return
    
    session = login_csdn()
    if not session:
        return
    
    # 获取待发布文章
    if not os.path.exists(ARTICLES_DIR):
        print('📭 无文章目录')
        return
    
    log = {}
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, encoding='utf-8') as f:
            log = json.load(f)
    
    published = log.get('published_csdn', [])
    
    files = sorted([f for f in os.listdir(ARTICLES_DIR) if f.endswith('.md')])
    todo = [f for f in files if os.path.join(ARTICLES_DIR, f) not in published]
    
    if not todo:
        print('📭 无待发布文章')
        return
    
    print('\n待发布: %d 篇\n' % len(todo))
    
    ok, fail = 0, 0
    for fname in todo:
        fpath = os.path.join(ARTICLES_DIR, fname)
        with open(fpath, encoding='utf-8') as f:
            content = f.read()
        
        title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        title = title_match.group(1) if title_match else fname.replace('.md', '')
        
        article = {
            'filepath': fpath,
            'title': title,
            'content': content,
            'tags': ['Python'],
        }
        
        success, result = publish_csdn(session, article)
        if success:
            log.setdefault('published_csdn', []).append(fpath)
            log.setdefault('article_ids_csdn', []).append({
                'filepath': fpath, 'title': title, 'id': result,
                'time': time.strftime('%Y-%m-%d %H:%M:%S'),
            })
            ok += 1
        else:
            log.setdefault('failed_csdn', []).append({
                'filepath': fpath, 'title': title, 'error': result,
                'time': time.strftime('%Y-%m-%d %H:%M:%S'),
            })
            fail += 1
            break  # 失败先停，看看原因
    
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    
    print('\n✅ 成功: %d | ❌ 失败: %d' % (ok, fail))

if __name__ == '__main__':
    main()
