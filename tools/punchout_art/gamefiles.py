"""Where Punch-Out!!'s banks come from: your own copy of the game, split by setup (demo.py --rom) into
tools/punchout_art/rom/original_files (PRG_Bank000-00C, PRG_BankDEF, CHR_Bank000-01F: the disassembly's
layout). PUNCHOUT_FILES can point somewhere else; the disassembly checkout works too."""
import hashlib, os, pathlib

HERE = pathlib.Path(__file__).parent
SHA1 = "b6f6bd9d78cdd264a117d4b647aee3309993e9a9"        # Mike Tyson's Punch-Out!! (USA): PRG + CHR, no header


DISASM = "mike-tysons-punch-out-disassembly"
NEED = ("Joe vs Mac needs the Punch-Out!! game: put a Mike Tyson's Punch-Out!! (USA) .nes file in this folder, or "
        f"the {DISASM} folder in ~/code, Downloads or Desktop.")


def places():
    """Where the game might be: here, or the disassembly checkout (cloned or unzipped: name-main) anywhere usual."""
    home = pathlib.Path.home()
    yield os.environ.get("PUNCHOUT_FILES")
    yield HERE / "disassembly"
    yield HERE / "rom"
    for base in (home / "code", HERE.parents[2], HERE.parents[1], home / "Downloads", home / "Desktop", home):
        if base.is_dir():
            yield from sorted(base.glob(DISASM + "*"))


def root():
    """The folder holding original_files/ (what cpu6502.Nes and the tools take)."""
    for d in places():
        if d and (pathlib.Path(d) / "original_files" / "PRG_BankDEF.bin").exists():
            return pathlib.Path(d)
    raise SystemExit(NEED)


def have():
    try:
        root()
        return True
    except SystemExit:
        return False


def banks():
    return root() / "original_files"


def split_rom(path):
    """Your .nes file -> rom/original_files, after checking it's the game the port matches."""
    data = pathlib.Path(path).read_bytes()
    if data[:4] != b"NES\x1a":
        raise SystemExit(f"{path} isn't an iNES (.nes) file.")
    body = data[16:16 + 0x40000]
    if len(body) != 0x40000 or hashlib.sha1(body).hexdigest() != SHA1:
        raise SystemExit(f"{path} isn't Mike Tyson's Punch-Out!! (USA), the version this demo is built on "
                         f"(SHA-1 of its data should be {SHA1}).")
    out = HERE / "rom" / "original_files"
    out.mkdir(parents=True, exist_ok=True)
    (out / "Header.bin").write_bytes(data[:16])
    prg, chr_ = body[:0x20000], body[0x20000:]
    for k in range(13):
        (out / f"PRG_Bank{k:03X}.bin").write_bytes(prg[k * 0x2000:(k + 1) * 0x2000])
    (out / "PRG_BankDEF.bin").write_bytes(prg[13 * 0x2000:])
    for k in range(32):
        (out / f"CHR_Bank{k:03X}.bin").write_bytes(chr_[k * 0x1000:(k + 1) * 0x1000])
    return out
