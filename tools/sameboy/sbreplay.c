// Replay recorded button presses in SameBoy, keyed to the game's own frame counter (hFrame), and dump frames; and
// flag what real hardware does differently from a forgiving emulator (tools/sameboy/check.py runs it in CI).
// sbreplay MODEL(cgb|dmg) BOOT ROM INPUTS OUTDIR hFrameAddr LoadSceneAddr target framesToRun dumpEvery [addr...]
// INPUTS: binary, byte n = button mask for game frame n (bit0 right,1 left,2 up,3 down,4 A,5 B,6 select,7 start);
// "-" for none. Past its end a seeded masher plays (the same buttons every run).
// LoadSceneAddr: LoadScene's address; a LoadScene with A = 2 (the first fight) loads scene `target` instead.
// OUTDIR/hardware.txt: each write the hardware drops (VRAM in mode 3, OAM in modes 2-3, CGB palettes in mode 3 --
// with the LCD on), each GDMA over a line's drawing (mode 3 somewhere from its start to its end), each fight VBlank
// without its frame's work or with two (SB_DONE: VBlankDone's address, bank 0, run once a frame; SB_ACTIVE:
// hFtActive's, 1 in a fight -- a VBlank's from line 144 to the next line 144, the LCD on and the fight on through
// it), and a closing SUMMARY line. SB_STRICT=1: exit status 2 when any of them was seen. Boot ROMs: SameBoy's own (its BootROMs/, built from source), never Nintendo's.
// Writes OUTDIR/frame_XXXXXX.rgb (160x144 RGB) every dumpEvery video frames from game start, and OUTDIR/ram.txt
// (per video frame: game frame, then the bytes at the addrs given).
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <Core/gb.h>
#include <Core/random.h>

static uint32_t pixels[160 * 144];
static int started = 0, scene_target = 0;
static uint16_t load_scene = 0;
static uint32_t rgb(GB_gameboy_t *gb, uint8_t r, uint8_t g, uint8_t b) { return (r << 16) | (g << 8) | b; }
static long vframe = -1; static FILE *apu; static uint64_t apu_hash = 1469598103934665603ULL; static uint32_t *prof; static long probe = -1; static long probe_ly[160]; static int in_fight = 0; static FILE *bad; static long nbad = 0, ngdma = 0, novr = 0;
static FILE *wav, *snd; static uint16_t snd_addr, snd_wnes, snd_wapu; static int snd_bank;
static long nsamples = 0;
static void sample_cb(GB_gameboy_t *gb, GB_sample_t *x) { nsamples++; int16_t m = (x->left + x->right) / 2; fwrite(&m, 2, 1, wav); }
static int gdma_pending = 0, gdma_ly = 0, gdma_mode = 0, gdma_len = 0, gdma_bank = 0; static uint16_t gdma_pc = 0;
static long done_addr = -1, active_addr = -1, nlost = 0, ntwice = 0; static int win_done = 0, win_valid = 0, armed = 0, last_ly = -1;
static void report(GB_gameboy_t *gb, const char *what, uint16_t addr) {
    nbad++;
    uint16_t sp = gb->sp, ret = GB_safe_read_memory(gb, sp) | (GB_safe_read_memory(gb, sp + 1) << 8);  // (the stack's top: a caller, often)
    fprintf(bad, "frame %ld LY %d STAT %d PC %04X bank %d %s %04X (stack top %04X)\n", vframe, gb->io_registers[GB_IO_LY],
                            gb->io_registers[GB_IO_STAT] & 3, gb->pc, gb->mbc5.rom_bank_low | (gb->mbc5.rom_bank_high << 8), what, addr, ret);
}
static bool write_cb(GB_gameboy_t *gb, uint16_t addr, uint8_t data) {
    if (!started) return true;
    bool lcd = gb->io_registers[GB_IO_LCDC] & 0x80;
    if (lcd && addr >= 0x8000 && addr < 0xA000 && gb->vram_write_blocked) report(gb, "VRAM write dropped", addr);
    if (lcd && addr >= 0xFE00 && addr < 0xFEA0 && gb->oam_write_blocked) report(gb, "OAM write dropped", addr);
    if (lcd && (addr == 0xFF69 || addr == 0xFF6B) && gb->cgb_palettes_blocked) report(gb, "palette write dropped", addr);
    if (apu && addr >= 0xFF10 && addr < 0xFF40) {
        apu_hash = (apu_hash ^ ((addr & 0xFF) | (data << 8))) * 1099511628211ULL;
    }
    if (addr == 0xFF55 && !(data & 0x80) && lcd) { gdma_pending = 1; gdma_ly = gb->io_registers[GB_IO_LY]; gdma_mode = gb->io_registers[GB_IO_STAT] & 3; gdma_len = (data & 0x7F) + 1; gdma_pc = gb->pc; gdma_bank = gb->mbc5.rom_bank_low | (gb->mbc5.rom_bank_high << 8); ngdma++; }
    return true;
}
static void exec_cb(GB_gameboy_t *gb, uint16_t addr, uint8_t op) {
    if (gdma_pending) {
        gdma_pending = 0;
        int ly = gb->io_registers[GB_IO_LY];
        fprintf(bad, "GDMA %d %d.%d %d.%d %04X\n", gdma_len, gdma_ly, gdma_mode, ly, gb->io_registers[GB_IO_STAT] & 3, gdma_pc);
        int mode = gb->io_registers[GB_IO_STAT] & 3;     // (VRAM's the screen's in mode 3 only: a GDMA from its start
        int ok = (mode == gdma_mode && mode != 3 && (ly == gdma_ly || mode == 1))     //  to its end in no mode 3 -- in
              || (gdma_mode == 0 && mode == 2 && ly == (gdma_ly + 1) % 154)          //  VBlank, in a line's HBlank
              || (gdma_mode == 1 && mode == 2 && ly == 0);                          //  and the next's OAM scan, or
        if (!ok) {                                                                  //  from VBlank to line 0's scan)
            novr++;
            fprintf(bad, "frame %ld GDMA of %d blocks from LY %d mode %d (PC %04X bank %d) to LY %d mode %d: over a line's drawing\n", vframe, gdma_len, gdma_ly, gdma_mode, gdma_pc, gdma_bank, ly, mode);
        }
    }
    if (!started && addr == 0x0100) started = 1;
    if (started && done_addr >= 0) {    // (each VBlank, line 144 to line 144: its frame's work run once)
        int ly = gb->io_registers[GB_IO_LY];
        if (!(gb->io_registers[GB_IO_LCDC] & 0x80)) win_valid = 0;
        if (ly == 144 && last_ly != 144) {
            int fight = active_addr < 0 || GB_safe_read_memory(gb, active_addr) == 1;
            if (!win_valid || !fight) armed = 0;            // (counted from the fight's first VBlank with its work in:
            if (win_valid && fight && armed && win_done != 1) {    //  not its load's last ones)
                if (win_done) ntwice++; else nlost++;
                fprintf(bad, "frame %ld VBlank %s\n", vframe, win_done ? "with its frame's work run twice" : "lost (no frame's work run in it)");
            }
            armed = armed || (win_valid && fight && win_done == 1);
            win_done = 0; win_valid = fight && (gb->io_registers[GB_IO_LCDC] & 0x80);
        }
        last_ly = ly;
        if (addr == done_addr) win_done++;
    }
    if (snd && started && addr == snd_addr && (gb->mbc5.rom_bank_low | (gb->mbc5.rom_bank_high << 8)) == snd_bank) {
        int32_t v = (int32_t)vframe; fwrite(&v, 4, 1, snd);       // (the engine entered: its state then)
        for (int i = 0; i < 0x800; i++) { uint8_t b = GB_safe_read_memory(gb, snd_wnes + i); fwrite(&b, 1, 1, snd); }
        for (int i = 0; i < 0x18; i++) { uint8_t b = GB_safe_read_memory(gb, snd_wapu + i); fwrite(&b, 1, 1, snd); }
    }
    if (prof && in_fight) {
        int bank = addr < 0x4000 ? 0 : (gb->mbc5.rom_bank_low | (gb->mbc5.rom_bank_high << 8)) & 0x1FF;
        if (addr < 0x8000) prof[bank * 0x4000 + (addr & 0x3FFF)]++;
        else if (addr >= 0xFF80) prof[512 * 0x4000 + (addr & 0x7F)]++;
    }
    static long probe_frame = -1;
    if (addr == probe && in_fight && probe_frame != vframe) { probe_frame = vframe; probe_ly[gb->io_registers[GB_IO_LY] % 160]++; }
    if (load_scene && addr == load_scene) {
        GB_registers_t *r = GB_get_registers(gb);
        if (r->a == 2) r->a = scene_target;
    }
}
int main(int argc, char **argv) {
    if (argc < 11) { fprintf(stderr, "usage\n"); return 1; }
    int cgb = strcmp(argv[1], "cgb") == 0;
    GB_random_seed(12345);
    GB_gameboy_t *gb = GB_init(GB_alloc(), cgb ? GB_MODEL_CGB_E : GB_MODEL_DMG_B);
    if (GB_load_boot_rom(gb, argv[2]) || GB_load_rom(gb, argv[3])) { fprintf(stderr, "load failed\n"); return 1; }
    long n = 0; uint8_t *inputs = malloc(1);
    if (strcmp(argv[4], "-")) {
        FILE *f = fopen(argv[4], "rb");
        if (!f) { fprintf(stderr, "can't read %s\n", argv[4]); return 1; }
        fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
        inputs = realloc(inputs, n + 1); fread(inputs, 1, n, f); fclose(f);
    }
    const char *out = argv[5];
    uint16_t hframe = strtol(argv[6], 0, 0); load_scene = strtol(argv[7], 0, 0); scene_target = atoi(argv[8]);
    long total = atol(argv[9]); long every = atol(argv[10]);
    int naddr = argc - 11; uint16_t addrs[64];
    for (int i = 0; i < naddr && i < 64; i++) addrs[i] = strtol(argv[11 + i], 0, 0);
    GB_set_pixels_output(gb, pixels);
    GB_set_rgb_encode_callback(gb, rgb);
    GB_set_color_correction_mode(gb, GB_COLOR_CORRECTION_DISABLED);
    GB_set_execution_callback(gb, exec_cb);
    GB_set_write_memory_callback(gb, write_cb);
    if (getenv("SB_APU")) apu = fopen(getenv("SB_APU"), "w");
    if (getenv("SB_PROF")) prof = calloc(512 * 0x4000 + 128, sizeof(uint32_t));
    if (getenv("SB_PROBE")) probe = strtol(getenv("SB_PROBE"), 0, 0);
    if (getenv("SB_DONE")) done_addr = strtol(getenv("SB_DONE"), 0, 0);
    if (getenv("SB_ACTIVE")) active_addr = strtol(getenv("SB_ACTIVE"), 0, 0);
    char bpath[512]; snprintf(bpath, sizeof bpath, "%s/hardware.txt", argv[5]); bad = fopen(bpath, "w");
    if (!bad) { fprintf(stderr, "can't write %s\n", bpath); return 1; }
    if (getenv("SB_WAV")) { wav = fopen(getenv("SB_WAV"), "wb"); GB_set_sample_rate(gb, 48000);
        GB_set_highpass_filter_mode(gb, GB_HIGHPASS_ACCURATE); GB_apu_set_sample_callback(gb, sample_cb);
        if (getenv("SB_SOLO")) for (int c = 0; c < 4; c++) GB_set_channel_muted(gb, c, c != atoi(getenv("SB_SOLO"))); }
    else GB_set_sample_rate(gb, 0);
    if (getenv("SB_SND")) { unsigned a, b, w, p; sscanf(getenv("SB_SND"), "%x %x %x %x", &a, &b, &w, &p);
        snd_addr = a; snd_bank = b; snd_wnes = w; snd_wapu = p; char sp[512]; snprintf(sp, sizeof sp, "%s/snd.bin", out); snd = fopen(sp, "wb"); }
    char path[512]; snprintf(path, sizeof path, "%s/ram.txt", out); FILE *ram = fopen(path, "w");
    while (!started) GB_run_frame(gb);
    long game = 0; uint8_t last = GB_safe_read_memory(gb, hframe);
    for (long v = 0; v < total; v++) {
        long next = game + 1;
        uint8_t m = next < n ? inputs[next] : 0;
        vframe = v;
        if (next >= n) {                    // (past the recording: a fighter's mashing, to keep the fight going)
            static uint32_t rnd = 12345; static uint8_t held = 0; static int hold = 0;
            if (hold-- <= 0) { rnd = rnd * 1103515245 + 12345; static const uint8_t pick[] = {0, 0x10, 0x20, 0x14, 0x24, 0x01, 0x02, 0x08, 0x80};
                held = pick[(rnd >> 16) % 9]; hold = 2 + (rnd >> 8) % 12; if (held == 0x80 && (rnd & 3)) held = 0; }
            m = held;
        }
        for (int k = 0; k < 8; k++) {
            static const GB_key_t map[8] = {GB_KEY_RIGHT, GB_KEY_LEFT, GB_KEY_UP, GB_KEY_DOWN, GB_KEY_A, GB_KEY_B, GB_KEY_SELECT, GB_KEY_START};
            GB_set_key_state(gb, map[k], (m >> k) & 1);
        }
        in_fight = getenv("SB_ACTIVE") ? GB_safe_read_memory(gb, strtol(getenv("SB_ACTIVE"), 0, 0)) == 1 : 1;
        GB_run_frame(gb);
        uint8_t now = GB_safe_read_memory(gb, hframe);
        game += (uint8_t)(now - last); last = now;
        if (apu) { fprintf(apu, "%ld %016llx\n", game, (unsigned long long)apu_hash); apu_hash = 1469598103934665603ULL; }
        fprintf(ram, "%ld %ld", v, game); { GB_registers_t *R = GB_get_registers(gb); fprintf(ram, " pc=%04X sp=%04X bank=%d", R->pc, R->sp, gb->mbc5.rom_bank_low); if (wav) fprintf(ram, " s=%ld", nsamples); }
        for (int i = 0; i < naddr; i++) fprintf(ram, " %d", GB_safe_read_memory(gb, addrs[i]));
        fprintf(ram, "\n");
        static long prev = -1;
        if (every && game % every == 0 && game != prev) { prev = game;
            snprintf(path, sizeof path, "%s/sb_%06ld.rgb", out, game);
            FILE *o = fopen(path, "wb");
            for (int i = 0; i < 160 * 144; i++) { uint8_t px[3] = {pixels[i] >> 16, pixels[i] >> 8, pixels[i]}; fwrite(px, 1, 3, o); }
            fclose(o);
        }
    }
    fclose(ram); if (apu) fclose(apu); if (wav) fclose(wav); if (snd) fclose(snd);
    fprintf(bad, "SUMMARY dropped writes %ld, GDMAs %ld, over drawing %ld, VBlanks lost %ld, twice %ld\n", nbad, ngdma, novr, nlost, ntwice); fclose(bad);
    if (prof) { FILE *pf = fopen(getenv("SB_PROF"), "w");
        for (long i = 0; i < 512 * 0x4000 + 128; i++) if (prof[i]) fprintf(pf, "%ld %ld %u\n", i / 0x4000, i % 0x4000, prof[i]);
        fclose(pf); }
    if (probe >= 0) { printf("probe LY:"); for (int i = 0; i < 160; i++) if (probe_ly[i]) printf(" %d:%ld", i, probe_ly[i]); printf("\n"); }
    printf("dropped writes %ld, GDMAs %ld, over drawing %ld, VBlanks lost %ld, twice %ld\n", nbad, ngdma, novr, nlost, ntwice);
    return getenv("SB_STRICT") && (nbad || novr || nlost || ntwice) ? 2 : 0;
}
