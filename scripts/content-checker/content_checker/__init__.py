"""
content-checker — 发文前内容合规检查工具

检查敏感词、违规内容、平台特有规范，支持红线/黄线分级检测。

用法:
    content-checker check <文章路径>
    content-checker scan [目录路径]
"""

from .core import (
    check_file,
    check_text,
    scan_directory,
    SENSITIVE_WORDS,
)

__version__ = "1.0.0"
__all__ = ["check_file", "check_text", "scan_directory", "SENSITIVE_WORDS"]
