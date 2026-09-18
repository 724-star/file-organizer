# -*- coding: utf-8 -*-
"""
preview.py —— 右侧预览面板

根据选中的文件类型，显示不同内容：
  - 图片：显示缩略图
  - 文本文件：显示前 50 行内容
  - 其他类型：显示完整路径、后缀、大小、时间等基础信息
"""

import os
import tkinter as tk
from tkinter import ttk

import config
import file_ops

# 尝试导入 Pillow（用于图片缩略图）；如果没装，就用 HAS_PIL 标记，预览图片时给出提示
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class PreviewPanel(ttk.Frame):
    """右侧预览面板：用一个可滚动文本区，既能显示文字，也能嵌入图片。"""

    def __init__(self, master):
        super().__init__(master)
        self._img_ref = None   # 保存图片引用，防止被垃圾回收导致图片不显示
        self._build()

    def _build(self):
        """搭建预览面板界面：一个标题 + 一个可滚动文本区。"""
        # 标题
        header = ttk.Label(self, text="预览", font=("微软雅黑", 12, "bold"))
        header.pack(anchor="w", padx=8, pady=(8, 2))

        # 文本区（带滚动条）
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=6, pady=6)
        self.text = tk.Text(container, wrap="word", font=("微软雅黑", 9),
                            relief="flat", state="disabled")
        scroll = ttk.Scrollbar(container, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.clear()   # 初始显示提示语

    def clear(self):
        """清空预览区，显示默认提示。"""
        self._img_ref = None                        # 释放旧图片引用
        self.text.configure(state="normal")         # 允许写入
        self.text.delete("1.0", tk.END)             # 清空
        self.text.insert("1.0", "在左侧或中间选中一个文件即可预览")
        self.text.configure(state="disabled")       # 只读

    def show(self, file_item):
        """根据文件类型显示对应预览。file_item 是 FileItem 对象，可能为 None。"""
        self._img_ref = None
        self.text.configure(state="normal")
        self.text.delete("1.0", tk.END)
        if file_item is None:
            self.text.insert("1.0", "在左侧或中间选中一个文件即可预览")
        elif config.is_image_file(file_item.name):
            self._show_image(file_item.path)        # 图片 -> 缩略图
        elif config.is_text_file(file_item.name):
            self._show_text(file_item.path)         # 文本 -> 前 50 行
        else:
            self._show_info(file_item)              # 其他 -> 基础信息
        self.text.configure(state="disabled")

    # ---------- 三种预览 ----------
    def _show_text(self, path):
        """显示文本文件的前 50 行内容。"""
        try:
            # 最多读 200KB，足够 50 行，避免大文件卡顿
            with open(path, "rb") as f:
                raw = f.read(200 * 1024)
        except OSError as e:
            self.text.insert("1.0", "无法读取文件：%s" % e)
            return
        # 依次尝试 utf-8 / gbk 解码，避免中文乱码
        text = None
        for enc in ("utf-8", "gbk"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:                            # 都解不了就用容错模式
            text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()[:config.PREVIEW_MAX_LINES]   # 只取前 50 行
        if not lines:
            self.text.insert("1.0", "（空文件）")
        else:
            self.text.insert("1.0", "\n".join(lines))

    def _show_image(self, path):
        """显示图片缩略图。"""
        if not HAS_PIL:
            self.text.insert("1.0", "（未安装 Pillow，无法预览图片缩略图）\n请运行：pip install Pillow")
            return
        try:
            img = Image.open(path)                 # 打开图片
            width, height = img.size               # 记录原始尺寸
            img.thumbnail(config.THUMBNAIL_SIZE)   # 缩小到缩略图尺寸
            photo = ImageTk.PhotoImage(img)        # 转成 tkinter 能显示的图片
            self._img_ref = photo                  # 保存引用，防止被回收
            self.text.image_create("1.0", image=photo)   # 把图片插入文本区
            self.text.insert("1.0", "\n%s\n原始尺寸：%d x %d" % (os.path.basename(path), width, height))
        except Exception as e:
            self.text.insert("1.0", "无法预览图片：%s" % e)

    def _show_info(self, file_item):
        """其他类型：显示基础信息。"""
        f = file_item
        lines = [
            "文件名：%s" % f.name,
            "后缀：%s" % (f.ext.upper() if f.ext else "无"),
            "分类：%s" % f.category,
            "大小：%s" % file_ops.format_size(f.size),
            "修改时间：%s" % file_ops.format_time(f.mtime),
        ]
        # 额外读一下创建时间
        try:
            ctime = os.path.getctime(f.path)
            lines.append("创建时间：%s" % file_ops.format_time(ctime))
        except OSError:
            pass
        lines += ["", "完整路径：", f.path]
        self.text.insert("1.0", "\n".join(lines))
