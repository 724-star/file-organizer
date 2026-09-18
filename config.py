# -*- coding: utf-8 -*-
"""
config.py —— 全局配置与分类规则

这个文件集中放三样东西：
1. 文件分类规则（哪些后缀算图片、哪些算文档……）
2. 每个分类对应的图标、文件夹名
3. 一些通用常量

好处：以后想改分类、加新类型，只需要改这一个文件，别的代码不用动。
"""

import os


# ---------- 分类规则 ----------
# 结构：类别名 -> 属于该类的文件后缀列表（小写、不带点）
# 「其他」是兜底类：凡是匹配不上前面所有类的文件，都归到这里，所以它的列表是空的。
CATEGORY_RULES = {
    "图片": ["jpg", "jpeg", "png", "gif", "bmp", "webp", "svg", "ico", "tiff"],
    "文档": ["doc", "docx", "pdf", "txt", "md", "xls", "xlsx", "ppt", "pptx", "csv", "rtf"],
    "视频": ["mp4", "avi", "mkv", "mov", "wmv", "flv", "webm", "mpg", "mpeg"],
    "压缩包": ["zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso"],
    "代码": ["py", "js", "html", "css", "java", "c", "cpp", "h", "ts", "json",
             "xml", "yml", "yaml", "sh", "bat", "sql", "go", "rs", "php", "vue"],
    "其他": [],
}


# ---------- 每个分类的文件夹名（执行整理时会新建这些文件夹）----------
CATEGORY_FOLDER = {
    "图片": "图片",
    "文档": "文档",
    "视频": "视频",
    "压缩包": "压缩包",
    "代码": "代码",
    "其他": "其他",
}


# ---------- 每个分类在列表里显示的图标 ----------
# 说明：用单字中文当图标，而不是 emoji。
# 原因：Tk 8.6 引擎只支持 U+FFFF 以内的字符，emoji（如 📄💻）编号超过这个范围会报错；
#       单字中文既在范围内、又直观，新手一眼能看懂。
CATEGORY_ICON = {
    "图片": "图",
    "文档": "文",
    "视频": "视",
    "压缩包": "包",
    "代码": "码",
    "其他": "其",
}


# ---------- 文本文件后缀（预览面板显示前 50 行内容）----------
TEXT_EXTENSIONS = {
    "txt", "py", "html", "js", "css", "json", "xml", "yml", "yaml", "md",
    "java", "c", "cpp", "h", "ts", "sh", "bat", "sql", "csv", "log",
    "ini", "conf", "go", "rs", "php", "vue", "rb", "pl",
}


# ---------- 图片文件后缀（预览面板显示缩略图）----------
IMAGE_EXTENSIONS = {
    "jpg", "jpeg", "png", "gif", "bmp", "webp", "ico", "tiff", "svg",
}


# ---------- 其他常量 ----------
PREVIEW_MAX_LINES = 50         # 文本预览最多显示的行数
THUMBNAIL_SIZE = (420, 320)    # 图片缩略图的最大宽高（像素）


# ---------- 工具函数 ----------
def get_extension(filename):
    """取文件后缀（小写、不带点）。如 'a.JPG' -> 'jpg'；没有后缀返回空字符串 ''。"""
    return os.path.splitext(filename)[1][1:].lower()


def get_category(filename):
    """判断文件属于哪一类，匹配不上就返回「其他」。"""
    ext = get_extension(filename)               # 先取后缀
    for category, exts in CATEGORY_RULES.items():
        if category == "其他":
            continue                            # 跳过兜底类，它靠最后 return 兜底
        if ext in exts:
            return category                     # 匹配上就返回这个类别
    return "其他"


def is_text_file(filename):
    """判断是不是文本文件（预览时显示前 50 行）。"""
    return get_extension(filename) in TEXT_EXTENSIONS


def is_image_file(filename):
    """判断是不是图片文件（预览时显示缩略图）。"""
    return get_extension(filename) in IMAGE_EXTENSIONS
