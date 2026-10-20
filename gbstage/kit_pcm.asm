; ---- Punch-Out!!'s crowd, recorded: its NES sample played on the wave channel (off the fight) ---------------
; The NES plays its crowd as a sample (the DMC); the GB has no such channel, but its wave channel plays 32
; four-bit steps over and over. So: the sample (CrowdPcm: the NES's own, decoded and taken to 16384 Hz, 4 bits),
; 32 steps at a time, the wave channel retriggered on each with the next 32, by the timer (512 a second: 16384 /
; 32), read from its bank (mapped, then hBank's again: it's set before every switch, so an interrupt never
; leaves the wrong one). In the fight the noise channel's stands in for it (kit_nes_sound.asm, DmcStep).

DEF rTIMA EQU $FF05
DEF rTMA EQU $FF06
DEF rTAC EQU $FF07
DEF _AUD3WAVERAM EQU $FF30

SECTION "Crowd PCM state", WRAM0
wPcmOn: db                  ; playing
wPcmPtr: dw                 ; the next 16 bytes

SECTION "Crowd PCM, from any bank", ROM0
; A = the DMC sample just started (1: the crowd): off the fight, the recording instead of the noise's.
PcmMaybeFar::
    cp 1
    ret nz
    ldh a, [hFtActive]
    and a
    ret nz
    ld hl, CrowdPcm
    ld a, l
    ld [wPcmPtr], a
    ld a, h
    ld [wPcmPtr + 1], a
    ld a, 1
    ld [wPcmOn], a
    call PcmFill
    ld a, 256 - 128         ; (65536 Hz, counting: 512 overflows a second)
    ldh [rTMA], a
    ldh [rTIMA], a
    ld a, %110
    ldh [rTAC], a
    ldh a, [rIE]
    or %100
    ldh [rIE], a
    ei                      ; (off the fight no handler runs, VBlank only waking HALT: the timer's must)
    ret

; Timer: the next 32 steps.
PcmTick::
    push af
    push bc
    push hl
    call PcmFill
    pop hl
    pop bc
    pop af
    reti

; The wave channel off, its RAM the next 16 bytes, on again from the first (8192 steps a second: 2048 - 256).
PcmFill::
    ld a, BANK(CrowdPcm)
    ld [$2100], a
    ld a, [wPcmPtr]
    ld l, a
    ld a, [wPcmPtr + 1]
    ld h, a
    xor a                   ; (the channel off as short a time as can be: unrolled)
    ldh [rAUD3ENA], a
    FOR N, 16
        ld a, [hl+]
        ldh [_AUD3WAVERAM + N], a
    ENDR
    ld a, $80
    ldh [rAUD3ENA], a
    ld a, $20               ; (all of it)
    ldh [rAUD3LEVEL], a
    ld a, $80
    ldh [rAUD3LOW], a
    ld a, $87               ; (restart: 2048 - $780 = 128)
    ldh [rAUD3HIGH], a
    ldh a, [hBank]
    ld [$2100], a
    ld a, l
    cp LOW(CrowdPcm + CROWD_PCM_SIZE)
    jr nz, .on
    ld a, h
    cp HIGH(CrowdPcm + CROWD_PCM_SIZE)
    jr nz, .on
    ld a, [wDmcLoop]        ; its end: again, if it loops, else done
    and a
    jr z, PcmStop
    ld hl, CrowdPcm
.on:
    ld a, l
    ld [wPcmPtr], a
    ld a, h
    ld [wPcmPtr + 1], a
    ret

; HL's 16 bytes into the wave RAM (its channel off), then on.
PcmWave:
    ld c, LOW(_AUD3WAVERAM)
.byte:
    ld a, [hl+]
    ldh [c], a
    inc c
    ld a, c
    cp LOW(_AUD3WAVERAM) + 16
    jr nz, .byte
    ld a, $80
    ldh [rAUD3ENA], a
    ret

; Done (its end, the fight, or another sample): the timer off, the wave channel the triangle's again.
PcmStop::
    xor a
    ld [wPcmOn], a
    ldh [rTAC], a
    ldh a, [rIE]
    and ~%100
    ldh [rIE], a
    ldh a, [hFtActive]      ; (off the fight, handlers off again; a fight's are its own)
    and a
    jr nz, .fight
    di
.fight:
    xor a
    ldh [rAUD3ENA], a
    ld hl, PcmTriangle
    call PcmWave
    xor a
    ldh [rAUD3LEVEL], a     ; (silent till the triangle's next note: TriangleOut starts it afresh)
    ld [wGbVol + 2], a
    ld a, $FF
    ld [wGbFreq + 5], a
    ret

PcmTriangle:                ; (ApuTriangle's, here in ROM0: the interrupt may stop it)
    db $76, $54, $32, $10, $01, $23, $45, $67, $89, $AB, $CD, $EF, $FE, $DC, $BA, $98
