"""Windows native shell integration. Requires Windows 10 or 11."""
from __future__ import annotations

import ctypes
import os
import string
import uuid
from pathlib import Path


def fixed_drives() -> list[Path]:
    if os.name != "nt":
        raise OSError("A interface de discos locais requer Windows.")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetLogicalDrives.restype = ctypes.c_uint32
    kernel.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
    mask = kernel.GetLogicalDrives()
    return [Path(f"{letter}:\\") for index, letter in enumerate(string.ascii_uppercase)
            if mask & (1 << index) and kernel.GetDriveTypeW(f"{letter}:\\") == 3]


def recycle_directory(path: Path) -> None:
    """Use IFileOperation with RECYCLEONDELETE, never a permanent-delete fallback."""
    if os.name != "nt" or tuple(__import__("sys").getwindowsversion()[:2]) < (10, 0):
        raise OSError("Envio à Lixeira disponível somente no Windows 10/11.")
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("data", ctypes.c_ubyte * 16)]

        @classmethod
        def parse(cls, value: str) -> "GUID":
            return cls((ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le))

    hresult = ctypes.c_long
    ole = ctypes.OleDLL("ole32")
    shell = ctypes.OleDLL("shell32")
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole.CoInitializeEx.restype = hresult
    ole.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD,
                                   ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    ole.CoCreateInstance.restype = hresult
    shell.SHCreateItemFromParsingName.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p,
                                                 ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    shell.SHCreateItemFromParsingName.restype = hresult

    def check(value: int) -> None:
        if value < 0:
            raise OSError(f"Falha na operação do Windows (HRESULT 0x{value & 0xffffffff:08X}).")

    def invoke(pointer: ctypes.c_void_p, index: int, args: list, *values):
        table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        method = ctypes.WINFUNCTYPE(hresult, ctypes.c_void_p, *args)(table[index])
        return method(pointer, *values)

    initialized = ole.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED
    check(initialized)
    operation, item = ctypes.c_void_p(), ctypes.c_void_p()
    try:
        clsid = GUID.parse("3ad05575-8857-4850-9277-11b85bdb8e09")
        interface = GUID.parse("947aab5f-0a5c-4c13-b4d6-4bf7836fc9f8")
        shell_item = GUID.parse("43826d1e-e718-42ee-bc55-a1e261c37bfe")
        check(ole.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(interface), ctypes.byref(operation)))
        # Recycle + undo record + stop on errors. Keep the shell's destruction warning.
        flags = 0x00080000 | 0x20000000 | 0x00100000 | 0x0400 | 0x4000 | 0x0004
        check(invoke(operation, 5, [wintypes.DWORD], flags))
        check(shell.SHCreateItemFromParsingName(str(path), None, ctypes.byref(shell_item), ctypes.byref(item)))
        check(invoke(operation, 18, [ctypes.c_void_p, ctypes.c_void_p], item, None))
        check(invoke(operation, 21, []))
        aborted = wintypes.BOOL()
        check(invoke(operation, 22, [ctypes.POINTER(wintypes.BOOL)], ctypes.byref(aborted)))
        if aborted.value:
            raise OSError("O envio à Lixeira foi cancelado pelo Windows.")
    finally:
        if item:
            invoke(item, 2, [])
        if operation:
            invoke(operation, 2, [])
        ole.CoUninitialize()
