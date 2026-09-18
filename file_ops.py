# -*- coding: utf-8 -*-
"""
file_ops.py —— 文件操作核心逻辑（不涉及界面）

这个文件只做「纯逻辑」：扫描目录、分类、生成整理方案、执行移动、撤销。
好处：
1. 界面(app.py)和逻辑(file_ops.py)分开，逻辑可以单独测试；
2. 「先规划、后执行」：所有真正改动文件的操作，都先算好方案，确认后才执行。

安全原则：这里没有任何「偷偷删除/覆盖」的代码——
移动会避开重名，删除只在界面二次确认后才调用。
"""

import os
import shutil
import datetime

import config


class FileItem:
    """一个文件的描述信息，供文件列表展示、排序、批量操作用。"""

    def __init__(self, path):
        self.path = path                               # 文件完整路径
        self.name = os.path.basename(path)             # 文件名（含后缀）
        self.ext = config.get_extension(self.name)     # 后缀，如 'jpg'
        self.category = config.get_category(self.name)  # 分类，如 '图片'
        self.size = 0                                  # 大小（字节）
        self.mtime = 0                                 # 修改时间（时间戳）
        self._load_stat()                              # 读取大小和时间

    def _load_stat(self):
        """读取文件大小和修改时间；读不到就保持 0，不报错、不中断。"""
        try:
            st = os.stat(self.path)      # 获取文件信息
            self.size = st.st_size       # 大小（字节）
            self.mtime = st.st_mtime     # 修改时间戳
        except OSError:
            pass                         # 文件可能被占用/删除，忽略即可


class MovePlan:
    """一条整理方案：某个文件要从 src 移到 dst，属于 category 类。"""

    def __init__(self, src, dst, category):
        self.src = src              # 源文件完整路径
        self.dst = dst              # 目标完整路径
        self.category = category    # 分类名（用于界面展示）


# ---------- 格式化函数 ----------
def format_size(num_bytes):
    """把字节数转成可读大小，如 1536 -> '1.5 KB'。"""
    if num_bytes < 1024:
        return "%d B" % num_bytes            # 小于 1KB 直接显示字节
    for unit in ["KB", "MB", "GB", "TB"]:
        num_bytes /= 1024.0                  # 逐级除以 1024
        if num_bytes < 1024:
            return "%.1f %s" % (num_bytes, unit)  # 保留 1 位小数
    return "%.1f PB" % num_bytes             # 兜底（几乎不可能）


def format_time(timestamp):
    """把时间戳转成 '2026-09-06 20:30' 这种可读格式。"""
    if not timestamp:
        return "-"
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


# ---------- 扫描 ----------
def scan_directory(directory):
    """扫描目录，返回该目录下所有「文件」（不含子文件夹）的 FileItem 列表，按名称排序。"""
    items = []
    try:
        names = os.listdir(directory)        # 列出目录里的所有条目
    except OSError:
        return items                         # 目录打不开（权限/不存在）就返回空列表
    for name in names:
        full = os.path.join(directory, name)  # 拼出完整路径
        if os.path.isdir(full):
            continue                         # 跳过子文件夹（文件夹在左侧目录树里展示）
        items.append(FileItem(full))
    items.sort(key=lambda x: x.name.lower())  # 按文件名排序（忽略大小写）
    return items


def list_subdirectories(directory):
    """列出某目录下的所有子文件夹完整路径（给左侧目录树用），按名称排序。"""
    result = []
    try:
        for name in os.listdir(directory):
            full = os.path.join(directory, name)
            if os.path.isdir(full):          # 只保留文件夹
                result.append(full)
    except OSError:
        pass                                 # 打不开就返回空
    result.sort(key=lambda x: os.path.basename(x).lower())
    return result


# ---------- 整理方案（先规划、后执行）----------
def build_organize_plan(files, target_dir):
    """
    生成整理方案：根据每个文件的分类，算出它应该移到 target_dir 下的哪个分类文件夹。
    注意：这里只「计算」、不「移动」，返回 MovePlan 列表。
    """
    plans = []
    for f in files:
        folder_name = config.CATEGORY_FOLDER.get(f.category, "其他")  # 分类对应的文件夹名
        dst_dir = os.path.join(target_dir, folder_name)               # 目标分类文件夹
        dst_path = os.path.join(dst_dir, f.name)                      # 目标文件完整路径
        # 如果文件本来就在目标位置（比如重复整理），跳过它，避免原地移动
        if os.path.normpath(f.path) == os.path.normpath(dst_path):
            continue
        plans.append(MovePlan(f.path, dst_path, f.category))
    return plans


def execute_plans(plans):
    """
    真正执行移动：新建分类文件夹，把文件移过去。
    返回一个「撤销记录」字典，供 undo_last() 撤销用。
    安全性：目标重名时自动加序号，绝不覆盖已有文件。
    """
    moved = []           # 记录移动成功的 (源路径, 目标路径)
    created_dirs = []    # 记录本次新建的文件夹（撤销时要删掉它们）
    for plan in plans:
        dst_dir = os.path.dirname(plan.dst)       # 目标所在的文件夹
        if not os.path.exists(dst_dir):           # 文件夹不存在就新建
            os.makedirs(dst_dir, exist_ok=True)
            created_dirs.append(dst_dir)          # 记下来，撤销时删
        actual_dst = plan.dst
        if os.path.exists(actual_dst):            # 目标重名，加序号避免覆盖
            actual_dst = _unique_path(plan.dst)
        try:
            shutil.move(plan.src, actual_dst)     # 执行移动
            moved.append((plan.src, actual_dst))
        except OSError:
            continue                              # 单个失败不影响整体
    return {"moved": moved, "created_dirs": created_dirs}


def _unique_path(path):
    """给路径加 ' (1)'、' (2)' 后缀，直到它不跟现有文件冲突，避免覆盖。"""
    base, ext = os.path.splitext(path)     # 拆出主名和后缀
    i = 1
    while os.path.exists("%s (%d)%s" % (base, i, ext)):
        i += 1                             # 一直试到不重名
    return "%s (%d)%s" % (base, i, ext)


def undo_last(undo_record):
    """
    撤销上一次整理：把移动过的文件移回原位，并删掉本次新建的空文件夹。
    undo_record 是 execute_plans() 返回的字典。
    """
    if not undo_record:
        return 0
    count = 0
    # 第一步：把文件移回原位（反向执行）
    for src, dst in undo_record.get("moved", []):
        try:
            shutil.move(dst, src)      # 移回原位
            count += 1
        except OSError:
            continue
    # 第二步：删除新建的文件夹（rmdir 只能删空文件夹，安全）
    for d in undo_record.get("created_dirs", []):
        try:
            os.rmdir(d)
        except OSError:
            continue                   # 文件夹非空就留着，不硬删
    return count


# ---------- 手动批量操作 ----------
def move_files_to(files, target_dir):
    """把一批文件移动到指定文件夹（手动「移动到…」功能用）。返回移动成功的列表。"""
    if not os.path.exists(target_dir):           # 目标文件夹不存在就新建
        os.makedirs(target_dir, exist_ok=True)
    moved = []
    for f in files:
        dst = os.path.join(target_dir, f.name)   # 目标路径
        if os.path.normpath(f.path) == os.path.normpath(dst):
            continue                             # 原地移动，跳过
        if os.path.exists(dst):                  # 重名就加序号
            dst = _unique_path(dst)
        try:
            shutil.move(f.path, dst)
            moved.append((f.path, dst))
        except OSError:
            continue
    return moved


def rename_files(files, prefix, start_number=1):
    """
    批量重命名：加前缀 + 序号，保留原后缀。
    如前缀='照片'、起始=1：'a.jpg' -> '照片_001.jpg'，'b.png' -> '照片_002.png'。
    这里只计算新名字，返回 (旧路径, 新路径) 列表，真正改名用 execute_renames()。
    """
    records = []
    for i, f in enumerate(files):
        number = start_number + i                         # 序号
        base = "%s_%03d" % (prefix, number)              # 前缀 + 三位序号
        new_name = base + ("." + f.ext if f.ext else "")  # 拼回后缀
        new_path = os.path.join(os.path.dirname(f.path), new_name)  # 新完整路径
        if os.path.normpath(f.path) == os.path.normpath(new_path):
            continue                                     # 名字没变，跳过
        if os.path.exists(new_path):                     # 重名就加序号
            new_path = _unique_path(new_path)
        records.append((f.path, new_path))
    return records


def execute_renames(records):
    """执行批量重命名，返回重命名成功的列表。"""
    done = []
    for src, dst in records:
        try:
            os.rename(src, dst)     # 同一盘改名/移动
            done.append((src, dst))
        except OSError:
            continue
    return done


def delete_files(files):
    """
    永久删除一批文件（不进回收站！）。
    调用前必须由界面弹出二次确认框。返回删除成功的数量。
    """
    count = 0
    for f in files:
        try:
            os.remove(f.path)       # 删除文件
            count += 1
        except OSError:
            continue                # 删除失败就跳过，不中断
    return count
