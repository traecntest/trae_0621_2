import json
from tkinter import messagebox

from config import APP_TITLE, APP_VERSION, DATA_DIR, DISCLAIMER

_DISCLAIMER_FILE = DATA_DIR / ".disclaimer_accepted"


def is_accepted() -> bool:
    if _DISCLAIMER_FILE.exists():
        try:
            data = json.loads(_DISCLAIMER_FILE.read_text("utf-8"))
            return bool(data.get("accepted"))
        except Exception:
            return False
    return False


def _accept(version: str):
    _DISCLAIMER_FILE.write_text(
        json.dumps({"accepted": True, "version": version,
                    "text": DISCLAIMER}, ensure_ascii=False),
        encoding="utf-8",
    )


def show_disclaimer_if_first_run(parent=None) -> bool:
    """首次运行时展示免责声明。

    返回 ``True`` 表示用户已同意（含此前已同意的情况），
    返回 ``False`` 表示拒绝，调用方应退出程序。
    """
    if is_accepted():
        return True
    agree = messagebox.askyesno(
        f"{APP_TITLE} - 免责声明",
        DISCLAIMER + "\n\n是否同意以上声明并继续使用？",
        parent=parent,
        icon=messagebox.WARNING,
    )
    if agree:
        _accept(APP_VERSION)
        return True
    return False
