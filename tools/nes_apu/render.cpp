// The NES's sound, rendered by blargg's Nes_Apu (libgme) from a log of the sound registers as the NES's own code
// writes them, a frame at a time.
//   render IMAGE LOG OUT.raw   IMAGE: $8000-$FFFF as the sound engine has it mapped (for the samples it plays);
//   (SOLO=n in the environment: that channel alone, 0-4 square 1, square 2, triangle, noise, samples)
//   LOG: lines "frame addr value" in write order;  OUT: 48 kHz mono signed 16-bit
#include "Nes_Apu.h"
#include "Blip_Buffer.h"
#include <cstdio>
#include <cstdlib>
#include <vector>

static unsigned char image[0x8000];
static int read_dmc(void*, nes_addr_t a) { return a >= 0x8000 ? image[a - 0x8000] : 0; }

int main(int argc, char** argv) {
    if (argc < 4) { fprintf(stderr, "usage: render IMAGE LOG OUT\n"); return 1; }
    FILE* f = fopen(argv[1], "rb"); fread(image, 1, sizeof image, f); fclose(f);
    Nes_Apu apu; Blip_Buffer buf;
    buf.clock_rate(1789773); buf.set_sample_rate(48000, 1000 / 30); buf.bass_freq(90);   // (the NES's own 90 Hz high-pass)
    apu.output(&buf); apu.dmc_reader(read_dmc, 0);
    if (getenv("SOLO")) for (int i = 0; i < Nes_Apu::osc_count; i++) if (i != atoi(getenv("SOLO"))) apu.osc_output(i, 0);
    const int FRAME = 29781;
    FILE* log = fopen(argv[2], "r"); FILE* out = fopen(argv[3], "wb");
    long frame, a, v, at = 0, cur = 0; std::vector<blip_sample_t> s(4096);
    auto flush = [&]() {
        apu.end_frame(FRAME); buf.end_frame(FRAME);
        long n = buf.read_samples(s.data(), s.size()); fwrite(s.data(), 2, n, out);
        cur++; at = 0;
    };
    while (fscanf(log, "%ld %lx %lx", &frame, &a, &v) == 3) {
        while (cur < frame) flush();
        apu.write_register(20 + at, a, v); at += 12;      // (the frame's writes, as its NMI makes them, at its start)
    }
    flush();
    fclose(out);
    return 0;
}
