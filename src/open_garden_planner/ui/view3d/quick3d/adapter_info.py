"""Graphics adapter inspection and software rasterizer detection (#535).

On Windows, inspects DXGI adapters via DXGIFactory1 to detect software rasterizers
(Microsoft Basic Render Driver, WARP) so the 3D workspace automatically applies
compatibility look without freezing for 12+ seconds on sky light probes or wasting
1,300% CPU on continuous wind animation. On other platforms or when configured
via environment variables (QSG_RHI_PREFER_SOFTWARE_RENDERER=1 or LIBGL_ALWAYS_SOFTWARE=1),
software mode is activated accordingly.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Final

_log = logging.getLogger(__name__)

SOFTWARE_ADAPTER_KEYWORDS: Final[tuple[str, ...]] = (
    "microsoft basic render driver",
    "llvmpipe",
    "software rasterizer",
    "warp",
)

# DXGI_ADAPTER_FLAG_SOFTWARE = 2 (bit 1)
DXGI_ADAPTER_FLAG_SOFTWARE: Final[int] = 2

if sys.platform == "win32":
    import ctypes

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong),
            ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    class DXGI_ADAPTER_DESC1(ctypes.Structure):
        _fields_ = [
            ("Description", ctypes.c_wchar * 128),
            ("VendorId", ctypes.c_uint),
            ("DeviceId", ctypes.c_uint),
            ("SubSysId", ctypes.c_uint),
            ("Revision", ctypes.c_uint),
            ("DedicatedVideoMemory", ctypes.c_size_t),
            ("DedicatedSystemMemory", ctypes.c_size_t),
            ("SharedSystemMemory", ctypes.c_size_t),
            ("AdapterLuid_Low", ctypes.c_uint),
            ("AdapterLuid_High", ctypes.c_int),
            ("Flags", ctypes.c_uint),
        ]

    IID_IDXGI_FACTORY1 = GUID(
        0x770AAE78,
        0xF26F,
        0x4DBA,
        (ctypes.c_ubyte * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87),
    )

    IUnknown_Release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
    IDXGIFactory1_EnumAdapters1 = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)
    )
    IDXGIAdapter1_GetDesc1 = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(DXGI_ADAPTER_DESC1)
    )


def _safe_release_com(ptr: Any, vtable_index: int = 2) -> None:
    """Safely call IUnknown::Release on a COM interface pointer if valid."""
    if sys.platform != "win32":
        return
    import ctypes

    if not isinstance(ptr, ctypes.c_void_p) or not ptr.value:
        return
    try:
        vtable = ctypes.cast(
            ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p)).contents,
            ctypes.POINTER(ctypes.c_void_p),
        )
        release_fn = IUnknown_Release(vtable[vtable_index])
        release_fn(ptr)
    except Exception:
        pass


def is_software_adapter_name(name: str | None) -> bool:
    """Return True if the graphics adapter description indicates software rendering."""
    if not name:
        return False
    lower = name.lower()
    return any(keyword in lower for keyword in SOFTWARE_ADAPTER_KEYWORDS)


def _is_hardware_adapter(desc: str, flags: int) -> bool:
    """Return True if an adapter description and flags represent a hardware GPU.

    Checks that DXGI_ADAPTER_FLAG_SOFTWARE (bit 1, value 2) is not set and the
    description does not match known software rasterizers. Does not require
    dedicated VRAM > 0 so integrated GPUs (Intel UHD/Iris, AMD APUs) that use
    shared system memory are recognized as hardware.
    """
    return (flags & DXGI_ADAPTER_FLAG_SOFTWARE) == 0 and not is_software_adapter_name(desc)


def _enum_adapters_dxgi() -> list[tuple[str, int]] | None:
    """Enumerate (description, flags) for all DXGI adapters on Windows.

    Returns None if DXGI factory creation fails or an unrecoverable exception occurs.
    """
    if sys.platform != "win32":
        return None

    import ctypes

    factory = ctypes.c_void_p()
    try:
        hr = ctypes.windll.dxgi.CreateDXGIFactory1(ctypes.byref(IID_IDXGI_FACTORY1), ctypes.byref(factory))
        if hr != 0:
            _log.debug("DXGIFactory1 creation failed (hr=0x%08x); fallback to hardware", hr)
            return None

        fvtable = ctypes.cast(
            ctypes.cast(factory, ctypes.POINTER(ctypes.c_void_p)).contents,
            ctypes.POINTER(ctypes.c_void_p),
        )
        enum_adapters1 = IDXGIFactory1_EnumAdapters1(fvtable[12])

        adapters: list[tuple[str, int]] = []
        i = 0
        while True:
            adapter = ctypes.c_void_p()
            if enum_adapters1(factory, i, ctypes.byref(adapter)) != 0:
                break
            try:
                avtable = ctypes.cast(
                    ctypes.cast(adapter, ctypes.POINTER(ctypes.c_void_p)).contents,
                    ctypes.POINTER(ctypes.c_void_p),
                )
                get_desc1 = IDXGIAdapter1_GetDesc1(avtable[10])
                desc = DXGI_ADAPTER_DESC1()
                get_desc1(adapter, ctypes.byref(desc))
                adapters.append((desc.Description, desc.Flags))
            finally:
                _safe_release_com(adapter)
            i += 1

        return adapters
    except Exception as exc:
        _log.debug("DXGI adapter enumeration failed: %s; fallback to hardware", exc)
        return None
    finally:
        _safe_release_com(factory)


def has_hardware_adapter() -> bool:
    """Check whether the host has at least one hardware GPU adapter.

    On Windows, inspects DXGI adapters via DXGIFactory1. Returns False if all
    adapters are software devices (DXGI_ADAPTER_FLAG_SOFTWARE = 2) or match
    known software rasterizer names.
    On non-Windows platforms, returns True (hardware rasterizer assumed unless
    software rendering is requested via environment variable).
    """
    if os.environ.get("QSG_RHI_PREFER_SOFTWARE_RENDERER") == "1" or os.environ.get("LIBGL_ALWAYS_SOFTWARE") == "1":
        return False

    if sys.platform != "win32":
        return True

    adapters = _enum_adapters_dxgi()
    if adapters is None:
        # Fallback to assuming hardware is available if DXGI query fails
        return True

    if not adapters:
        return False

    return any(_is_hardware_adapter(desc, flags) for desc, flags in adapters)


def detect_is_software() -> bool:
    """True when the current execution must use software compatibility mode."""
    if os.environ.get("QSG_RHI_PREFER_SOFTWARE_RENDERER") == "1" or os.environ.get("LIBGL_ALWAYS_SOFTWARE") == "1":
        return True
    return not has_hardware_adapter()
