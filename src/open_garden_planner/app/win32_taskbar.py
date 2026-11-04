"""Native Windows taskbar icon and property configuration (Win32 / DWM / Shell)."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget


def setup_windows_taskbar_icon(window: QWidget) -> None:
    """Configure native Win32 window properties and taskbar icon for Windows 10/11.

    Windows 10 and 11 taskbars decouple window icons from process grouping.
    To ensure the application icon displays reliably on the taskbar:
    1. Sets both WM_SETICON (BIG and SMALL) window messages.
    2. Updates the window class icons (GCLP_HICON and GCLP_HICONSM) so Windows Explorer
       does not fall back to IDI_APPLICATION (0x1002b generic blank window icon).
    3. Stamps System.AppUserModel.RelaunchIconResource and System.AppUserModel.ID
       onto the window's COM IPropertyStore via SHGetPropertyStoreForWindow.
    """
    if sys.platform != "win32":
        return

    try:
        raw_id = window.winId()
        if raw_id is None:
            return
        hwnd = int(raw_id)
        if not hwnd:
            return

        import ctypes
        from ctypes import wintypes
        from pathlib import Path

        icons_dir = Path(__file__).resolve().parent.parent / "resources" / "icons"
        ico_path = icons_dir / "ogp_app.ico"
        if not ico_path.is_file():
            return

        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32

        image_icon = 1
        lr_loadfromfile = 0x0010
        lr_defaultsize = 0x0040
        wm_seticon = 0x007F
        icon_small = 0
        icon_big = 1
        gclp_hicon = -14
        gclp_hiconsm = -34

        set_class_long_ptr = (
            user32.SetClassLongPtrW
            if hasattr(user32, "SetClassLongPtrW")
            else user32.SetClassLongW
        )

        # 1. Load native Win32 icons from multi-resolution .ico
        h_big = user32.LoadImageW(
            None, str(ico_path), image_icon, 0, 0, lr_loadfromfile | lr_defaultsize
        )
        h_small = user32.LoadImageW(
            None, str(ico_path), image_icon, 16, 16, lr_loadfromfile
        )

        if h_big:
            user32.SendMessageW(hwnd, wm_seticon, icon_big, h_big)
            set_class_long_ptr(hwnd, gclp_hicon, h_big)
        if h_small:
            user32.SendMessageW(hwnd, wm_seticon, icon_small, h_small)
            set_class_long_ptr(hwnd, gclp_hiconsm, h_small)

        # 2. Window property store: System.AppUserModel.RelaunchIconResource & ID
        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_byte * 8),
            ]

        class PROPERTYKEY(ctypes.Structure):
            _fields_ = [
                ("fmtid", GUID),
                ("pid", wintypes.DWORD),
            ]

        class PROPVARIANT(ctypes.Structure):
            _fields_ = [
                ("vt", ctypes.c_ushort),
                ("wReserved1", wintypes.WORD),
                ("wReserved2", wintypes.WORD),
                ("wReserved3", wintypes.WORD),
                ("pwszVal", wintypes.LPWSTR),
                ("dummy", ctypes.c_byte * 8),
            ]

        iid_ipropertystore = GUID(
            0x886D8EEB,
            0x8CF2,
            0x4446,
            (ctypes.c_byte * 8)(
                0x8D, 0x02, 0xCD, 0xBA, 0x1D, 0xBD, 0xCF, 0x99
            ),
        )
        p_prop_store = ctypes.c_void_p()
        hr = shell32.SHGetPropertyStoreForWindow(
            hwnd, ctypes.byref(iid_ipropertystore), ctypes.byref(p_prop_store)
        )
        if hr == 0 and p_prop_store.value:
            vtable = ctypes.cast(
                p_prop_store.value, ctypes.POINTER(ctypes.c_void_p)
            )[0]
            vtable_methods = ctypes.cast(
                vtable, ctypes.POINTER(ctypes.c_void_p)
            )

            set_value_func_type = ctypes.WINFUNCTYPE(
                ctypes.c_long,
                ctypes.c_void_p,
                ctypes.POINTER(PROPERTYKEY),
                ctypes.POINTER(PROPVARIANT),
            )
            commit_func_type = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)
            release_func_type = ctypes.WINFUNCTYPE(
                ctypes.c_ulong, ctypes.c_void_p
            )

            set_value = set_value_func_type(vtable_methods[6])
            commit = commit_func_type(vtable_methods[7])
            release = release_func_type(vtable_methods[2])

            guid_appuser = GUID(
                0x9F4C2855,
                0x9F79,
                0x4B39,
                (ctypes.c_byte * 8)(
                    0xA8, 0xD0, 0xE1, 0xD4, 0x2D, 0xE1, 0xD5, 0xF3
                ),
            )
            pkey_icon = PROPERTYKEY(guid_appuser, 3)
            pkey_id = PROPERTYKEY(guid_appuser, 5)

            pv_icon = PROPVARIANT()
            pv_icon.vt = 31  # VT_LPWSTR
            pv_icon.pwszVal = f"{ico_path},0"
            set_value(
                p_prop_store.value,
                ctypes.byref(pkey_icon),
                ctypes.byref(pv_icon),
            )

            from open_garden_planner.main import WINDOWS_APP_ID

            pv_id = PROPVARIANT()
            pv_id.vt = 31  # VT_LPWSTR
            pv_id.pwszVal = WINDOWS_APP_ID
            set_value(
                p_prop_store.value, ctypes.byref(pkey_id), ctypes.byref(pv_id)
            )

            commit(p_prop_store.value)
            release(p_prop_store.value)
    except Exception:
        pass
