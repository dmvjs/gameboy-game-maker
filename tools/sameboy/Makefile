# The SameBoy hardware check's tools: SameBoy's core (headless: no SDL, no frontend), its own open-source boot ROMs
# (assembled from its BootROMs/ with RGBDS -- never Nintendo's), and sbreplay linked against the core.
#   make -C tools/sameboy SAMEBOY=/path/to/SameBoy RGBDS=/path/to/rgbds/
# SAMEBOY: a SameBoy checkout at the commit tools/sameboy/check.py pins (SAMEBOY_COMMIT); RGBDS: the directory of
# rgbasm/rgblink/rgbgfx, with its trailing slash (empty: on PATH). Everything is built under $(SAMEBOY)/build.

SAMEBOY ?= $(HOME)/.gbstage/sameboy/26a56bd6a122
RGBDS ?=
CC ?= cc
OUT := $(abspath $(SAMEBOY))/build/sbcheck
CORE_SOURCES := $(wildcard $(SAMEBOY)/Core/*.c)
CORE_OBJECTS := $(patsubst $(SAMEBOY)/Core/%.c,$(OUT)/core/%.o,$(CORE_SOURCES))
OPT ?= -O3 -ffast-math         # (SameBoy's own release flags)
CORE_CFLAGS := $(OPT) -std=gnu11 -D_GNU_SOURCE -D_USE_MATH_DEFINES -DNDEBUG -DGB_INTERNAL \
               -DGB_VERSION='"sbcheck"' -DGB_COPYRIGHT_YEAR='"2026"' -I$(SAMEBOY)

all: $(OUT)/sbreplay boot

# (flags changed? rm -rf $(OUT) first: the core's struct layouts follow them, and a mix of objects hangs)
$(OUT)/core/%.o: $(SAMEBOY)/Core/%.c
	@mkdir -p $(dir $@)
	$(CC) $(CORE_CFLAGS) -c $< -o $@

$(OUT)/libsameboy.a: $(CORE_OBJECTS)
	rm -f $@
	ar -crs $@ $^

$(OUT)/sbreplay: sbreplay.c $(OUT)/libsameboy.a
	$(CC) $(CORE_CFLAGS) -Wall -o $@ $< $(OUT)/libsameboy.a -lm

# (SameBoy's own Makefile for its boot ROMs: its pb12 compressor and logo, then RGBDS)
boot:
	$(MAKE) -C $(SAMEBOY) RGBDS=$(RGBDS) CONF=release build/bin/BootROMs/cgb_boot.bin build/bin/BootROMs/dmg_boot.bin

.PHONY: all boot
