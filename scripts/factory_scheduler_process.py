from __future__ import annotations

import ctypes
import hashlib
import os
import sys
from functools import cache
from pathlib import Path
from typing import Protocol, cast

from scripts.factory_scheduler_models import LeaseOwner

PROC_PIDTBSDINFO = 3
LINUX_BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
LINUX_STAT_MAX_BYTES = 4_096
LINUX_BOOT_ID_MAX_BYTES = 65
READ_CHUNK_BYTES = 4_096


class _ProcBsdInfo(ctypes.Structure):
    _fields_ = [
        ("pbi_flags", ctypes.c_uint32),
        ("pbi_status", ctypes.c_uint32),
        ("pbi_xstatus", ctypes.c_uint32),
        ("pbi_pid", ctypes.c_uint32),
        ("pbi_ppid", ctypes.c_uint32),
        ("pbi_uid", ctypes.c_uint32),
        ("pbi_gid", ctypes.c_uint32),
        ("pbi_ruid", ctypes.c_uint32),
        ("pbi_rgid", ctypes.c_uint32),
        ("pbi_svuid", ctypes.c_uint32),
        ("pbi_svgid", ctypes.c_uint32),
        ("rfu_1", ctypes.c_uint32),
        ("pbi_comm", ctypes.c_char * 16),
        ("pbi_name", ctypes.c_char * 32),
        ("pbi_nfiles", ctypes.c_uint32),
        ("pbi_pgid", ctypes.c_uint32),
        ("pbi_pjobc", ctypes.c_uint32),
        ("e_tdev", ctypes.c_uint32),
        ("e_tpgid", ctypes.c_uint32),
        ("pbi_nice", ctypes.c_int32),
        ("pbi_start_tvsec", ctypes.c_uint64),
        ("pbi_start_tvusec", ctypes.c_uint64),
    ]


class _ProcPidInfo(Protocol):
    def __call__(
        self,
        pid: int,
        flavor: int,
        arg: int,
        buffer: object,
        buffer_size: int,
    ) -> int: ...


class ProcessIdentityError(RuntimeError):
    pass


def current_lease_owner(owner_id: str) -> LeaseOwner:
    pid = os.getpid()
    start_digest = process_start_token(pid)
    if start_digest is None:
        raise ProcessIdentityError("current process identity is unavailable")
    return LeaseOwner(owner_id=owner_id, pid=pid, process_start_token=start_digest)


def probe_owner(owner: LeaseOwner) -> bool | None:
    exists = _pid_exists(owner.pid)
    if exists is not True:
        return exists
    start_digest = process_start_token(owner.pid)
    if start_digest is None:
        return False if _pid_exists(owner.pid) is False else None
    return start_digest == owner.process_start_token


def process_start_token(pid: int) -> str | None:
    if isinstance(pid, bool) or not 1 <= pid <= 2_147_483_647:
        return None
    identity = _process_start_identity(pid)
    if identity is None:
        return None
    return _identity_digest(pid, identity)


def _process_start_identity(pid: int) -> str | None:
    if sys.platform == "darwin":
        return _macos_process_start_identity(pid)
    if sys.platform.startswith("linux"):
        return _linux_process_start_identity(pid)
    return None


def _macos_process_start_identity(pid: int) -> str | None:
    try:
        query = _macos_proc_pidinfo()
        info = _ProcBsdInfo()
        size = query(
            pid,
            PROC_PIDTBSDINFO,
            0,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
    except (OSError, TypeError, ValueError):
        return None
    if (
        size != ctypes.sizeof(info)
        or info.pbi_pid != pid
        or info.pbi_start_tvsec <= 0
        or info.pbi_start_tvusec >= 1_000_000
    ):
        return None
    return f"macos:{info.pbi_start_tvsec}:{info.pbi_start_tvusec}"


@cache
def _macos_proc_pidinfo() -> _ProcPidInfo:
    library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    query = library.proc_pidinfo
    query.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint64,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    query.restype = ctypes.c_int
    return cast(_ProcPidInfo, query)


def _linux_process_start_identity(pid: int) -> str | None:
    stat_text = _read_ascii_bounded(
        Path(f"/proc/{pid}/stat"),
        max_bytes=LINUX_STAT_MAX_BYTES,
    )
    boot_id_text = _read_ascii_bounded(
        LINUX_BOOT_ID,
        max_bytes=LINUX_BOOT_ID_MAX_BYTES,
    )
    if stat_text is None or boot_id_text is None:
        return None
    boot_id = boot_id_text.strip()
    closing_parenthesis = stat_text.rfind(")")
    if closing_parenthesis < 2 or not boot_id or len(boot_id) > 64:
        return None
    fields_after_name = stat_text[closing_parenthesis + 2 :].split()
    if len(fields_after_name) <= 19 or not fields_after_name[19].isdigit():
        return None
    return f"linux:{boot_id}:{fields_after_name[19]}"


def _read_ascii_bounded(path: Path, *, max_bytes: int) -> str | None:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
        )
        payload = bytearray()
        while len(payload) <= max_bytes:
            chunk = os.read(
                descriptor,
                min(READ_CHUNK_BYTES, max_bytes + 1 - len(payload)),
            )
            if not chunk:
                break
            payload.extend(chunk)
        if len(payload) > max_bytes:
            return None
        return bytes(payload).decode("ascii")
    except (OSError, UnicodeError):
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _identity_digest(pid: int, identity: str) -> str:
    digest = hashlib.sha256(f"{pid}:{identity}".encode()).hexdigest()
    return f"proc_{digest}"


def _pid_exists(pid: int) -> bool | None:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return None
    except OSError:
        return None
    return True
