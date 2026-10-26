; ---- Punch-Out!!'s crowd, recorded: its NES sample played on the wave channel ------------------------------
; The NES plays its crowd as a sample (the DMC); the GB has no such channel, but its wave channel plays 32
; four-bit steps over and over. So: the sample (CrowdPcm: the NES's own, decoded, 4 bits, in order), the wave
; channel restarted by the timer every 27 of its steps (404 a second) on the next 32. A restart plays the step it
; was on once more, then the RAM's from its second: 26 new steps a restart (the recording's at 26/27 of the
; channel's rate, 10518 Hz, for it), and 27 to 31 of the RAM's are the steps to come -- a restart late (an
; interrupt, VBlank's sprite copy, the screen's splits ahead of it: up to 4 1/2 steps on the original) plays on
; into them, never back to the RAM's first, and the next buffer's taken from as far on as it's late, so the steps
; run on unbroken. Off the fight (and in it on the original) straight from the recording, in WRAMX (copied there
; the first time): the interrupt never touches a ROM bank (the far calls map theirs without noting it, and it
; couldn't put the right one back). In the fight on Color, from a ring of buffers with the triangle mixed in
; (PcmProduce, each frame), in WRAMX's second bank: the recording fills the first.

DEF rTIMA EQU $FF05
DEF rTMA EQU $FF06
DEF rTAC EQU $FF07
DEF rSVBK EQU $FF70
DEF _AUD3WAVERAM EQU $FF30
DEF PCM_STEP EQU 13           ; (bytes a restart: 26 steps)
DEF PCM_MIRROR EQU 32         ; (past a buffer's end, its start again: a late restart's 32 steps read on into it)
DEF MIX_AHEAD EQU 160         ; (the ring's bytes kept ready past where it plays: some 30 ms, a slow frame covered)

SECTION "Crowd PCM buffer", WRAMX[$D000], BANK[1]
wPcm: ds CROWD_PCM_SIZE + PCM_MIRROR

SECTION "Crowd mix ring", WRAMX[$D000], BANK[2]   ; (a page: its place in it a byte, wrapping on its own)
wMixRing: ds 256 + PCM_MIRROR

SECTION "Crowd PCM timer", HRAM    ; (the interrupt's: in order)
hPcmT:
hPcmLateAt: db              ; the timer's count, the restart a byte late (its reload and half a byte's counts)
hPcmPtr: dw                 ; where the next restart plays from, if on time
hPcmEndHi: db               ; its end (past it: again from its start, if it loops, else done)
hPcmEndLo: db
hPcmSize: dw
hPcmLoop: db
hPcmBias: db                ; the timer's reload less half a byte's counts (late: from it, whole bytes, rounded)
hPcmQ: db                   ; the timer's counts a byte (2 steps)

SECTION "Crowd PCM state", WRAM0
wPcmOn: db                  ; playing
wPcmWave: db                ; the wave RAM the crowd's: TriangleOut's to put back
wPcmLoaded: db              ; (copied to wPcm)
wPcmMix: db                 ; in the fight (Color): played from the mixed ring (the triangle mixed in)
wMixHead: db                ; the ring: the next buffer to fill (its byte)
wMixStop: db                ; (PcmProduce's A: the screen line its topping up stops at, VBlank's lines free)
wMixCrowd: dw               ; the crowd's next 16 bytes
wMixPhase: dw               ; the triangle: its phase (32 steps a turn, the top 5 bits), its step a sample, its period
wMixInc: dw
wMixPer: dw
wMixOn: db                  ; (sounding)

SECTION "Crowd mix scratch", WRAM0, ALIGN[5]
wMixTmp: ds 32              ; a buffer's 32 steps, in playing order (one page: its loop counts on the low byte)

SECTION "Crowd mix bytes", HRAM
hMixSrc: ds 16              ; the crowd's 16 bytes for it

SECTION "Crowd PCM, from any bank", ROM0
; A fight starting with the crowd's sample under way: its recording from where the sample's got to.
PcmResume::
    ld a, [wDmcSample]
    cp 1
    ret nz
    ld hl, PcmResumeIn
    jr PcmFar
; A = the DMC sample just started (1: the crowd): the recording instead of the noise's.
PcmMaybeFar::
    cp 1
    ret nz
    ld hl, PcmStart
PcmFar:                     ; HL: the routine, in its bank, the caller's (hBank) back after
    push hl
    call PcmLoad
    pop hl
    ld a, BANK(PcmStart)
    ld [$2100], a
    call .hl
    ldh a, [hBank]
    ld [$2100], a
    ret
.hl:
    jp hl

; The crowd's recording into WRAMX, its first time (the fight's load does it, screen dark: not mid-fight, where
; it ran past a frame); the caller's bank (hBank) back after.
PcmLoad::
    ld a, [wPcmLoaded]
    and a
    ret nz
    ld a, 1                 ; (WRAMX: its bank)
    ldh [rSVBK], a
    ld a, BANK(CrowdPcm)
    ld [$2100], a
    ld hl, CrowdPcm
    ld de, wPcm
    ld bc, CROWD_PCM_SIZE + PCM_MIRROR
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
    ret

; Timer: the wave channel restarted on the next 32 steps, from as far on as it's late. At the timer's own vector
; (no jump to it: 404 a second). WRAMX's bank is the one it plays from all the while it plays (PcmStart).
PUSHS
SECTION "Interrupt: Timer", ROM0[$50]
PcmTick::
    push af
    ei                      ; (the fight's splits may cut in: never late for them)
    push hl
    ld hl, hPcmT
    ldh a, [rTIMA]          ; how late: a byte's time (2 steps) or more since the timer overflowed?
    cp [hl]
    jr nc, .late
    inc l
    ld a, [hl+]
    ld h, [hl]
    ld l, a
.copy:
    xor a                   ; (the channel off as short a time as can be: unrolled)
    ldh [rAUD3ENA], a
    FOR N, 16
        ld a, [hl+]
        ldh [_AUD3WAVERAM + N], a
    ENDR
    ld a, $87               ; (on, and restarted: 2048 - $740 = 192, its level and low byte set at the start)
    ldh [rAUD3ENA], a
    ldh [rAUD3HIGH], a
    ld hl, hPcmPtr          ; on 26 steps
    ld a, [hl]
    add PCM_STEP
    ld [hl+], a
    jr nc, .same
    inc [hl]
.same:
    ld a, [hl+]
    cp [hl]
    jr nc, .end
.done:
    pop hl
    pop af
    reti
.late:                      ; late: the buffer from that many bytes on (the steps that time's played already)
    push bc
    ld hl, hPcmBias
    sub [hl]
    inc l
    ld c, 0
.count:
    inc c
    sub [hl]
    cp [hl]
    jr nc, .count
    ld hl, hPcmPtr
    ld a, [hl+]
    add c
    ld c, a
    ld a, [hl]
    adc 0
    ld h, a
    ld l, c
    pop bc
    jr .copy
.end:                       ; its end reached? Past it: again from as far into its start, if it loops, else done
    jr nz, .past
    inc l
    ld a, [hPcmPtr]
    cp [hl]
    jr c, .done
.past:
    ld a, [hPcmLoop]
    and a
    jr z, .stop
    push bc
    ld hl, hPcmSize
    ld a, [hl+]
    ld b, [hl]
    ld c, a
    ld hl, hPcmPtr
    ld a, [hl]
    sub c
    ld [hl+], a
    ld a, [hl]
    sbc b
    ld [hl], a
    pop bc
    jr .done
.stop:
    call PcmStop
    jr .done
POPS

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

; Done (its end, the fight, or another sample): the timer off, the wave channel the triangle's again.
PcmStop::
    xor a
    ld [wPcmOn], a
    ld [wPcmMix], a
    ldh [rTAC], a
    inc a                   ; (WRAMX: the recording's bank again)
    ldh [rSVBK], a
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
; PcmResume, in its bank: the sample's frame * 88 bytes (10518 Hz), to whole 16-byte blocks, its recording from there.
PcmResumeIn:
    ld a, [wPcmOn]
    and a
    ret nz
    ld a, [wDmcFrame]
    ld b, a
    ld hl, 0
    ld de, 88
    inc b
.frames:
    dec b
    jr z, .counted
    add hl, de
    jr .frames
.counted:
    ld a, l
    and $F0
    ld e, a
    ld d, h
    ld a, e
    sub LOW(CROWD_PCM_SIZE)
    ld a, d
    sbc HIGH(CROWD_PCM_SIZE)
    ret nc                  ; (past its end)
    jr PcmStartAt

; PcmMaybeFar, in its bank: the crowd from its start (PcmStartAt: DE bytes in). Mixing already (its sample
; begun again in the fight on Color): the ring plays on, its crowd from there; else the timer's set going.
PcmStart:
    ld de, 0
PcmStartAt:
    ld hl, wPcm
    add hl, de
    ld b, 0                 ; (the ring: on Color in the fight -- the triangle mixed in; on the original, the
    ldh a, [hFtActive]      ;  crowd's alone while it lasts: its noise imitation can't make its band, 250-1000 Hz)
    and a
    jr z, .plain
    ldh a, [hIsCGB]
    and a
    jr z, .plain
    inc b
.plain:
    ld a, [wPcmMix]
    and b
    jr z, .new
    ld a, l                 ; (the ring under way: its crowd from here)
    ld [wMixCrowd], a
    ld a, h
    ld [wMixCrowd + 1], a
    ret
.new:
    xor a                   ; (the timer stopped while it's set up: none due meanwhile)
    ldh [rTAC], a
    ldh a, [rIF]
    and ~%100
    ldh [rIF], a
    ld a, b
    ld [wPcmMix], a
    and a
    jr z, .fromPcm
    ld a, l
    ld [wMixCrowd], a
    ld a, h
    ld [wMixCrowd + 1], a
    ld hl, wMixRing
    xor a
    ld [wMixHead], a
    ld a, $FF               ; (the triangle's period: none yet)
    ld [wMixPer + 1], a
    ld a, 2                 ; (WRAMX: the ring's bank while it plays)
    ldh [rSVBK], a
    ld a, 1
    ld [hPcmLoop], a
    ld a, HIGH(wMixRing + 256)
    ld [hPcmEndHi], a
    ld bc, 256
    jr .ptr
.fromPcm:
    ld a, 1                 ; (WRAMX: the recording's bank)
    ldh [rSVBK], a
    ld a, [wDmcLoop]
    ld [hPcmLoop], a
    ld a, HIGH(wPcm + CROWD_PCM_SIZE)
    ld [hPcmEndHi], a
    ld a, LOW(wPcm + CROWD_PCM_SIZE)
    ld [hPcmEndLo], a
    ld bc, CROWD_PCM_SIZE
.ptr:
    ld a, l
    ld [hPcmPtr], a
    ld a, h
    ld [hPcmPtr + 1], a
    ld a, c
    ld [hPcmSize], a
    ld a, b
    ld [hPcmSize + 1], a
    ld a, [wPcmMix]
    and a
    jr z, .endLo
    xor a
    ld [hPcmEndLo], a
.endLo:
    ld a, 1
    ld [wPcmOn], a
    ld a, $20               ; (all of it)
    ldh [rAUD3LEVEL], a
    ld a, $40
    ldh [rAUD3LOW], a
    ld a, [wPcmMix]         ; (mixing: the ring's first buffers now, whatever the line)
    and a
    ld a, 144
    ld [wMixStop], a
    call nz, PcmProduceIn
    ldh a, [hIsCGB]         ; (the original's timer at 65536 Hz, 6 counts a step; Color's double speed doubles
    and a                   ; its 16384 Hz: 3)
    ld bc, (256 - 27 * 6) << 8 | 12
    jr z, .rate
    ld bc, (256 - 27 * 3) << 8 | 6
.rate:
    ld a, c
    ld [hPcmQ], a
    srl c
    ld a, b
    sub c
    ld [hPcmBias], a
    ld a, b
    add c
    ld [hPcmLateAt], a
    ld a, b
    ldh [rTMA], a
    ld a, $FF               ; (its first at once)
    ldh [rTIMA], a
    ldh a, [hIsCGB]
    and a
    ld a, %110
    jr z, .tac
    inc a
.tac:
    ldh [rTAC], a
    ldh a, [rIE]
    or %100
    ldh [rIE], a
    ei                      ; (off the fight no handler runs, VBlank only waking HALT: the timer's must)
    ret

; The fight's mixer (Color): the ring topped up, each buffer 32 steps of the crowd (wMixCrowd) with the triangle
; mixed in at its pitch (the NES's: its 32-step wave, CPU / (period + 1) steps a second), through MixTable. The
; ring's WRAMX bank (the second) in all the while; the crowd's 16 bytes fetched from the first with the timer held
; off (.fetch). A ring short of three buffers is topped up whatever the line: it never runs dry.
PcmProduceIn:
    ld a, [wMixStop]        ; (144, "fill it, whatever the line": the crowd just started, its ring empty; mid-frame,
    cp 144                  ;  a few buffers now -- the first at once -- and the rest at the frame's usual top-ups,
    jr nz, .more            ;  not all of them in one go: that ran a hundred lines on and dropped the frame)
    ldh a, [rLY]
    cp 144
    ld a, 20                ; (in VBlank: as its own top-up, to the screen's line 20)
    jr nc, .limit
    ldh a, [rLY]
    add 24
    cp 144
    jr c, .limit
    ld a, 143
.limit:
    ld [wMixStop], a
.more:
    ld a, [hPcmPtr]         ; (MIX_AHEAD bytes ready past where it plays: enough)
    ld b, a
    ld a, [wMixHead]
    sub b
    cp MIX_AHEAD
    ret nc
    cp 48
    jr c, .go               ; (under three buffers: one more, whatever the line)
    ld a, [wMixStop]
    ld c, a
    ldh a, [rLY]
    cp 144
    jr nc, .go              ; (VBlank's lines: room)
    cp c
    ret nc                  ; (another buffer would run on into VBlank: the rest next time)
.go:
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
.mix:                       ; pass 2: each with its crowd step (its high step first)
    ld a, [wMixCrowd]
    ld l, a
    ld a, [wMixCrowd + 1]
    ld h, a
    ld de, hMixSrc
    call .fetch
    call .fetch
    push hl
    ld bc, hMixSrc          ; ([DE] = MixTable[[DE] | the crowd's step], each)
    ld de, wMixTmp
    ld h, HIGH(MixTable)
.byte:
    ld a, [bc]
    swap a
    and $0F
    ld l, a
    ld a, [de]
    or l
    ld l, a
    ld a, [hl]
    ld [de], a
    inc e
    ld a, [bc]
    and $0F
    ld l, a
    ld a, [de]
    or l
    ld l, a
    ld a, [hl]
    ld [de], a
    inc e
    inc c
    ld a, c
    cp LOW(hMixSrc + 16)
    jr nz, .byte
    pop hl
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
    ld a, [wMixHead]        ; pass 3: packed into the ring, in order (its first 32 bytes past its end too)
    ld l, a
    ld h, HIGH(wMixRing)
    ld de, wMixTmp
    ld c, 16
.pack:
    ld a, [de]
    inc e
    swap a
    ld b, a
    ld a, [de]
    inc e
    or b
    ld [hl], a
    ld b, a
    ld a, l
    cp PCM_MIRROR
    jr nc, .packed
    inc h
    ld [hl], b
    dec h
.packed:
    inc l
    dec c
    jr nz, .pack
    ld a, l
    ld [wMixHead], a
    jp .more
.fetch:                     ; 8 of the crowd's bytes HL -> DE, from WRAMX's first bank (the timer's plays from the
    di                      ; second: held off the while, some 25 cycles)
    ld a, 1
    ldh [rSVBK], a
    REPT 8
        ld a, [hl+]
        ld [de], a
        inc e
    ENDR
    ld a, 2
    ldh [rSVBK], a
    reti
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
    inc bc                  ; inc = 348489 / (period + 1) (2048 a step, 1789773 / 10518 steps... a sample)
    ld hl, 0                ; (24 / 16 bits, by shifts: the quotient in DE)
    ld de, 0
    ld a, 24
    push af
    ld a, $05
    ld [wMixTmp], a         ; (348489 = $055149: its bytes, high first, into the scratch)
    ld a, $51
    ld [wMixTmp + 1], a
    ld a, $49
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
