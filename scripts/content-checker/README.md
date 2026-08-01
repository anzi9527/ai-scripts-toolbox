# Content Checker 内容合规检查器

> 发文前自动检查敏感词、违规内容、平台规范 — 一步到位，别再让文章被夹。

## 痛点

在掘金/CSDN/知乎发文，最怕什么？  
— 写半天，发出去三分钟被删，最惨是被封号。

这个工具在 **发文前** 帮你自己先查一遍。

## 功能

- 🔴 **红线违规检测** — 政治、色情、暴力、违法信息，一抓一个准
- 🟡 **黄线警告检测** — 营销过度、版权模糊、外链过多等
- ⚠️ **平台特有规则** — 掘金/CSDN/知乎各有各的雷区
- 📦 纯 Python 实现，零外部依赖
- 🖥️ CLI 一键检查 + JSON 输出（可集成到 CI/Pipeline）

## 安装

```bash
pip install content-checker
```

或直接从源码安装：

```bash
git clone https://github.com/xiaoling/content-checker.git
cd content-checker
pip install -e .
```

## 用法

### 检查单个文件

```bash
content-checker check 文章.md
```

### 扫描目录下所有 Markdown 文件

```bash
content-checker scan output/articles/
```

### 输出 JSON（方便集成）

```bash
content-checker json 文章.md | jq .
```

### 作为 Python 模块使用

```python
from content_checker import check_text, check_file

# 直接检查文本
results = check_text("你的文章内容...")
print(results["red_flags"])   # 红线违规
print(results["yellow_flags"]) # 黄线警告

# 检查文件
results, verdict = check_file("文章.md")
print(verdict)  # 判定结果
```

## 判定规则

| 结果 | 含义 | 建议 |
|:----|:----|:----|
| ✅ 合规 | 无任何违规 | 放心发 |
| 🟡 可发布 | 有黄线警告但不严重 | 建议检查提醒事项 |
| ⚠️ 修改后发 | 黄线较多或外链过多 | 改完再发 |
| ❌ 禁止发布 | 存在红线违规 | 必须删除违规内容 |

## 自定义敏感词库

创建 `~/.content-checker/custom_words.json`:

```json
{
  "red": ["你的自定义红线词"],
  "yellow": ["你的自定义警告词"]
}
```

## 适用场景

- 自媒体作者发文前自检
- CI/CD 流水线中自动检查发布内容
- 内容团队批量审核稿件
- 多平台同步发文前的统一检查

## License

MIT
