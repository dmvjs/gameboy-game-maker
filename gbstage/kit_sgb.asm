; Super Game Boy: found by what its boot ROM leaves in C ($14; a Game Boy's $13, Color's $00), kept at boot (wSgbBoot);
; the first LoadScene sends the border and the screen's four colors (the grey look's: every screen as on the original).
; Packets go to the SGB through P1: a reset pulse, 128 bits (each byte's lowest first: $20 a 0, $10 a 1, $30 between),
; a 0 to end; four frames between packets. The border goes as VRAM shown on screen (CHR_TRN, PCT_TRN).
; Everything here runs with the display off (or showing what a transfer sends), never in a fight's frames.

SECTION "SGB state", WRAM0
wSgbBoot: db                ; the boot ROM's C: $14 on an SGB, the border not sent yet; $FF once it is (LoadScene)
wSgbKeep: ds 64 + 3         ; (VRAM's first tiles -- the cursor's, put there at boot -- and SCX, SCY, BGP: the
                            ;  border's transfer shows its own)

SECTION "SGB", ROMX
SgbScene::                  ; LoadScene, wSgbBoot $14: the first time on an SGB (at boot, the display off), the
    ldh a, [hIsCGB]         ; border and the colors sent; wSgbBoot $FF after (Color's C is $00: only in case)
    and a
    ld a, 0
    jr nz, .notSgb
    dec a
.notSgb:
    ld [wSgbBoot], a
    and a
    ret z
    ld hl, $8000
    ld de, wSgbKeep
    ld bc, 64
    call SgbCopy
    ldh a, [rSCX]
    ld [de], a
    inc de
    ldh a, [rSCY]
    ld [de], a
    inc de
    ldh a, [rBGP]
    ld [de], a
    ld b, 6                 ; (the SGB ready for packets)
    call SgbFrames
    ld hl, SgbMaskFreeze    ; the SGB's screen held while the border's data shows on ours
    call SgbSend
    ld b, 4
    call SgbFrames
    ld hl, SgbBorderChr
    ld de, $8000
    ld bc, $1000
    call SgbCopy
    ld hl, SgbChrTrn0
    call SgbTransfer
    ld hl, SgbBorderChr + $1000
    ld de, $8000
    ld bc, $1000
    call SgbCopy
    ld hl, SgbChrTrn1
    call SgbTransfer
    ld hl, SgbBorderMap     ; the map (32x28), then palette 4 at $800
    ld de, $8000
    ld bc, 32 * 28 * 2
    call SgbCopy
    ld hl, SgbBorderPal
    ld de, $8800
    ld bc, 32
    call SgbCopy
    ld hl, SgbPctTrn
    call SgbTransfer
    ld hl, SgbPal01         ; the colors, then the SGB's screen shown again
    call SgbSend
    ld b, 4
    call SgbFrames
    ld hl, SgbMaskOff
    call SgbSend
    ld b, 4
    call SgbFrames
    ld hl, wSgbKeep         ; (what the transfers showed in their place, back)
    ld de, $8000
    ld bc, 64
    call SgbCopy
    ld a, [hl+]
    ldh [rSCX], a
    ld a, [hl+]
    ldh [rSCY], a
    ld a, [hl]
    ldh [rBGP], a
    ret

SgbFrames:                  ; B frames (70224 clocks each, 2508 times 28), the display on or off
.frame:
    ld de, 2508
.wait:
    dec de
    ld a, d
    or e
    jr nz, .wait
    dec b
    jr nz, .frame
    ret

SgbSend:                    ; the command at HL: its packets (16 bytes each, as many as its first byte's low 3 bits)
    ld a, [hl]
    and 7
    ld c, a
.packet:
    xor a                   ; reset
    ldh [rP1], a
    ld a, $30
    ldh [rP1], a
    ld b, 16
.byte:
    ld e, [hl]
    inc hl
    ld d, 8
.bit:
    ld a, $10
    srl e
    jr c, .one
    ld a, $20
.one:
    ldh [rP1], a
    ld a, $30
    ldh [rP1], a
    dec d
    jr nz, .bit
    dec b
    jr nz, .byte
    ld a, $20               ; the end: a 0
    ldh [rP1], a
    ld a, $30
    ldh [rP1], a
    dec c
    jr nz, .packet
    ret

SgbCopy:                    ; BC bytes, HL -> DE
    ld a, [hl+]
    ld [de], a
    inc de
    dec bc
    ld a, b
    or c
    jr nz, SgbCopy
    ret

SgbTransfer:                ; VRAM's $8000-$8FFF shown (tiles 0-255 in order, 20 a row), the packet at HL sent;
    push hl                 ; the SGB reads the screen over the next frames, then the display off again
    ld hl, $9800
    ld c, 0
    ld d, 13
.row:
    ld b, 20
.tile:
    ld a, c
    ld [hl+], a
    inc c
    dec b
    jr nz, .tile
    ld a, l
    add 12
    ld l, a
    adc h
    sub l
    ld h, a
    dec d
    jr nz, .row
    ld a, %11100100
    ldh [rBGP], a
    xor a
    ldh [rSCX], a
    ldh [rSCY], a
    ld a, $91               ; display on, BG from $9800 with tiles at $8000
    ldh [rLCDC], a
    pop hl
    call SgbSend
.shown:                     ; (sent: the SGB reads the screen from here)
    ld b, 5
    call SgbFrames
.vblank:
    ldh a, [rLY]
    cp 144
    jr c, .vblank
    xor a
    ldh [rLCDC], a
    ret

SgbMaskFreeze:
    db $B9, $01, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
SgbMaskOff:
    db $B9, $00, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
SgbChrTrn0:
    db $99, $00, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
SgbChrTrn1:
    db $99, $01, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
SgbPctTrn:
    db $A1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
