; ---- Sound effects: three voices (pulse 1, pulse 2, noise), one effect each at a time --------
; PlaySfx starts an effect if its priority is at least that of what the voice is playing.
; SfxUpdate runs once a frame and steps each playing effect.

DEF rNR10 EQU $FF10
DEF rNR11 EQU $FF11
DEF rNR12 EQU $FF12
DEF rNR13 EQU $FF13
DEF rNR14 EQU $FF14
DEF rNR21 EQU $FF16
DEF rNR22 EQU $FF17
DEF rNR23 EQU $FF18
DEF rNR24 EQU $FF19
DEF rNR42 EQU $FF21
DEF rNR43 EQU $FF22
DEF rNR44 EQU $FF23
DEF rNR50 EQU $FF24
DEF rNR51 EQU $FF25
DEF rNR52 EQU $FF26

SECTION "Sound effect voices", WRAM0
; per voice: pointer to the next step (0 = idle), frames left, priority, duty, transpose
wSfx: ds 3 * 6
DEF SFX_PTR EQU 0
DEF SFX_TIMER EQU 2
DEF SFX_PRIORITY EQU 3
DEF SFX_DUTY EQU 4
DEF SFX_TRANSPOSE EQU 5

SECTION "Code: Sound effects", ROM0

SfxInit:
    ld a, $80               ; sound on
    ldh [rNR52], a
    ld a, $FF               ; every channel to both speakers
    ldh [rNR51], a
    ld a, $77               ; full volume
    ldh [rNR50], a
    ld hl, wSfx
    ld b, 3 * 6
    xor a
.clear:
    ld [hl+], a
    dec b
    jr nz, .clear
    ret

; Start effect A, transposed up hSfxTranspose semitones. Keeps BC, DE, HL.
PlaySfx:
IF DEF(FT_NES_SOUND)
    push hl                 ; the NES game's own effect for this one, if it has one (the fight's come from
    push af                 ; its code, so none while it runs: hNesSound 1)
    ldh a, [hNesSound]
    dec a
    jr z, .none
    pop af
    push af
    add LOW(SfxNes)
    ld l, a
    adc HIGH(SfxNes)
    sub l
    ld h, a
    ld a, [hl]
    and a
    jr z, .theirs
    call NesSfx
.none:
    pop af
    pop hl
    ret
.theirs:
    ldh a, [hNesSound]      ; none: ours, unless the NES's engine still has the hardware
    and a
    jr nz, .none
    pop af
    pop hl
ENDC
    push hl
    push de
    push bc
    add a
    add LOW(SfxTable)
    ld l, a
    adc HIGH(SfxTable)
    sub l
    ld h, a
    ld a, [hl+]
    ld h, [hl]
    ld l, a                 ; HL = effect header
    ld a, [hl+]             ; voice
    ld b, a
    add a                   ; voice * 6
    add b
    add a
    add LOW(wSfx)
    ld e, a
    adc HIGH(wSfx)
    sub e
    ld d, a                 ; DE = voice slot
    ld a, [hl+]             ; priority
    ld c, a
    push hl
    ld hl, SFX_PTR + 1
    add hl, de
    ld a, [hl]              ; idle voices (pointer high byte 0) always take a new effect
    and a
    jr z, .take
    inc hl
    inc hl                  ; SFX_PRIORITY
    ld a, [hl]
    cp c
    jr z, .take
    jr c, .take
    pop hl
    jr .done                ; something more important is playing
.take:
    pop hl
    ld a, [hl+]             ; duty
    push af
    ld a, b                 ; pulse 1: set the sweep now
    and a
    ld a, [hl+]
    jr nz, .noSweep
    ldh [rNR10], a
.noSweep:
    ld a, l                 ; pointer to the first step
    ld [de], a
    inc de
    ld a, h
    ld [de], a
    inc de
    ld a, 1                 ; play the first step on the next update
    ld [de], a
    inc de
    ld a, c
    ld [de], a
    inc de
    pop af
    ld [de], a
    inc de
    ldh a, [hSfxTranspose]
    ld [de], a
.done:
    xor a
    ldh [hSfxTranspose], a
    pop bc
    pop de
    pop hl
    ret

SfxUpdate:
IF DEF(FT_NES_SOUND)
    ldh a, [hNesSound]      ; 1: the fight runs the NES's sound engine; 2: it plays out after it
    and a
    jr z, .ours
    dec a
    ret z
    jp NesSoundAfter
.ours:
ENDC
    ld hl, wSfx
    ld b, 0                 ; voice
.voice:
    ld a, [hl+]
    ld e, a
    ld a, [hl+]
    ld d, a                 ; DE = next step
    or e
    jr z, .next
    dec [hl]                ; frames left
    jr nz, .next
    ld a, [de]              ; step: frames (0 = the end), envelope, note / noise
    inc de
    and a
    jr z, .finish
    ld [hl], a
    push hl
    ld a, [de]
    inc de
    ld c, a                 ; C = envelope
    ld a, [de]
    inc de
    push af
    dec hl
    ld a, d                 ; store the pointer to the step after this one
    ld [hl-], a
    ld [hl], e
    pop af                  ; A = note / noise
    ld e, a
    inc hl
    inc hl
    inc hl
    inc hl                  ; SFX_DUTY
    ld a, [hl+]
    ld d, a                 ; D = duty
    ld a, b
    cp 2
    jr z, .noise
    ld a, e                 ; a pulse note: 0 is a rest
    and a
    jr z, .rest
    add [hl]                ; + transpose
    cp SFX_NOTE_TOP + 1
    jr c, .inRange
    ld a, SFX_NOTE_TOP
.inRange:
    add a
    add LOW(SfxNotes)
    ld l, a
    adc HIGH(SfxNotes)
    sub l
    ld h, a
    ld a, [hl+]
    ld e, a                 ; E = period low
    ld a, [hl]
    or $80                  ; trigger
    ld h, a
    ld a, b
    and a
    jr nz, .pulse2
    ld a, d
    ldh [rNR11], a
    ld a, c
    ldh [rNR12], a
    ld a, e
    ldh [rNR13], a
    ld a, h
    ldh [rNR14], a
    jr .played
.pulse2:
    ld a, d
    ldh [rNR21], a
    ld a, c
    ldh [rNR22], a
    ld a, e
    ldh [rNR23], a
    ld a, h
    ldh [rNR24], a
    jr .played
.rest:
    ld c, 0                 ; silence: the envelope off
    ld a, b
    and a
    ld a, c
    jr nz, .restPulse2
    ldh [rNR12], a
    jr .played
.restPulse2:
    ldh [rNR22], a
    jr .played
.noise:
    ld a, c
    ldh [rNR42], a
    ld a, e
    ldh [rNR43], a
    ld a, $80
    ldh [rNR44], a
.played:
    pop hl
.next:
    ld a, l                 ; to the next voice slot (6 bytes each; HL is 2 in)
    add 4
    ld l, a
    adc h
    sub l
    ld h, a
    inc b
    ld a, b
    cp 3
    jp c, .voice
    ret
.finish:                    ; the effect ended: free the voice and fade it out
    dec hl
    dec hl
    xor a
    ld [hl+], a             ; pointer
    ld [hl+], a
    ld [hl+], a             ; timer
    ld [hl], a              ; priority
    dec hl
    ld a, b
    and a
    jr nz, .notPulse1
    xor a
    ldh [rNR12], a
    jr .next
.notPulse1:
    cp 1
    jr nz, .notPulse2
    xor a
    ldh [rNR22], a
    jr .next
.notPulse2:
    xor a
    ldh [rNR42], a
    jr .next
