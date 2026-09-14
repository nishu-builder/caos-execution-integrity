"""Narrow Linux x86_64 network-socket filter for the lab proxy, installed before exec.

This is not a general sandbox. Docker supplies the outer containment; UID separation
protects the dispatcher. The proxy starts with no inherited network descriptors.
"""
import ctypes
import errno
import platform

def no_network_sockets():
    if platform.machine() != "x86_64":
        raise RuntimeError("The lab syscall filter currently supports Linux x86_64 only")
    class Filter(ctypes.Structure):
        _fields_ = [("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte),
                    ("jf", ctypes.c_ubyte), ("k", ctypes.c_uint)]
    class Program(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ushort), ("filters", ctypes.POINTER(Filter))]
    allow, deny, kill = 0x7fff0000, 0x50000 | errno.EPERM, 0x80000000
    # seccomp_data: nr @0, arch @4, args[0] @16. Reject compatibility ABIs.
    rules = [
        (0x20, 0, 0, 4), (0x15, 1, 0, 0xc000003e), (0x06, 0, 0, kill),
        (0x20, 0, 0, 0), (0x35, 0, 1, 0x40000000), (0x06, 0, 0, kill),
        (0x15, 0, 4, 41),  # socket: only AF_UNIX may be created
        (0x20, 0, 0, 16), (0x15, 1, 0, 1), (0x06, 0, 0, deny),
        (0x06, 0, 0, allow),
        # Disallow io_uring, which offers a separate socket-creation path.
        (0x15, 2, 0, 425), (0x15, 1, 0, 426), (0x15, 0, 1, 427),
        (0x06, 0, 0, deny), (0x06, 0, 0, allow),
    ]
    array = (Filter * len(rules))(*(Filter(*r) for r in rules))
    program = Program(len(rules), array)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) or libc.prctl(22, 2, ctypes.byref(program), 0, 0):
        raise OSError(ctypes.get_errno(), "installing seccomp filter")
