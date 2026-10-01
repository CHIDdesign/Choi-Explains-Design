"""Windows 전용 도우미: 관리자 권한 확인, 관리자 창에서도 탐색기 끌어다 놓기.

관리자 권한으로 실행된 창에는 윈도 보안(UIPI) 때문에 일반 탐색기의 OLE 드래그 앤 드롭이 들어오지 않는다.
대신 옛 방식(WM_DROPFILES)만 허용 목록에 올리고(ChangeWindowMessageFilterEx) 창이 파일을 받겠다고 알리면
(DragAcceptFiles) 탐색기에서 끌어다 놓은 파일 경로를 받을 수 있다. 다른 OS 에서는 아무것도 하지 않는다.
"""
from __future__ import annotations

import sys
from typing import Callable

WM_DROPFILES = 0x0233
WM_COPYDATA = 0x004A
WM_COPYGLOBALDATA = 0x0049
MSGFLT_ALLOW = 1


def is_admin() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def enable_elevated_drop(widget, on_files: Callable[[list[str]], None]) -> bool:
    """관리자 창(widget 의 최상위 창)에서 탐색기 파일 끌어다 놓기를 켠다. 성공하면 True."""
    if sys.platform != "win32" or not is_admin():
        return False
    try:
        import ctypes
        from ctypes import wintypes
        from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication

        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
        hwnd = int(widget.window().winId())
        for msg in (WM_DROPFILES, WM_COPYDATA, WM_COPYGLOBALDATA):
            user32.ChangeWindowMessageFilterEx(wintypes.HWND(hwnd), msg, MSGFLT_ALLOW, None)
        ole32.RevokeDragDrop(wintypes.HWND(hwnd))  # Qt 의 OLE 드롭 대상은 관리자 창에서 어차피 동작하지 않는다
        shell32.DragAcceptFiles(wintypes.HWND(hwnd), True)

        shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
        shell32.DragQueryFileW.restype = wintypes.UINT
        # 64비트 핸들 — argtypes 가 없으면 ctypes 가 32비트 long 으로 넘기다 4GB 위 주소에서 ArgumentError
        shell32.DragFinish.argtypes = [wintypes.HANDLE]
        shell32.DragFinish.restype = None

        class _Filter(QAbstractNativeEventFilter):
            def nativeEventFilter(self, event_type, message):  # noqa: N802
                if event_type not in (b"windows_generic_MSG", "windows_generic_MSG"):
                    return False, 0
                msg = wintypes.MSG.from_address(int(message))
                if msg.message != WM_DROPFILES:
                    return False, 0
                hdrop = msg.wParam
                paths = []
                try:
                    n = shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
                    for i in range(n):
                        size = shell32.DragQueryFileW(hdrop, i, None, 0) + 1
                        buf = ctypes.create_unicode_buffer(size)
                        shell32.DragQueryFileW(hdrop, i, buf, size)
                        paths.append(buf.value)
                finally:
                    try:
                        shell32.DragFinish(hdrop)
                    except Exception:  # noqa: BLE001 - 핸들 정리 실패로 받은 경로를 잃지 않게
                        pass
                if paths:
                    on_files(paths)
                return True, 0

        flt = _Filter()
        QCoreApplication.instance().installNativeEventFilter(flt)
        widget._elevated_drop_filter = flt  # 가비지 컬렉션 방지
        return True
    except Exception:  # noqa: BLE001 - 실패해도 '찾아보기'·붙여넣기로 쓸 수 있다
        return False
