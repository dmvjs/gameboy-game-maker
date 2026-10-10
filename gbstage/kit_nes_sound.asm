; ==== Punch-Out!!'s sound engine (PRG bank 8 + the fixed bank's tables), line for line ===============
; NesSound runs once a frame, as the NES game's frame does ($A68D): it reads the requests the fight code
; leaves at $F0-$F3 (SQ1 effect, SQ2 effect, music, DMC sample) and writes the NES's sound registers, here
; a shadow copy (wApu = $4000-$4017). ApuOut then plays that shadow on the Game Boy: the NES's envelopes,
; length counters and sweeps run here in software (two half-frame and four quarter-frame clocks a frame,
; as the game's $C0 to $4017 each frame makes them), and the result goes to the GB's pulse, wave
; (triangle) and noise channels. Proven against the original code by gbstage/nestests.py.
;
; Bank 8 sits verbatim at $4000 (NesSnd: NES $8000 -> GB $4000, so its music pointers are NES addresses
; less $4000); the fixed bank's $F400-$F8FF follows as NesSndFix.

DEF SND_DELTA EQU $40       ; NES bank 8 pointer high byte -> GB

; the fixed bank's tables (NES $F400 + offset)
DEF NotesTbl EQUS "(NesSndFix + $013C)"
DEF NoteLengthsTbl EQUS "(NesSndFix + $01BC)"
DEF SQDCEnvTbl EQUS "(NesSndFix + $0274)"
DEF NoiseDecayTbl EQUS "(NesSndFix + $0314)"
DEF NoiseDatTbl EQUS "(NesSndFix + $033C)"
DEF DMCSamplePtrTbl EQUS "(NesSndFix + $0368)"
DEF FallSweepTbl EQUS "(NesSndFix + $0376)"
DEF PnchMs1Tbl EQUS "(NesSndFix + $037E)"
DEF PnchMs2Tbl EQUS "(NesSndFix + $038E)"
DEF Talk1CntrlTbl EQUS "(NesSndFix + $0398)"
DEF Talk1NoteTbl EQUS "(NesSndFix + $039C)"
DEF Talk2NoteTbl EQUS "(NesSndFix + $03AC)"
DEF Talk3NoteTbl EQUS "(NesSndFix + $03BC)"
DEF RefCtrlTbl EQUS "(NesSndFix + $03CC)"   ; $F7CC: the referee's voice, SQ1 control
DEF RefNoteTbl EQUS "(NesSndFix + $03EB)"   ; $F7EB: and its timer low
DEF DodgeTbl EQUS "(NesSndFix + $0409)"     ; $F809
DEF Fall2SweepTbl EQUS "(NesSndFix + $040F)"
DEF StarTimeTbl EQUS "(NesSndFix + $0416)"
DEF StarNoteTbl EQUS "(NesSndFix + $041A)"
DEF MagicLoTbl EQUS "(NesSndFix + $041E)"
DEF MagicTimeTbl EQUS "(NesSndFix + $0422)"
DEF MagicVolTbl EQUS "(NesSndFix + $042E)"
DEF MagicCtrlATbl EQUS "(NesSndFix + $0435)"
DEF MagicCtrlBTbl EQUS "(NesSndFix + $0445)"
DEF MagicHiTbl EQUS "(NesSndFix + $0454)"
DEF Honk2CtrlTbl EQUS "(NesSndFix + $0458)"
; bank 8's
DEF MusSeqIndexTbl EQUS "(NesSnd + $1000)"
DEF MusicInitTbl1 EQUS "(NesSnd + $1069)"
DEF MusicInitTbl2 EQUS "(NesSnd + $10DE)"

; sound RAM (NES addresses)
DEF nSFXInitSQ1 EQU $F0
DEF nSFXInitSQ2 EQU $F1
DEF nMusicInit EQU $F2
DEF nDMCInit EQU $F3
DEF nSFXIndexSQ1 EQU $F4
DEF nSFXIndexSQ2 EQU $F5
DEF nMusicIndex EQU $F6
DEF nDMCIndex EQU $F7
DEF nMusicPtr EQU $F8
DEF nSQ2NoteIndex EQU $FC
DEF nSQ1NoteIndex EQU $FD
DEF nSQ2NoteRemain EQU $0700
DEF nSQ1NoteRemain EQU $0701
DEF nTriNoteRemain EQU $0702
DEF nNoiseNoteRemain EQU $0703
DEF nSQ2NoteLength EQU $0704
DEF nSQ1NoteLength EQU $0705
DEF nTriNoteLength EQU $0706
DEF nNoiseNoteLength EQU $0707
DEF nSQ2EnvIndex EQU $0708
DEF nSQ1EnvIndex EQU $0709
DEF nMusSeqBase EQU $070A
DEF nMusSeqIndex EQU $070B
DEF nNoiseIndexReload EQU $070C
DEF nNoteLengthsBase EQU $070D
DEF nSQ1SweepCntrl EQU $070E
DEF nSQ1LoFreq EQU $070F
DEF nSQ2LoFreq EQU $0710
DEF nVibratoLo EQU $0711
DEF nSQ1SFXTimer EQU $0712
DEF nSQ1SFXByte EQU $0713
DEF nSQ2SFXTimer EQU $0715
DEF nSQ2SFXByte1 EQU $0716
DEF nSQ2SFXByte2 EQU $0717
DEF nSQ2ShortPause EQU $0718
DEF nSQ1ShortPause EQU $0719
DEF nSQ2Restart EQU $071A
DEF nSQ1Restart EQU $071B
DEF nSQ2EnvBase EQU $071C
DEF nSQ1EnvBase EQU $071D
DEF nDMCLaughLength EQU $071E
DEF nDMCLghAudLength EQU $071F
DEF nNoiseVolIndex EQU $0720
DEF nNoiseBeatType EQU $0721
DEF nTriNoteIndex EQU $0722
DEF nNoiseMusicIndex EQU $0723
DEF nNoiseInUse EQU $0724
DEF nSQ2InUse EQU $0725
DEF nSQ1InUse EQU $0726
DEF nMagicFlip EQU $0728
DEF nMagicStep EQU $0729
DEF nTriMidBlip EQU $072A
DEF nTriFrontBlip EQU $072B
DEF nTriBlipType EQU $072C

SECTION "NES sound registers", WRAM0, ALIGN[7]   ; (all in one page)
wApu:: ds $18               ; $4000-$4017 as last written
wApuNew:: ds 5              ; writes ApuOut hasn't taken yet: $4001/$4003, $4005/$4007, $400B, $400F, $4015
                            ; (each the value written; the game never writes 0 to these)
; ApuOut's NES side: per pulse (0, 1) and noise (2): envelope volume, divider, start; length counter
wEnv: ds 9                  ; per envelope (pulse 1, pulse 2, noise): start, volume, divider
wApuLength: ds 4            ; pulse 1, pulse 2, triangle, noise
wApuSweepDiv: ds 2
wApuSweepReload: ds 2
wApuLinear: db              ; the triangle's linear counter
wApuLinReload: db
wApuStart: ds 4             ; a channel restarted this frame
wApuPeriod: ds 4            ; the pulses' timers as the NES has them (its sweeps move them; a write sets them)
wApuSeenLo: ds 2            ; the $4002/$4006 we last saw (a change is a write)
wDmcSample: db              ; the DMC sample playing (1-7, 0: none), on the GB's noise channel when it's free
wDmcFrame: db               ; its frame
wDmcLoop: db                ; it repeats ($4010 bit 6)
wTicks: db
wSwCtl: db                  ; SweepCalc's: the pulse's $4001, period, target
wSwPeriod: dw
wSwTarget: dw
; and what the Game Boy was last given: per channel volume (pulse, pulse, wave on/off, noise), frequency
wGbVol: ds 4
wGbFreq: ds 6               ; pulse 1, pulse 2, wave (low, high each)
wGbDuty: ds 2
wGbNoise: db
wGbPer: ds 4                ; the pulse timers last converted
wGbPerFreq: ds 4            ; and their GB frequencies
wApuEnd:

; A to NES sound register \1, noting the writes ApuOut reacts to.
MACRO apu
    ld [wApu + (\1)], a
    IF (\1) == $15
        ld [wApuNew + 4], a
    ELIF (\1) < $10 && (((\1) & 3) == 3 || ((\1) < 8 && ((\1) & 3) == 1))
        IF ((\1) & 3) == 3
            ld [wApuNew + ((\1) >> 2)], a
        ENDC
        IF ((\1) & 3) == 1
            ld [wApuSweepReload + ((\1) >> 2)], a
        ENDC
    ENDC
ENDM

; A = table \1 [A]
MACRO tbl
    ld hl, \1
    add l
    ld l, a
    adc h
    sub l
    ld h, a
    ld a, [hl]
ENDM

;;PART sound

; ---- the frame ($8000) -------------------------------------------------------------------------------
NesSound::
    call SoundEngine
    jp ApuOut

SoundEngine::
    ld a, $C0               ; the frame counter: 5-step, restarted
    apu $17
    call PlayDMC
    call PlaySQ1
    call PlaySQ2
    call PlayMusic
    xor a
    ld [wNes + nSFXInitSQ1], a
    ld [wNes + nSFXInitSQ2], a
    ld [wNes + nMusicInit], a
    ld [wNes + nDMCInit], a
    ret

; ---- the fixed bank's helpers ($F400-$F53B) ------------------------------------------------------------

; $F400: A = the note length for this byte (its low 5 bits, from this music's base). Uses HL.
NoteLength:
    and $1F
    ld hl, wNes + nNoteLengthsBase
    add [hl]
    tbl NoteLengthsTbl
    ret

; $F40B: B to $4000, C to $4001.
SetSQ1Control:
    ld a, b
    apu $00
    ld a, c
    apu $01
    ret

; $F412 / $F414: B to $4004, C ($7F: sweep off) to $4005.
SQ2CntrlSwpDis:
    ld c, $7F
SetSQ2Control:
    ld a, b
    apu $04
    ld a, c
    apu $05
    ret

; $F41B, $F41E, $F422, $F426, $F429: A = note.
UpdateSQ2:
    push af
    call SetSQ2Control
    pop af
UpdateSQ2Note:
    ld e, 4
    jr ChannelNote
UpdateTriNote:
    ld e, 8
    jr ChannelNote
UpdateSQ1:
    push af
    call SetSQ1Control
    pop af
UpdateSQ1Note:
    ld e, 0
; $F42B: note A (NotesTbl: high, low) to the channel at E (0, 4, 8). Z: no note (low 0). Keeps BC.
ChannelNote:
    push bc
    ld c, e
    ld e, a
    ld d, 0
    ld hl, NotesTbl
    add hl, de
    ld d, [hl]              ; high
    inc hl
    ld a, [hl]              ; low
    and a
    jr z, .done
    ld b, a
    ld a, c
    and a
    jr nz, .sq2
    ld a, b
    ld [wNes + nSQ1LoFreq], a
    apu $02
    ld a, d
    or $08
    apu $03
    jr .done
.sq2:
    cp 4
    jr nz, .tri
    ld a, b
    ld [wNes + nSQ2LoFreq], a
    apu $06
    ld a, d
    or $08
    apu $07
    jr .done
.tri:
    ld a, b
    apu $0A
    ld a, d
    or $08
    apu $0B
.done:                      ; (Z from the low byte, or NZ from the high byte's OR)
    pop bc
    ret

; $F44D-$F450: the logarithmic sweeps. A = C less (A >> n, at least 1); carry as the 6502's SBC leaves it
; (set: no borrow). $E0 holds the step.
LogDiv32:
    srl a
LogDiv16:
    srl a
LogDiv8:
    srl a
    srl a
    srl a
    jr nz, .some
    inc a
.some:
    ld [wNes + $E0], a
    ld b, a
    ld a, c
    sub b
    ccf
    ret

; $F45E-$F493: vibrato: the channel's timer low a step either side of the note, by bit 2 of A (a timer).
; $F463: SQ1, from its note time; if SQ1's note low is 0, the SQ2 code runs instead (the game's way).
VibratoSQ1:
    ld a, [wNes + nSQ1NoteRemain]
    ld b, a
    ld a, [wNes + nSQ1LoFreq]
    and a
    jr z, VibratoSQ2Timer
    ld c, $00
    jr Vibrato
VibratoSQ2Timer:            ; $F46D
    ld a, [wNes + nSQ2SFXTimer]
    and a
    jr nz, .t
    ld a, [wNes + nSQ2NoteRemain]
.t:
    ld b, a
    jr VibratoSQ2.go
VibratoSQ2:                 ; $F472
    ld a, [wNes + nSQ2NoteRemain]
    ld b, a
.go:
    ld c, $04
    ld a, [wNes + nSQ2LoFreq]
Vibrato:                    ; B = timer, C = channel, A = the note's low byte
    ld [wNes + nVibratoLo], a
    ld d, a
    bit 2, b
    jr nz, .up
    dec a                   ; low - 1, or + 1 where that's 0
    jr nz, .set
.up:
    ld a, d
    inc a
.set:
    ld b, a
    ld a, c
    and a
    ld a, b
    jr nz, .sq2
    apu $02
    ret
.sq2:
    apu $06
    ret

; $F494: the bells and the referee: SQ1 effect A frames long, index C; both squares, sweeps off.
InitBellSFX:
    ld [wNes + nSQ1SFXTimer], a
    ld a, c
    ld [wNes + nSFXIndexSQ1], a
    xor a
    ld [wNes + nSQ1InUse], a
    ld a, $7F
    apu $01
    apu $05
    call FreeNoise
    ld a, 1
    ld [wNes + nSQ2InUse], a
    ld a, [wNes + nSFXIndexSQ1]
    cp $0C
    ret z
    cp $15
    ret z
    ld a, $0A
    apu $03
    apu $07
    ret

; $F4CD: A to $4000, and A - 3 (at least $90) to $4004.
RefCtrl:
    apu $00
    sub 3
    cp $90
    jr nc, .ok
    ld a, $90
.ok:
    apu $04
    ret

; $F4DD: A to $4002, and A - $0A (or 0) to $4006.
RefNote:
    apu $02
    cp $0A
    jr nc, .sub
    xor a
    jr .set
.sub:
    sub $0A
.set:
    apu $06
    ret

; the noise channel back from an effect ($F4F9 and others)
FreeNoise:
    ld a, [wNes + nNoiseInUse]
    and a
    ret z
    ld a, $10
    apu $0C
    xor a
    ld [wNes + nNoiseInUse], a
    ret

; and SQ2
FreeSQ2:
    ld a, [wNes + nSQ2InUse]
    and a
    ret z
    ld a, $10
    apu $04
    xor a
    ld [wNes + nSQ2InUse], a
    ret

; $F4EF: an SQ1 effect A frames long, index C.
InitSQ1SFX:
    ld [wNes + nSQ1SFXTimer], a
    ld a, c
    ld [wNes + nSFXIndexSQ1], a
    ld a, 1
    ld [wNes + nSQ1InUse], a
    call FreeNoise
    jr FreeSQ2

; $F518: an effect on the noise channel, A frames long, index C; SQ1 quiet.
InitNoiseSFX:
    ld [wNes + nSQ1SFXTimer], a
    ld a, c
    ld [wNes + nSFXIndexSQ1], a
    xor a
    ld [wNes + nSQ1InUse], a
    call FreeSQ2
    ld a, $10
    apu $00
    ld a, 1
    ld [wNes + nNoiseInUse], a
    ret

; Which routine of a player's table runs ($80CE and on): the requested effect C starts unless the one
; playing (A) comes first in the game's checks (both ascending), else the one playing continues.
; B = the last index. Returns: Z clear and A = index, carry set to start; Z set: nothing.
Dispatch:
    ld d, a
    ld a, c
    and a
    jr z, .cont
    cp b
    jr z, .startOk
    jr nc, .cont
.startOk:
    ld a, d                 ; playing one first?
    and a
    jr z, .start
    cp b
    jr z, .le
    jr nc, .start
.le:
    cp c
    jr c, .cont
.start:
    ld a, c
    or a                    ; (NZ)
    scf
    ret
.cont:
    ld a, d
    and a
    ret z
    cp b
    jr z, .go
    jr nc, .none
.go:
    and a                   ; (NZ, carry clear)
    ret
.none:
    xor a
    ret

; jump to routine A of table HL (2 bytes each, from index 1)
JumpTable:
    dec a
    add a
    add l
    ld l, a
    adc h
    sub l
    ld h, a
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    jp hl

; ---- DMC samples ($8025) -------------------------------------------------------------------------------
PlayDMC:
    ld a, [wNes + nDMCInit]
    bit 7, a
    jr nz, DMCDone
    and a
    jr nz, DMCInit
    ld a, [wNes + nDMCIndex]
    cp 1                    ; the crowd: it repeats on its own
    ret z
    and a
    jr z, DMCDisable
    ld hl, wNes + nDMCLaughLength
    dec [hl]
    jr z, .nextLaugh
    ld hl, wNes + nDMCLghAudLength
    dec [hl]
    jr z, DMCDisable
    ret
.nextLaugh:                 ; $801C
    ld a, [wNes + nDMCIndex]
    cp 6
    jr nc, DMCDone
    inc a
    ld [wNes + nDMCInit], a
    jr PlayDMC
DMCInit:                    ; $8040
    ld [wNes + nDMCIndex], a
    ld c, a
    ld a, $0E
    ld [wNes + nDMCLaughLength], a
    ld a, c
    cp 7
    ld a, 5
    jr nz, .len
    ld a, 3
.len:
    ld [wNes + nDMCLghAudLength], a
    ld a, c
    add a
    sub 2
    ld e, a
    ld d, 0
    ld hl, DMCSamplePtrTbl
    add hl, de
    ld a, [hl+]
    apu $12
    ld a, [hl]
    apu $13
    ld a, c
    cp 1
    ld a, $4F               ; the crowd repeats
    jr z, .rate
    ld a, $0F
.rate:
    apu $10
    ld a, $0F
    apu $15
    ld a, $1F
    apu $15
    ret
DMCDone:
    xor a
    ld [wNes + nDMCIndex], a
DMCDisable:
    ld a, $0F
    apu $15
    ret

; ---- SQ1 effects ($80CA) -------------------------------------------------------------------------------
PlaySQ1:
    ld a, [wNes + nSFXInitSQ1]
    bit 7, a
    jp nz, SilenceSQ1SFX
    ld c, a
    ld a, [wNes + nSFXIndexSQ1]
    ld b, $18
    call Dispatch
    ret z
    ld hl, SQ1Starts
    jr c, .go
    ld hl, SQ1Conts
.go:
    jp JumpTable

SQ1Starts:
    dw SQ1IntroPunchInit, SQ1FallInit, SQ1Punch1Init, SQ1BlockInit, SQ1OppPunchInit, SQ1Miss1Init
    dw SQ1Miss2Init, SQ1Punch2Init, SQ1Talk1Init, SQ1Talk23Init, SQ1Talk23Init, SQ1Bell1Init
    dw SQ1FightInit, SQ1KOInit, SQ1TKOInit, SQ1CountInit, SQ1DodgeInit, SQ1DigitInit
    dw SQ1Punch3Init, SQ1BeepInit, SQ1Bell3Init, SQ1StarInit, SQ1HippoInit, SQ1HoleInit
SQ1Conts:
    dw SQ1IntroPunchCont, SQ1FallCont, SQ1Punch1Cont, FinishSQ1SFX, SQ1OppPunchCont, SQ1Miss1Cont
    dw SQ1Miss2Cont, FinishSQ1SFX, SQ1Talk1Cont, SQ1Talk1Cont, SQ1Talk1Cont, SQ1Bell1Cont
    dw SQ1RefCont, SQ1RefCont, SQ1RefCont, SQ1RefCont, SQ1DodgeCont, FinishSQ1SFX
    dw SQ1Punch3Cont, SQ1BeepCont, SQ1Bell3Cont, SQ1StarCont, SQ1HippoCont, FinishSQ1SFX

; the rotate that makes a timer from an effect's byte: A (and carry) -> $4002 after \1 ROLs, then the
; next ROL's low bits (AND \2) | 8 -> $4003
MACRO timer_rol
    REPT \1
        rla
    ENDR
    apu \3 + 2
    rla
    and \2
    or $08
    apu \3 + 3
ENDM

SQ1IntroPunchInit:          ; $8085
    ld a, $40
    call InitSQ1SFX
    ld a, $1A
    ld [wNes + nSQ1SFXByte], a
    ld bc, $9F83
    call SetSQ1Control
SQ1IntroPunchCont:
    ld a, [wNes + nSQ1SFXTimer]
    cp $40
    jr nc, .step
    srl a
    srl a
    or $90
    apu $00
.step:
    ld a, [wNes + nSQ1SFXTimer]
    and $07
    jp nz, FinishSQ1SFX
    ld a, [wNes + nSQ1SFXByte]
    swap a
    and $0F
    ld hl, wNes + nSQ1SFXByte
    scf
    adc [hl]
    ld [hl], a
    timer_rol 3, $07, $00
    jp FinishSQ1SFX

SQ1FallInit:                ; $80EB
    ld a, $7F
    call InitSQ1SFX
    ld bc, $9C7F
    ld a, $62
    call UpdateSQ1
SQ1FallCont:
    ld a, [wNes + nSQ1SFXTimer]
    cp $6C
    jp z, FinishSQ1SFX
    jr c, .second
    and $07
    tbl FallSweepTbl
    apu $01
    jp FinishSQ1SFX
.second:
    cp $6B
    jr nz, .vol
    ld a, $A5
    apu $01
    ld a, [wNes + nSQ1SFXTimer]
.vol:
    cp $30
    jp nc, FinishSQ1SFX
    srl a
    srl a
    or $90
    apu $00
    jp FinishSQ1SFX

SQ1Punch1Init:              ; $8124
    ld a, $16
    call InitSQ1SFX
    ld bc, $5F8B
    ld a, $12
    call UpdateSQ1
SQ1Punch1Cont:
    ld a, [wNes + nSQ1SFXTimer]
    cp $10
    jp nc, FinishSQ1SFX
    or $50
    apu $00
    ; fall through
; $813E
FinishSQ1SFX:
    ld hl, wNes + nSQ1SFXTimer
    dec [hl]
    ret nz
SilenceSQ1SFX:
    call FreeNoise
    call FreeSQ2
    xor a
    ld [wNes + nSQ1InUse], a
    ld [wNes + nSFXIndexSQ1], a
    ld a, $10
    apu $00
    ret

SQ1BlockInit:               ; $8170
    ld a, $04
    call InitNoiseSFX
    ld a, $08
    apu $0F
    ld a, $0A
    apu $0E
    ld a, $1A
    apu $0C
    ld bc, $DA85
    ld a, $24
    call UpdateSQ1
    jp FinishSQ1SFX

SQ1OppPunchInit:            ; $8190
    ld a, $20
    call InitSQ1SFX
    ld a, $FF
    ld [wNes + nSQ1SFXByte], a
    ld bc, $1E81
    call SetSQ1Control
SQ1OppPunchCont:
    ld a, [wNes + nSQ1SFXByte]
    ld c, a
    call LogDiv8
    ld [wNes + nSQ1SFXByte], a
    timer_rol 2, $03, $00
    ld a, [wNes + nSQ1SFXTimer]
    cp $0E
    jp nc, FinishSQ1SFX
    or $90
    apu $00
    jp FinishSQ1SFX

SQ1Miss1Init:               ; $81F2
    ld a, $10
    call InitNoiseSFX
SQ1Miss1Cont:
    ld a, [wNes + nSQ1SFXTimer]
    tbl PnchMs1Tbl - 1
; $81FD: noise from a table byte: low nibble the period, high nibble the volume
NoiseData:
    ld b, a
    and $0F
    apu $0E
    ld a, b
    swap a
    and $0F
    or $10
    apu $0C
    ld a, $08
    apu $0F
    jp FinishSQ1SFX

SQ1Miss2Init:               ; $8215
    ld a, $0A
    call InitNoiseSFX
SQ1Miss2Cont:
    ld a, [wNes + nSQ1SFXTimer]
    tbl PnchMs2Tbl - 1
    jr NoiseData

SQ1Punch2Init:              ; $8222
    ld a, $10
    call InitSQ1SFX
    ld bc, $4384
    ld a, $4C
    call UpdateSQ1
    jp FinishSQ1SFX

SQ1Talk1Init:               ; $8233
    ld a, $04
    call InitSQ1SFX
    ld a, $7F
    apu $01
    ld hl, wNes + nSQ1SFXByte
    inc [hl]
    ld a, [hl]
    and $0F
    tbl Talk1NoteTbl
    call UpdateSQ1Note
SQ1Talk1Cont:
    ld a, [wNes + nSQ1SFXTimer]
    tbl Talk1CntrlTbl - 1
    apu $00
    jp FinishSQ1SFX

SQ1Talk23Init:              ; $8258
    ld a, $04
    call InitSQ1SFX
    ld a, $BC
    apu $01
    ld hl, wNes + nSQ1SFXByte
    inc [hl]
    ld a, [hl]
    and $0F
    ld b, a
    ld a, [wNes + nSFXIndexSQ1]
    cp $0B
    jr z, .talk3
    ld a, b
    tbl Talk2NoteTbl
    and a
    jr nz, .note
.talk3:
    ld a, b
    tbl Talk3NoteTbl
.note:
    call UpdateSQ1Note
    jr SQ1Talk1Cont

SQ1Bell1Init:               ; $82A2
    ld a, $40
BellStart:                  ; $82A4 (A = frames, C = index)
    call InitBellSFX
    ld a, $88
    apu $00
    apu $04
    ld a, $58
    call UpdateSQ1Note
    ld a, $22
    apu $06
    ld a, $08
    apu $07
SQ1Bell1Cont:               ; $82BE
    ld a, [wNes + nSQ1SFXTimer]
    cp $28
    jp nz, FinishSQ1SFX
    ld a, $8F
    apu $00
    apu $04
    jp FinishSQ1SFX

SQ1FightInit:               ; $82D0
    ld a, $0F
    call InitBellSFX
    xor a
    jr RefStart
SQ1KOInit:                  ; $82F2
    ld a, $12
    call InitBellSFX
    ld a, $08
    jr RefStart
SQ1TKOInit:                 ; $82FE
    ld a, $1E
    call InitBellSFX
    ld a, $08
    jr RefStart
SQ1CountInit:               ; $830A
    ld a, $0C
    call InitBellSFX
    ld a, $18
RefStart:
    ld [wNes + nSQ1SFXByte], a
SQ1RefCont:                 ; $82DA
    ld a, [wNes + nSQ1SFXTimer]
    srl a
    ld hl, wNes + nSQ1SFXByte
    add [hl]
    ld b, a
    tbl RefCtrlTbl
    call RefCtrl
    ld a, b
    tbl RefNoteTbl
    call RefNote
    jp FinishSQ1SFX

SQ1DodgeInit:               ; $8359
    ld a, $05
    call InitNoiseSFX
SQ1DodgeCont:
    ld a, [wNes + nSQ1SFXTimer]
    tbl DodgeTbl
    jp NoiseData

SQ1DigitInit:               ; $8367
    ld a, $20
    call InitSQ1SFX
    ld bc, $987F
    ld a, $64
    call UpdateSQ1
    jp FinishSQ1SFX

SQ1Punch3Init:              ; $8378
    ld a, $12
    call InitSQ1SFX
    ld bc, $5F8B
    ld a, $0E
    call UpdateSQ1
SQ1Punch3Cont:
    ld a, [wNes + nSQ1SFXTimer]
    cp $0C
    jp nc, FinishSQ1SFX
    or $50
    apu $00
    jp FinishSQ1SFX

SQ1BeepInit:                ; $8395
    ld a, $06
    call InitSQ1SFX
    ld bc, $957F
    ld a, $4A
    call UpdateSQ1
SQ1BeepCont:
    ld a, [wNes + nSQ1SFXTimer]
    cp $03
    jp nz, FinishSQ1SFX
    ld a, $42
    call UpdateSQ1Note
    jp FinishSQ1SFX

SQ1Bell3Init:               ; $83B2
    ld a, $04
    ld [wNes + nSQ1SFXByte], a
.ring:
    ld a, $18
    ld c, $15
    jp BellStart
SQ1Bell3Cont:
    ld a, [wNes + nSQ1SFXTimer]
    cp $01
    jp nz, SQ1Bell1Cont
    ld hl, wNes + nSQ1SFXByte
    dec [hl]
    jr nz, SQ1Bell3Init.ring
    jp SQ1Bell1Cont

SQ1StarInit:                ; $83CD
    ld a, $24
    call InitSQ1SFX
.again:                     ; $83D2
    ld hl, wNes + nSQ1SFXTimer
    dec [hl]
    ld a, $8F
    ld [wNes + nSQ1SFXByte], a
    ld bc, $9C82
    call SetSQ1Control
SQ1StarCont:
    ld a, [wNes + nSQ1SFXTimer]
    cp $12
    jr z, SQ1StarInit.again
    ld a, [wNes + nSQ1SFXByte]
    ld c, a
    call LogDiv16
    ld [wNes + nSQ1SFXByte], a
    timer_rol 2, $03, $00
    jp FinishSQ1SFX

SQ1HippoInit:               ; $8423
    ld a, $10
    call InitSQ1SFX
    ld bc, $82A2
    ld a, $56
    call UpdateSQ1
SQ1HippoCont:
    ld a, [wNes + nSQ1SFXTimer]
    cp $0E
    jp nz, FinishSQ1SFX
    ld a, $3E
    call UpdateSQ1Note
    jp FinishSQ1SFX

SQ1HoleInit:                ; $8440
    ld a, $20
    call InitNoiseSFX
    ld a, $09
    apu $0C
    ld a, $0F
    apu $0E
    ld a, $08
    apu $0F
    ld a, $0F
    apu $08
    xor a
    apu $0A
    ld a, $09
    apu $0B
    jp FinishSQ1SFX

; ---- SQ2 effects ($84B1) -------------------------------------------------------------------------------
PlaySQ2:
    ld a, [wNes + nSQ2InUse]
    and a
    jr z, .free
    xor a
    ld [wNes + nSFXIndexSQ2], a
    ret
.free:
    ld a, [wNes + nSFXInitSQ2]
    bit 7, a
    jp nz, SilenceSQ2SFX
    ld c, a
    ld a, [wNes + nSFXIndexSQ2]
    ld b, $15
    call Dispatch
    ret z
    ld hl, SQ2Starts
    jr nc, .cont
    ld [wNes + nSFXIndexSQ2], a     ; every start: STY SFXIndexSQ2
    ld b, a
    jp JumpTable
.cont:
    ld hl, SQ2Conts
    jp JumpTable

SQ2Starts:
    dw SQ2IntroPunchInit, SQ2FallInit, SQ2StarInit, SQ2Honk1Init, SQ2Honk2Init, SQ2Punch6Init
    dw SQ2Punch7Init, SQ2Punch8Init, SQ2Punch9Init, SQ2PunchAInit, SQ2Spring1Init, SQ2PunchCInit
    dw SQ2Punch4Init, SQ2StunInit, SQ2TigerInit, SQ2MagicInit, SQ2Punch11Init, SQ2MachoInit
    dw SQ2HippoInit, SQ2WindUpInit, SQ2Spring2Init
SQ2Conts:
    dw SQ2IntroPunchCont, SQ2FallCont, SQ2StarCont, SQ2Honk1Cont, SQ2Honk2Cont, FinishSQ2SFX
    dw SQ2Punch7Cont, FinishSQ2SFX, SQ2Punch9Cont, SQ2PunchACont, FinishSQ2SFX, SQ2PunchCCont
    dw FinishSQ2SFX, SQ2StunCont, SQ2TigerCont, SQ2MagicCont, SQ2Punch11Cont, SQ2MachoCont
    dw SQ2HippoCont, SQ2WindUpCont, FinishSQ2SFX

; $8466: every 8th frame, the punch's byte grows (by its high nibble, plus 1) into SQ2's timer.
SQ2Rise:
    ld a, [wNes + nSQ2SFXTimer]
    and $07
    ret nz
    ld a, [wNes + nSQ2SFXByte1]
    swap a
    and $0F
    ld hl, wNes + nSQ2SFXByte1
    scf
    adc [hl]
    ld [hl], a
    timer_rol 3, $07, $04
    ret

SQ2IntroPunchInit:          ; $848A
    ld a, $40
    ld [wNes + nSQ2SFXTimer], a
    ld a, $1A
    ld [wNes + nSQ2SFXByte1], a
    ld bc, $9F83
    call SetSQ2Control
SQ2IntroPunchCont:
    ld a, [wNes + nSQ2SFXTimer]
    cp $40
    jr nc, .rise
    srl a
    srl a
    or $90
    apu $04
.rise:
    call SQ2Rise
    ; fall through
; $8514
FinishSQ2SFX:
    ld hl, wNes + nSQ2SFXTimer
    dec [hl]
    ret nz
SilenceSQ2SFX:
    xor a
    ld [wNes + nSFXIndexSQ2], a
    ld a, $10
    apu $04
    ret

SQ2FallInit:                ; $84DC
    ld a, $7F
    ld [wNes + nSQ2SFXTimer], a
    ld bc, $9C7F
    ld a, $62
    call UpdateSQ2
SQ2FallCont:
    ld a, [wNes + nSQ2SFXTimer]
    cp $6C
    jp z, FinishSQ2SFX
    jr c, .second
    and $07
    tbl Fall2SweepTbl
    apu $05
    jp FinishSQ2SFX
.second:
    cp $6B
    jr nz, .vol
    ld a, $A5
    apu $05
    ld a, [wNes + nSQ2SFXTimer]
.vol:
    cp $30
    jp nc, FinishSQ2SFX
    srl a
    srl a
    or $90
    apu $04
    jp FinishSQ2SFX

SQ2StarInit:                ; $8523
    ld a, $10
    ld [wNes + nSQ2SFXTimer], a
    ld a, $04
    ld [wNes + nSQ2SFXByte1], a
SQ2StarCont:
    ld a, [wNes + nSQ2SFXByte1]
    tbl StarTimeTbl
    ld b, a
    ld a, [wNes + nSQ2SFXTimer]
    cp b
    jp nz, FinishSQ2SFX
    ld b, $84
    call SQ2CntrlSwpDis
    ld a, [wNes + nSQ2SFXByte1]
    tbl StarNoteTbl
    apu $06
    ld a, $08
    apu $07
    ld hl, wNes + nSQ2SFXByte1
    dec [hl]
    jp FinishSQ2SFX

SQ2Honk1Init:               ; $8553
    ld a, $20
    ld [wNes + nSQ2SFXTimer], a
    ld bc, $1ACD
    ld a, $42
    jr SQ2Note
SQ2Honk1Cont:
    ld a, [wNes + nSQ2SFXTimer]
    cp $18
    jp nz, FinishSQ2SFX
    ld bc, $94C5
    ld a, $50
SQ2Note:                    ; $856F
    call UpdateSQ2
    jp FinishSQ2SFX

SQ2Honk2Init:               ; $8575
    ld a, $10
    ld [wNes + nSQ2SFXTimer], a
    ld a, $38
    jr SQ2Honk2.note
SQ2Honk2Cont:
    ld a, [wNes + nSQ2SFXTimer]
    cp $0C
    jr nz, SQ2Honk2.vol
    ld a, $44
SQ2Honk2:
.note:                      ; $8589
    ld b, a
    ld a, $CD
    apu $05
    ld a, b
    call UpdateSQ2Note
.vol:                       ; $8591
    ld a, [wNes + nSQ2SFXTimer]
    tbl Honk2CtrlTbl
    apu $04
    jp FinishSQ2SFX

SQ2Punch6Init:              ; $859D
    ld a, $10
    ld [wNes + nSQ2SFXTimer], a
    ld bc, $4384
    ld a, $4C
    jr SQ2Note

SQ2Punch7Init:              ; $85DB
    ld a, $16
    ld [wNes + nSQ2SFXTimer], a
    ld bc, $5F8B
    ld a, $0E
    call UpdateSQ2
SQ2Punch7Cont:
    ld a, [wNes + nSQ2SFXTimer]
    cp $10
    jp nc, FinishSQ2SFX
    or $50
    apu $04
    jp FinishSQ2SFX

SQ2Punch8Init:              ; $85FA
    ld a, $10
    ld [wNes + nSQ2SFXTimer], a
    ld bc, $8585
    ld a, $1C
    jr SQ2Note

SQ2Punch9Init:              ; $860D
    ld a, $20
    ld [wNes + nSQ2SFXTimer], a
    ld a, $8F
    ld [wNes + nSQ2SFXByte1], a
    ld bc, $5D81
    call SetSQ2Control
SQ2Punch9Cont:
    ld a, [wNes + nSQ2SFXByte1]
    ld c, a
    call LogDiv16
    ld [wNes + nSQ2SFXByte1], a
SQ2Punch9Timer:             ; $862A
    timer_rol 2, $03, $04
    ld a, [wNes + nSQ2SFXTimer]
    cp $0D
    jp nc, FinishSQ2SFX
    or $90
    apu $04
    jp FinishSQ2SFX

SQ2PunchAInit:              ; $8646
    ld a, $10
    ld [wNes + nSQ2SFXTimer], a
    ld a, $FF
    ld [wNes + nSQ2SFXByte1], a
    ld bc, $5D81
    call SetSQ2Control
SQ2PunchACont:
    ld a, [wNes + nSQ2SFXByte1]
    ld c, a
    call LogDiv8
    ld [wNes + nSQ2SFXByte1], a
    jr SQ2Punch9Timer

SQ2Spring1Init:             ; $8681
    ld a, $18
    ld [wNes + nSQ2SFXTimer], a
    ld bc, $C8CC
    ld a, $34
    jp SQ2Note

SQ2PunchCInit:              ; $8694
    ld a, $0C
    ld [wNes + nSQ2SFXTimer], a
    ld bc, $03C5
    call SetSQ2Control
    ld a, $38
    jp SQ2Note
SQ2PunchCCont:
    ld a, [wNes + nSQ2SFXTimer]
    cp $08
    jp nz, FinishSQ2SFX
    ld bc, $02CC
    call SetSQ2Control
    ld a, $48
    jp SQ2Note

SQ2Punch4Init:              ; $86BC
    ld a, $10
    ld [wNes + nSQ2SFXTimer], a
    ld bc, $88D3
    ld a, $1C
    call UpdateSQ2
    ld a, $3A
    call UpdateTriNote
    ld a, $1C
    apu $08
    jp FinishSQ2SFX

SQ2StunInit:                ; $86FC
    ld a, $0A
    ld [wNes + nSQ2SFXTimer], a
    ld a, $1A
    ld [wNes + nSQ2SFXByte1], a
    ld bc, $9F83
    call SetSQ2Control
SQ2StunCont:
    ld a, [wNes + nSQ2SFXTimer]
    cp $06
    jr c, .low
    call SQ2Rise
    jp FinishSQ2SFX
.low:
    cp $05
    jp nz, FinishSQ2SFX
    ld bc, $818B
    ld a, $34
    jp SQ2Note

SQ2TigerInit:               ; $872B
    ld a, $18
    ld [wNes + nSQ2SFXTimer], a
    ld a, $14
    ld [wNes + nSQ2SFXByte1], a
    ld bc, $9EB3
    ld a, $40
    jp SQ2Note
SQ2TigerCont:
    ld a, [wNes + nSQ2SFXByte1]
    ld b, a
    ld a, [wNes + nSQ2SFXTimer]
    cp b
    jp nz, FinishSQ2SFX
    ld bc, $86C5
    ld a, $5E
    jp SQ2Note

SQ2MagicInit:               ; $8753
    ld a, $60
    ld [wNes + nSQ2SFXTimer], a
    ld a, $0C
    ld [wNes + nSQ2SFXByte1], a
    ld a, $0F
    ld [wNes + nSQ2SFXByte2], a
    xor a
    ld [wNes + nMagicFlip], a
    ld a, $04
    ld [wNes + nMagicStep], a
SQ2MagicCont:               ; $876E
    ld a, [wNes + nMagicFlip]
    and a
    jr z, .a
    ld a, [wNes + nSQ2SFXByte2]
    tbl MagicCtrlBTbl
    and a
    jr nz, .ctrl
.a:
    ld a, [wNes + nSQ2SFXByte2]
    tbl MagicCtrlATbl
.ctrl:
    apu $04
    ld a, [wNes + nSQ2SFXByte1]
    ld c, a
    tbl MagicTimeTbl
    ld b, a
    ld a, [wNes + nSQ2SFXTimer]
    cp b
    jr nz, .fade
    ld a, c                 ; the next step
    inc a
    srl a
    tbl MagicVolTbl
    ld [wNes + nSQ2SFXByte2], a
    ld a, c
    rra
    ld a, $CA
    ld b, $00
    jr nc, .flip
    ld a, $BB
    ld b, $01
.flip:
    ld c, a
    ld a, b
    ld [wNes + nMagicFlip], a
    ld a, c
    apu $05
    ld hl, wNes + nSQ2SFXByte1
    ld a, [hl]
    and a
    jr z, .note
    dec [hl]
.note:
    ld a, [wNes + nMagicStep]
    ld c, a
    tbl MagicLoTbl
    apu $06
    ld a, c
    tbl MagicHiTbl
    apu $07
    dec c
    jr nz, .step
    ld c, $04
.step:
    ld a, c
    ld [wNes + nMagicStep], a
.fade:                      ; $87CB
    ld hl, wNes + nSQ2SFXByte2
    ld a, [hl]
    and a
    jp z, FinishSQ2SFX
    dec [hl]
    jp FinishSQ2SFX

SQ2Punch11Init:             ; $87F4
    ld a, $08
    ld [wNes + nSQ2SFXTimer], a
    ld a, $1F
    ld [wNes + nSQ2SFXByte1], a
    ld bc, $9A83
    call SetSQ2Control
SQ2Punch11Cont:
    ld a, [wNes + nSQ2SFXTimer]
    cp $04
    jr c, .low
    call SQ2Rise
    jp FinishSQ2SFX
.low:
    cp $03
    jp nz, FinishSQ2SFX
    ld bc, $818B
    ld a, $50
    jp SQ2Note

SQ2MachoInit:               ; $8823
    ld a, $40
    ld [wNes + nSQ2SFXTimer], a
    ld a, $FF
    ld [wNes + nSQ2SFXByte1], a
    ld bc, $1E82
    call SetSQ2Control
SQ2MachoCont:
    ld a, [wNes + nSQ2SFXByte1]
    ld c, a
    call LogDiv16
    ld [wNes + nSQ2SFXByte1], a
    timer_rol 2, $03, $04
    ld a, [wNes + nSQ2SFXTimer]
    cp $0C
    jp nc, FinishSQ2SFX
    or $90
    apu $04
    jp FinishSQ2SFX

SQ2HippoInit:               ; $885C
    ld a, $10
    ld [wNes + nSQ2SFXTimer], a
    ld bc, $82A2
    ld a, $56
    call UpdateSQ2
SQ2HippoCont:
    ld a, [wNes + nSQ2SFXTimer]
    cp $0E
    jp nz, FinishSQ2SFX
    ld a, $3E
    call UpdateSQ2Note
    jp FinishSQ2SFX

SQ2WindUpInit:              ; $887B
    ld a, $20
    ld [wNes + nSQ2SFXTimer], a
    ld a, $7F
.set:                       ; $888B
    ld [wNes + nSQ2SFXByte1], a
    ld bc, $9E82
    call SetSQ2Control
SQ2WindUpCont:
    ld a, [wNes + nSQ2SFXTimer]
    cp $10
    jr nz, .rise
    ld hl, wNes + nSQ2SFXTimer
    dec [hl]
    ld a, $5F
    jr SQ2WindUpInit.set
.rise:
    ld a, [wNes + nSQ2SFXByte1]
    ld c, a
    call LogDiv32
    ld [wNes + nSQ2SFXByte1], a
    timer_rol 2, $03, $04
    jp FinishSQ2SFX

SQ2Spring2Init:             ; $88CF
    ld a, $10
    ld [wNes + nSQ2SFXTimer], a
    ld bc, $C8AC
    ld a, $42
    jp SQ2Note

; ---- music ($88E2) -------------------------------------------------------------------------------------

; A = music data byte Y (A) of the current piece
MusicByte:
    ld hl, wNes + nMusicPtr
    add [hl]
    ld e, a
    inc l
    ld a, [hl]
    adc 0
    sub SND_DELTA
    ld d, a
    ld a, [de]
    ret

PlayMusic:
    ld a, [wNes + nMusicInit]
    bit 7, a
    jr nz, StopMusic
    cp $1B
    jr z, StopMusic
    cp $1C
    jr z, StopMusic
    and a
    jp nz, InitMusic
    ld a, [wNes + nMusicIndex]
    and a
    ret z
    jp UpdateSQ2Music

RepeatMusic:                ; $88FC
    ld a, [wNes + nMusicIndex]
    cp $1A
    jp nc, MusicIndexSet
StopMusic:
    xor a
    ld [wNes + nMusicIndex], a
; $8906: every channel no effect is using goes quiet
SilenceChannels:
    ld a, [wNes + nNoiseInUse]
    and a
    jr z, .sq1
    ld a, [wNes + nSFXIndexSQ2]
    and a
    jr nz, .sq1Quiet
    ld a, $10
    apu $04
.sq1Quiet:
    ld a, $10
    apu $00
    xor a
    apu $08
    jr .envelopes
.sq1:
    ld a, [wNes + nSQ1InUse]
    and a
    jr z, .sq2
    ld a, [wNes + nSFXIndexSQ2]
    and a
    jr nz, .triNoise
    ld a, $10
    apu $04
    jr .triNoise
.sq2:
    ld a, [wNes + nSQ2InUse]
    and a
    jr nz, .triNoise
    ld a, [wNes + nSFXIndexSQ2]
    and a
    ld a, $10
    jr nz, .sq1TriNoise
    apu $04
.sq1TriNoise:
    apu $00
.triNoise:
    ld a, $10
    apu $0C
    xor a
    apu $08
.envelopes:
    xor a
    ld [wNes + nSQ2EnvIndex], a
    ld [wNes + nSQ1EnvIndex], a
    ld [wNes + nNoiseVolIndex], a
    ret

InitMusic:                  ; $8964
    push af
    call SilenceChannels
    pop af
MusicIndexSet:              ; $8969
    ld [wNes + nMusicIndex], a
    ld [wNes + nMusSeqBase], a
    xor a
    ld [wNes + nMusSeqIndex], a
NextSegment:                ; $8973
    ld a, [wNes + nMusSeqBase]
    tbl MusSeqIndexTbl - 1
    ld hl, wNes + nMusSeqIndex
    add [hl]
    inc [hl]
    tbl MusSeqIndexTbl
    and a
    jp z, RepeatMusic
    ld e, a
    ld d, 0
    ld a, [wNes + nMusicIndex]
    cp $10
    ld hl, MusicInitTbl1
    jr c, .lower
    ld hl, MusicInitTbl2
.lower:
    add hl, de
    ld a, [hl+]
    ld [wNes + nNoteLengthsBase], a
    ld a, [hl+]
    ld [wNes + nMusicPtr], a
    ld a, [hl+]
    ld [wNes + nMusicPtr + 1], a
    ld a, [hl+]
    ld [wNes + nTriNoteIndex], a
    ld a, [hl+]
    ld [wNes + nSQ1NoteIndex], a
    ld a, [hl+]
    ld [wNes + nNoiseMusicIndex], a
    ld [wNes + nNoiseIndexReload], a
    ld a, [hl+]
    ld [wNes + nSQ2EnvBase], a
    ld a, [hl]
    ld [wNes + nSQ1EnvBase], a
    xor a                   ; $89F3
    ld [wNes + nSQ2NoteIndex], a
    inc a
    ld [wNes + nSQ2NoteRemain], a
    ld [wNes + nSQ1NoteRemain], a
    ld [wNes + nTriNoteRemain], a
    ld [wNes + nNoiseNoteRemain], a
    ld a, $7F
    ld [wNes + nSQ1SweepCntrl], a
    ; fall through
; $8A0A: SQ2
UpdateSQ2Music:
    ld a, [wNes + nSFXIndexSQ2]
    ld b, a
    ld a, [wNes + nSQ2InUse]
    or b
    jr z, .dec
    ld a, [wNes + nSQ2EnvBase]
    cp $40
    jr nc, .noEnv
    ld a, $3F
    ld [wNes + nSQ2EnvIndex], a
    ld a, 1
    ld [wNes + nSQ2Restart], a
    jr .dec
.noEnv:
    xor a
    ld [wNes + nSQ2EnvIndex], a
.dec:
    ld hl, wNes + nSQ2NoteRemain
    dec [hl]
    jr nz, SQ2NoteContinue
    jr .next
.length:                    ; $8A32
    call NoteLength
    ld [wNes + nSQ2NoteLength], a
.next:                      ; $8A38
    ld hl, wNes + nSQ2NoteIndex
    ld a, [hl]
    inc [hl]
    call MusicByte
    and a
    jp z, NextSegment
    bit 7, a
    jr nz, .length
    ld [wNes + nSQ2ShortPause], a
    ld c, a
    ld a, [wNes + nSFXIndexSQ2]
    ld b, a
    ld a, [wNes + nSQ2InUse]
    or b
    jr nz, .reset
    ld a, c
    call UpdateSQ2Note
    jr z, .reset
    ld a, [wNes + nSQ2EnvBase]
    cp $80
    ld a, $7F
    jr nc, .env
    ld a, $3F
.env:
    ld [wNes + nSQ2EnvIndex], a
.reset:                     ; $8A63
    ld a, [wNes + nSQ2NoteLength]
    ld [wNes + nSQ2NoteRemain], a
SQ2NoteContinue:            ; $8A69
    ld a, [wNes + nSFXIndexSQ2]
    ld b, a
    ld a, [wNes + nSQ2InUse]
    or b
    jr nz, UpdateSQ1Music
    ld a, [wNes + nSQ2EnvBase]
    cp $40
    jr nc, .env
    ld a, [wNes + nSQ2ShortPause]
    cp $02
    jr z, .quiet
    ld b, a
    ld a, [wNes + nSQ2Restart]
    and a
    jr z, .remain
    ld a, b
    call UpdateSQ2Note
    xor a
    ld [wNes + nSQ2Restart], a
.remain:
    ld a, [wNes + nSQ2NoteRemain]
    cp $02
    jr nc, .env
.quiet:
    ld b, $10
    jr .set
.env:                       ; $8A98
    call VibratoSQ2
    ld hl, wNes + nSQ2EnvIndex
    ld a, [hl]
    and a
    jr z, .base
    srl a
    srl a
    dec [hl]
.base:
    ld hl, wNes + nSQ2EnvBase
    add [hl]
    tbl SQDCEnvTbl
    ld b, a
.set:
    call SQ2CntrlSwpDis
    ; fall through
; $8AB1: SQ1
UpdateSQ1Music:
    ld a, [wNes + nSQ1NoteIndex]
    and a
    jp z, UpdateTriMusic
    ld a, [wNes + nSFXIndexSQ1]
    and a
    jr z, .dec
    ld a, [wNes + nSQ1EnvBase]
    cp $40
    jr nc, .noEnv
    ld a, $3F
    ld [wNes + nSQ1EnvIndex], a
    ld a, 1
    ld [wNes + nSQ1Restart], a
    jr .dec
.noEnv:
    xor a
    ld [wNes + nSQ1EnvIndex], a
.dec:
    ld hl, wNes + nSQ1NoteRemain
    dec [hl]
    jr nz, SQ1NoteContinue
    jr .next
.length:                    ; $8ADB
    call NoteLength
    ld [wNes + nSQ1NoteLength], a
.next:                      ; $8AE1
    ld hl, wNes + nSQ1NoteIndex
    ld a, [hl]
    inc [hl]
    call MusicByte
    bit 7, a
    jr nz, .length
    and a
    jr nz, .note
    ld hl, wNes + nSQ1NoteIndex     ; 0: a sweep byte follows
    ld a, [hl]
    inc [hl]
    call MusicByte
    ld [wNes + nSQ1SweepCntrl], a
    and a
    jr nz, .next
.note:                      ; $8AF6
    ld [wNes + nSQ1ShortPause], a
    ld c, a
    ld a, [wNes + nSFXIndexSQ1]
    and a
    jr nz, .reset
    ld a, c
    call UpdateSQ1Note
    jr z, .reset
    ld a, [wNes + nSQ1EnvBase]
    cp $80
    ld a, $7F
    jr nc, .env
    ld a, $3F
.env:
    ld [wNes + nSQ1EnvIndex], a
.reset:                     ; $8B12
    ld a, [wNes + nSQ1NoteLength]
    ld [wNes + nSQ1NoteRemain], a
SQ1NoteContinue:            ; $8B18
    ld a, [wNes + nSFXIndexSQ1]
    and a
    jp nz, UpdateTriMusic
    ld a, [wNes + nSQ1EnvBase]
    cp $40
    jr nc, .env
    ld a, [wNes + nSQ1ShortPause]
    cp $02
    jr z, .quiet
    ld b, a
    ld a, [wNes + nSQ1Restart]
    and a
    jr z, .remain
    ld a, b
    call UpdateSQ1Note
    xor a
    ld [wNes + nSQ1Restart], a
.remain:
    ld a, [wNes + nSQ1NoteRemain]
    cp $02
    jr nc, .env
.quiet:
    ld b, $10
    jr .set
.env:                       ; $8B42
    call VibratoSQ1
    ld hl, wNes + nSQ1EnvIndex
    ld a, [hl]
    and a
    jr z, .base
    srl a
    srl a
    dec [hl]
.base:
    ld hl, wNes + nSQ1EnvBase
    add [hl]
    tbl SQDCEnvTbl
    ld b, a
.set:                       ; $8B58
    ld a, [wNes + nSQ1SweepCntrl]
    ld c, a
    call SetSQ1Control
    ld a, c                 ; (the 6502 branches on the sweep byte: 0 skips the triangle)
    and a
    jp z, UpdateNoiseMusic
    ; fall through
; $8B63: the triangle
UpdateTriMusic:
    ld a, [wNes + nTriNoteIndex]
    and a
    jp z, UpdateNoiseMusic
    ld hl, wNes + nTriMidBlip
    dec [hl]
    ld hl, wNes + nTriNoteRemain
    dec [hl]
    jr nz, TriContinue
    jr .next
.length:                    ; $8B72
    call NoteLength
    ld [wNes + nTriNoteLength], a
.next:
    ld hl, wNes + nTriNoteIndex
    ld a, [hl]
    inc [hl]
    call MusicByte
    bit 7, a
    jr nz, .length
    ld c, a
    ld a, [wNes + nSFXIndexSQ2]
    cp $0D
    jr z, .reset
    ld a, [wNes + nSFXIndexSQ1]
    cp $18
    jr z, .reset
    ld a, c
    cp $02
    jr nz, .play
    xor a
    apu $08
    jr .reset
.play:
    ld a, $81
    apu $08
    ld a, c
    call UpdateTriNote
.reset:                     ; $8BA1
    ld a, [wNes + nTriNoteLength]
    ld [wNes + nTriNoteRemain], a
    ld c, a
    ld a, [wNes + nMusicIndex]
    cp $15
    jr z, .blips
    cp $04
    jr nc, TriContinue
.blips:                     ; $8BB1
    ld a, c
    cp $0B
    ld a, $02
    jr nc, .type
    ld a, c
    sub 2
    ld [wNes + nTriFrontBlip], a
    ld a, c
    srl a
    ld [wNes + nTriMidBlip], a
    cp $04
    ld a, $00
    jr c, .type
    inc a
.type:
    ld [wNes + nTriBlipType], a
TriContinue:                ; $8BD2
    ld a, [wNes + nSFXIndexSQ2]
    cp $0D
    jr z, UpdateNoiseMusic
    ld a, [wNes + nSFXIndexSQ1]
    cp $18
    jr z, UpdateNoiseMusic
    ld a, [wNes + nMusicIndex]
    cp $15
    jr z, .blip
    cp $04
    jr nc, .end
.blip:
    ld a, [wNes + nTriBlipType]
    cp $01
    jr z, .mid
    cp $02
    jr z, .back
    ld a, [wNes + nTriFrontBlip]
    ld b, a
    ld a, [wNes + nTriNoteRemain]
    cp b
    jr nz, UpdateNoiseMusic
    jr .quiet
.mid:
    ld a, [wNes + nTriMidBlip]
    cp $02
    jr nz, UpdateNoiseMusic
    jr .quiet
.back:
    ld a, [wNes + nTriNoteRemain]
    cp $07
    jr nz, UpdateNoiseMusic
    jr .quiet
.end:                       ; $8C0F
    ld a, [wNes + nTriNoteRemain]
    cp $02
    jr nz, UpdateNoiseMusic
.quiet:
    xor a
    apu $08
    ; fall through
; $8C1B: the drums
UpdateNoiseMusic:
    ld a, [wNes + nNoiseMusicIndex]
    and a
    ret z
    ld a, [wNes + nNoiseInUse]
    and a
    jr z, .dec
    xor a
    ld [wNes + nNoiseVolIndex], a
.dec:
    ld hl, wNes + nNoiseNoteRemain
    dec [hl]
    jr nz, .decay
    jr .next
.length:                    ; $8C31
    call NoteLength
    ld [wNes + nNoiseNoteLength], a
.next:
    ld hl, wNes + nNoiseMusicIndex
    ld a, [hl]
    inc [hl]
    call MusicByte
    bit 7, a
    jr nz, .length
    and a
    jr nz, .beat
    ld a, [wNes + nNoiseIndexReload]   ; 0: the beat starts over
    ld [wNes + nNoiseMusicIndex], a
    and a
    jr nz, .next
.beat:                      ; $8C4B
    ld c, a
    ld [wNes + nNoiseBeatType], a
    ld a, [wNes + nNoiseInUse]
    and a
    jr nz, .reset
    ld b, 0
    ld hl, NoiseDatTbl - 2
    add hl, bc
    ld a, [hl+]
    apu $0C
    ld a, [hl+]
    apu $0D + 1
    ld a, [hl]
    apu $0F
    ld a, $27
    ld [wNes + nNoiseVolIndex], a
.reset:                     ; $8C6B
    ld a, [wNes + nNoiseNoteLength]
    ld [wNes + nNoiseNoteRemain], a
.decay:                     ; $8C71
    ld a, [wNes + nNoiseBeatType]
    cp $26
    ret c
    ld a, [wNes + nNoiseInUse]
    and a
    ret nz
    ld hl, wNes + nNoiseVolIndex
    ld a, [hl]
    and a
    jr z, .vol
    dec [hl]
.vol:
    tbl NoiseDecayTbl
    apu $0C
    ret

; ==== The NES's sound on the Game Boy ===================================================================

DEF rAUD1SWEEP EQU $FF10
DEF rAUD1LEN EQU $FF11
DEF rAUD1ENV EQU $FF12
DEF rAUD1LOW EQU $FF13
DEF rAUD2LEN EQU $FF16
DEF rAUD2ENV EQU $FF17
DEF rAUD2LOW EQU $FF18
DEF rAUD3ENA EQU $FF1A
DEF rAUD3LEVEL EQU $FF1C
DEF rAUD3LOW EQU $FF1D
DEF rAUD3HIGH EQU $FF1E
DEF rAUD4ENV EQU $FF21
DEF rAUD4POLY EQU $FF22
DEF rAUD4GO EQU $FF23
DEF rAUDVOL EQU $FF24
DEF rAUDTERM EQU $FF25
DEF rAUDENA EQU $FF26

; NES length counter loads, by bits 3-7 of $4003 and the others
ApuLengths:
    db 10, 254, 20, 2, 40, 4, 80, 6, 160, 8, 60, 10, 14, 12, 26, 14
    db 12, 16, 24, 18, 48, 20, 96, 22, 192, 24, 72, 26, 16, 28, 32, 30
; GB wave RAM: the NES triangle's 32 steps
ApuTriangle:
    db $FE, $DC, $BA, $98, $76, $54, $32, $10, $01, $23, $45, $67, $89, $AB, $CD, $EF
; NES noise periods (4 to 4068 CPU cycles) as the GB's noise clock (NR43 shift and divider), nearest
ApuNoiseClock:
    db $00, $01, $02, $05, $15, $17, $25, $26, $27, $35, $37, $45, $47, $55, $65, $75

; The GB's sound on, the wave channel loaded with the triangle, everything quiet until the NES says.
ApuInit::
    ld a, $80
    ldh [rAUDENA], a
    ld a, $FF
    ldh [rAUDTERM], a
    ld a, $77
    ldh [rAUDVOL], a
    xor a
    ldh [rAUD1SWEEP], a          ; the GB's own sweep off (the NES's runs here)
    ldh [rAUD3ENA], a          ; wave RAM only loads with the channel off
    ld hl, ApuTriangle
    ld c, $30
    ld b, 16
.wave:
    ld a, [hl+]
    ldh [c], a
    inc c
    dec b
    jr nz, .wave
    ld a, $80
    ldh [rAUD3ENA], a
    xor a
    ldh [rAUD3LEVEL], a          ; silent, running
    ldh [rAUD3LOW], a
    ld a, $80
    ldh [rAUD3HIGH], a
    xor a
    ldh [rAUD1ENV], a
    ldh [rAUD2ENV], a
    ldh [rAUD4ENV], a
    ld hl, wApu
    ld b, wGbVol - wApu
.clear:
    ld [hl+], a
    dec b
    jr nz, .clear
    ld a, $FF               ; nothing given yet
    ld b, wApuEnd - wGbVol
.unknown:
    ld [hl+], a
    dec b
    jr nz, .unknown
    ret

; The GB's sound back to quiet (leaving the fight).
ApuQuiet::
    xor a
    ldh [rAUD1ENV], a
    ldh [rAUD2ENV], a
    ldh [rAUD3LEVEL], a
    ldh [rAUD4ENV], a
    ret

; Once a frame, after NesSound: the frame's clocks around its writes, then the GB channels. The game's $C0
; to $4017 clocks a quarter and a half frame at once; before the next one come three quarters and a half.
ApuOut:
    ld a, 1
    call ApuClocks
    call ApuTake
    ld a, 3
    call ApuClocks
    ld e, 0
    call PulseOut
    ld e, 1
    call PulseOut
    call TriangleOut
    jp NoiseOut

; A quarter-frame clocks (envelopes, the linear counter) and one half-frame clock (lengths, sweeps).
ApuClocks:
    ld [wTicks], a
    ld b, a
    ld a, [wApu + $00]
    ld c, a
    ld hl, wEnv + 0
    call EnvTicks
    ld a, [wTicks]
    ld b, a
    ld a, [wApu + $04]
    ld c, a
    ld hl, wEnv + 3
    call EnvTicks
    ld a, [wTicks]
    ld b, a
    ld a, [wApu + $0C]
    ld c, a
    ld hl, wEnv + 6
    call EnvTicks
    ld a, [wTicks]          ; the triangle's linear counter: reloaded while flagged, else counting down
    ld b, a
    ld a, [wApu + $08]
    ld c, a
    and $7F
    ld e, a
    ld hl, wApuLinear
    ld a, [wApuLinReload]
    and a
    jr z, .linear
    ld [hl], e
    bit 7, c                ; control set: it reloads every tick
    jr nz, .lengths
    xor a
    ld [wApuLinReload], a
    dec b
.linear:
    ld a, b
    and a
    jr z, .lengths
    ld a, [hl]
    sub b
    jr nc, .linSet
    xor a
.linSet:
    ld [hl], a
.lengths:
    ld hl, wApuLength
    ld a, [wApu + $00]
    call .len
    ld a, [wApu + $04]
    call .len
    ld a, [wApu + $08]      ; the triangle's halt is bit 7
    rrca
    rrca
    call .len
    ld a, [wApu + $0C]
    call .len
    ld e, 0
    call ApuSweep
    ld e, 1
    jp ApuSweep
.len:                       ; A bit 5 = halt; HL = the counter (advanced)
    bit 5, a
    jr nz, .keep
    ld a, [hl]
    and a
    jr z, .keep
    dec [hl]
.keep:
    inc l
    ret

; B quarter-frame ticks of the envelope at HL (start, volume, divider), C = its control register: a start
; sets 15 and the period; each time the divider runs out the volume drops (or loops, bit 5).
EnvTicks:
    ld a, c
    and $0F
    ld e, a
    ld a, [hl]
    and a
    jr z, .running
    ld [hl], 0
    ld d, 15
    ld a, e
    dec b
    jr z, .save
    jr .tick
.running:
    inc hl
    ld d, [hl]
    inc hl
    ld a, [hl]
    dec hl
    dec hl
.tick:
    and a
    jr z, .step
    dec a
    jr .next
.step:
    ld a, d
    and a
    jr z, .wrap
    dec d
    ld a, e
    jr .next
.wrap:
    bit 5, c
    ld a, e
    jr z, .next
    ld d, 15
.next:
    dec b
    jr nz, .tick
.save:
    inc hl
    ld [hl], d
    inc hl
    ld [hl], a
    ret

; Writes that start something: $4003, $4007, $400B, $400F (length; envelope or linear counter).
ApuTake:
    ld e, 0
.channel:
    ld hl, wApuNew
    ld a, l
    add e
    ld l, a
    ld a, [hl]
    and a
    jr z, .next
    ld [hl], 0
    rrca                    ; length index: bits 3-7
    rrca
    rrca
    and $1F
    tbl ApuLengths
    ld b, a
    ld hl, wApuLength
    ld a, l
    add e
    ld l, a
    ld [hl], b
    ld hl, wApuStart
    ld a, l
    add e
    ld l, a
    ld [hl], 1
    ld a, e
    cp 2
    jr nz, .env
    ld a, 1                 ; the triangle: its linear counter reloads
    ld [wApuLinReload], a
    jr .next
.env:
    jr c, .envIndex         ; pulse 1, 2: envelopes 0, 1; noise (3): envelope 2
    dec a
.envIndex:
    ld b, a
    add a
    add b
    ld hl, wEnv
    add l
    ld l, a
    ld [hl], 1
.next:
    inc e
    ld a, e
    cp 4
    jr nz, .channel
    ld hl, wApuNew + 4      ; $4015: the DMC starts a sample (bit 4) or stops
    ld a, [hl]
    and a
    jr z, .pulses
    ld [hl], 0
    bit 4, a
    ld a, 0
    jr z, .sample
    ld a, [wApu + $10]
    and $40
    ld [wDmcLoop], a
    ld a, [wApu + $12]      ; which one, by its address
    ld hl, DmcAddr
    ld b, 7
.find:
    cp [hl]
    jr z, .found
    inc hl
    dec b
    jr nz, .find
    xor a
    jr .sample
.found:
    ld a, 8
    sub b
.sample:
    ld [wDmcSample], a
    xor a
    ld [wDmcFrame], a
.pulses:
    ld e, 0
    call .period
    ld e, 1
.period:                    ; pulse E: restarted, its timer as written; a new low byte, just that
    ld a, e
    add a
    add a
    add LOW(wApu + 2)
    ld l, a
    ld h, HIGH(wApu)
    ld c, [hl]              ; low
    inc l
    ld a, [hl]
    and $07
    ld b, a                 ; high
    ld a, e
    add LOW(wApuSeenLo)
    ld l, a
    ld a, [hl]
    ld [hl], c
    ld d, a                 ; the low we saw before
    ld a, e
    add a
    add LOW(wApuPeriod)
    ld l, a
    ld a, e
    add LOW(wApuStart)
    push hl
    ld l, a
    ld a, [hl]
    pop hl
    and a
    jr nz, .whole
    ld a, d
    cp c
    ret z
    ld [hl], c
    ret
.whole:
    ld [hl], c
    inc l
    ld [hl], b
    ret

; Pulse E's sweep: when its divider runs out (enabled, shifting, not muted) the period becomes the target.
ApuSweep:
    ld a, e
    add a
    add a
    add LOW(wApu + 1)
    ld l, a
    ld h, HIGH(wApu)
    ld a, [hl]
    ld [wSwCtl], a
    ld hl, wApuSweepDiv
    ld a, l
    add e
    ld l, a
    ld a, [wSwCtl]
    bit 7, a
    jr z, .divider
    and $07
    jr z, .divider
    ld a, [hl]
    and a
    jr nz, .divider
    push hl
    call SweepCalc
    jr c, .muted
    ld a, e
    add a
    add LOW(wApuPeriod)
    ld l, a
    ld h, HIGH(wApuPeriod)
    ld a, [wSwTarget]
    ld [hl+], a
    ld a, [wSwTarget + 1]
    and $07
    ld [hl], a
.muted:
    pop hl
.divider:                   ; reloaded when it's out or $4001 was written, else counting down
    ld a, [wSwCtl]
    swap a
    and $07
    ld b, a
    ld a, e
    add LOW(wApuSweepReload)
    ld l, a
    ld h, HIGH(wApuSweepReload)
    ld c, [hl]
    ld [hl], 0
    ld a, e
    add LOW(wApuSweepDiv)
    ld l, a
    ld a, c
    and a
    jr nz, .reload
    ld a, [hl]
    and a
    jr z, .reload
    dec [hl]
    ret
.reload:
    ld [hl], b
    ret

; Pulse E: carry if muted (timer under 8, or an upward sweep target past $7FF); wSwPeriod = its timer.
PulseMuted:
    ld a, e
    add a
    add LOW(wApuPeriod)
    ld l, a
    ld h, HIGH(wApuPeriod)
    ld a, [hl+]
    ld [wSwPeriod], a
    ld c, a
    ld a, [hl]
    ld [wSwPeriod + 1], a
    ld b, a
    and a
    jr nz, .long
    ld a, c
    cp 8
    ret c
.long:
    ld a, e
    add a
    add a
    add LOW(wApu + 1)
    ld l, a
    ld h, HIGH(wApu)
    ld a, [hl]
    bit 3, a                ; downward: never too high
    jr nz, .sounds
    and $07
    jp nz, SweepCalc
    ld a, b                 ; no shift: the target is twice the timer
    cp $04
    ccf
    ret
.sounds:
    and a
    ret

; Pulse E: wSwCtl = $4001, wSwPeriod, wSwTarget (period +/- period >> shift; pulse 1 negates one less).
; Carry: muted (period under 8, or an upward target past $7FF). Keeps E.
SweepCalc:
    ld a, e
    add a
    add a
    add LOW(wApu + 1)
    ld l, a
    ld h, HIGH(wApu)
    ld a, [hl]
    ld [wSwCtl], a
    ld a, e
    add a
    add LOW(wApuPeriod)
    ld l, a
    ld c, [hl]
    inc l
    ld b, [hl]
    ld a, c
    ld [wSwPeriod], a
    ld a, b
    ld [wSwPeriod + 1], a
    ld a, [wSwCtl]
    and $07
    ld d, a
    ld h, b
    ld l, c
    inc d
.shift:
    dec d
    jr z, .shifted
    srl h
    rr l
    jr .shift
.shifted:
    ld a, [wSwCtl]
    bit 3, a
    jr nz, .down
    add hl, bc
    jr .target
.down:
    ld a, c
    sub l
    ld l, a
    ld a, b
    sbc h
    ld h, a
    ld a, e
    and a
    jr nz, .target
    dec hl
.target:
    ld a, l
    ld [wSwTarget], a
    ld a, h
    ld [wSwTarget + 1], a
    ld a, b
    and a
    jr nz, .long
    ld a, c
    cp 8
    ret c
.long:
    ld a, [wSwCtl]
    bit 3, a
    jr nz, .sounds
    ld a, h
    cp 8
    ccf
    ret
.sounds:
    and a
    ret

; HL = NES timer + 1 -> HL = the GB frequency for the same pitch: 2048 - 1.171875 HL (none under 0).
; The GB pulse (and the 32-step wave) run 131072/(2048 - x) Hz; the NES pulse 111861/(t + 1). Keeps DE.
GbFreq:
    push de
    ld d, h
    ld e, l
    srl h
    rr l
    srl h
    rr l
    srl h
    rr l
    push hl                 ; t/8
    srl h
    rr l
    srl h
    rr l
    ld b, h
    ld c, l                 ; t/32
    srl h
    rr l                    ; t/64
    add hl, bc
    pop bc
    add hl, bc
    add hl, de
    ld a, l
    cpl
    ld l, a
    ld a, h
    cpl
    ld h, a
    inc hl
    ld de, 2048
    add hl, de
    pop de
    bit 7, h
    ret z
    ld hl, 0
    ret

; Pulse E to the GB's pulse E: a volume change or a fresh note restarts it; a pitch change just retunes.
PulseOut:
    call PulseMuted
    ld b, 0
    jr c, .volume           ; muted
    ld d, 0
    ld hl, wApuLength
    add hl, de
    ld a, [hl]
    and a
    jr z, .volume
    ld a, e
    add a
    add a
    add LOW(wApu)
    ld l, a
    ld h, HIGH(wApu)
    ld a, [hl]
    bit 4, a
    jr z, .envelope
    and $0F
    ld b, a
    jr .volume
.envelope:
    ld a, e
    add a
    add e
    add LOW(wEnv + 1)
    ld l, a
    ld h, HIGH(wEnv)
    ld b, [hl]
.volume:
    ld a, e                 ; the timer as last converted? its frequency then
    add a
    add LOW(wGbPer)
    ld l, a
    ld h, HIGH(wGbPer)
    ld a, [wSwPeriod]
    cp [hl]
    jr nz, .convert
    inc l
    ld a, [wSwPeriod + 1]
    cp [hl]
    jr nz, .convert
    ld a, e
    add a
    add LOW(wGbPerFreq)
    ld l, a
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    jr .converted
.convert:
    ld a, e
    add a
    add LOW(wGbPer)
    ld l, a
    ld h, HIGH(wGbPer)
    ld a, [wSwPeriod]
    ld [hl+], a
    ld a, [wSwPeriod + 1]
    ld [hl], a
    push bc
    ld a, [wSwPeriod]
    ld l, a
    ld a, [wSwPeriod + 1]
    ld h, a
    inc hl
    call GbFreq
    ld a, e
    add a
    add LOW(wGbPerFreq)
    ld c, a
    ld b, HIGH(wGbPerFreq)
    ld a, l
    ld [bc], a
    inc c
    ld a, h
    ld [bc], a
    pop bc
.converted:
    ld a, e                 ; C = its first GB register: NR11 or NR21
    and a
    ld c, LOW(rAUD1LEN)
    jr z, .regs
    ld c, LOW(rAUD2LEN)
.regs:
    ld d, 0
    push hl
    ld hl, wApuStart
    add hl, de
    ld a, [hl]
    ld [hl], 0
    ld hl, wGbVol
    add hl, de
    and a
    jr nz, .restart
    ld a, [hl]
    cp b
    jr z, .retune
.restart:
    ld [hl], b
    ld a, e
    add a
    add a
    add LOW(wApu)
    ld l, a
    ld h, HIGH(wApu)
    ld a, [hl]
    and $C0
    ldh [c], a              ; duty
    inc c
    ld hl, wGbDuty
    add hl, de
    ld [hl], a
    ld a, b
    swap a
    ldh [c], a              ; volume (0: off)
    inc c
    pop hl
    and a
    ret z
    ld a, l
    ldh [c], a
    inc c
    ld a, h
    or $80
    ldh [c], a
    jr .saveFreq
.retune:
    pop hl
    push hl
    ld a, e
    add a
    ld hl, wGbFreq
    add l
    ld l, a
    adc h
    sub l
    ld h, a
    pop bc                  ; BC = frequency
    ld a, [hl+]
    cp c
    jr nz, .new
    ld a, [hl]
    cp b
    jr z, .duty
.new:
    dec hl
    ld a, c
    ld [hl+], a
    ld [hl], b
    ld a, e
    and a
    ld a, c
    ld c, LOW(rAUD1LOW)
    jr z, .tune
    ld c, LOW(rAUD2LOW)
.tune:
    ldh [c], a
    inc c
    ld a, b
    ldh [c], a
    jr .duty
.saveFreq:                  ; HL = frequency
    ld b, h
    ld c, l
    ld a, e
    add a
    ld hl, wGbFreq
    add l
    ld l, a
    adc h
    sub l
    ld h, a
    ld [hl], c
    inc hl
    ld [hl], b
    ret
.duty:                      ; a duty change alone
    ld a, e
    add a
    add a
    add LOW(wApu)
    ld l, a
    ld h, HIGH(wApu)
    ld a, [hl]
    and $C0
    ld b, a
    ld hl, wGbDuty
    add hl, de
    cp [hl]
    ret z
    ld [hl], a
    ld a, e
    and a
    ld c, LOW(rAUD1LEN)
    jr z, .setDuty
    ld c, LOW(rAUD2LEN)
.setDuty:
    ld a, b
    ldh [c], a
    ret

; The triangle on the GB's wave channel: on while its linear and length counters run and it's audible.
TriangleOut:
    xor a
    ld [wApuStart + 2], a
    ld a, [wApu + $0A]
    ld l, a
    ld a, [wApu + $0B]
    and $07
    ld h, a
    ld b, $00
    ld a, [wApuLinear]
    and a
    jr z, .vol
    ld a, [wApuLength + 2]
    and a
    jr z, .vol
    ld a, h
    and a
    jr nz, .on
    ld a, l
    cp 2
    jr c, .vol
.on:
    ld b, $20
.vol:
    ld a, [wGbVol + 2]
    cp b
    jr z, .tune
    ld a, b
    ld [wGbVol + 2], a
    ldh [rAUD3LEVEL], a
.tune:
    inc hl
    call GbFreq
    ld a, [wGbFreq + 4]
    cp l
    jr nz, .new
    ld a, [wGbFreq + 5]
    cp h
    ret z
.new:
    ld a, l
    ld [wGbFreq + 4], a
    ldh [rAUD3LOW], a
    ld a, h
    ld [wGbFreq + 5], a
    ldh [rAUD3HIGH], a
    ret

; The DMC sample's frame: D = its loudness (0: none), E = its noise clock; on to its next frame.
DmcStep:
    ld d, 0
    ld a, [wDmcSample]
    and a
    ret z
    dec a
    push bc
    ld c, a
    ld b, 0
    ld hl, DmcClock
    add hl, bc
    ld e, [hl]
    ld hl, DmcEnvelope
    add hl, bc
    add hl, bc
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    ld a, [wDmcFrame]
    cp [hl]                 ; past its end: again, or done
    jr c, .play
    ld a, [wDmcLoop]
    and a
    jr z, .done
    xor a
.play:
    ld c, a
    inc a
    ld [wDmcFrame], a
    inc hl
    add hl, bc
    ld d, [hl]
    pop bc
    ret
.done:
    ld [wDmcSample], a
    pop bc
    ret

; The noise channel: the NES's period as the nearest GB clock, its short mode as the GB's 7-step one.
NoiseOut:
    ld b, 0
    ld a, [wApuLength + 3]
    and a
    jr z, .clock
    ld a, [wApu + $0C]
    bit 4, a
    jr z, .envelope
    and $0F
    ld b, a
    jr .clock
.envelope:
    ld a, [wEnv + 7]
    ld b, a
.clock:
    ld a, [wApu + $0E]
    and $0F
    tbl ApuNoiseClock
    ld c, a
    ld a, [wApu + $0E]
    bit 7, a
    jr z, .mode
    set 3, c
.mode:
    call DmcStep            ; a sample playing: its loudness now in D, clock in E (D 0: none)
    ld a, b
    and a
    jr nz, .nes
    ld b, d                 ; the noise channel's free: the sample
    ld c, e
.nes:
    ld a, [wApuStart + 3]
    and a
    jr nz, .restart
    ld a, [wGbVol + 3]
    cp b
    jr z, .retune
.restart:
    xor a
    ld [wApuStart + 3], a
    ld a, b
    ld [wGbVol + 3], a
    ld a, c
    ld [wGbNoise], a
    ldh [rAUD4POLY], a
    ld a, b
    swap a
    ldh [rAUD4ENV], a
    and a
    ret z
    ld a, $80
    ldh [rAUD4GO], a
    ret
.retune:
    ld a, [wGbNoise]
    cp c
    ret z
    ld a, c
    ld [wGbNoise], a
    ldh [rAUD4POLY], a
    ret
