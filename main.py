# -*- coding: utf-8 -*-
"""
main.py —— 程序入口

直接运行本文件即可启动「文件整理工具」：
    python main.py
"""

from app import MainWindow


def main():
    """创建主窗口并进入消息循环。"""
    win = MainWindow()   # 创建主窗口（内部会读取桌面文件、搭好三栏界面）
    win.run()            # 进入图形界面主循环，直到用户关闭窗口


if __name__ == "__main__":
    main()
