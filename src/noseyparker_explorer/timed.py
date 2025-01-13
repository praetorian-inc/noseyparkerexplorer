from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter

@contextmanager
def timed(msg: str):
    """
    A context manager that prints `msg` with a seconds-based timestamp to 6
    decimal points upon exit.
    """
    t1 = perf_counter()
    try:
        yield
    except:
        t2 = perf_counter()
        print(f"{msg} in {t2 - t1:.6f}s")
        raise
    else:
        t2 = perf_counter()
        print(f"{msg} in {t2 - t1:.6f}s")
