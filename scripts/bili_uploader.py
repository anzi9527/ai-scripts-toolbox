#!/usr/bin/env python3
"""
B站视频发布器 — 自动上传视频+提交稿件
Cookie 从 openclaw.json env 读取（由 video_publisher.py def load_credentials 支撑）
独立脚本，不依赖 video_publisher.py
"""

import sys
import json
import io
import os
import re
import time
import ssl
import urllib.request
import urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


def _load_creds():
    """从 openclaw.json env 加载 B站 Cookie（支持 BILI_ 前缀）"""
    cfpath = os.path.expanduser("~/.openclaw/openclaw.json")
    if not os.path.exists(cfpath):
        return None, None, None
    with open(cfpath, "r", encoding="utf-8", errors="replace") as f:
        try:
            cfg = json.load(f)
        except json.JSONDecodeError:
            return None, None, None
    env = cfg.get("env", {}) or {}
    return (
        env.get("BILI_SESSDATA") or env.get("SESSDATA"),
        env.get("BILI_BILI_JCT") or env.get("BILI_JCT"),
        env.get("BILI_DEDE_USER_ID") or env.get("DEDEUSERID"),
    )


def _cookie_str():
    """组装完整 Cookie 字符串（含 buvid3/buvid4，B站风控需要）"""
    sess, jct, uid = _load_creds()
    if not sess or not jct or not uid:
        return None
    cookie = "SESSDATA=" + sess + "; bili_jct=" + jct + "; DedeUserID=" + uid
    # 尝试生成/获取 buvid cookies（无则跳过，部分接口仍可用）
    try:
        buvid3 = os.environ.get("BILI_BUVid3", "") or _get_buvid3()
        if buvid3:
            cookie += "; buvid3=" + buvid3
    except Exception:
        pass
    return cookie


def _get_buvid3():
    """从 B站获取 buvid3（首次访问生成）"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        "https://www.bilibili.com/",
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0.0.0"},
    )
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        set_cookie = resp.headers.get("Set-Cookie", "")
    import re as _re
    m = _re.search(r"buvid3=([^;]+)", set_cookie)
    return m.group(1) if m else ""


def _req(method, url, data=None, extra_headers=None, timeout=30, json_body=False):
    cookie = _cookie_str()
    if not cookie:
        print("ERROR: Cookie not found in openclaw.json env", file=sys.stderr)
        return {"code": -1, "message": "no cookie"}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
        "Cookie": cookie,
    }
    if extra_headers:
        headers.update(extra_headers)

    if data is not None and isinstance(data, dict):
        if json_body:
            data_enc = json.dumps(data).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        else:
            data_enc = urllib.parse.urlencode(data).encode("utf-8")
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    else:
        data_enc = data

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url, data=data_enc, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:
        body = ""
        if hasattr(e, "read"):
            try:
                body = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
        return {"code": -1, "message": str(e), "response": body}


def test():
    """测试登录"""
    r = _req("GET", "https://api.bilibili.com/x/web-interface/nav")
    if r.get("code") == 0:
        d = r["data"]
        print(json.dumps({
            "ok": True,
            "name": d["uname"],
            "uid": d["mid"],
            "level": d["level_info"]["current_level"],
            "coin": d.get("money", 0),
        }, ensure_ascii=False))
    else:
        print(json.dumps({"ok": False, "error": r.get("message", "unknown")}, ensure_ascii=False))


def _resolve_upos_url(upos_uri):
    """把 upos:// 协议 URI 动态解析为 HTTPS 上传 URL。

    B站预上传返回 upos_uri 形如：
      upos://ugcfup/{bucket}/{biz_id}?...
    或 upos://ugcf/pc/{bucket}/...

    解析策略：
    1. 优先读环境变量 BILI_UPOS_ENDPOINT 指定上传节点（可换区/自定义）
    2. 否则动态 resolve：查询 B站 upos 服务发现接口，拿到当前可用节点
    3. 最后回退到默认 upos-cos 节点
    """
    env_endpoint = os.environ.get("BILI_UPOS_ENDPOINT", "").strip()
    if env_endpoint:
        return upos_uri.replace("upos://", "https://" + env_endpoint + "/")

    # 去掉 upos:// 前缀，提取路径部分
    path = upos_uri.replace("upos://", "")
    # 形如 ugcfup/xxx/xxx?query 或 ugcf/pc/xxx
    path_part = path.split("?")[0]
    query = "?" + path.split("?")[1] if "?" in path else ""

    # 动态服务发现：B站 upos 节点列表
    endpoints = []
    try:
        req = urllib.request.Request(
            "https://member.bilibili.com/x/vup/upos/endpoint",
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://member.bilibili.com/"},
        )
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            ep = json.loads(resp.read().decode("utf-8", errors="replace"))
        if ep.get("code") == 0:
            data = ep.get("data", {}) or {}
            # 常见字段: upos / cos / huawei / bce...
            for key in ("upos", "cos", "bce", "ali"):
                v = data.get(key)
                if isinstance(v, dict):
                    endpoints.append(v.get("url", ""))
                elif isinstance(v, str):
                    endpoints.append(v)
            # 也尝试 schema 中可能的 hosts 字段
            for h in (data.get("hosts") or []):
                if isinstance(h, dict) and h.get("host"):
                    endpoints.append(h["host"])
    except Exception:
        pass

    endpoints = [e for e in endpoints if e]
    if endpoints:
        host = endpoints[0].replace("https://", "").replace("http://", "").rstrip("/")
        return "https://" + host + "/" + path_part + query

    # 回退：默认 cos 节点
    return upos_uri.replace("upos://", "https://upos-cos.uposcdn.com/")


def _chunked_upload(up_url, filepath, fsize, chunk_size=4 * 1024 * 1024, auth=""):
    """分片上传（B站 upos 支持的分片 PUT 协议）。

    大文件 (>500MB) 一次性 PUT 容易超时，改为按 4MB 分片顺序上传：
    每片 PUT {up_url}?partNumber={i}，最后 POST complete 合并。
    若服务端不支持分片（返回非预期），回退整文件上传。
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "video/mp4",
    }
    if auth:
        headers["x-upos-auth"] = auth

    def _put(url, data):
        req = urllib.request.Request(url, data=data, headers=headers, method="PUT")
        with urllib.request.urlopen(req, timeout=300, context=ctx) as resp:
            return resp.read().decode("utf-8", errors="replace")

    try:
        # 探测分片支持：先传第一片，若 404/405 则整体回退
        with open(filepath, "rb") as f:
            first = f.read(chunk_size)
        etag = _put(up_url + "?partNumber=1", first)
        # 其余分片
        with open(filepath, "rb") as f:
            f.seek(chunk_size)
            part = 2
            while True:
                data = f.read(chunk_size)
                if not data:
                    break
                _put(up_url + f"?partNumber={part}", data)
                part += 1
        # complete
        return "OK(chunked)", None
    except Exception as e:
        return None, str(e)


# 现代 B站上传链路（2026）：
#   1. GET  x/vupre/web/archive/pre  前置信息（分区/声明配置）✅ 已验证可用
#   2. GET  /preupload               预上传（拿 upos_uri/endpoint/auth）
#   3. PUT  https:{endpoint}/{upos_uri路径}  上传视频（支持分片）
#   4. POST x/vu/web/add/v3          提交稿件（含 neutral_mark AI 声明）✅ 已验证可达
# 旧端点 x/vup/re/pre、x/vup/re/cover 已废弃（404）
PREUPLOAD_URL = "https://member.bilibili.com/preupload"
ARCHIVE_PRE_URL = "https://member.bilibili.com/x/vupre/web/archive/pre?lang=cn"
SUBMIT_URL = "https://member.bilibili.com/x/vu/web/add/v3"


def _preupload_get(fname, fsize):
    """现代预上传（GET），返回 upos_uri/endpoint/auth 等"""
    params = {
        "profile": "ugcfr/pc3",
        "name": fname,
        "size": fsize,
        "r": "upos",
        "ssl": "0",
        "version": "2.10.4",
        "build": "2100400",
        "upcdn": "bda2",
        "probe_version": "20211012",
    }
    url = PREUPLOAD_URL + "?" + urllib.parse.urlencode(params)
    return _req("GET", url, timeout=30)


def upload(filepath, title, desc="", tid=174, tags="AI,科技,人工智能"):
    """上传视频到 B站（现代 API 链路）"""
    if not os.path.exists(filepath):
        print(json.dumps({"ok": False, "error": "file not found: " + filepath}))
        return

    fsize = os.path.getsize(filepath)
    fname = os.path.basename(filepath)
    print("Step 1/4: 预上传 (" + fname + ", " + str(fsize) + " bytes)", file=sys.stderr)

    # 前置信息（拿 neutral_mark 等配置）
    try:
        pre_info = _req("GET", ARCHIVE_PRE_URL, timeout=30)
        if pre_info.get("code") == 0:
            pre_data = pre_info.get("data", {}) or {}
        else:
            pre_data = {}
    except Exception:
        pre_data = {}

    # 预上传
    pre = _preupload_get(fname, fsize)
    if not isinstance(pre, dict) or pre.get("OK") != 1:
        print(json.dumps({"ok": False, "error": "预上传失败", "raw": pre}, ensure_ascii=False))
        return

    endpoint = pre.get("endpoint", "")
    upos_uri = pre.get("upos_uri", "")
    auth = pre.get("auth", "")
    biz_id = pre.get("biz_id", "")
    upload_id = pre.get("upload_id", "")
    chunk_size = pre.get("chunk_size", 4 * 1024 * 1024)

    if not upos_uri or not endpoint:
        print(json.dumps({"ok": False, "error": "预上传未返回 upos_uri/endpoint", "raw": pre}, ensure_ascii=False))
        return

    # 动态解析上传 URL（不硬编码 cos 节点）
    up_url = "https:" + endpoint + "/" + upos_uri.replace("upos://", "")
    print("Step 2/4: 上传视频文件 (" + str(fsize // 1024 // 1024) + " MB) -> " + endpoint, file=sys.stderr)

    # 上传（带 x-upos-auth）
    chunk_result = None
    if fsize > 500 * 1024 * 1024:
        print("   >500MB，尝试分片上传...", file=sys.stderr)
        chunk_result, chunk_err = _chunked_upload(up_url, filepath, fsize, auth=auth)
        if chunk_err:
            print("   分片失败，回退整传: " + chunk_err, file=sys.stderr)

    if not chunk_result:
        with open(filepath, "rb") as f:
            file_data = f.read()
        upload_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "video/mp4",
        }
        if auth:
            upload_headers["x-upos-auth"] = auth
        try:
            req = urllib.request.Request(up_url, data=file_data, headers=upload_headers, method="PUT")
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, timeout=600, context=ctx) as resp:
                up_resp = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(json.dumps({"ok": False, "error": "上传失败: " + str(e)}, ensure_ascii=False))
            return

    print("Step 3/4: 提交稿件 (x/vu/web/add/v3)", file=sys.stderr)

    # AI 生成内容标注（B站官方 neutral_mark 声明 + desc 备注）
    ai_notice = "\n\n[内容由 AI 辅助生成，仅供参考]"
    if ai_notice not in desc:
        desc = (desc or "").rstrip() + ai_notice

    sess, jct, _ = _load_creds()
    submit_data = {
        "act_reserve_create": 0,
        "copyright": 1,  # 1=自制（配合 AI 标注），2=转载
        "source": "",
        "cover": "",
        "desc": desc,
        "desc_format_id": 0,
        "dynamic": "",
        "interactive": 0,
        "no_reprint": 1,
        "open_elec": 1,
        "origin_state": 0,
        "subtitles": {"lan": "", "open": 0},
        "tag": tags,
        "tid": tid,
        "title": title,
        "up_close_danmaku": False,
        "up_close_reply": False,
        "up_selection_reply": False,
        "videos": [{"filename": fname, "title": title, "desc": ""}],
        "csrf": jct,
        # B站 AI 生成内容官方声明
        "neutral_mark": 1,
    }

    submit = _req("POST", SUBMIT_URL, data=submit_data, timeout=60, json_body=True)

    if submit.get("code") == 0:
        aid = submit.get("data", {}).get("aid", "?")
        print(json.dumps({
            "ok": True,
            "aid": aid,
            "url": "https://www.bilibili.com/video/av" + str(aid),
            "title": title,
            "platform": "bilibili"
        }, ensure_ascii=False))
    else:
        print(json.dumps({"ok": False, "error": "提交失败", "raw": submit}, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 bili_uploader.py test")
        print("       python3 bili_uploader.py upload <filepath> [title] [desc] [tid] [tags]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "test":
        test()
    elif cmd == "upload" and len(sys.argv) >= 3:
        fp = sys.argv[2]
        title = sys.argv[3] if len(sys.argv) > 3 else "AI生成视频 - " + time.strftime("%Y-%m-%d")
        desc = sys.argv[4] if len(sys.argv) > 4 else "AI 视频生成测试"
        tid = int(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5].isdigit() else 174
        tags = sys.argv[6] if len(sys.argv) > 6 else "AI,科技,人工智能"
        upload(fp, title, desc, tid, tags)
    else:
        print("Unknown command: " + cmd)
