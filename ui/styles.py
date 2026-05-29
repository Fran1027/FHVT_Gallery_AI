MAIN_STYLE = """
    QMainWindow, QTabWidget::pane { background-color: #0a0a0a; border: none; }
    QLabel { color: #cccccc; }
    QPushButton { background-color: transparent; color: #cccccc; border: 1px solid #ffffff; border-radius: 6px; padding: 0; }
    QPushButton#btn_sort, QPushButton#btn_group { padding: 0 15px; }
    QPushButton:hover { background-color: #333333; color: #ffffff; }
    QPushButton:pressed { background-color: #007acc; border: 1px solid #007acc; color: #ffffff; }
    QPushButton:disabled { color: #555555; background-color: transparent; border: 1px solid #333333; }
    QLineEdit { background-color: #252526; color: #cccccc; border: 1px solid #3e3e42; padding: 6px 16px; border-radius: 14px; font-size: 13px; }
    QLineEdit:focus { border: 1px solid #007acc; }
    QScrollArea { border: none; background-color: #1e1e1e; }
    QSplitter::handle { background-color: #1e1e1e; }
    QTabBar::tab { background-color: #252526; color: #999999; padding: 10px 20px; border: none; border-right: 1px solid #1e1e1e; }
    QTabBar::tab:selected { background-color: #1e1e1e; color: #ffffff; border-top: 2px solid #007acc; }
    QTabBar::tab:hover:!selected { background-color: #333333; }
    QStatusBar { background-color: #1a1a1a; color: #888; border-top: 1px solid #333; min-height: 25px; }
    QStatusBar::item { border: none; }
"""

CONTEXT_MENU_STYLE = "QMenu { background-color: #1a1a1a; border: 1px solid #333; color: #ccc; } QMenu::item:selected { background-color: #007acc; color: white; } QMenu::item:disabled { color: #555; }"
