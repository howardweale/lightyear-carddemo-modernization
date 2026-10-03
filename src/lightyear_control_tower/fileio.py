"""Regular-file reads that reject special files and allow delete sharing.

Windows MoveFileEx still refuses to replace an open destination. Delete sharing
alone does not make these reads safe against a live Python atomic writer; the
campaign adapter refuses live Windows sources before opening any evidence.
"""

import os
import stat
from contextlib import contextmanager


@contextmanager
def regular_reader(path):
    if os.name == "nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes

        api = ctypes.WinDLL("kernel32", use_last_error=True)
        create = api.CreateFileW
        create.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        create.restype = wintypes.HANDLE
        # READ | WRITE | DELETE sharing; OPEN_REPARSE_POINT refuses following links.
        handle = create(str(path), 0x80000000, 7, None, 3, 0x00200000, None)
        if handle == wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        except BaseException:
            close = api.CloseHandle
            close.argtypes = [wintypes.HANDLE]
            close(handle)
            raise
    else:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & 0x400
        ):
            raise ValueError("Only regular, non-reparse evidence files are allowed")
        with os.fdopen(fd, "rb") as stream:
            fd = None
            yield stream
    finally:
        if fd is not None:
            os.close(fd)
