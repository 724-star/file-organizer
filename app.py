# -*- coding: utf-8 -*-
"""
app.py —— 主窗口（三栏布局）

布局：
  顶部：操作按钮（预览整理方案 / 撤销上次整理 / 移动 / 重命名 / 删除 / 搜索）
  左栏：文件夹目录树（默认定位桌面，可展开切换任意文件夹）
  中栏：文件列表（图标、文件名、类型、大小、修改时间；可排序、可搜索、可多选）
  右栏：文件预览（图片缩略图 / 文本前50行 / 基础信息）
  底部：状态栏

安全设计：
  - 「预览整理方案」只计算不执行，点确认才真正移动文件；
  - 移动/删除都会弹出确认框；删除会二次确认；
  - 整理操作支持「撤销上次整理」。
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import config
import file_ops
from preview import PreviewPanel


class MainWindow:
    """应用主窗口。"""

    def __init__(self):
        self.root = tk.Tk()                              # 创建根窗口
        self.root.title("文件整理工具")                    # 窗口标题
        self.root.geometry("1200x700")                   # 初始大小
        self.root.minsize(900, 550)                      # 最小可缩到的尺寸

        # 默认定位到桌面；如果标准桌面路径不存在（比如被重定向到 OneDrive），退回用户主目录
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(desktop):
            desktop = os.path.expanduser("~")
        self.current_dir = desktop                       # 当前浏览的目录

        self.file_items = []        # 当前目录的文件列表（FileItem 对象）
        self.row_to_item = {}       # 文件列表的「行 id -> FileItem」映射（批量操作用）
        self.undo_record = None     # 最近一次整理的撤销记录
        self.sort_col = "name"      # 当前排序列
        self.sort_reverse = False   # 是否倒序

        self._build_ui()                     # 搭界面
        self._insert_tree_root()             # 左侧树先插入桌面节点
        self._load_directory(self.current_dir)  # 读取并显示桌面文件

    def run(self):
        """进入界面主循环。"""
        self.root.mainloop()

    # ================= 界面搭建 =================
    def _build_ui(self):
        """搭建整个界面：工具栏 + 三栏 + 状态栏。"""
        self._build_toolbar()          # 顶部按钮
        self._build_paned()            # 中间三栏
        # 底部状态栏
        self.status = ttk.Label(self.root, text="就绪", anchor="w",
                                relief="sunken", padding=(8, 2))
        self.status.pack(side="bottom", fill="x")

    def _build_toolbar(self):
        """顶部工具栏：按钮 + 搜索框。"""
        bar = ttk.Frame(self.root, padding=6)
        bar.pack(side="top", fill="x")

        ttk.Button(bar, text="刷新", command=self._refresh).pack(side="left", padx=2)
        ttk.Button(bar, text="预览整理方案", command=self._preview_plan).pack(side="left", padx=2)
        self.btn_undo = ttk.Button(bar, text="撤销上次整理", command=self._undo, state="disabled")
        self.btn_undo.pack(side="left", padx=2)

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)

        ttk.Button(bar, text="移动到…", command=self._batch_move).pack(side="left", padx=2)
        ttk.Button(bar, text="批量重命名", command=self._batch_rename).pack(side="left", padx=2)
        ttk.Button(bar, text="删除", command=self._batch_delete).pack(side="left", padx=2)

        # 搜索框（靠右）
        ttk.Label(bar, text="搜索：").pack(side="right", padx=(6, 0))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._refresh_file_list())
        ttk.Entry(bar, textvariable=self.search_var, width=18).pack(side="right", padx=4)

    def _build_paned(self):
        """中间三栏，用 PanedWindow 实现可拖动分隔条。"""
        self.paned = ttk.PanedWindow(self.root, orient="horizontal")
        self.paned.pack(side="top", fill="both", expand=True)
        self._build_tree(self.paned)       # 左
        self._build_filelist(self.paned)   # 中
        self._build_preview(self.paned)    # 右

    # ---------- 左栏：目录树 ----------
    def _build_tree(self, parent):
        """左侧目录树。"""
        frame = ttk.Frame(parent)
        parent.add(frame, weight=1)
        ttk.Label(frame, text="文件夹", font=("微软雅黑", 11, "bold")).pack(anchor="w", padx=6, pady=(6, 2))
        self.tree = ttk.Treeview(frame, show="tree", selectmode="browse")
        self.tree.pack(fill="both", expand=True, padx=4, pady=4)
        self.tree.bind("<<TreeviewOpen>>", self._on_tree_open)     # 展开时加载子目录
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)  # 选中时切换目录
        self.node_path = {}   # 树的「节点 id -> 完整路径」映射

    def _insert_tree_root(self):
        """左侧树只插入桌面这个根节点（其余子目录按需懒加载）。"""
        node = self._insert_node("", self.current_dir)
        self.tree.selection_set(node)   # 默认选中桌面

    def _insert_node(self, parent_id, path):
        """把一个目录作为节点插入树，并返回节点 id。"""
        name = os.path.basename(path) or path   # 根盘符（如 C:\）没有 basename，就显示全路径
        node = self.tree.insert(parent_id, "end", text=name)
        self.node_path[node] = path             # 记录节点对应的完整路径
        self.tree.insert(node, "end")           # 插入占位子节点，让节点显示可展开的小三角
        return node

    def _on_tree_open(self, event):
        """目录树节点被展开时，加载它的真实子目录（懒加载，避免一次扫太多）。"""
        node = self.tree.focus()
        if not node:
            return
        path = self.node_path.get(node)
        if not path:
            return
        children = self.tree.get_children(node)
        # 如果第一个子节点是「占位节点」（没记过路径），先删掉它
        if children and not self.node_path.get(children[0]):
            self.tree.delete(children[0])
        # 加载真实子目录
        for sub in file_ops.list_subdirectories(path):
            self._insert_node(node, sub)

    def _on_tree_select(self, event):
        """点击目录树节点，切换中间文件列表显示的目录。"""
        node = self.tree.focus()
        if not node:
            return
        path = self.node_path.get(node)
        if path:
            self._load_directory(path)

    # ---------- 中栏：文件列表 ----------
    def _build_filelist(self, parent):
        """中间文件列表。"""
        frame = ttk.Frame(parent)
        parent.add(frame, weight=3)
        ttk.Label(frame, text="文件", font=("微软雅黑", 11, "bold")).pack(anchor="w", padx=6, pady=(6, 2))

        columns = ("icon", "name", "type", "size", "time")
        self.flist = ttk.Treeview(frame, columns=columns, show="headings", selectmode="extended")
        # 表头：点一下按该列排序
        self.flist.heading("icon", text="")
        self.flist.heading("name", text="文件名", command=lambda: self._sort_by("name"))
        self.flist.heading("type", text="类型", command=lambda: self._sort_by("type"))
        self.flist.heading("size", text="大小", command=lambda: self._sort_by("size"))
        self.flist.heading("time", text="修改时间", command=lambda: self._sort_by("time"))
        # 每列宽度
        self.flist.column("icon", width=40, anchor="center", stretch=False)
        self.flist.column("name", width=300)
        self.flist.column("type", width=90, anchor="center")
        self.flist.column("size", width=90, anchor="e")
        self.flist.column("time", width=140, anchor="center")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.flist.yview)
        self.flist.configure(yscrollcommand=vsb.set)
        self.flist.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        vsb.pack(side="left", fill="y", pady=4)

        self.flist.bind("<<TreeviewSelect>>", self._on_file_select)     # 选中 -> 预览
        self.flist.bind("<Double-1>", self._on_file_double_click)       # 双击 -> 打开

    # ---------- 右栏：预览 ----------
    def _build_preview(self, parent):
        """右侧预览面板。"""
        self.preview = PreviewPanel(parent)
        parent.add(self.preview, weight=2)

    # ================= 目录加载与列表刷新 =================
    def _load_directory(self, path):
        """切换到某个目录：读取文件，刷新列表。"""
        self.current_dir = path
        self.file_items = file_ops.scan_directory(path)   # 读取该目录下的文件
        self._refresh_file_list()

    def _refresh(self):
        """刷新当前目录（重新读取）。"""
        self._load_directory(self.current_dir)

    def _refresh_file_list(self):
        """根据「搜索关键字 + 排序」重新填充文件列表。"""
        keyword = self.search_var.get().strip().lower() if hasattr(self, "search_var") else ""
        items = self.file_items
        if keyword:                                        # 搜索过滤：文件名包含关键字
            items = [f for f in items if keyword in f.name.lower()]
        items = sorted(items, key=self._sort_key, reverse=self.sort_reverse)  # 排序

        self.row_to_item = {}                              # 清空旧映射
        self.flist.delete(*self.flist.get_children())      # 清空旧行
        for f in items:
            row = self.flist.insert("", "end", values=(
                config.CATEGORY_ICON.get(f.category, "其"),  # 图标
                f.name,                                      # 文件名
                f.category,                                  # 类型（分类名）
                file_ops.format_size(f.size),                # 大小
                file_ops.format_time(f.mtime),               # 修改时间
            ))
            self.row_to_item[row] = f                       # 记住这行对应哪个文件
        self.status.config(text="共 %d 个文件　当前目录：%s" % (len(items), self.current_dir))

    def _sort_key(self, f):
        """排序用的键值函数。"""
        if self.sort_col == "size":
            return f.size
        if self.sort_col == "time":
            return f.mtime
        if self.sort_col == "type":
            return f.category
        return f.name.lower()                              # 默认按文件名

    def _sort_by(self, col):
        """点击表头排序：同一列再点就反向。"""
        if self.sort_col == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_col = col
            self.sort_reverse = False
        self._refresh_file_list()

    # ================= 事件处理 =================
    def _on_file_select(self, event):
        """选中文件时，右侧显示预览。"""
        sel = self.flist.selection()
        if not sel:
            self.preview.clear()
            return
        item = self.row_to_item.get(sel[0])
        self.preview.show(item)

    def _on_file_double_click(self, event):
        """双击文件，用系统默认程序打开。"""
        sel = self.flist.selection()
        if not sel:
            return
        item = self.row_to_item.get(sel[0])
        if item:
            try:
                os.startfile(item.path)   # Windows 下用默认程序打开
            except OSError:
                messagebox.showerror("错误", "无法打开该文件。")

    def _selected_items(self):
        """返回当前勾选文件的 FileItem 列表。"""
        rows = self.flist.selection()
        return [self.row_to_item[r] for r in rows if r in self.row_to_item]

    # ================= 自动整理 =================
    def _preview_plan(self):
        """预览整理方案：列出每个文件会被移到哪个分类文件夹，但不执行。"""
        items = self.file_items                 # 整理当前目录所有文件
        if not items:
            messagebox.showinfo("提示", "当前目录没有文件。")
            return
        plans = file_ops.build_organize_plan(items, self.current_dir)
        if not plans:
            messagebox.showinfo("提示", "没有需要整理的文件（可能都已经在对应分类文件夹里了）。")
            return
        self._show_plan_dialog(plans)

    def _show_plan_dialog(self, plans):
        """整理方案预览对话框：只展示方案，点「执行整理」才真正移动。"""
        dlg = tk.Toplevel(self.root)
        dlg.title("整理方案预览（尚未执行）")
        dlg.geometry("640x440")
        dlg.transient(self.root)   # 挂在主窗口上
        dlg.grab_set()             # 模态：关闭前不能操作主窗口

        ttk.Label(dlg, text="以下文件将被移动到对应分类文件夹（点「执行整理」后才真正移动）：",
                  font=("微软雅黑", 10)).pack(anchor="w", padx=10, pady=(10, 4))

        tree = ttk.Treeview(dlg, columns=("src", "cat", "dst"), show="headings")
        tree.heading("src", text="文件名")
        tree.heading("cat", text="分类")
        tree.heading("dst", text="将移动到")
        tree.column("src", width=200)
        tree.column("cat", width=80, anchor="center")
        tree.column("dst", width=300)
        for p in plans:
            folder = config.CATEGORY_FOLDER.get(p.category, "其他")
            tree.insert("", "end", values=(
                os.path.basename(p.src),
                p.category,
                os.path.join(folder, os.path.basename(p.src)),
            ))
        tree.pack(fill="both", expand=True, padx=10, pady=4)

        # 统计每个分类各有多少个
        summary = {}
        for p in plans:
            summary[p.category] = summary.get(p.category, 0) + 1
        text = "共 %d 个文件：" % len(plans) + "，".join("%s %d 个" % (k, v) for k, v in summary.items())
        ttk.Label(dlg, text=text, foreground="#666").pack(anchor="w", padx=10, pady=2)

        btns = ttk.Frame(dlg)
        btns.pack(pady=8)
        ttk.Button(btns, text="执行整理", command=lambda: self._do_execute(plans, dlg)).pack(side="left", padx=6)
        ttk.Button(btns, text="取消", command=dlg.destroy).pack(side="left", padx=6)

    def _do_execute(self, plans, dlg):
        """确认后真正执行整理，并保存撤销记录。"""
        dlg.destroy()
        if not messagebox.askyesno("确认执行",
                                   "确定要移动这 %d 个文件吗？\n（之后可点「撤销上次整理」反悔）" % len(plans)):
            return
        self.undo_record = file_ops.execute_plans(plans)   # 执行移动
        moved = len(self.undo_record.get("moved", []))
        self.btn_undo.config(state="normal")               # 启用撤销按钮
        self._refresh()
        messagebox.showinfo("完成", "已整理 %d 个文件。" % moved)

    def _undo(self):
        """撤销上一次整理：把文件移回原位。"""
        if not self.undo_record:
            return
        if not messagebox.askyesno("确认撤销", "确定要撤销上一次整理，把文件移回原位吗？"):
            return
        n = file_ops.undo_last(self.undo_record)
        self.undo_record = None
        self.btn_undo.config(state="disabled")
        self._refresh()
        messagebox.showinfo("完成", "已撤销，%d 个文件移回原位。" % n)

    # ================= 手动批量操作 =================
    def _batch_move(self):
        """把勾选的文件批量移动到指定文件夹。"""
        items = self._selected_items()
        if not items:
            messagebox.showinfo("提示", "请先勾选要移动的文件（可按住 Ctrl 多选）。")
            return
        target = filedialog.askdirectory(title="选择目标文件夹", initialdir=self.current_dir)
        if not target:
            return
        if not messagebox.askyesno("确认移动", "要把这 %d 个文件移动到：\n%s" % (len(items), target)):
            return
        moved = file_ops.move_files_to(items, target)
        self._refresh()
        messagebox.showinfo("完成", "已移动 %d 个文件。" % len(moved))

    def _batch_rename(self):
        """批量重命名：加前缀 + 序号，保留后缀。"""
        items = self._selected_items()
        if not items:
            messagebox.showinfo("提示", "请先勾选要重命名的文件。")
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("批量重命名")
        dlg.geometry("380x230")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text="前缀（如「照片」）：").pack(anchor="w", padx=12, pady=(14, 2))
        prefix = tk.StringVar()
        ttk.Entry(dlg, textvariable=prefix).pack(fill="x", padx=12)

        ttk.Label(dlg, text="起始序号：").pack(anchor="w", padx=12, pady=(8, 2))
        start = tk.StringVar(value="1")
        ttk.Entry(dlg, textvariable=start, width=8).pack(anchor="w", padx=12)

        ttk.Label(dlg, text="示例：前缀「照片」+ 起始 1 → 照片_001.jpg、照片_002.png…",
                  foreground="#666", font=("微软雅黑", 8)).pack(anchor="w", padx=12, pady=6)

        def ok():
            p = prefix.get().strip()
            if not p:
                messagebox.showwarning("提示", "前缀不能为空。")
                return
            try:
                n = int(start.get())
            except ValueError:
                messagebox.showwarning("提示", "起始序号必须是数字。")
                return
            records = file_ops.rename_files(items, p, n)     # 计算新名字
            if not records:
                messagebox.showinfo("提示", "没有需要重命名的文件。")
                dlg.destroy()
                return
            sample = "\n".join("%s → %s" % (os.path.basename(a), os.path.basename(b))
                               for a, b in records[:10])
            if len(records) > 10:
                sample += "\n… 共 %d 个" % len(records)
            if messagebox.askyesno("确认重命名", "将这样重命名：\n\n%s" % sample):
                done = file_ops.execute_renames(records)     # 真正改名
                dlg.destroy()
                self._refresh()
                messagebox.showinfo("完成", "已重命名 %d 个文件。" % len(done))
            else:
                dlg.destroy()

        ttk.Button(dlg, text="确定", command=ok).pack(pady=12)

    def _batch_delete(self):
        """删除勾选的文件（永久删除，二次确认）。"""
        items = self._selected_items()
        if not items:
            messagebox.showinfo("提示", "请先勾选要删除的文件。")
            return
        names = "\n".join("· %s" % f.name for f in items[:10])
        if len(items) > 10:
            names += "\n… 共 %d 个文件" % len(items)
        # 第一次确认
        if not messagebox.askyesno("确认删除（第一次确认）",
                                   "确定要删除下面 %d 个文件吗？\n\n%s" % (len(items), names),
                                   icon="warning"):
            return
        # 第二次确认（强提示）
        if not messagebox.askyesno("最终确认",
                                   "删除后无法恢复（不进回收站）！\n真的删除吗？",
                                   icon="warning"):
            return
        n = file_ops.delete_files(items)
        self._refresh()
        messagebox.showinfo("完成", "已删除 %d 个文件。" % n)
