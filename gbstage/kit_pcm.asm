; ---- Punch-Out!!'s crowd, recorded: its NES sample played on the wave channel (off the fight) ---------------
; The NES plays its crowd as a sample (the DMC); the GB has no such channel, but its wave channel plays 32
; four-bit steps over and over. So: the sample (CrowdPcm: the NES's own, decoded and taken to 10923 Hz, 4 bits),
; 32 steps at a time, the wave channel retriggered on each with the next 32, by the timer (341 a second). It's
; played from WRAMX (copied there the first time), so the interrupt never touches a ROM bank: the far calls map
; theirs without noting it, and it couldn't put the right one back. In the fight the noise channel's stands in
; for it (kit_nes_sound.asm, DmcStep).

DEF rTIMA EQU $FF05
DEF rTMA EQU $FF06
DEF rTAC EQU $FF07
DEF _AUD3WAVERAM EQU $FF30
DEF MIX_N EQU 12              ; (the ring's buffers: room for a slow frame)
DEF MIX_AHEAD EQU 9           ; (how many it keeps ready: some 35 ms of it, a slow frame covered, the triangle kept close)

SECTION "Crowd PCM buffer", WRAMX[$D000]
wPcm: ds CROWD_PCM_SIZE

SECTION "Crowd PCM state", WRAM0
wPcmOn: db                  ; playing
wPcmWave: db                ; the wave RAM the crowd's: TriangleOut's to put back
wPcmLoaded: db              ; (copied to wPcm)
wPcmPtr: dw                 ; the next 16 bytes
wPcmMix: db                 ; in the fight (Color): played from the mixed ring (the triangle mixed in)
wMixHead: db                ; the ring: the next buffer to fill, the next to play (MIX_N of them)
wMixTail: db
wMixCrowd: dw               ; the crowd's next 16 bytes (in its rotated blocks)
wMixPhase: dw               ; the triangle: its phase (32 steps a turn, the top 5 bits), its step a sample, its period
wMixInc: dw
wMixPer: dw
wMixOn: db                  ; (sounding)

SECTION "Crowd mix ring", WRAMX     ; (with the crowd's samples: no bank is ever switched)
wMixRing: ds 16 * MIX_N
wMixStop: db                ; (PcmProduce's A: the screen line its topping up stops at, VBlank's lines free)

SECTION "Crowd mix scratch", WRAM0, ALIGN[5]
wMixTmp: ds 32              ; a buffer's 32 steps, in playing order (one page: its loop counts on the low byte)

SECTION "Crowd PCM, from any bank", ROM0
; A = the DMC sample just started (1: the crowd): off the fight, the recording instead of the noise's.
PcmMaybeFar::
    cp 1
    ret nz
    xor a
    ld [wPcmMix], a
    ldh a, [hFtActive]
    and a
    jr z, .off
    ldh a, [hIsCGB]         ; (in the fight: on Color the triangle mixed in; on the original, the crowd's
    and a                   ; alone while it lasts: its noise imitation can't make its band, 250-1000 Hz)
    jr z, .off
    inc a
    ld [wPcmMix], a
.off:
    ld a, [wPcmLoaded]
    and a
    jr nz, .loaded
    ld a, BANK(CrowdPcm)    ; (its first time: into WRAMX, the caller's bank back after)
    ld [$2100], a
    ld hl, CrowdPcm
    ld de, wPcm
    ld bc, CROWD_PCM_SIZE
.copy:
    ld a, [hl+]
    ld [de], a
    inc de
    dec bc
    ld a, b
    or c
    jr nz, .copy
    ldh a, [hBank]
    ld [$2100], a
    ld a, 1
    ld [wPcmLoaded], a
.loaded:
    ld hl, wPcm
    ld a, l
    ld [wPcmPtr], a
    ld [wMixCrowd], a
    ld a, h
    ld [wPcmPtr + 1], a
    ld [wMixCrowd + 1], a
    xor a
    ld [wMixHead], a
    ld [wMixTail], a
    ld a, $FF               ; (the triangle's period: none yet)
    ld [wMixPer + 1], a
    ld a, 1
    ld [wPcmOn], a
    ld a, [wPcmMix]
    and a
    jr z, .plain
    ld a, 144               ; (the ring's first, whatever the line: then its first up)
    call PcmProduce
    call PcmMixOut
    jr .timer
.plain:
    call PcmFill
.timer:
    ldh a, [hIsCGB]         ; (341 overflows a second: the original's 65536 Hz / 192; Color's double speed
    and a                   ; doubles the timer's clock, so its 16384 Hz, made 32768, / 96)
    ld a, 256 - 192
    ld b, %110
    jr z, .rate
    ld a, 256 - 96
    ld b, %111
.rate:
    ldh [rTMA], a
    ldh [rTIMA], a
    ld a, b
    ldh [rTAC], a
    ldh a, [rIE]
    or %100
    ldh [rIE], a
    ei                      ; (off the fight no handler runs, VBlank only waking HALT: the timer's must)
    ret

; A fight starting with the crowd's sample under way: its recording from where the sample's got to (its frame,
; 91 bytes a frame, whole blocks), mixed on Color.
PcmResume::
    ld a, [wDmcSample]
    cp 1
    ret nz
    ld a, [wPcmOn]
    and a
    ret nz
    inc a                   ; (the crowd's sample: 1)
    call PcmMaybeFar
    ld a, [wDmcFrame]       ; (frame * 91, to whole 16-byte blocks)
    ld b, a
    ld hl, 0
    ld de, 91
    inc b
.frames:
    dec b
    jr z, .counted
    add hl, de
    jr .frames
.counted:
    ld a, l
    and $F0
    ld l, a
    ld de, CROWD_PCM_SIZE
    ld a, l
    sub e
    ld a, h
    sbc d
    ret nc                  ; (past its end)
    ld de, wPcm
    add hl, de
    ld a, l
    ld [wMixCrowd], a
    ld [wPcmPtr], a
    ld a, h
    ld [wMixCrowd + 1], a
    ld [wPcmPtr + 1], a
    xor a
    ld [wMixHead], a
    ld [wMixTail], a
    ld a, [wPcmMix]         ; (mixed: the ring filled now, before the timer's first asks for it)
    and a
    ret z
    ld a, 144
    jp PcmProduce

; Timer: the next 32 steps.
PcmTick::
    push af
    ei                      ; (the fight's splits may cut in: never late for them)
    push bc
    push hl
    ld a, [wPcmMix]
    and a
    jr nz, .mixed
    call PcmFill
    jr .done
.mixed:
    call PcmMixOut
.done:
    pop hl
    pop bc
    pop af
    reti

; The fight (Color): the ring's next mixed buffer up (none ready: the last again).
PcmMixOut:
    ld a, [wMixTail]
    ld b, a
    ld a, [wMixHead]
    cp b
    jr nz, .ready
    ld a, b                 ; (under: the one before again)
    and a
    jr nz, .back
    ld a, MIX_N
.back:
    dec a
    jr .at
.ready:
    ld a, b
    inc a
    cp MIX_N
    jr c, .next
    xor a
.next:
    ld [wMixTail], a
    ld a, b
.at:
    swap a
    add LOW(wMixRing)
    ld l, a
    ld a, 0
    adc HIGH(wMixRing)
    ld h, a
    xor a
    ldh [rAUD3ENA], a
    FOR N, 16
        ld a, [hl+]
        ldh [_AUD3WAVERAM + N], a
    ENDR
    ld a, $80
    ldh [rAUD3ENA], a
    ld a, $20
    ldh [rAUD3LEVEL], a
    ld a, $40
    ldh [rAUD3LOW], a
    ld a, $87
    ldh [rAUD3HIGH], a
    ret

; Each frame of a fight (Color, the crowd on): the ring topped up, from its bank (the mixer and its tables there),
; stopping at screen line A (a buffer takes some 13 lines: the frame's work never runs into VBlank for it; VBlank's own
; lines are free, and 144 never stops).
PcmProduce::
    ld [wMixStop], a
    ld a, BANK(PcmProduceIn)
    ld [$2100], a
    call PcmProduceIn
    ldh a, [hBank]
    ld [$2100], a
    ret

; The wave channel off, its RAM the next 16 bytes, on again from the first (8192 steps a second: 2048 - 256).
PcmFill::
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
    ld a, $40
    ldh [rAUD3LOW], a
    ld a, $87               ; (restart: 2048 - $740 = 192)
    ldh [rAUD3HIGH], a
    ld a, l
    cp LOW(wPcm + CROWD_PCM_SIZE)
    jr nz, .on
    ld a, h
    cp HIGH(wPcm + CROWD_PCM_SIZE)
    jr nz, .on
    ld a, [wDmcLoop]        ; its end: again, if it loops, else done
    and a
    jr z, PcmStop
    ld hl, wPcm
.on:
    ld a, l
    ld [wPcmPtr], a
    ld a, h
    ld [wPcmPtr + 1], a
    ret

; Done (its end, the fight, or another sample): the timer off, the wave channel the triangle's again.
PcmStop::
    xor a
    ld [wPcmOn], a
    ld [wPcmMix], a
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
    ldh [rAUD3LEVEL], a     ; (silent till the triangle's next note: TriangleOut starts it afresh, its wave
    ld [wGbVol + 2], a      ; put back first)
    ld a, $FF
    ld [wGbFreq + 5], a
    ld [wPcmWave], a
    ret

SECTION FRAGMENT "Screens far", ROMX
; The fight's mixer (Color): the ring topped up, each buffer 32 steps of the crowd (wMixCrowd, in its rotated
; blocks) with the triangle mixed in at its pitch (the NES's: its 32-step wave, CPU / (period + 1) steps a second),
; through MixTable; written back rotated, as the wave channel's restart wants.
PcmProduceIn:
.more:
    ld a, [wMixStop]
    ld c, a
    ldh a, [rLY]
    cp 144
    jr nc, .go              ; (VBlank's lines: room)
    cp c
    ret nc                  ; (another buffer would run on into VBlank: the rest next time)
.go:
    ld a, [wMixTail]        ; (MIX_AHEAD ready: enough)
    ld b, a
    ld a, [wMixHead]
    sub b
    jr nc, .ahead
    add MIX_N
.ahead:
    cp MIX_AHEAD
    ret nc
    ld a, [wMixHead]
    inc a
    cp MIX_N
    jr c, .head
    xor a
.head:
    ld b, a
    ld a, [wMixTail]
    cp b
    ret z                   ; (full)
    call .triangle
    ld a, [wMixOn]          ; pass 1: the triangle's step each sample (its value x16), or the middle when it's still
    and a
    jr nz, .steps
    ld hl, wMixTmp
    ld a, 7 << 4
    ld b, 32
.flat:
    ld [hl+], a
    dec b
    jr nz, .flat
    jr .mix
.steps:
    ld a, [wMixPhase]
    ld e, a
    ld a, [wMixPhase + 1]
    ld d, a
    ld bc, wMixTmp
    ld h, HIGH(MixTri)
.step:
    ld a, [wMixInc]
    add e
    ld e, a
    ld a, [wMixInc + 1]
    adc d
    ld d, a
    rrca
    rrca
    rrca
    and $1F
    ld l, a
    ld a, [hl]
    ld [bc], a
    inc c
    ld a, c
    cp LOW(wMixTmp + 32)
    jr nz, .step
    ld a, e
    ld [wMixPhase], a
    ld a, d
    ld [wMixPhase + 1], a
.mix:                       ; pass 2: each with its crowd step (playing order: the stored block's 2nd step on, its 1st last)
    ld a, [wMixCrowd]
    ld l, a
    ld a, [wMixCrowd + 1]
    ld h, a
    ld de, wMixTmp
    ld a, [hl+]             ; (byte 0: its low step first; its high, the block's last)
    push af
    and $0F
    call .one
    ld b, 15
.byte:
    ld a, [hl]
    swap a
    and $0F
    call .one
    ld a, [hl+]
    and $0F
    call .one
    dec b
    jr nz, .byte
    pop af
    swap a
    and $0F
    call .one
    ld a, l                 ; the crowd on (its end: again, if it loops, else done)
    cp LOW(wPcm + CROWD_PCM_SIZE)
    jr nz, .on
    ld a, h
    cp HIGH(wPcm + CROWD_PCM_SIZE)
    jr nz, .on
    ld a, [wDmcLoop]
    and a
    jp z, PcmStop
    ld hl, wPcm
.on:
    ld a, l
    ld [wMixCrowd], a
    ld a, h
    ld [wMixCrowd + 1], a
    ld a, [wMixHead]        ; pass 3: packed into the ring, rotated (the last step first)
    swap a
    add LOW(wMixRing)
    ld l, a
    ld a, 0
    adc HIGH(wMixRing)
    ld h, a
    ld de, wMixTmp
    ld a, [wMixTmp + 31]
    swap a
    ld b, a
    ld a, [de]
    inc de
    or b
    ld [hl+], a
    ld c, 15
.pack:
    ld a, [de]
    inc de
    swap a
    ld b, a
    ld a, [de]
    inc de
    or b
    ld [hl+], a
    dec c
    jr nz, .pack
    ld a, [wMixHead]
    inc a
    cp MIX_N
    jr c, .stored
    xor a
.stored:
    ld [wMixHead], a
    jp .more
.one:                       ; A = a crowd step: [DE] = MixTable[[DE] | A], DE on
    push hl
    ld h, a
    ld a, [de]
    or h
    ld l, a
    ld h, HIGH(MixTable)
    ld a, [hl]
    ld [de], a
    inc de
    pop hl
    ret
.triangle:                  ; wMixOn: sounding (its linear and length counters running, period 2 on); wMixInc for it
    xor a
    ld [wMixOn], a
    ld a, [wApuLinear]
    and a
    ret z
    ld a, [wApuLength + 2]
    and a
    ret z
    ld a, [wApu + $0A]
    ld c, a
    ld a, [wApu + $0B]
    and $07
    ld b, a                 ; BC = the period
    or c
    ret z
    ld a, b
    and a
    jr nz, .sounds
    ld a, c
    cp 2
    ret c
.sounds:
    ld a, 1
    ld [wMixOn], a
    ld a, [wMixPer]
    cp c
    jr nz, .new
    ld a, [wMixPer + 1]
    cp b
    ret z
.new:
    ld a, c
    ld [wMixPer], a
    ld a, b
    ld [wMixPer + 1], a
    inc bc                  ; inc = 335585 / (period + 1) (2048 a step, 1789773 / 10923 steps... a sample)
    ld hl, 0                ; (24 / 16 bits, by shifts: the quotient in DE)
    ld de, 0
    ld a, 24
    push af
    ld a, $05
    ld [wMixTmp], a         ; (335585 = $051EE1: its bytes, high first, into the scratch)
    ld a, $1E
    ld [wMixTmp + 1], a
    ld a, $E1
    ld [wMixTmp + 2], a
.div:
    ld a, [wMixTmp + 2]     ; the dividend's next bit into HL
    add a
    ld [wMixTmp + 2], a
    ld a, [wMixTmp + 1]
    rla
    ld [wMixTmp + 1], a
    ld a, [wMixTmp]
    rla
    ld [wMixTmp], a
    rl l
    rl h
    sla e                   ; (the quotient a bit on)
    rl d
    ld a, l
    sub c
    ld a, h
    sbc b
    jr c, .under
    ld a, l
    sub c
    ld l, a
    ld a, h
    sbc b
    ld h, a
    inc e
.under:
    pop af
    dec a
    push af
    jr nz, .div
    pop af
    ld a, e
    ld [wMixInc], a
    ld a, d
    ld [wMixInc + 1], a
    ret

    ALIGN 8
MixTable:                   ; the triangle's step (x16) with the crowd's, as the NES's mixer has them, its peaks
    MIX_TABLE               ; taken in softly (codegen _crowd_pcm)

    ALIGN 8
MixTri:                     ; the NES triangle's 32 steps (x16: MixTable's row)
    db 15 << 4, 14 << 4, 13 << 4, 12 << 4, 11 << 4, 10 << 4, 9 << 4, 8 << 4, 7 << 4, 6 << 4, 5 << 4, 4 << 4, 3 << 4, 2 << 4, 1 << 4, 0
    db 0, 1 << 4, 2 << 4, 3 << 4, 4 << 4, 5 << 4, 6 << 4, 7 << 4, 8 << 4, 9 << 4, 10 << 4, 11 << 4, 12 << 4, 13 << 4, 14 << 4, 15 << 4
