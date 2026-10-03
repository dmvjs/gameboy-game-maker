; gbstage self-test ROM.
; Draws four 40-pixel vertical bands using shades 0-3 (lightest to darkest) and writes
; "GBOK" to $C000 once setup is finished. The doctor and the browser check look for both.

DEF rLY   EQU $FF44
DEF rLCDC EQU $FF40
DEF rSCY  EQU $FF42
DEF rSCX  EQU $FF43
DEF rBGP  EQU $FF47

SECTION "Header", ROM0[$100]
    nop
    jp Start
    ds $150 - @, 0

SECTION "Start", ROM0
Start:
    di
.waitVBlank:                ; the LCD may only be switched off during VBlank
    ldh a, [rLY]
    cp 144
    jr c, .waitVBlank
    xor a
    ldh [rLCDC], a

    ld hl, $8000            ; copy the four shade tiles into VRAM
    ld de, Tiles
    ld bc, Tiles.end - Tiles
.copyTiles:
    ld a, [de]
    ld [hl+], a
    inc de
    dec bc
    ld a, b
    or c
    jr nz, .copyTiles

    ld hl, $9800            ; fill all 32 rows of the background map with the band pattern
    ld b, 32
.row:
    ld de, MapRow
    ld c, 32
.col:
    ld a, [de]
    ld [hl+], a
    inc de
    dec c
    jr nz, .col
    dec b
    jr nz, .row

    xor a
    ldh [rSCY], a
    ldh [rSCX], a
    ld a, %11100100         ; color 0 = lightest ... color 3 = darkest
    ldh [rBGP], a
    ld a, %10010001         ; LCD on, tiles at $8000, background on
    ldh [rLCDC], a

    ld hl, $C000
    ld a, "G"
    ld [hl+], a
    ld a, "B"
    ld [hl+], a
    ld a, "O"
    ld [hl+], a
    ld a, "K"
    ld [hl], a
.forever:
    jr .forever

SECTION "Data", ROM0
Tiles:
    ds 16, $00              ; color 0
    REPT 8
        db $FF, $00         ; color 1
    ENDR
    REPT 8
        db $00, $FF         ; color 2
    ENDR
    ds 16, $FF              ; color 3
.end:

MapRow:
    db 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3
    ds 12, 0
