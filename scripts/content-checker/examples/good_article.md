# 示例：合规文章

今天我们来聊聊如何用 Python 自动化公众号文章的排版工作。

## 问题

每次手动调整 Markdown 格式太累了，尤其是代码块和引用。

## 解决方案

用 Python 写个简单的转换脚本：

```python
import re

def convert_markdown(text):
    # 将普通引用转为标注格式
    text = re.sub(r'^> (.+)$', r'**引用:** \1', text, flags=re.MULTILINE)
    return text
```

## 总结

这套方法帮我每天节省了至少 20 分钟的排版时间。

---

*本文为作者原创，使用 GitHub 项目 [awesome-md-tools](https://github.com/example/awesome-md-tools) 辅助排版。*
