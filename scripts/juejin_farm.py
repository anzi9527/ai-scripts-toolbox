#!/usr/bin/env python3
"""
掘金自动养号脚本
每天执行：签到 + 浏览文章 → 增加活跃度

运行:
  python3 juejin_farm.py          # 单次运行
  python3 juejin_farm.py --once   # 单次 + 清理旧数据

由 cron 每天调用:
  0 10 * * *  (Asia/Shanghai)
"""

import sys, os, json, time, random, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import requests

BASE = os.path.dirname(__file__)
ACCOUNTS_FILE = os.path.join(BASE, 'output', 'accounts.json')
LOG_FILE = os.path.join(BASE, 'output', 'juejin_farm_log.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
    'Referer': 'https://juejin.cn/',
    'Origin': 'https://juejin.cn',
}

def get_session():
    if not os.path.exists(ACCOUNTS_FILE):
        print('❌ accounts.json not found')
        return None
    with open(ACCOUNTS_FILE, encoding='utf-8') as f:
        data = json.load(f)
    accounts = data.get('juejin', [])
    if not accounts:
        print('❌ No juejin account')
        return None
    acc = accounts[-1]
    cookies = {}
    for c in acc.get('cookies', []):
        cookies[c['name']] = c['value']
    s = requests.Session()
    s.cookies.update(cookies)
    s.headers.update(HEADERS)
    # 验证
    r = s.get('https://api.juejin.cn/user_api/v1/user/get')
    user = r.json().get('data', {})
    if user.get('user_name'):
        print('  ✅ %s' % user['user_name'])
        return s, user
    else:
        print('  ❌ Session expired')
        return None, None

def checkin(session):
    """掘金签到"""
    r = session.post('https://api.juejin.cn/growth_api/v1/check_in')
    resp = r.json()
    if resp.get('err_no') == 0:
        data = resp.get('data', {})
        days = data.get('incr_point', 0)
        total = data.get('sum_point', 0)
        print('  ✅ 签到成功 +%s 矿石 (总计 %s)' % (days, total))
        return True
    elif resp.get('err_msg') == 'already check in':
        print('  ℹ️ 今日已签到')
        return True
    else:
        print('  ❌ 签到失败: %s' % resp.get('err_msg', ''))
        return False

def browse_articles(session, count=5):
    """浏览推荐文章"""
    print('  📖 浏览文章...')
    for i in range(count):
        try:
            # 获取推荐列表
            r = session.get('https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed?aid=2608&uuid=&spider=0', 
                          json={'id_type': 2, 'client_type': 2608, 'sort_type': 200},
                          timeout=10)
            feed = r.json()
            items = feed.get('data', [])
            if not items:
                print('  ℹ️ 无推荐内容')
                break
            
            # 随机点一篇文章
            item = random.choice(items[:10])
            item_id = item.get('item_id', item.get('item_info', {}).get('article_id', ''))
            if not item_id:
                continue
            
            # 查看文章详情
            r2 = session.get(f'https://api.juejin.cn/content_api/v1/article/detail?article_id={item_id}', timeout=10)
            print('    📄 浏览 #%s' % item_id[-8:])
            
            # 随机间隔（模拟真实用户）
            time.sleep(random.uniform(3, 8))
        except Exception as e:
            print('    ⚠️ %s' % e)
            continue
    
    print('  ✅ 浏览完成')

def like_article(session):
    """给随机文章点赞"""
    try:
        r = session.get('https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed?aid=2608&uuid=&spider=0',
                      json={'id_type': 2, 'client_type': 2608, 'sort_type': 200},
                      timeout=10)
        items = r.json().get('data', [])
        if items:
            item = items[0]
            art_id = item.get('item_id', '')
            if art_id:
                # 点赞
                r2 = session.post('https://api.juejin.cn/interact_api/v1/digg/save', 
                                json={'itemId': art_id, 'itemType': 2})
                if r2.json().get('err_no') == 0:
                    print('  👍 点赞 +1')
    except:
        pass

def get_dip_coin(session):
    """领取免费矿石"""
    r = session.post('https://api.juejin.cn/growth_api/v1/dip/tonality')
    resp = r.json()
    if resp.get('err_no') == 0:
        point = resp.get('data', {}).get('dip_value', 0)
        print('  🪙 领取矿石 %s' % point)
    else:
        print('  ℹ️ 矿石已领取或不可用')

def main():
    print('=== 掘金自动养号 ===')
    print('时间: %s' % time.strftime('%Y-%m-%d %H:%M'))

    sess_data = get_session()
    if not sess_data:
        return
    session, user = sess_data

    # 签到
    checkin(session)
    time.sleep(random.uniform(2, 4))

    # 领取矿石
    get_dip_coin(session)
    time.sleep(random.uniform(2, 4))

    # 浏览文章
    browse_articles(session, count=5)
    time.sleep(random.uniform(2, 4))

    # 点赞
    like_article(session)

    # 记录日志
    log = {}
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, encoding='utf-8') as f:
            log = json.load(f)
    today = time.strftime('%Y-%m-%d')
    log[today] = {
        'time': time.strftime('%H:%M'),
        'user': user.get('user_name', ''),
    }
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    
    print('\n  🎉 养号完成！')

if __name__ == '__main__':
    main()
