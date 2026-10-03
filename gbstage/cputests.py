"""Run Blargg's test ROMs (cpu_instrs, instr_timing, ...) against the profiler's CPU.

The ROMs aren't bundled. Get them from https://github.com/retrio/gb-test-roms and point
`python3 -m gbstage test --cpu-roms DIR` at a folder of .gb files. Each test reports over the
serial port, ending in "Passed" or "Failed".
"""

import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from .machine import Machine
from .sm83 import Unsupported

TIME_LIMIT = 300


def run_one(path):
    m = Machine(Path(path).read_bytes(), cgb=False)
    start = time.time()
    try:
        while time.time() - start < TIME_LIMIT:
            for _ in range(20000):
                m.step()
            out = "".join(m.serial)
            if "Passed" in out or "Failed" in out:
                break
        else:
            out = "".join(m.serial) + " [timed out]"
    except Unsupported as e:
        out = "".join(m.serial) + f" [unsupported: {e}]"
    text = " ".join(out.split())
    return Path(path).name, "Passed" in text and "Failed" not in text, text


def run(directory, log=print):
    roms = sorted(str(p) for p in Path(directory).glob("*.gb"))
    if not roms:
        log(f"No .gb files in {directory}")
        return False
    log(f"CPU tests: {len(roms)} ROM(s) from {directory}\n")
    passed = 0
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as pool:
        for name, ok, text in pool.map(run_one, roms):
            passed += ok
            log(f"  {'✓' if ok else '✗'} {name:30} {'' if ok else text[-200:]}")
    log(f"\n{passed}/{len(roms)} CPU test ROM(s) passed.")
    return passed == len(roms)
