; ---- NES opponent engine: Punch-Out!!'s own opponent logic, ported ---------------------------------
; The rival runs the original game's fighter data, unchanged: an 8 KB bank of state scripts (poses,
; positions, moves, timings, punches, defense), AI scripts (which state next, and when) and a round
; timeline (AI modes by the clock). This file is a line-by-line port of the routines that run them, from
; the NES game's main bank (addresses in the comments are the originals):
;     timeline $B069, AI mode $B10A, guard reaction $C291, AI $B196, state tick $C4E7 + ops $C550-$C827
; The game's RAM is mirrored at wNes, at the same addresses, so the data's own reads and writes (it
; pokes and tests RAM directly) work as they did. The fighter bank sits at $4000, $4000 below where the
; NES saw it, so a pointer read from it has $40 taken off its high byte (see NesPtr).
; Registers in the port: NES A = A, X = B, Y = C. HL, DE are scratch.

DEF NES_BANK_DELTA EQU $40          ; NES $8000-$9FFF -> GB $4000-$5FFF

; NES RAM addresses (named as in the disassembly)
DEF nKnockdownSts EQU $05
DEF nRoundNumber EQU $06
DEF nComboTimer EQU $4A
DEF nComboCountDown EQU $4B
DEF nMacStatus EQU $50
DEF nMacPunchType EQU $74
DEF nOppCurState EQU $90
DEF nOppStateStatus EQU $91
DEF nOppStateTimer EQU $92
DEF nOppStateIndex EQU $93
DEF nOppStBasePtr EQU $94
DEF nOppStRepeat EQU $96
DEF nOppPunching EQU $97
DEF nOppPunchSts EQU $98
DEF nOppAnimSeg EQU $9A
DEF nOppAnimSegTimer EQU $9B
DEF nOppOutlineTimer EQU $9C
DEF nOppIndexReturn EQU $9D
DEF nOppPtrReturn EQU $9E
DEF nOppAnimFlags EQU $A0
DEF nOppBaseAnimIndex EQU $A1
DEF nOppFlip EQU $A2
DEF nOppBaseX EQU $B0
DEF nOppBaseY EQU $B1
DEF nOppPunchSide EQU $B4
DEF nOppPunchDamage EQU $B5
DEF nOppHitDefense EQU $B6
DEF nDPad1Status EQU $D2
DEF nRoundTmrStart EQU $0300
DEF nRoundTmrCntrl EQU $0301
DEF nRoundTimerUB EQU $0306
DEF nSecondsLeft EQU $0311
DEF nVulnerableTimer EQU $04FD
DEF nVariableStTime EQU $0581
DEF nTimerVal0585 EQU $0585
DEF nReactTimer EQU $05B8
DEF nSpecialKD EQU $03CB

DEF PUNCH_ACTIVE EQU $80
DEF NES_FULL_HP EQU 96
DEF STAT_FINISHED EQU $83

SECTION "NES RAM", WRAM0, ALIGN[8]
wNes:: ds $800                      ; the NES's 2 KB of RAM, at its own addresses
wNesRand: db                        ; random source (the NES rotates $18 through the carry)
wNesCue: db                         ; 1: his outline in the dodge cue's color
wNesAnim: db                        ; his sprite changes ($A0) the GB hasn't shown yet

;;PART common

; HL = a NES pointer read from the fighter bank: L = low byte, A = high byte. Returns the GB address.
NesPtr:
    sub NES_BANK_DELTA
    ld h, a
    ret

; A = a random byte (an LFSR; the NES's $18 is rotated through whatever carry was left).
NesRandom:
    ld a, [wNesRand]
    and a
    jp nz, .go
    inc a
.go:
    add a
    jp nc, .done
    xor $1D
.done:
    ld [wNesRand], a
    ret

; $AEAB: A = chance (0-15). Carry set (it happens) with chance A/16: when A > a random 0-15 (A = 15:
; always). $AEC8 / $AECE: the same against a random 0-127 / 0-255 ($7F / $FF: always). Keeps B, C.
NesChance15:
    ld e, $0F
    jp NesChanceMask
NesChance7F:
    ld e, $7F
    jp NesChanceMask
NesChanceFF:
    ld e, $FF
NesChanceMask:
    cp e
    jp z, .yes
    ld d, a
    call NesRandom
    and e
    ld e, a
    ld a, d
    cp e                    ; carry: A < random
    jp z, .no
    jp c, .no
.yes:
    scf
    ret
.no:
    and a
    ret

; Byte C of a script whose GB address is at [HL] (a pointer in NES RAM, already converted).
NesByteAt:
    ld a, [hl+]
    add c
    ld e, a
    ld a, [hl]
    adc 0
    ld d, a
    ld a, [de]
    ret

;;PART fighter
; ---- the state script ------------------------------------------------------------------------------

; A = the script byte at index C (the 6502's LDA (OppStBasePtr),Y).
OppByte:
    ld a, [wNes + nOppStBasePtr]
    add c
    ld l, a
    ld a, [wNes + nOppStBasePtr + 1]
    adc 0
    ld h, a
    ld a, [hl]
    ret

; $C4E7: once a frame. The current state's timer runs down; then its script goes on.
NesOppTick::
    ld a, [wNes + nOppCurState]
    and a
    ret z
    bit 7, a
    jp nz, OppInit
.running:                   ; $C4ED
    ld hl, wNes + nComboTimer
    ld a, [hl]
    and a
    jp z, .timer
    dec a
    ld [hl], a
    jp nz, .timer
    ld [wNes + nComboCountDown], a
    ld [wNes + $4C], a
.timer:                     ; $C4FA
    ld hl, wNes + nOppStateTimer
    dec [hl]
    ret nz
    ld a, [wNes + nOppCurState]
    cp 1
    jp nz, OppNext
    ld a, [wNes + $04FF]    ; waiting, with a guard change pending: show it
    bit 7, a
    jp z, OppNext
    and $7F
    ld [wNes + $04FF], a
    ld a, $82
OppGuardPose:               ; $C50E: pose $82 / $80 (low / high guard), and his defense to match
    ld hl, wNes + $04FF
    sub [hl]
    sub [hl]
    ld [wNes + nOppBaseAnimIndex], a
    ld a, $81
    ld [wNes + nOppAnimFlags], a
    ld a, [wNes + $04FF]
    add a
    add a
    ld e, a
    ld d, 0
    ld hl, GuardDefense
    add hl, de
    xor a
    ld [wNes + nOppPunchSide], a
    ld [wNes + nOppPunchDamage], a
    ld de, wNes + nOppHitDefense
    REPT 4
        ld a, [hl+]
        ld [de], a
        inc e
    ENDR
OppNext:                    ; $C535
    ld hl, wNes + nOppStateTimer
    inc [hl]
    ld a, [wNes + nOppAnimSeg]
    and a
    jp z, OppStateUpdate
    dec a                   ; a segmented move: the next step of it
    ld [wNes + nOppAnimSeg], a
    ld a, [wNes + nOppAnimSegTimer]
    ld [wNes + nOppStateTimer], a
    ld hl, wNes + nOppStateIndex
    dec [hl]
    ld c, [hl]
    jp OppMoveAgain

GuardDefense:               ; $C828: per guard, face (right, left) and stomach (right, left)
    db $00, $00, $08, $08   ; gloves low: face open, stomach blocked
    db $08, $08, $00, $00   ; gloves high: face blocked, stomach open

; $C46B: a new state (OppCurState with bit 7 set).
OppInit:
    and $7F
    ld [wNes + nOppCurState], a
    ld hl, wNes + nOppStateStatus
    set 7, [hl]
    xor a
    ld hl, wNes + nOppStateTimer   ; $92-$9A cleared
    REPT 9
        ld [hl+], a
    ENDR
    ld hl, wNes + nOppPunchSide    ; $B4-$B9 cleared
    REPT 6
        ld [hl+], a
    ENDR
    inc a
    ld [wNes + nOppOutlineTimer], a
    ld [wNes + nOppStateTimer], a
    xor a
    ld [wNes + $5A], a
    ld [wNes + $AF], a
    ld a, [wNes + nOppCurState]    ; the state's script: from the first pointer table below $40, the second above
    cp $40
    ld hl, NesFighter + 2
    jp c, .table
    sub $40
    ld hl, NesFighter + 4
.table:
    ld c, a
    ld a, [hl+]             ; the table's address (a NES pointer)
    ld e, a
    ld a, [hl]
    sub NES_BANK_DELTA
    ld d, a
    ld l, c
    ld h, 0
    add hl, hl
    add hl, de
    ld a, [hl+]
    ld [wNes + nOppStBasePtr], a
    ld a, [hl]
    sub NES_BANK_DELTA
    ld [wNes + nOppStBasePtr + 1], a
    ld a, [wNes + nOppCurState]
    cp 1
    jp nz, NesOppTick.running
    xor a                   ; the wait state: standing on guard
    ld [wNes + $BA], a
    ld hl, wNes + $04FF
    res 7, [hl]
    ld a, $0A
    jp OppGuardPose

; $C550: run the script from OppStateIndex until an op sets a wait.
OppStateUpdate:
    ld hl, wNes + nOppStateIndex
    ld c, [hl]
    inc [hl]
    call OppByte
    inc c                   ; Y past the op
    ld b, a
    and $0F
    ld e, a                 ; X = low nibble
    ld a, b
    swap a
    and $0F
    ld b, e
    add a
    ld e, a
    ld d, 0
    ld hl, OppOps
    add hl, de
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    jp hl

OppOps:
    dw OppLoadSprites, OppSpritesXY, OppSetXYTimed, OppChance
    dw OppLoadSpritesFlip, OppSpritesXYFlip, OppSprtMove, OppMoveSprites
    dw OppSetTimer, OppPoke, OppBigMove, OppUpdate1
    dw OppUpdate1, OppUpdate1, OppUpdate1, OppUpdate2

; $C582: a zero byte after an op means "and go straight on".
OppZeroByte:
    ld a, [wNes + nOppStateIndex]
    ld c, a
    call OppByte
    and a
    ret nz
    ld hl, wNes + nOppStateIndex
    inc [hl]
    jp OppStateUpdate

OppLoadSpritesFlip:         ; $C5C8
    ld a, 1
    ld [wNes + nOppFlip], a
OppLoadSprites:             ; $C58D: show frame (byte), for X frames
    ld a, b
    ld [wNes + nOppStateTimer], a
    call OppByte
    ld [wNes + nOppBaseAnimIndex], a
    ld a, $80
    ld [wNes + nOppAnimFlags], a
    ld hl, wNes + nOppStateIndex
    inc [hl]
    jp OppZeroByte

OppSpritesXYFlip:           ; $C5CE
    ld a, 1
    ld [wNes + nOppFlip], a
OppSpritesXY:               ; $C59B: frame, then X and Y position
    ld a, b
    ld [wNes + nOppStateTimer], a
    call OppByte
    inc c
    ld [wNes + nOppBaseAnimIndex], a
    ld a, $80
    ld [wNes + nOppAnimFlags], a
OppXYPos:                   ; $C5A6
    call OppByte
    inc c
    ld [wNes + nOppBaseX], a
    call OppByte
    inc c
    ld [wNes + nOppBaseY], a
    ld a, c
    ld [wNes + nOppStateIndex], a
    ret

OppSetXYTimed:              ; $C5B3
    ld a, b
    ld [wNes + nOppStateTimer], a
    jp OppXYPos

OppChance:                  ; $C5B7: with chance X/16, jump to index (byte); else go on
    ld a, b
    push bc
    call NesChance15
    pop bc
    jp nc, .skip
    call OppByte
    ld c, a
    jp .go
.skip:
    inc c
.go:
    ld a, c
    ld [wNes + nOppStateIndex], a
    jp OppStateUpdate

OppSprtMove:                ; $C5D4: move by (byte) once, for X frames
    ld a, b
    ld [wNes + nOppStateTimer], a
OppMoveAgain:               ; $C5D6
    call OppByte
    ld hl, wNes + nOppStateIndex
    inc [hl]
    call OppMovePair
    ld a, 1                 ; position changed
    ld [wNes + nOppAnimFlags], a
    jp OppZeroByte

; $C830: add the signed nibbles of A to OppBaseX (high) and OppBaseY (low).
OppMovePair:
    ld e, a
    swap a
    call .nibble
    ld hl, wNes + nOppBaseX
    add [hl]
    ld [hl+], a
    ld a, e
    call .nibble
    add [hl]
    ld [hl], a
    ret
.nibble:
    and $0F
    cp $08
    ret c
    or $F0
    ret

OppMoveSprites:             ; $C5E6: X: bits 0-1 frames per step - 1, bits 2-3 steps - 1
    ld a, b
    and 3
    inc a
    ld [wNes + nOppStateTimer], a
    ld [wNes + nOppAnimSegTimer], a
    ld a, b
    srl a
    srl a
    inc a
    ld [wNes + nOppAnimSeg], a
    jp OppMoveAgain

OppSetTimer:                ; $C5F9
    call OppByte
    ld [wNes + nOppStateTimer], a
    ld hl, wNes + nOppStateIndex
    inc [hl]
    ret

OppPoke:                    ; $C600: write X bytes to a RAM address
    call OppByte
    inc c
    ld e, a
    call OppByte
    inc c
    add HIGH(wNes)
    ld d, a
.copy:
    call OppByte
    inc c
    ld [de], a
    inc de
    dec b
    jp nz, .copy
    ld a, c
    ld [wNes + nOppStateIndex], a
    jp OppStateUpdate

OppBigMove:                 ; $C61E: step toward ($04D0, $04D1), at most ($04D2, $04D3) a frame
    ld a, b
    ld [wNes + nOppStateTimer], a
    ld b, 0
.axis:                      ; $C622 / $C649, for X = B
    ld hl, wNes + nOppBaseX
    ld a, l
    add b
    ld l, a
    ld d, [hl]              ; position
    ld hl, wNes + $04D0
    ld a, l
    add b
    ld l, a
    ld a, d
    sub [hl]                ; position - target
    inc l
    inc l
    ld e, [hl]              ; the most it moves
    bit 7, a
    jp z, .down
    cpl                     ; below the target: up by min(target - position, step)
    inc a
    cp e
    jp c, .up
    ld a, e
.up:
    add d
    jp .store
.down:                      ; above (or on) it: down by min(position - target, step)
    cp e
    jp c, .sub
    ld a, e
.sub:
    ld e, a
    ld a, d
    sub e
.store:
    ld hl, wNes + nOppBaseX
    ld e, a
    ld a, l
    add b
    ld l, a
    ld [hl], e
    inc b
    ld a, b
    cp 2
    jp nz, .axis
    ld a, [wNes + nOppBaseX]          ; there on both axes?
    ld hl, wNes + $04D0
    cp [hl]
    jp nz, .notThere
    ld a, [wNes + nOppBaseY]
    inc l
    cp [hl]
    jp nz, .notThere
    call OppByte            ; arrived: on to index (byte)
    ld [wNes + nOppStateIndex], a
    ret
.notThere:
    inc c
    ld a, c
    ld [wNes + nOppStateIndex], a
    ret

; ---- $C670: ops $B0-$EF (low nibble X) ----
OppUpdate1:
    ld a, b
    add a
    ld e, a
    ld d, 0
    ld hl, OppOps1
    add hl, de
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    jp hl

OppOps1:
    dw OppCall, OppReturn, OppStateUpdate, OppStateUpdate
    dw OppVarTime, OppNotPunch, OppSprite8, OppSprite16
    dw OppIf16, OppClock, OppStateUpdate, OppStateUpdate
    dw OppAudio, OppStateUpdate, OppStateUpdate, OppStateUpdate

OppCall:                    ; $C68E: call a script subroutine (a NES pointer)
    ld a, [wNes + nOppStBasePtr]
    ld [wNes + nOppPtrReturn], a
    ld a, [wNes + nOppStBasePtr + 1]
    ld [wNes + nOppPtrReturn + 1], a
    call OppByte
    inc c
    ld b, a
    call OppByte
    inc c
    sub NES_BANK_DELTA
    ld [wNes + nOppStBasePtr + 1], a
    ld a, b
    ld [wNes + nOppStBasePtr], a
    ld a, c
    ld [wNes + nOppIndexReturn], a
    xor a
    ld [wNes + nOppStateIndex], a
    jp OppStateUpdate

OppReturn:                  ; $C6AA
    ld a, [wNes + nOppPtrReturn]
    ld [wNes + nOppStBasePtr], a
    ld a, [wNes + nOppPtrReturn + 1]
    ld [wNes + nOppStBasePtr + 1], a
    ld a, [wNes + nOppIndexReturn]
    ld [wNes + nOppStateIndex], a
    xor a
    ld [wNes + nOppPtrReturn + 1], a
    jp OppStateUpdate

OppVarTime:                 ; $C6BD
    ld a, [wNes + nVariableStTime]
    ld [wNes + nOppStateTimer], a
    ret

OppNotPunch:                ; $C6C3
    xor a
    ld [wNes + nOppPunching], a
    jp OppStateUpdate

OppSprite8:                 ; $C6CA: 8x8 sprites (the NES's drawing; noted, not needed here)
    ld a, 8
    ld [wNes + $80], a
    jp OppStateUpdate
OppSprite16:                ; $C6D7
    ld a, $10
    ld [wNes + $80], a
    jp OppStateUpdate

OppIf16:                    ; $C6DF: if RAM (16-bit address) = value, go to index
    call OppByte
    inc c
    ld e, a
    call OppByte
    inc c
    add HIGH(wNes)
    ld d, a
    jp OppIfAt

OppClock:                   ; $C6EA: start (1) or stop (0) the round clock
    call OppByte
    and a
    jp z, .set
    ld b, a
    ld a, [wNes + nRoundTmrStart]
    and a
    ld a, b
    jp nz, .set
    ld [wNes + nRoundTmrStart], a
.set:
    xor 1
    ld b, a
    ld a, [wNes + nRoundTmrCntrl]
    and $FE
    or b
    ld [wNes + nRoundTmrCntrl], a
    ld hl, wNes + nOppStateIndex
    inc [hl]
    ld a, $64
    ld [wNes + nRoundTimerUB], a
    ret

OppAudio:                   ; $C70C: start a sound (low 2 bits: the channel's slot at $F0)
    call OppByte
    ld hl, wNes + nOppStateIndex
    inc [hl]
    ld e, a
    and 3
    ld l, a
    ld h, HIGH(wNes)
    ld a, l
    add $F0
    ld l, a
    ld a, e
    and $FC
    bit 7, a
    jp nz, .set
    srl a
    srl a
.set:
    ld [hl], a
    jp OppStateUpdate

; ---- $C720: ops $F0-$FF ----
OppUpdate2:
    ld a, b
    add a
    ld e, a
    ld d, 0
    ld hl, OppOps2
    add hl, de
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    jp hl

OppOps2:
    dw OppPunchActive, OppJump, OppIfZp, OppRepeatTo
    dw OppToWait, OppRepeat, OppPunchSideDmg, OppDefense
    dw OppC7E1, OppPunch, OppWrite, OppSpecTimer
    dw OppComboWait, OppSet5A, OppStatus82, OppDone

OppPunchActive:             ; $C744: the punch is out; once resolved, go to the result's index
    ld a, [wNes + nOppPunchSts]
    bit 7, a
    jp nz, OppStay
    and a
    jp nz, OppPunchResult
    ld a, PUNCH_ACTIVE
    ld [wNes + nOppPunchSts], a
OppStay:                    ; $C74E: stay on this op
    ld hl, wNes + nOppStateIndex
    dec [hl]
    ret
OppPunchResult:
    cp 3                    ; landed: past the three result indexes
    jp z, .landed
    dec a                   ; blocked 1 -> +0, ducked 2 -> +1, dodged 4 -> +2
    cp 3
    jp c, .index
    dec a
.index:
    add c
    ld c, a
    call OppByte
    jp .end
.landed:
    ld a, c
    add 3
.end:
    ld c, a
    xor a
    ld [wNes + nOppPunchSts], a
    ld a, c
    ld [wNes + nOppStateIndex], a
    jp OppStateUpdate

OppJump:                    ; $C770: to another state's script (a NES pointer), at an index
    call OppByte
    inc c
    ld b, a
    call OppByte
    inc c
    ld d, a
    call OppByte            ; the index, read before the pointer moves
    ld [wNes + nOppStateIndex], a
    ld a, b
    ld [wNes + nOppStBasePtr], a
    ld a, d
    sub NES_BANK_DELTA
    ld [wNes + nOppStBasePtr + 1], a
    jp OppStateUpdate

OppIfZp:                    ; $C784: if zero page (byte) = value (byte), go to index (byte)
    call OppByte
    inc c
    ld e, a
    ld d, HIGH(wNes)
OppIfAt:                    ; $C78B: DE = RAM address; value, then the index
    call OppByte
    inc c
    ld b, a
    ld a, [de]
    cp b
    jp nz, .no
    call OppByte
    ld c, a
    jp .go
.no:
    inc c
.go:
    ld a, c
    ld [wNes + nOppStateIndex], a
    jp OppStateUpdate

OppRepeatTo:                ; $C7A7: repeat from index (byte) until the counter runs out
    ld hl, wNes + nOppStRepeat
    dec [hl]
    jp z, .done
    call OppByte
    ld c, a
    jp .go
.done:
    inc c
.go:
    ld a, c
    ld [wNes + nOppStateIndex], a
    jp OppStateUpdate

OppToWait:                  ; $C7B6
    ld a, $81
    ld [wNes + nOppCurState], a
    ret

OppRepeat:                  ; $C7BB
    call OppByte
    ld [wNes + nOppStRepeat], a
    ld hl, wNes + nOppStateIndex
    inc [hl]
    ret

OppPunchSideDmg:            ; $C7C2: which side of Mac it comes at, and its damage
    call OppByte
    inc c
    ld [wNes + nOppPunchSide], a
    call OppByte
    inc c
    ld [wNes + nOppPunchDamage], a
OppIndexZero:               ; $C7CC
    ld a, c
    ld [wNes + nOppStateIndex], a
    jp OppZeroByte

OppDefense:                 ; $C7D1: four defense bytes
    ld de, wNes + nOppHitDefense
    REPT 4
        call OppByte
        inc c
        ld [de], a
        inc e
    ENDR
    jp OppIndexZero

OppC7E1:                    ; $C7E1
    ld hl, wNes + $53
    inc [hl]
    inc [hl]
    ld a, 1
    ld [wNes + $52], a
    ret

OppPunch:                   ; $C7EA: he's throwing a punch
    ld a, 1
    ld [wNes + nOppPunching], a
    jp OppStateUpdate

OppWrite:                   ; $C7F1: write a zero-page byte
    call OppByte
    inc c
    ld e, a
    call OppByte
    inc c
    ld d, HIGH(wNes)
    ld [de], a
    jp OppIndexZero

OppSpecTimer:               ; $C806
    ld a, [wNes + nTimerVal0585]
    ld [wNes + nComboTimer], a
    ret

OppComboWait:               ; $C80C: until the combo timer runs out
    ld a, [wNes + nComboTimer]
    and a
    jp z, OppStateUpdate
    jp OppStay

OppSet5A:                   ; $C816
    call OppByte
    ld [wNes + $5A], a
    ld hl, wNes + nOppStateIndex
    inc [hl]
    ret

OppStatus82:                ; $C81D
    ld a, $82
    ld [wNes + nOppStateStatus], a
    ret

OppDone:                    ; $C821: the end of the state
    ld hl, wNes + nOppStateIndex
    dec [hl]
    ld a, STAT_FINISHED
    ld [wNes + nOppStateStatus], a
    ret

; ---- the AI ---------------------------------------------------------------------------------------

AiByte:                     ; byte C of the AI script ($3B)
    ld hl, wNes + $3B
    jp NesByteAt
TlByte:                     ; byte C of the round timeline ($31)
    ld hl, wNes + $31
    jp NesByteAt

; $B10A: while he waits, a new AI mode can take over (from the timeline, or after a knockdown etc.).
NesAiMode::
    ld a, [wNes + nOppCurState]
    and $7F
    cp 1
    ret nz
    ld a, [wNes + $36]
    bit 7, a
    ret nz
    and a
    jp z, .pending
    srl a
    ld b, 1
    jp c, NesAiSet.b
    srl a
    ld b, 7
    jp c, NesAiSet.b
    srl a
    ld b, 6
    jp c, NesAiSet.b
    srl a
    ld b, 2
    jp c, NesAiSet.b
    ret
.pending:
    ld a, [wNes + $37]
    bit 7, a
    ret z
NesAiSet:                   ; $B139: A = mode (0-7): its AI script and timings, from the table at $0500
    ld b, a
.b:
    ld a, b
    and 7
    ld [wNes + $35], a
    ld b, a
    and 6
    swap a                  ; (mode & 6) * 16
    ld e, a                 ; X
    ld a, b
    and 1
    add a
    add e
    ld l, a                 ; Y
    ld h, HIGH(wNes + $0500)
    ld a, [hl+]
    ld [wNes + $3B], a
    ld a, [hl]
    sub NES_BANK_DELTA
    ld [wNes + $3C], a
    xor a
    ld [wNes + $3A], a
    ld [wNes + $37], a
    inc a
    ld [wNes + $39], a
    ld l, e
    ld h, HIGH(wNes + $0500)
    ld a, l
    add 4
    ld l, a
    ld a, [hl+]             ; $0504
    ld [wNes + $0584], a
    ld a, [hl+]             ; $0505
    ld [wNes + $0580], a
    ld [wNes + nVariableStTime], a
    ld a, [hl]              ; $0506
    and 7
    ld [wNes + $0582], a
    ld a, [hl+]
    and $F8
    rrca
    rrca
    rrca
    ld [wNes + $0583], a
    ld de, wNes + $0585     ; $0507-$050E
    REPT 8
        ld a, [hl+]
        ld [de], a
        inc e
    ENDR
    ld a, $80
    ld [wNes + $36], a
    ret

; $B196: while he waits, his AI script counts down and then picks his next state.
NesAi::
    ld a, [wNes + $38]
    and a
    ret z
    ld a, [wNes + nOppCurState]
    cp 1
    ret nz
    ld hl, wNes + $39
    dec [hl]
    ret nz
    inc [hl]
AiNext:                     ; $B1A5
    ld a, [wNes + $3A]
    ld c, a
    call AiByte
    ld b, a
    ld hl, wNes + $3A
    inc [hl]
    inc c
    cp $80
    jp nc, AiHigh
    ld a, b
    and $0F
    ld d, a                 ; X
    ld a, b
    swap a
    and $0F
    jp z, .state
    dec a
    jp z, AiChance
    dec a
    jp z, AiRandom
    ret
.state:                     ; $B1C1: wait X, then this state now
    ld a, d
    ld [wNes + $39], a
    ld hl, wNes + $3A
    inc [hl]
AiSetState:                 ; $B1C5
    call AiByte
    ld [wNes + nOppCurState], a
    ld a, 1
    ld [wNes + nOppStateTimer], a
    ret
AiChance:                   ; $B1CE: with chance X/16, jump
    ld a, d
    call NesChance15
    jp nc, AiSkip
AiJumpHere:                 ; $B1D4
    call AiByte
    ld c, a
AiGoto:                     ; $B1D7
    ld a, c
    ld [wNes + $3A], a
    jp AiNext
AiSkip:                     ; $B1DC
    inc c
    jp AiGoto
AiRandom:                   ; $B1DF: one of the next 8 states, at random
    ld a, d
    ld [wNes + $39], a
    call NesRandom
    and 7
    ld hl, wNes + $3A
    add [hl]
    ld c, a
    ld a, [hl]
    add 8
    ld [hl], a
    jp AiSetState

AiHigh:                     ; $B1F4
    ld a, b
    cp $F0
    jp nc, AiControl
    cp $90
    jp nc, AiPoke
    and $0F                 ; $80-$8F: how long before the next step
    jp z, .byte
    cp 1
    jp z, .either
    add a                   ; $82+: 4 frames per step of the low nibble
    add a
    ld [wNes + $39], a
    ret
.either:                    ; $81: one of the next two bytes, at random
    call NesRandom
    bit 7, a
    jp nz, .first
    inc c
    call AiByte
    inc c
    jp .set
.first:
    call AiByte
    inc c
    inc c
    jp .set
.byte:                      ; $80: the next byte
    call AiByte
    inc c
.set:
    ld b, a
    ld a, c
    ld [wNes + $3A], a
    ld a, b
    ld [wNes + $39], a
    ret

AiPoke:                     ; $B21E: write bytes to RAM
    and $0F
    ld b, a
    call AiByte
    inc c
    ld [wNes + $E1], a
    call AiByte
    inc c
    add HIGH(wNes)
    ld [wNes + $E2], a
.copy:
    call AiByte
    inc c
    push af
    ld a, [wNes + $E1]
    ld e, a
    ld a, [wNes + $E2]
    ld d, a
    pop af
    ld [de], a
    inc de
    ld a, e
    ld [wNes + $E1], a
    ld a, d
    ld [wNes + $E2], a
    dec b
    jp nz, .copy
    jp AiGoto

AiControl:                  ; $B23C
    and $0F
    jp z, .modeBack
    dec a
    jp z, .clear
    dec a
    jp z, .ifZp
    dec a
    jp z, .loopN
    dec a
    jp z, .loopTo
    ret
.modeBack:                  ; $F0: back to the mode in $0584
    ld a, [wNes + $0584]
    jp NesAiSet
.clear:                     ; $F1
    ld hl, wNes + $36
    res 7, [hl]
    jp AiNext
.ifZp:                      ; $F2: if zero page (byte) = value (byte), jump
    call AiByte
    inc c
    ld b, a
    call AiByte
    inc c
    ld e, b
    ld d, HIGH(wNes)
    ld b, a
    ld a, [de]
    cp b
    jp z, AiJumpHere
    jp AiSkip
.loopN:                     ; $F3: a loop count
    call AiByte
    ld [wNes + $3D], a
    ld hl, wNes + $3A
    inc [hl]
    jp AiNext
.loopTo:                    ; $F4: until the count runs out, jump
    ld hl, wNes + $3D
    dec [hl]
    jp z, AiSkip
    jp AiJumpHere

; $B069: the round timeline. At its next entry's time (seconds left, $0311) or right away ($D0+), it
; sets an AI mode, writes RAM or copies AI tables into $0500; zero bytes chain more actions.
NesTimeline::
    ld a, [wNes + $30]
    and a
    ret z
    ld c, 0
    call TlByte
    cp $D0
    jp nc, .op
    ld hl, wNes + nSecondsLeft
    cp [hl]
    ret nz
.and:                       ; $B07A
    inc c
    call TlByte
.op:                        ; $B07D
    inc c
    cp $E0
    jp nc, .e0
    and $87                 ; an AI mode (bit 7: take it when he next waits)
    ld [wNes + $37], a
    jp .more
.e0:
    cp $F0
    jp nc, .f0
    cp $E0
    jp z, .more
    and $0F                 ; $E1-$EF: write bytes to RAM. The NES steps the pointer's index, not the
    ld b, a                 ; address ($B0A3: STA ($E1,X), INX), so only the first byte lands; the rest go
    call TlByte             ; through scratch bytes that point into ROM (its drawing leaves $E3 = $80), and
    inc c                   ; are lost. Kept that way: Joe's data counts on it.
    ld l, a
    push hl
    call TlByte
    inc c
    add HIGH(wNes)
    pop hl
    ld h, a
    push hl
    call TlByte
    inc c
    pop hl
    ld [hl], a
.lost:
    dec b
    jp z, .more
    inc c
    jp .lost
.more:                      ; $B0AA: a zero next means another action now
    call TlByte
    and a
    jp z, .and
    ld hl, wNes + $31       ; done: the timeline moves on
    ld a, [hl]
    add c
    ld [hl+], a
    ld a, [hl]
    adc 0
    ld [hl], a
    ret
.f0:
    cp $FF
    jp z, .copy
    cp $FE
    ld b, 1
    jp z, .set
    cp $FD
    ld b, 2
    jp z, .set
    jp .more
.copy:                      ; $FF: dest in $0500, count, AI table number
    call TlByte
    inc c
    ld [wNes + $E3], a      ; dest offset
    call TlByte
    inc c
    ld b, a                 ; count
    call TlByte
    inc c
    ld e, a
    ld d, 0
    ld a, [wNes + $33]
    ld l, a
    ld a, [wNes + $34]
    ld h, a
    add hl, de
    ld a, [hl+]             ; the table (a NES pointer)
    ld e, a
    ld a, [hl]
    sub NES_BANK_DELTA
    ld d, a
    ld a, [wNes + $E3]
    ld l, a
    ld h, HIGH(wNes + $0500)
.copyByte:
    ld a, [de]
    inc de
    ld [hl+], a
    dec b
    jp nz, .copyByte
    jp .more
.set:                       ; $FE / $FD: a $0500 offset, then 1 or 2 bytes
    call TlByte
    inc c
    ld l, a
    ld h, HIGH(wNes + $0500)
.setByte:
    push hl
    call TlByte
    pop hl
    inc c
    ld [hl+], a
    dec b
    jp nz, .setByte
    jp .more

; $C291: his guard follows where Mac aims (after his reaction time), and when Mac throws, he may
; block or slip it, by the chances in his AI mode ($0586-$058C).
NesGuard::
    ld a, [wNes + nOppCurState]
    and a
    ret z
    cp $81
    jp z, .newWait
    cp 1
    jp nz, GuardPunch
    ld a, [wNes + nVulnerableTimer]
    and a
    jp nz, .vulnerable
    ld a, [wNes + $AC]
    and a
    jp z, GuardPunch
    bit 7, a
    jp nz, GuardPunch
    ld a, [wNes + $04FE]
    and a
    jp nz, .counting
    ld a, [wNes + nMacStatus]
    and $7F
    cp 1
    jp nz, GuardPunch
    call GuardAimed
    jp z, GuardPunch
    ld a, [wNes + $05BC]
    bit 7, a
    jp nz, .react
    ld [wNes + $04FE], a
    call GuardSwitch
    jp GuardPunch
.react:
    ld a, [wNes + nReactTimer]
    ld [wNes + nVulnerableTimer], a
    jp GuardPunch
.counting:
    dec a
    ld [wNes + $04FE], a
    call GuardAimed
    jp z, GuardPunch
    ld a, [wNes + nReactTimer]
    ld [wNes + nVulnerableTimer], a
    xor a
    ld [wNes + $04FE], a
    jp GuardPunch
.vulnerable:                ; $C2E5
    dec a
    cp $80
    jp nz, .store
    xor a
.store:
    ld [wNes + nVulnerableTimer], a
    and a
    call z, GuardSwitch
    jp GuardPunch
.newWait:                   ; $C27B
    ld a, [wNes + $AC]
    bit 7, a
    jp nz, GuardPunch
    xor a
    ld [wNes + $04FE], a
    ld [wNes + $AC], a
    ld hl, wNes + $04FF
    set 7, [hl]
GuardPunch:                 ; $C2F7: Mac just threw a punch ($99)
    ld a, [wNes + $99]
    and a
    ret z
    ld [wNes + $E5], a
    xor a
    ld [wNes + $99], a
    ld [wNes + $E7], a
    ld a, [wNes + nVulnerableTimer]
    and a
    jp z, .decide
    bit 7, a
    ret nz
    ld hl, wNes + $05B9     ; open: how long he stays open depends on the timer
    cp [hl]
    ld a, [wNes + $05BA]
    jp nc, .open
    ld a, [wNes + $05BB]
.open:
    ld [wNes + nVulnerableTimer], a
    ret
.decide:                    ; $C319
    ld a, [wNes + nOppPunching]
    and a
    ret nz
    ld a, [wNes + nComboTimer]
    and a
    ret nz
    ld a, [wNes + nMacPunchType]
    ld b, a
    ld a, [wNes + $0348]
    and a
    jp nz, .special
    bit 7, b
    jp nz, .slipStar
.special:                   ; $C32B
    ld a, [wNes + nSpecialKD]
    cp 1
    jp nz, .kd7
    bit 7, b
    jp z, .normal
    ret
.kd7:
    cp 7
    jp nz, .normal
    bit 7, b
    ret z
.slipStar:                  ; $C33D
    ld a, $83
.state:
    ld [wNes + nOppCurState], a
    ret
.normal:                    ; $C342
    bit 7, b
    jp z, .punch
    ld a, $89
    jp .state
.punch:                     ; $C349: X = 0 to the face, 2 to the body
    ld a, b
    and 2
    ld b, a
    xor 2
    srl a
    ld [wNes + $E6], a
    ld a, [wNes + $E5]
    bit 7, a
    jp z, .guardSide
    and $7F
    ld hl, wNes + $058A
    and [hl]
    jp z, .guardSide
    ld a, [wNes + $058B]
    push bc
    call NesChanceFF
    pop bc
    jp nc, .guardSide
    ld a, [wNes + $058C]
    jp .state
.guardSide:                 ; $C369: is his guard already where the punch goes?
    ld a, [wNes + $AC]
    bit 7, a
    jp nz, .which
    ld a, [wNes + nOppCurState]
    and $7F
    cp 1
    jp nz, .which
    ld a, [wNes + $04FF]
    and $7F
    ld hl, wNes + $E6
    cp [hl]
    jp nz, .which
    ld hl, wNes + $E7
    inc [hl]
.which:                     ; $C380
    ld a, b
    and a
    jp z, .face
    ld a, [wNes + $E7]      ; to the body
    and a
    jp nz, .bodyBlock
    ld a, [wNes + $0587]
    call NesChanceFF
    ret nc
.bodyBlock:                 ; $C38F
    ld a, [wNes + $0589]
    and $7F
.bodyRoll:                  ; $C392
    call NesChance7F
    jp nc, .bodyGuard
    ld a, 1
    ld [wNes + $AB], a
.bodyGuard:                 ; $C39D: guard states $89-$8C by the punch
    ld a, [wNes + nMacPunchType]
    and 3
    add $89
    jp .state
.face:                      ; $C3A2
    ld a, [wNes + $E7]
    and a
    jp nz, .faceBlock
    ld a, [wNes + $0586]
    call NesChanceFF
    ret nc
.faceBlock:                 ; $C3AE
    ld a, [wNes + $0588]
    bit 7, a
    jp nz, .faceAsBody
    call NesChance7F
    jp nc, .slip
    ld a, $80
    ld [wNes + $AB], a
.slip:                      ; $C3BC: slip states $83-$84 by the punch's side
    ld a, [wNes + nMacPunchType]
    and 1
    add $83
    jp .state
.faceAsBody:
    and $7F
    jp .bodyRoll

GuardSwitch:                ; $C3C1: the guard goes where he's being aimed at (bit 7: show it)
    call GuardAimed
    or $80
    ld [wNes + $04FF], a
    ret
GuardAimed:                 ; $C3CA: A = up on the d-pad (1/0); Z if his guard is already there
    ld a, [wNes + $04FF]
    and $7F
    ld [wNes + $E7], a
    ld a, [wNes + nDPad1Status]
    srl a
    srl a
    srl a
    ld hl, wNes + $E7
    cp [hl]
    ret

; ---- starting a fight and a round ----

; $AB0C: his fight data (96 bytes) to $05A0, the timeline and AI tables' addresses to $31-$34.
NesFightStart::
    ld hl, wNes             ; a clean start, but the sound engine's ($F0-$FF, $0700-$07FF): what's playing
    ld bc, $F0              ; (the crowd) plays on into the fight
.clear:
    xor a
    ld [hl+], a
    dec bc
    ld a, b
    or c
    jp nz, .clear
    ld hl, wNes + $100
    ld bc, $600
.clear2:
    xor a
    ld [hl+], a
    dec bc
    ld a, b
    or c
    jp nz, .clear2
    ld a, [NesFighter + FT_NES_OFFSET + $0E]
    ld l, a
    ld a, [NesFighter + FT_NES_OFFSET + $0F]
    sub NES_BANK_DELTA
    ld h, a
    ld de, wNes + $05A0
    ld b, $60
.data:
    ld a, [hl+]
    ld [de], a
    inc de
    dec b
    jp nz, .data
    ld a, [wNes + $05B0]    ; stars: hits before the first
    ld [wNes + $0347], a
    ld a, [wNes + $05B2]
    ld [wNes + $0348], a
    ld hl, wNes + $05E8     ; timeline and AI table pointers, made GB addresses
    ld a, [hl+]
    ld [wNes + $31], a
    ld a, [hl+]
    sub NES_BANK_DELTA
    ld [wNes + $32], a
    ld a, [hl+]
    ld [wNes + $33], a
    ld a, [hl]
    sub NES_BANK_DELTA
    ld [wNes + $34], a
    ld a, 3                 ; $AB37: three rounds
    ld [wNes + $0310], a
    ld a, 1
    ld [wNes + nVulnerableTimer], a
    ld [wNes + $04FE], a
    ld a, $80               ; points count
    ld [wNes + $03E7], a
    inc a                   ; $81: both at full HP, then live ($8806)
    ld [wNes + $0390], a
    ret

; $AE5F: the HP each comes back with after a knockdown this round (Mac's scripts restore it, $84BE):
; Mac's, plus the corner's refill ($03D9: up to $5F; a loss leaves at least 1); his, as it is.
NesHpCarry:
    ld a, [wNes + $0391]
    ld b, a
    ld a, [wNes + $03D9]
    and a
    jp z, .none
    bit 7, a
    jp nz, .loss
    add b
    cp $5F
    jp c, .set
    ld a, $5F
    jp .set
.loss:
    add b
    jp z, .one
    bit 7, a
    jp z, .set
.one:
    ld a, 1
    jp .set
.none:
    ld a, b
.set:
    ld [wNes + $0397], a
    xor a
    ld [wNes + $03D9], a
    ld a, [wNes + $0398]
    ld [wNes + $039E], a
    ret

; $ABB3: a round begins (A = round number, 1-3): the clock's seconds, his AI from the start, waiting.
NesRoundStart::             ; A = round (1-3)
    ld [wNes + nRoundNumber], a
    ld a, $C0               ; ($ABB3) the timeline's seconds; fresh state for the round
    ld [wNes + nSecondsLeft], a
    xor a
    ld [wNes + nKnockdownSts], a
    ld [wNes + nVulnerableTimer], a
    ld [wNes + $04FE], a
    ld [wNes + $04FF], a
    ld [wNes + nOppAnimSeg], a
    ld [wNes + $36], a
    ld [wNes + $35], a
    ld [wNes + $03CA], a    ; knockdowns this round
    ld [wNes + $8F], a
    dec a
    ld [wNes + $39], a
    ld a, $81
    ld [wNes + $40], a
    dec a
    ld [wNes + $37], a
    ld a, $81               ; the screen's on (his intro waits for it)
    ld [wNes + $1B], a
    ld a, [wNes + $05CE]    ; $AB96: him at his place
    ld [wNes + $B0], a
    ld a, [wNes + $05CF]
    ld [wNes + $B1], a
    ld a, 176               ; Mac at his
    ld [wNes + nMacX], a
    ld hl, wNes + $0310     ; $ABB0: a round fewer to go
    dec [hl]
    ld a, 1                 ; $ABD8
    ld [wNes + $03E0], a
    xor a                   ; $ABE3: the bars fill up from empty to the HP each brings in
    ld [wNes + $0392], a
    ld [wNes + $0393], a
    ld [wNes + $0399], a
    ld [wNes + $039A], a
.fill:
    call NesHp
    xor a                   ; ($C041 draws them)
    ld [wNes + $0394], a
    ld [wNes + $039B], a
    ld a, [wNes + $0392]
    ld hl, wNes + $0393
    cp [hl]
    jp nz, .fill
    ld a, [wNes + $0399]
    ld hl, wNes + $039A
    cp [hl]
    jp nz, .fill
    call NesHpCarry
    ld a, $30               ; $AC2D: the first frame sets the round up ($B5A9)
    ld [wNes + $00], a      ; the game's own: hearts, clock rate, both to their pre-round states
    ld a, 1                 ; ($AC31) his timeline and AI run
    ld [wNes + $30], a
    ld [wNes + $38], a
    ret

;;PART common
; ==== Little Mac: the NES game's own (PRG bank B, at $4000 as NesMac) ===============================
; Buttons ($AFBD), input ($8119), and his state scripts ($8319 + ops $8363-$85CA): poses, his place
; ($15), timing, when his punch arrives ($58), his defense ($76/$77), and when he can act again ($51).

DEF nMacX EQU $15
DEF nJoy1Buttons EQU $D0
DEF nMacCanPunch EQU $BC

; byte C of Mac's script ($54)
MacByte:
    ld hl, wNes + $54
    jp NesByteAt

; $AFBD: the buttons into status/history pairs ($D2-$DB). GB hPad -> NES bits A $80, B $40, select $20,
; start $10, up 8, down 4, left 2, right 1. History: bit 7 = pressed (once, the frame after it settles).
NesJoypad::
    ldh a, [hPad]
    ld b, a
    xor a
    bit PAD_RIGHT, b
    jp z, .r
    or $01
.r:
    bit PAD_LEFT, b
    jp z, .l
    or $02
.l:
    bit PAD_DOWN, b
    jp z, .d
    or $04
.d:
    bit PAD_UP, b
    jp z, .u
    or $08
.u:
    bit PAD_START, b
    jp z, .s
    or $10
.s:
    bit 2, b                ; select
    jp z, .se
    or $20
.se:
    bit PAD_B, b
    jp z, .bb
    or $40
.bb:
    bit PAD_A, b
    jp z, .aa
    or $80
.aa:
    ld [wNes + nJoy1Buttons], a
    ret
NesButtons::                ; $D0 into the status/history pairs
    ld a, [wNes + nJoy1Buttons]
    ld c, a
    and $0F
    ld b, 0
    call .button
    ld a, c
    and $80
    ld b, 2
    call .button
    ld a, c
    and $40
    ld b, 4
    call .button
    ld a, c
    and $10
    ld b, 6
    call .button
    ld a, c
    and $20
    ld b, 8
    call .button
    ld a, [wNes + nMacStatus]
    and $7F
    cp 7                    ; blocking: the buttons' presses wait
    ret nz
    ld b, 8
.mask:
    ld hl, wNes + $D3
    ld a, l
    add b
    ld l, a
    res 7, [hl]
    dec b
    dec b
    jp nz, .mask
    ret
.button:                    ; $B001: A = this button's bits now, B = its pair ($D2 + B status, + 1 history)
    ld d, a
    ld hl, wNes + $D2
    ld a, l
    add b
    ld l, a
    ld a, d
    cp [hl]
    jp z, .same
    ld [hl+], a             ; changed: not a press yet
    res 7, [hl]
    ret
.same:
    inc l
    and a
    jp z, .released
    bit 0, [hl]             ; held and settled: a press, once
    ret nz
    ld a, [hl]
    or $81
    ld [hl], a
    ret
.released:
    ld a, [hl]
    and $7E
    ld [hl], a
    ret

;;PART mac
; $81EF: was button B (0 A, 2 B, 4 START: histories at $D5 + B) newly pressed? Then it's used up: carry.
MacPressed:
    ld hl, wNes + $D5
    ld a, l
    add b
    ld l, a
    bit 7, [hl]
    ret z                   ; (carry clear from the add: no overflow in page)
    res 7, [hl]
    scf
    ret

; $8119: buttons into what Mac does next (status with bit 7: start it), when he's free to.
NesMacInput::
    ld a, [wNes + nMacStatus]
    and a
    ret z
    cp $40
    ret nc
    ld a, [wNes + $51]
    bit 7, a
    ret nz
    ld a, [wNes + nMacCanPunch]
    and a
    jp z, .tired
    ld b, 0                 ; A: the right hand, to the face with up held ($6B: 1 to the face)
    call MacPressed
    jp nc, .notA
    ld a, [wNes + nDPad1Status]
    and 8
    ld a, $89
    ld c, 0
    jp z, .set
    ld a, $8B
    ld c, 1
    jp .set
.notA:
    ld b, 2                 ; B: the left
    call MacPressed
    jp nc, .notB
    ld a, [wNes + nDPad1Status]
    and 8
    ld a, $8A
    ld c, 0
    jp z, .set
    ld a, $8C
    ld c, 1
    jp .set
.notB:
    ld a, [wNes + $0342]    ; START: a star punch, if he has one
    and a
    jp z, .pad
    ld b, 4
    call MacPressed
    jp nc, .pad
    ld a, $FF
    ld [wNes + $0341], a
    ld a, [wNes + $0348]
    and a
    jp z, .noDec
    dec a
    ld [wNes + $0348], a
.noDec:
    ld a, $8D
    ld c, 0
.set:                       ; $8180
    ld [wNes + nMacStatus], a
    ld a, c
    ld [wNes + $6B], a
    ret
.pad:                       ; $8187: the d-pad: dodge right, left, or block
    ld a, [wNes + $D3]
    bit 7, a
    jp z, .held
    and $7F
    ld c, a
    ld a, [wNes + nDPad1Status]
    ld b, a
    bit 0, b
    ld a, $83
    jp nz, .dir
    bit 1, b
    ld a, $85
    jp nz, .dir
    bit 2, b
    ld a, $87
    jp z, .none
.dir:                       ; $81AB
    ld [wNes + nMacStatus], a
    ld a, c
    ld [wNes + $D3], a
.none:
    xor a
    ld [wNes + $6B], a
    ret
.held:                      ; $81B4: a punch just ended with the d-pad still held: act on it now
    ld c, a
    ld a, [wNes + $6B]
    and a
    ret z
    ld a, [wNes + nJoy1Buttons]
    ld b, a
    bit 0, b
    ld a, $83
    jp nz, .dir
    bit 1, b
    ld a, $85
    jp nz, .dir
    bit 2, b
    ld a, $87
    jp nz, .dir
    jp .none
.tired:                     ; $81C8: no hearts: a punch button only makes him flail
    ld b, 0
    call MacPressed
    jp c, .flail
    ld b, 2
    call MacPressed
    jp c, .flail
    ld b, 4
    call MacPressed
    jp nc, .pad
.flail:
    ld a, $0A
    ld [wNes + $53], a
    xor a
    ld [wNes + $6B], a
    ret

; $85E2: carry with chance A/16 (Mac's version: against a random 1-16; A = 15 always).
MacChance:
    cp $0F
    jp z, .yes
    ld d, a
    call NesRandom
    and $0F
    inc a
    ld e, a
    ld a, d
    cp e                    ; SM83 carry = A < r; the 6502's = A >= r
    ccf
    ret
.yes:
    scf
    ret

; $8319: once a frame. A new status (bit 7) starts its script; otherwise the timer runs out, then on.
NesMacTick::
    ld a, [wNes + nMacStatus]
    and a
    ret z
    bit 7, a
    jp z, .running
    and $7F                 ; $82CC: a new status
    ld [wNes + nMacStatus], a
    ld hl, wNes + $51
    set 7, [hl]             ; busy until his script says he can act again
    ld a, 1
    ld [wNes + $52], a
    xor a
    ld [wNes + $53], a
    ld [wNes + $56], a
    ld [wNes + $58], a
    ld [wNes + $59], a
    ld b, a
    ld a, [wNes + nComboTimer]
    and a
    jp z, .noCombo
    ld a, [wNes + nComboCountDown]
    and a
    jp z, .noCombo
    inc b
.noCombo:
    ld a, b
    ld [wNes + $5B], a
    xor a
    ld hl, wNes + nMacPunchType     ; $74-$77
    ld [hl+], a
    ld [hl+], a
    ld [hl+], a
    ld [hl], a
    ld a, [wNes + nMacStatus]       ; his script: from $9800 below $40, $982C above
    ld hl, NesMac + $1800
    cp $40
    jp c, .table
    sub $40
    ld hl, NesMac + $182C
.table:
    add a
    ld e, a
    ld d, 0
    add hl, de
    ld a, [hl+]
    ld [wNes + $54], a
    ld a, [hl]
    sub NES_BANK_DELTA
    ld [wNes + $55], a
.running:
    ld hl, wNes + $52
    dec [hl]
    ret nz
    inc [hl]
MacStep:                    ; $8325
    ld hl, wNes + $53
    ld c, [hl]
    inc [hl]
    call MacByte
    inc c
    ld b, a
    and $0F
    ld e, a
    ld a, b
    swap a
    and $0F
    ld b, e                 ; X
    add a
    ld e, a
    ld d, 0
    ld hl, MacOps
    add hl, de
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    jp hl

MacOps:
    dw MacFrame, MacFrameAt, MacMove, MacChanceOp, MacFrameMove, MacWait, MacWait, MacWait
    dw MacWait, MacSub, MacSub, MacSub, MacSub, MacSub, MacSub, MacF

MacZero:                    ; $8358: a zero next: go straight on
    ld a, [wNes + $53]
    ld c, a
    call MacByte
    and a
    ret nz
    ld hl, wNes + $53
    inc [hl]
    jp MacStep

MacFrame:                   ; $8363: frame (byte), for X frames
    ld a, b
    ld [wNes + $52], a
    call MacByte
    inc c
MacShow:                    ; $8368
    ld [wNes + $61], a
    ld a, $80
    ld [wNes + $60], a
MacIndex:                   ; $836E
    ld a, c
    ld [wNes + $53], a
    ret

MacFrameAt:                 ; $8371: frame and place
    ld a, b
    ld [wNes + $52], a
    call MacByte
    inc c
    ld [wNes + $61], a
    call MacByte
    inc c
    ld [wNes + nMacX], a
    ld a, $80
    ld [wNes + $60], a
    jp MacIndex

MacMove:                    ; $837F: his place moves (signed byte), for X frames
    ld a, b
    ld [wNes + $52], a
    call MacByte
    inc c
    ld hl, wNes + nMacX
    add [hl]
    ld [hl], a
    jp MacIndex

MacChanceOp:                ; $838B: with chance X/16, jump
    ld a, b
    call MacChance
    jp nc, .skip
    call MacByte
    ld c, a
    jp .go
.skip:
    inc c
.go:
    ld a, c
    ld [wNes + $53], a
    jp MacStep

MacFrameMove:               ; $839C: frame, then a move for X frames
    call MacByte
    inc c
    ld [wNes + $61], a
    ld a, $80
    ld [wNes + $60], a
    jp MacMove

MacWait:                    ; $83A7: wait (byte) frames
    call MacByte
    ld [wNes + $52], a
    ld hl, wNes + $53
    inc [hl]
    ret

MacSub:                     ; $83AE: ops $9x-$Ex by the low nibble
    ld a, b
    add a
    ld e, a
    ld d, 0
    ld hl, MacSubs
    add hl, de
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    jp hl

MacSubs:
    dw MacIfRight, MacIfLeft, MacIfDown, MacIfZp, MacDuck, MacPunchType, MacClock, MacHead
    dw MacBody, MacCall, MacReturn, MacHpReset, MacAudio, MacIf16, MacStep, MacStep

MacIfRight:                 ; $83CE: if the d-pad (just pressed) has right or up: jump
    ld e, 9
    jp MacIfPad
MacIfLeft:
    ld e, $0A
    jp MacIfPad
MacIfDown:
    ld e, 4
MacIfPad:                   ; $83D8
    ld a, [wNes + $D3]
    bit 7, a
    jp z, .skip
    and $7F
    ld d, a
    ld a, [wNes + nDPad1Status]
    and e
    jp z, .skip
    ld a, d
    ld [wNes + $D3], a
    call MacByte
    ld c, a
    jp .go
.skip:
    inc c
.go:
    ld a, c
    ld [wNes + $53], a
    jp MacStep

MacIfZp:                    ; $83F4: if zero page (byte) = value (byte): jump (byte)
    call MacByte
    inc c
    ld e, a
    ld d, HIGH(wNes)
MacIfAt:                    ; $83FB: DE = the address
    push de
    call MacByte
    inc c
    pop de
    ld b, a
    ld a, c
    ld [wNes + $53], a
    ld a, [de]
    cp b
    jp nz, .no
    call MacByte
    ld c, a
    jp .go
.no:
    inc c
.go:
    ld a, c
    ld [wNes + $53], a
    jp MacStep

MacIf16:                    ; $84E1: the same, for a 16-bit address
    call MacByte
    inc c
    ld b, a
    call MacByte
    inc c
    add HIGH(wNes)
    ld d, a
    ld e, b
    jp MacIfAt

MacDuck:                    ; $8417: ducking (down again while blocking) / blocking held
    ld a, [wNes + $6A]
    and a
    jp z, .first
    bit 7, a
    jp nz, .letGo
    ld a, [wNes + $D3]
    bit 7, a
    jp z, .past
    and $7F
    ld d, a
    ld a, [wNes + nDPad1Status]
    and 4
    jp z, .past
    ld a, d
    ld [wNes + $D3], a
    ld a, $0E               ; duck
    ld [wNes + nMacStatus], a
    call MacByte
    ld c, a
    ld a, c
    ld [wNes + $53], a
    jp MacStep
.past:                      ; $8438
    inc c
    ld a, c
    ld [wNes + $53], a
    ret
.letGo:                     ; $843C
    ld a, [wNes + $D3]
    and $81
    jp nz, .past
    ld b, $81
    ld a, [wNes + nMacCanPunch]
    and a
    jp nz, .wait
    inc b
.wait:
    ld a, b
    ld [wNes + nMacStatus], a
    jp .past
.first:                     ; $844D
    ld a, [wNes + $D3]
    and $81
    jp nz, .past
    ld a, 1
    ld [wNes + $6A], a
    jp .past

MacPunchType:               ; $8459: a punch is thrown (its type)
    ld a, 1
    ld [wNes + $99], a
    call MacByte
    inc c
    ld [wNes + nMacPunchType], a
    ld a, c
    ld [wNes + $53], a
    ret

MacClock:                   ; $8465: start / stop the clock
    call MacByte
    and a
    jp z, .set
    ld b, a
    ld a, [wNes + nRoundTmrStart]
    and a
    ld a, b
    jp nz, .set
    ld [wNes + nRoundTmrStart], a
.set:
    xor 1
    ld b, a
    ld a, [wNes + nRoundTmrCntrl]
    and $FE
    or b
    ld [wNes + nRoundTmrCntrl], a
    ld hl, wNes + $53
    inc [hl]
    ret

MacHead:                    ; $8482: $70 += byte; show it
    ld hl, wNes + $70
    jp MacPart
MacBody:                    ; $848F
    ld hl, wNes + $71
MacPart:
    call MacByteKeep
    inc c
    add [hl]
    ld [hl], a
    jp MacShow
MacByteKeep:                ; MacByte keeping HL
    push hl
    call MacByte
    pop hl
    ret

MacCall:                    ; $8493: call a script subroutine (a NES pointer)
    ld a, [wNes + $54]
    ld [wNes + $7E], a
    ld a, [wNes + $55]
    ld [wNes + $7F], a
    call MacByte
    inc c
    ld b, a
    call MacByte
    inc c
    sub NES_BANK_DELTA
    ld [wNes + $55], a
    ld a, b
    ld [wNes + $54], a
    ld a, c
    ld [wNes + $7D], a
    xor a
    ld [wNes + $53], a
    jp MacStep

MacReturn:                  ; $84AF
    ld a, [wNes + $7E]
    ld [wNes + $54], a
    ld a, [wNes + $7F]
    ld [wNes + $55], a
    ld a, [wNes + $7D]
    ld [wNes + $53], a
    jp MacStep

MacHpReset:                 ; $84BE
    ld a, [wNes + $0397]
    ld [wNes + $0391], a
    ld a, [wNes + $039E]
    ld [wNes + $0398], a
    jp MacStep

MacAudio:                   ; $84CD
    call MacByte
    ld hl, wNes + $53
    inc [hl]
    ld e, a
    and 3
    add $F0
    ld l, a
    ld h, HIGH(wNes)
    ld a, e
    and $FC
    bit 7, a
    jp nz, .set
    srl a
    srl a
.set:
    ld [hl], a
    jp MacStep

MacF:                       ; $84EC: ops $Fx
    ld a, b
    add a
    ld e, a
    ld d, 0
    ld hl, MacFs
    add hl, de
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    jp hl

MacFs:
    dw MacPunchOut, MacJump, MacReady, MacRepeatTo, MacDoneWait, MacRepeat, MacDamage, MacDefense
    dw MacIncZp, MacStep, MacSetZp, MacPal, MacPal2, MacHitSide, MacStep, MacFinished

MacPunchOut:                ; $8510: his punch is out; once it's resolved ($58), on to the result
    ld a, [wNes + $58]
    bit 7, a
    jp nz, .stay
    and a
    jp nz, .result
    ld b, $80
    ld a, [wNes + $5B]
    and a
    jp z, .mark
    inc b
.mark:
    ld a, b
    ld [wNes + $58], a
.stay:
    ld hl, wNes + $53
    dec [hl]
    ret
.result:
    dec a
    jp z, .first            ; 1: jump to the first byte
    dec a
    jp nz, .past            ; 3+: on past both
    inc c                   ; 2: the second
.first:
    call MacByte
    ld c, a
    jp MacJumpEnd
.past:
    inc c
    inc c
MacJumpEnd:                 ; $852C
    ld a, c
    ld [wNes + $53], a
    xor a
    ld [wNes + $58], a
    jp MacStep

MacJump:                    ; $8539: to another script (a NES pointer), at an index
    call MacByte
    inc c
    ld b, a
    call MacByte
    inc c
    push af                 ; (MacByte uses DE)
    call MacByte
    ld c, a
    ld a, b
    ld [wNes + $54], a
    pop af
    sub NES_BANK_DELTA
    ld [wNes + $55], a
    jp MacJumpEnd

MacReady:                   ; $854D: he can take new input
    ld hl, wNes + $51
    res 7, [hl]
    jp MacStep

MacRepeatTo:                ; $8556
    ld hl, wNes + $56
    dec [hl]
    jp z, .done
    call MacByte
    ld c, a
    jp .go
.done:
    inc c
.go:
    ld a, c
    ld [wNes + $53], a
    jp MacStep

MacDoneWait:                ; $8565: back to waiting ($81), or worn out ($82) with no hearts
    ld a, [wNes + nMacCanPunch]
    ld b, a
    ld a, $82
    sub b
    ld [wNes + nMacStatus], a
    ret

MacRepeat:                  ; $856D
    call MacByte
    ld [wNes + $56], a
    ld hl, wNes + $53
    inc [hl]
    ret

MacDamage:                  ; $8574: his punch's damage
    call MacByte
    inc c
    ld [wNes + $75], a
MacIndexZero:               ; $8579
    ld a, c
    ld [wNes + $53], a
    jp MacZero

MacDefense:                 ; $857E: his defense, both sides ($FF dodge, $80 duck, $08 block)
    call MacByte
    inc c
    ld [wNes + $76], a
    call MacByte
    inc c
    ld [wNes + $77], a
    jp MacIndexZero

MacIncZp:                   ; $858C
    call MacByte
    ld hl, wNes + $53
    inc [hl]
    ld l, a
    ld h, HIGH(wNes)
    inc [hl]
    jp MacStep

MacSetZp:                   ; $8596
    call MacByte
    inc c
    ld b, a
    call MacByte
    inc c
    ld e, b
    ld d, HIGH(wNes)
    ld [de], a
    jp MacIndexZero

MacPal:                     ; $85A4: palette effects (the NES's; not needed here)
MacPal2:
    jp MacStep

MacHitSide:                 ; $85C1
    call MacByte
    ld [wNes + $59], a
    ld hl, wNes + $53
    inc [hl]
    jp MacStep

MacFinished:                ; $85CA
    ld hl, wNes + $53
    dec [hl]
    ld a, $83
    ld [wNes + $51], a
    ret

;;PART common
; ==== Bank 7's bookkeeping each frame: HP, hearts, stars (their logic; the GB draws its own HUD) =====

; $881E: HP. $0390: 0 off, bit 7 a fresh start ($60 each, then 1), else live: next HP ($0391/$0398)
; becomes current ($0392/$0399, what knockouts check), and the shown HP ($0393/$039A) steps a point
; toward it while its bar isn't waiting to be drawn ($0394/$039B bit 7, cleared by the vblank's $C041).
NesHp::
    ld a, [wNes + $0390]
    and a
    ret z
    bit 7, a
    jp z, .live
    and $7F                 ; $8806
    ld [wNes + $0390], a
    xor a
    ld hl, wNes + $0391
    ld b, $0F
.zero:
    ld [hl+], a
    dec b
    jp nz, .zero
    ld a, $60
    ld [wNes + $0391], a
    ld [wNes + $0398], a
    ret
.live:
    ld a, [wNes + $0391]
    ld [wNes + $0392], a
    ld hl, wNes + $0393
    call .step
    ld a, [wNes + $0398]
    ld [wNes + $0399], a
    ld hl, wNes + $039A
.step:                      ; HL = shown, A = current; HL+1 = its bar's draw flag
    ld b, a
    inc l
    bit 7, [hl]
    ret nz
    dec l
    ld a, [hl]
    cp b
    ret z
    jp c, .up
    dec a                   ; down a point: the bar redraws on even points
    ld [hl+], a
    rrca
    ret c
    ld [hl], $80
    ret
.up:
    inc a                   ; up a point: on even points, and at 1
    ld [hl+], a
    cp 1
    jp z, .flag
    rrca
    ret c
.flag:
    ld [hl], $80
    ret

; $890D: hearts. $0320 set: new hearts ($0321/$0322) become current ($0323/$0324); bit 7: none left.
NesHearts::
    ld a, [wNes + $0320]
    and a
    ret z
    bit 7, a
    jp z, .new
    ld b, a                 ; $88FC
    ld a, 1
    ld [wNes + $0320], a
    ld a, b
    cp $80
    ld b, 2
    jp nz, .clear
    ld b, 4
.clear:                     ; zero $0320 + X down to $0321
    ld hl, wNes + $0320
    ld a, l
    add b
    ld l, a
    xor a
.clr:
    ld [hl-], a
    dec b
    jp nz, .clr
    ld a, $80               ; $8945: to be drawn
    ld [wNes + $0325], a
    ret
.new:
    ld a, [wNes + $0321]
    ld b, a
    ld a, [wNes + $0322]
    or b
    ret z
    ld a, b
    ld [wNes + $0323], a
    ld a, [wNes + $0322]
    ld [wNes + $0324], a
    ld b, 2
    jp .clear

; $8974: stars. $0340 bit 7: none; $0341 is a change ($FF: all gone); $0343 the star-earned moment
; (when it's over: one more star and 100 points).
NesStars::
    ld a, [wNes + $0340]
    and a
    ret z
    bit 7, a
    jp z, .live
    xor a                   ; $894F
    ld [wNes + $0341], a
    ld [wNes + $0342], a
    ld [wNes + $0343], a
    inc a
    ld [wNes + $0340], a
    ld a, $80               ; $8999: to be drawn
    ld [wNes + $0349], a
    ret
.live:
    ld a, [wNes + $0341]
    and a
    jp z, .earning
    ld b, a
    xor a
    ld [wNes + $0341], a
    ld a, [wNes + $0342]
    add b
    bit 7, a
    jp z, .some
    xor a
    jp .set
.some:                      ; $8961: three at most
    cp 3
    jp c, .set
    ld a, [wNes + $0348]
    and a
    ld a, 3
    jp nz, .set
    ld a, [wNes + $05B3]
    ld [wNes + $0348], a
    ld a, 3
.set:
    ld [wNes + $0342], a
    ld a, $80               ; $8999: to be drawn
    ld [wNes + $0349], a
.earning:                   ; $899E
    ld a, [wNes + $0343]
    and a
    ret z
    bit 7, a
    jp z, .count
    ld a, [wNes + $0344]    ; $89BE: it starts
    and a
    ret z
    ld a, $14               ; (the count starts next frame)
    ld [wNes + $0343], a
    ret
.count:
    ld hl, wNes + $0343
    dec [hl]
    jp z, .earned
    ld a, $81               ; $89B9: the star flashes (a sprite transfer)
    ld [wNes + $17], a
    ret
.earned:
    ld a, [wNes + $03E0]    ; $89DE: earned (points first, if others are pending)
    and a
    jp nz, .wait
    ld [wNes + $0344], a
    inc a
    ld [wNes + $0341], a
    ld [wNes + $03E4], a
    ld [wNes + $03E0], a
    ret
.wait:
    inc [hl]
    ret

; Bank 7 $8A6F: the crowd's cheering, as far as the fight follows it: $40 (bit 7: a new mode, taken on
; the frame counter's 16-frame beat; mode 3 turns to 4 on the beat). Mac's scripts wait on it. Its script
; only flashes palettes and writes to the screen (the GB's own crowd does that).
NesCrowd:
    ld a, [wNes + $40]
    bit 7, a
    jr nz, .new
    cp 3
    ret nz
    ld a, [wNes + $46]
    and a
    ret nz
    ld a, [wNes + $1E]
    and $0F
    ret nz
    ld a, 4
    ld [wNes + $40], a
    ret
.new:                       ; $8A4B
    and $7F
    ld b, a
    ld a, [wNes + $1E]
    and $0F
    ret nz
    ld a, b
    ld [wNes + $40], a
    ld a, $80
    ld [wNes + $41], a
    ld a, 1
    ld [wNes + $42], a
    xor a
    ld [wNes + $43], a
    ret

; The NMI's part before the engine ($A5C3): two transfers a vblank. Sprites ($17) and Mac's new pose
; ($60 = 1) come first; with one left, the HUD part the frame count's turn names goes out ($A61A).
; Each clears the flag the bookkeeping waits on. Then the count ($1E).
NesVblank:
    ld b, 2
    ld hl, wNes + $17
    ld a, [hl]
    and a
    jr z, .mac
    ld [hl], 0
    dec b
.mac:
    ld hl, wNes + $60
    ld a, [hl]
    dec a
    jr nz, .hud
    ld [hl], a
    dec b
.hud:
    ld a, b
    and a
    jr z, .count
    ld a, [wNes + $1E]
    and 3
    jr z, .hearts
    dec a
    jr z, .points
    dec a
    jr z, .clock
    ld hl, wNes + $0394     ; 3: the HP bars ($C041)
    call .sent
    ld hl, wNes + $039B
    jr .last
.hearts:                    ; 0: hearts and stars ($C079, $C09D)
    ld hl, wNes + $0325
    call .sent
    ld hl, wNes + $0349
    jr .last
.points:                    ; 1: points ($C0BB)
    ld hl, wNes + $03F0
    jr .last
.clock:                     ; 2: the clock ($C0E0)
    ld hl, wNes + $030A
.last:
    call .sent
.count:
    ld hl, wNes + $1E
    inc [hl]
    ret
.sent:
    bit 7, [hl]
    ret z
    ld [hl], 0
    ret

IF DEF(FT_NES_SOUND)
; An NES SQ1 effect (A) outside the fight: the engine wakes (its sound RAM cleared the first time since it
; was last idle) and plays it out from the main loop (hNesSound 2, NesSoundAfter).
NesSfx::
    call NesSfxWake
    ld [wNes + $F0], a
    ret

NesSfxWake:                 ; (A kept)
    push af
    push bc
    push de
    push hl
    ld b, a
    ldh a, [hNesSound]
    and a
    jr nz, .request
    ld a, BANK(NesSnd)
    ld [$2000], a
    push bc
    call ApuInit
    pop bc
    xor a
    ld hl, wNes + $F0
    ld c, $10
.zp:
    ld [hl+], a
    dec c
    jr nz, .zp
    ld hl, wNes + $0700
    ld c, $30
.ram:
    ld [hl+], a
    dec c
    jr nz, .ram
    ldh a, [hScene]         ; the scene's data bank back
    add LOW(SceneBanks)
    ld l, a
    adc HIGH(SceneBanks)
    sub l
    ld h, a
    ld a, [hl]
    ld [$2000], a
    ld a, 2
    ldh [hNesSound], a
.request:
    pop hl
    pop de
    pop bc
    pop af
    ret

; An NES DMC sample (A: 1 the crowd) outside the fight, the same way.
NesDmc::
    push af
    ld a, $FF               ; (no SQ1 effect: NesSfx wakes the engine and asks for none)
    call NesSfxWake
    pop af
    ld [wNes + $F3], a
    ret

; After the fight: the NES's sound engine plays on (its music, its effects) until it's done, then the
; hardware goes back to the game's own effects. The scene's data bank is mapped again after.
NesSoundAfter::
    ld a, BANK(NesSnd)
    ld [$2000], a
    call NesSound
    ld a, [wNes + $F6]
    ld b, a
    ld a, [wNes + $F4]
    or b
    ld b, a
    ld a, [wNes + $F5]
    or b
    ld b, a
    ld a, [wNes + $F7]      ; (a sample playing, the crowd: on)
    or b
    jr nz, .bank
    call ApuQuiet
    xor a
    ldh [hNesSound], a
.bank:
    ldh a, [hScene]
    add LOW(SceneBanks)
    ld l, a
    adc HIGH(SceneBanks)
    sub l
    ld h, a
    ld a, [hl]
    ld [$2000], a
    ret
ENDC

; The NES game's frame, in its order (its $A669 NMI): bank 7's clock, points, HP, hearts, stars; the
; buttons ($D0 already read); his timeline, AI mode, guard, AI and state; Mac's input and state (his
; new pose drawn: $60 = 1); where they meet; Mac getting up; the phase machine.
NesEngineFrame::
    call NesVblank
    ld a, BANK(NesFighter)
    ld [$2000], a
    call NesClock
    call NesPoints
    call NesHp
    call NesHearts
    call NesStars
    call NesButtons
IF DEF(FT_NES_SOUND)
    ld a, BANK(NesSnd)      ; ($A68D) bank 8: the sound engine
    ld [$2000], a
    call NesSound
    ld a, BANK(NesFighter)
    ld [$2000], a
ENDC
    call NesTimeline
    call NesAiMode
    call NesGuard
    call NesAi
    call NesOppTick
    ld hl, wNes + nOppAnimFlags ; $C890: his new sprites go out (the GB's when it shows them: wNesAnim)
    ld a, [hl]
    and a
    jr z, .still
    ld [hl], 0
    ld hl, wNesAnim
    or [hl]
    ld [hl], a
    ld a, 1
    ld [wNes + $17], a
.still:
    ld a, BANK(NesMac)
    ld [$2000], a
    call NesMacInput
    call NesMacTick
    ld hl, wNes + $60
    bit 7, [hl]
    jr z, .notDrawn
    ld [hl], 1
.notDrawn:
    call NesCrowd
    ld a, BANK(NesFighter)
    ld [$2000], a
    call NesExchange
    call NesMacGetup
    call NesOutline
    jp NesPhase

; $C440: his outline: the dodge cue's color ($05EC) when his script sets the timer with bit 7, back to
; normal ($05ED) when it runs out. wNesCue says which, for the GB's palettes.
NesOutline:
    ld a, [wNes + nOppOutlineTimer]
    and a
    ret z
    bit 7, a
    jp nz, .cue
    dec a
    ld [wNes + nOppOutlineTimer], a
    ret nz
    xor a                   ; normal again
    jp .set
.cue:
    and $7F
    ld [wNes + nOppOutlineTimer], a
    ld a, 1
.set:
    ld [wNesCue], a
    ret

;;PART fighter
; ==== The exchange: PRG bank 7's $805D, the moment punches meet ====================================
; His punch out ($98 active) meets Mac's defense ($76/$77: $FF dodged, $80 ducked, 8 blocked, else it
; lands, or trades with Mac's punch if that's out too); otherwise Mac's punch arriving ($58) meets his
; defense ($B6 + punch type): 0 lands (a combo while the combo timer runs), 8 is blocked, $80+ is
; slipped, else the damage left after it. Hearts, HP, stars, combos and knockdowns follow, as the game.

NesExchange::
    ld a, [wNes + nOppPunchSts]
    bit 7, a
    jp z, MacPunchLands
    ld a, [wNes + $58]      ; $8069: his punch is out
    bit 7, a
    jp z, .noPending
    xor a
    ld [wNes + $58], a
.noPending:
    xor a
    ld [wNes + nVulnerableTimer], a
    ld a, [wNes + nOppPunchSide]
    and 1
    ld e, a
    ld d, 0
    ld hl, wNes + $76
    add hl, de
    ld a, [hl]
    cp $80
    jp z, .ducked
    cp $FF
    jp nz, ExTrade
    ld a, [wNes + nMacStatus]   ; dodged
    ld [wNes + $03B0], a
    xor a
    ld [wNes + $03C5], a
    ld a, [wNes + $05A0]
    ld b, a
    ld a, 4
    jp .result
.ducked:                    ; $8090
    ld a, [wNes + $05A1]
    ld b, a
    ld a, [wNes + nMacStatus]
    cp $0E
    jp nz, .duck2
    ld a, [wNes + $05A2]
    ld b, a
.duck2:
    ld a, 2
.result:                    ; $809E
    ld [wNes + nOppPunchSts], a
    ld [wNes + $BD], a
    ld a, [wNes + nMacCanPunch]
    and a
    jp nz, .clear
    ld a, b                 ; worn out: a dodge gets some hearts back
    call HeartsRecover
    ld a, [wNes + nMacCanPunch]
    and a
    jp z, .clear
    xor a
    ld [wNes + $03C5], a
.clear:
    xor a
    ld [wNes + nOppPunchDamage], a
    ld [wNes + nOppPunchSide], a
    ret

ExTrade:                    ; $80FF: E = his punch's side
    ld a, [wNes + $76]      ; (the defense on that side)
    bit 0, e
    jp z, .def
    ld a, [wNes + $77]
.def:
    ld b, a
    ld a, [wNes + nOppPunchDamage]
    sub b
    jp z, ExBlocked
    bit 7, a
    jp nz, ExBlocked
    ld [wNes + $E0], a
    ld a, [wNes + nMacPunchType]
    and 3
    ld e, a
    ld d, 0
    ld hl, wNes + nOppHitDefense
    add hl, de
    ld a, [wNes + $75]
    sub [hl]
    bit 7, a
    jp z, .e1
    xor a
.e1:
    ld [wNes + $E1], a
    and a
    jp nz, ExCounter
    ld a, 3                 ; $811C: it lands on Mac
    ld [wNes + nOppPunchSts], a
    ld [wNes + $BD], a
    ld a, [wNes + nMacCanPunch]
    and a
    jp nz, .canPunch
    ld a, [wNes + $05A3]
    call HeartsRecover
    ld a, 1
    ld [wNes + $0329], a
.canPunch:                  ; $8131: each punch he lands, the next comes sooner
    ld a, [wNes + $0582]
    ld b, a
    ld a, [wNes + nVariableStTime]
    sub b
    ld hl, wNes + $0583
    cp [hl]
    jp nc, .time
    ld a, [hl]
.time:
    ld [wNes + nVariableStTime], a
    ld a, 3
    call HeartsLose
    ld a, $FF
    ld [wNes + $0341], a
    call MacHit
    ld a, [wNes + $03C5]
    and a
    jp nz, ExInstant
    ld a, $82
    ld [wNes + $03D2], a
    call OppHpBoost
ExMacDamage:                ; $815D: E0 + his base damage off Mac's HP
    ld a, [wNes + $E0]
    ld hl, wNes + $05AF
    add [hl]
    call MacHpLose
    jp nz, ExCleanup
    jp ExMacDown
ExInstant:                  ; $816E
    xor a
    ld [wNes + $0391], a
ExMacDown:                  ; $80F8
    call MacKnockdown
    jp ExReset
ExCleanup:                  ; $80E8
    call ExClear
    jp ExReset

ExBlocked:                  ; $80BA: no damage gets through (E = side)
    ld hl, wNes + $76
    ld a, l
    add e
    ld l, a
    ld a, [hl]
    cp 8
    jp z, .blocked
    ld a, 2
    ld [wNes + nOppPunchSts], a
    ld [wNes + $BD], a
    ret
.blocked:                   ; $80C7: blocked: a heart, and a little HP
    ld a, 1
    ld [wNes + nOppPunchSts], a
    ld [wNes + $BD], a
    ld a, $88
    ld [wNes + nMacStatus], a
    ld a, 1
    call HeartsLose
    ld a, $82
    ld [wNes + $03D2], a
    ld a, [wNes + nMacCanPunch]
    and a
    ld a, 2
    jp nz, .chip
    ld a, 4
.chip:
    call MacHpLose
    jp nz, ExCleanup
    ld a, 3                 ; $80EF
    ld [wNes + nOppPunchSts], a
    ld [wNes + $BD], a
    call MacHit
    jp ExMacDown

ExCounter:                  ; $8176: his punch and Mac's meet: Mac's lands too
    xor a
    ld [wNes + nOppPunchSts], a
    ld [wNes + $BD], a
    ld a, $8D
    call OppStateByPunch3
    call MacHit
    ld a, 3
    call HeartsLose
    ld a, $FF
    ld [wNes + $0341], a
    ld b, 0
    ld a, [wNes + nSpecialKD]
    cp 9
    jp z, .kd9
    ld b, $81
.kd9:
    ld a, b
    ld [wNes + $03D2], a
    xor a
    call OppHpLose
    jp z, .down
    ld a, $82
    jp .owner
.down:
    call OppKnockdown
    xor a                   ; ($8404 returns with X = 0: no last puncher)
.owner:
    ld [wNes + $03D2], a
    jp ExMacDamage

; ---- $81B2: Mac's punch arrives ($58 with bit 7) ----
MacPunchLands:
    ld a, [wNes + $58]
    bit 7, a
    ret z
    ld b, a
    xor a
    ld [wNes + $0344], a
    ld a, b
    cp $80
    jp nz, .combo
    ; $8259: a plain punch (or a star)
.plain:
    ld a, [wNes + nMacPunchType]
    bit 7, a
    jp z, .notStar
.starPunch:                 ; $825D
    call ComboClear
.notStar:
    ld a, [wNes + nMacPunchType]
    and 3
    ld e, a
    ld d, 0
    ld hl, wNes + nOppHitDefense
    add hl, de
    ld a, [hl]
    bit 7, a
    jp z, .damage
.slipped:                   ; $8267: he's out of the way
    ld a, 2
    ld [wNes + $58], a
    ld a, 1
    call HeartsLose
    ld b, 0
    ld a, [wNes + nMacPunchType]
    and 3
    ld e, a
    ld d, 0
    ld hl, wNes + nOppHitDefense
    add hl, de
    ld a, [hl]
    cp $80
    jp z, .bb
    call ExReset
    ld b, 1
.bb:
    ld a, b
    ld [wNes + $BB], a
    jp ExClear
.combo:                     ; $81C4: a punch while the combo timer runs
    ld a, [wNes + nMacPunchType]
    bit 7, a
    jp nz, .starPunch
    ld a, [wNes + nComboTimer]
    and a
    jp z, .starPunch        ; ($81C1 -> $825D)
    ld a, [wNes + nMacPunchType]
    and 3
    ld e, a
    ld d, 0
    ld hl, wNes + nOppHitDefense
    add hl, de
    ld a, [hl]
    and a
    jp z, .comboHit
    cp 8
    jp nz, .slipped
    call ComboClear
    jp .blocked
.comboHit:                  ; $81E0
    ld a, [wNes + $0580]
    ld [wNes + nVariableStTime], a
    ld a, $20
    ld [wNes + nComboTimer], a
    ld a, 1
    ld [wNes + $03E5], a
    ld a, $80
    ld [wNes + $03E0], a
    ld a, [wNes + nComboCountDown]
    and a
    jp z, .comboLast
    dec a
    ld [wNes + nComboCountDown], a
    jp z, .comboEnd
    ld a, [wNes + $4C]
    and 1
    jp z, .comboNext
    jp .comboSeq
.comboEnd:                  ; $8204
    ld a, [wNes + $4C]
    and 1
    jp nz, .comboMore
.comboLast:                 ; $820A: the combo's last punch
    call ComboClear
    ld a, 3
    ld [wNes + $58], a
    ld a, $8D
    call OppStateByPunch3
    call ExReset
.comboScore:                ; $8219
    call StarCount
    ld a, $81
    ld b, a
    ld a, [wNes + nSpecialKD]
    cp 9
    ld a, b
    jp nz, .owner
    xor a
.owner:
    ld [wNes + $03D2], a
    ld a, [wNes + $05C5]
    call OppHpLose
    jp nz, ExClear
    ld a, $8D
    call OppStateByPunch3
    jp .knockdown
.comboMore:                 ; $823E
    ld hl, wNes + nComboCountDown
    inc [hl]
.comboSeq:                  ; $8240
    ld hl, wNes + $05C4
    dec [hl]
    jp nz, .seq
    xor a
    ld [wNes + $4C], a
    jp .comboNext
.seq:
    call ComboSequence
.comboNext:                 ; $824E
    ld a, 3
    ld [wNes + $58], a
    ld a, $91
    call OppStateByPunch3
    jp .comboScore
.damage:                    ; $82B2: damage past his defense?
    ld b, a
    ld a, [wNes + $75]
    sub b
    jp z, .noDamage
    bit 7, a
    jp nz, .noDamage
    ld [wNes + $E0], a
    ld a, [wNes + nOppPunchSide]
    and 1
    ld e, a
    ld d, 0
    ld hl, wNes + $76
    add hl, de
    ld a, [wNes + nOppPunchDamage]
    sub [hl]
    bit 7, a
    jp z, .e1
    xor a
.e1:
    ld [wNes + $E1], a
    and a
    jp z, .lands
    xor a                   ; $82CF: both land
    ld [wNes + $58], a
    ld a, $8D
    call OppStateByPunch3
    call MacHit
    ld a, 1
    call HeartsLose
    ld a, $FF
    ld [wNes + $0341], a
    ld a, $82
    ld [wNes + $03D2], a
    ld a, [wNes + $E1]
    ld hl, wNes + $05AF
    add [hl]
    call MacHpLose
    jp z, .bothMacDown
    ld b, $81
    ld a, [wNes + nSpecialKD]
    cp 9
    jp nz, .both
    ld b, 0
    jp .both
.bothMacDown:
    call MacKnockdown
    ld b, 0                 ; ($83EB returns with X = 0)
.both:                      ; $8305
    ld a, b
    ld [wNes + $03D2], a
    ld a, [wNes + $E0]
    call OppHpLose
    jp nz, .done
    jp .knockdown
.noDamage:                  ; $8288
    ld a, [hl]              ; (HL = his defense for this punch)
    cp 8
    jp z, .blocked
    ld a, 2
    ld [wNes + $58], a
    xor a
    ld [wNes + $BB], a
    ret
.blocked:                   ; $8297: it hits his gloves
    ld a, 1
    ld [wNes + $58], a
    xor a
    ld [wNes + $0343], a
    ld [wNes + nVulnerableTimer], a
    ld a, $85
    call OppStateByPunch3
    ld a, 1
    call HeartsLose
    call ExClear
    jp ExReset
.lands:                     ; $8319: it lands
    ld a, 3
    ld [wNes + $58], a
    ld a, $81
    ld [wNes + $03D2], a
    ld a, 5                 ; points: a star punch's at $03E4, others' at $03E5
    ld e, 4
    ld b, a
    ld a, [wNes + nMacPunchType]
    bit 7, a
    ld a, b
    jp nz, .points
    inc e
    ld a, 1
.points:
    ld hl, wNes + $03E0
    ld d, a
    ld a, l
    add e
    ld l, a
    ld [hl], d
    ld a, $80
    ld [wNes + $03E0], a
    ld a, [wNes + $BA]      ; caught in his charge: down he goes
    and a
    jp z, .special
.kdNow:                     ; $8339
    xor a
    ld [wNes + $0398], a
.kdState:                   ; $833E
    ld a, $8D
    call OppStateByPunch3
    jp .knockdown
.special:                   ; $8345
    ld a, [wNes + nSpecialKD]
    cp 1
    jp z, .kd1
    cp 9
    jp z, .kd9
    jp .hp
.kd1:
    ld a, [wNes + nMacPunchType]
    bit 7, a
    jp z, .hp
    xor a
    ld [wNes + $0398], a
    jp .kdOut
.kd9:
    ld a, [wNes + nMacPunchType]
    bit 7, a
    jp nz, .hp
    xor a
    ld [wNes + $03D2], a
.hp:                        ; $8366
    call MacHpBoost
    ld a, [wNes + $E0]
    ld b, a
    ld a, [wNes + nMacPunchType]
    bit 7, a
    ld a, b
    jp z, .notStarDmg
    ld hl, wNes + $05D3     ; a star punch's extra
    add [hl]
.notStarDmg:
    call OppHpLose
    jp nz, .standing
    ld a, [wNes + nMacPunchType]
    bit 7, a
    jp z, .kdState
.kdOut:                     ; $837C
    ld a, $82
    ld [wNes + nOppCurState], a
    jp .knockdown
.standing:                  ; $8382
    ld a, [wNes + $0580]
    ld [wNes + nVariableStTime], a
    ld hl, wNes + $03B1
    inc [hl]
    ld a, [wNes + nComboTimer]
    and a
    jp z, .notCombo
    ld a, [wNes + nComboCountDown]
    and a
    jp nz, .comboOn
    call ComboStart
    ld a, [wNes + nComboCountDown]
    dec a
    jp nz, .comboOn
    ld a, $80
    ld [wNes + $4C], a
.comboOn:                   ; $839F
    ld a, $20
    ld [wNes + nComboTimer], a
    ld a, $91
    call OppStateByPunch3
    call StarCount
    jp ExClear
.notCombo:                  ; $83AE
    ld a, [wNes + nMacPunchType]
    bit 7, a
    jp z, .hit
    ld a, $82               ; a star punch that doesn't drop him
    ld [wNes + nOppCurState], a
    call StarCount
.done:                      ; $83B9
    call ExClear
    jp ExReset
.hit:                       ; $83C0
    ld a, $8D
    call OppStateByPunch3
    ld hl, wNes + $0347     ; toward a star
    dec [hl]
    jp nz, .noStar
    ld a, [wNes + $05B1]
    ld [hl], a
    jp .star
.noStar:
    ld a, [wNes + $0343]
    bit 7, a
    jp nz, .done
    ld a, [wNes + $0342]
    and a
    jp z, .done
    ld a, [wNes + $05B4]
    call NesChance15
    jp nc, .done
.star:
    ld a, $80
    ld [wNes + $0343], a
    jp .done
.knockdown:                 ; $8312
    call OppKnockdown
    jp ExReset

; ---- the helpers ($83EB-$8574) ----

MacKnockdown:               ; $83EB: Mac goes down
    ld a, $80
    ld [wNes + $0320], a
    ld [wNes + $0340], a
    ld [wNes + $BB], a
    call ClockHalt
    ld a, 2
    ld [wNes + nKnockdownSts], a
    ld a, 1
    ld [wNes + nMacCanPunch], a
    xor a
    ld [wNes + $03C5], a
    ret

OppKnockdown:               ; $8404: he goes down
    call ComboClear
    call ClockHalt
    ld a, 1
    ld [wNes + $03E3], a
    ld a, $80
    ld [wNes + $03E0], a
    ld a, 1
    ld [wNes + nKnockdownSts], a
    ld [wNes + $36], a
    xor a
    ld [wNes + $BB], a
    ld [wNes + nSpecialKD], a
    ret

ClockHalt:                  ; $8421
    ld hl, wNes + nRoundTmrCntrl
    set 0, [hl]
    ret

StarCount:                  ; $842A
    ld hl, wNes + $0347
    dec [hl]
    ret nz
    inc [hl]
    ret

ComboClear:                 ; $8435
    xor a
    ld [wNes + nComboTimer], a
    ld [wNes + nComboCountDown], a
    ld [wNes + $4C], a
    ret

; $843E: A hearts lost (BCD, $0323/$0324 -> new $0321/$0322); none left: worn out.
HeartsLose:
    ld b, a
    ld a, [wNes + $0323]
    ld c, a
    ld a, [wNes + $0324]
    or c
    ret z
    ld a, [wNes + $0324]
    sub b
    jp nc, .ld
    add 10
    scf
.ld:
    ld [wNes + $0322], a
    ld a, [wNes + $0323]
    sbc 0
    ld [wNes + $0321], a
    jp c, .out
    and a
    ret nz
    ld a, [wNes + $0322]
    and a
    ret nz
.out:                       ; $8469
    xor a
    ld [wNes + nMacCanPunch], a
    ld [wNes + $0329], a
    ld a, $20
    ld [wNes + $0328], a
    ld a, [wNes + $05A4]
    ld [wNes + $032A], a
    ld a, $14
    ld [wNes + $048E], a
    ld a, $80
    ld [wNes + $0320], a
    ld [wNes + $04A0], a
    ld a, [wNes + $36]
    and $80
    or 4
    ld [wNes + $36], a
    ret

; $849F: Mac is hit: his reaction status.
MacHit:
    ld a, [wNes + $5A]
    bit 7, a
    jp nz, .set
    ld a, [wNes + nOppPunchSide]
    and 1
    or $90
    ld hl, wNes + $59
    add [hl]
.set:
    ld [wNes + nMacStatus], a
    ld a, $25
    ld [wNes + $048E], a
    ld a, $81
    ld [wNes + $04A0], a
    ret

; $84B9: worn out: A toward getting his breath back; then his hearts come back.
HeartsRecover:
    ld hl, wNes + $0328
    add [hl]
    ld [hl], a
    jp z, .back
    bit 7, a
    jp z, .cap
    xor a
    ld [hl], a
.back:                      ; $84C9
    ld a, 1
    ld [wNes + nMacCanPunch], a
    ld a, $8F
    ld [wNes + $048E], a
    ld a, $80
    ld [wNes + $04A0], a
    ld a, [wNes + $36]
    and $80
    or 8
    ld [wNes + $36], a
    ld a, [wNes + $0329]
    add a
    add 5
    ld e, a
    ld d, 0
    ld hl, wNes + $0328
    add hl, de
    ld a, [hl+]
    ld [wNes + $0321], a
    ld a, [hl]
    ld [wNes + $0322], a
    ret
.cap:                       ; $84F3
    ld hl, wNes + $032A
    cp [hl]
    ret c
    ld a, [hl]
    ld [wNes + $0328], a
    ret

; $84FF / $8503: A off his ($0399) / Mac's ($0392) HP into the next HP ($0398 / $0391).
; Z: knocked out (when a last puncher is set).
OppHpLose:
    ld hl, wNes + $0399
    jp HpLose
MacHpLose:
    ld hl, wNes + $0392
HpLose:
    ld b, a
    ld a, [hl-]
    sub b
    jp z, .zero
    bit 7, a                ; (the sign only, as the 6502's BPL)
    jp nz, .zero
    ld [hl], a
    ld a, 1
    and a
    ret
.zero:
    ld a, [wNes + $03D2]
    and a
    jp z, .alive
    xor a
    ld [hl], a
    ret                     ; Z
.alive:
    xor a
    ld [hl], a
    inc a
    ret                     ; NZ

; $8525 / $852B: HP low: a little back (Mac: at 15 or less; him: at his cap or less).
MacHpBoost:
    ld a, $0F
    ld hl, wNes + $0392
    jp HpBoost
OppHpBoost:
    ld a, [wNes + $05D7]
    ld hl, wNes + $0399
HpBoost:
    cp [hl]
    ret c
    ld a, [hl-]
    add 4
    ld [hl], a
    ret

ExClear:                    ; $8540
    xor a
    ld hl, wNes + nMacPunchType
    ld [hl+], a
    ld [hl+], a
    ld [hl+], a
    ld [hl], a
    ld hl, wNes + nOppPunchSide
    ld [hl+], a
    ld [hl+], a
    ld [hl+], a
    ld [hl+], a
    ld [hl+], a
    ld [hl], a
    ret

ExReset:                    ; $8550: both back to their scripts; a knockdown begins
    ld a, $81
    ld [wNes + $51], a
    ld [wNes + nOppStateStatus], a
    jp NesKnockdownStart

OppStateByPunch3:           ; $8562: his state A + the punch (0-3)
    ld b, a
    ld a, [wNes + nMacPunchType]
    and 3
    add b
    ld [wNes + nOppCurState], a
    ret

; $B3A3: a combo begins: its pattern, and how many punches it takes.
ComboStart:
    ld a, [wNes + $05C4]
    and a
    ld b, $80
    jp z, .counted
    ld c, 0
    ld b, 0
    call ComboByte
    bit 7, a
    jp nz, .any1
    ld hl, wNes + $03B0
    cp [hl]
    jp nz, .counted
.any1:
    inc c
    call ComboByte
    bit 7, a
    jp nz, .any2
    ld hl, wNes + nMacPunchType
    cp [hl]
    jp nz, .counted
.any2:
    inc c
    ld a, c
    ld [wNes + $4D], a
    ld a, [wNes + nMacPunchType]
    ld [wNes + $03B0], a
    inc b
.counted:                   ; $B3CB
    ld a, b
    ld [wNes + $4C], a
    ld a, [wNes + $05C2]    ; his combo table (a NES pointer)
    ld l, a
    ld a, [wNes + $05C3]
    sub NES_BANK_DELTA
    ld h, a
    ld a, [wNes + nComboTimer]
    ld b, a
.find:
    ld a, b
    cp [hl]
    jp z, .found
    jp c, .found
    inc hl
    inc hl
    jp .find
.found:
    inc hl
    ld a, [hl]
    ld [wNes + nComboCountDown], a
    ret

ComboByte:                  ; byte C of the combo pattern ($4E, a NES pointer)
    ld a, [wNes + $4E]
    add c
    ld l, a
    ld a, [wNes + $4F]
    adc 0
    sub NES_BANK_DELTA
    ld h, a
    ld a, [hl]
    ret

; $B3EB: the next punch of a combo pattern.
ComboSequence:
    ld a, [wNes + $4D]
    ld c, a
    call ComboByte
    bit 7, a
    jp nz, .control
    ld b, a
    ld a, [wNes + nMacPunchType]
    and $83
    cp b
    jp z, .match
.broken:
    ld hl, wNes + $4C
    res 0, [hl]
    ret
.match:
    ld hl, wNes + $4D
    inc [hl]
    ld a, [wNes + nMacPunchType]
    ld [wNes + $03B0], a
    ret
.control:
    cp $FF
    jp z, .loop
    cp $FE
    ret z
    cp $FD
    jp nz, .loop
    ld a, [wNes + $03B0]    ; $FD: the other hand
    xor 1
    ld hl, wNes + nMacPunchType
    cp [hl]
    jp z, .match
    jp .broken
.loop:                      ; $FF: back to (byte)
    inc c
    call ComboByte
    ld [wNes + $4D], a
    jp ComboSequence

; $8051 -> $B2EB: a knockdown begins ($05: 1 him, 2 Mac): the referee's count, and when (and with how
; much HP) the fallen one gets up, from his tables. The count itself runs in the phase machine.
NesKnockdownStart:
    ld a, [wNes + nKnockdownSts]
    cp 1
    jp z, .opp
    cp 2
    ret nz
    ld hl, KdCountMac       ; $B298: Mac
    ld de, wNes + $C0
    ld b, 5
    call .copy
    ld hl, wNes + $8F
    inc [hl]
    ld hl, wNes + $03D0
    inc [hl]
    ld a, [wNes + nRoundNumber]
    ld e, a
    ld d, 0
    ld hl, wNes + $03DC
    add hl, de
    inc [hl]
    ld a, [wNes + $8F]
    cp 3
    jp z, .tko
    ld a, [wNes + $05D0]    ; his knockdown table (a NES pointer)
    ld l, a
    ld a, [wNes + $05D1]
    sub NES_BANK_DELTA
    ld h, a
    ld a, [wNes + $03C1]
    ld e, a
    ld d, 0
    add hl, de
    ld a, [hl+]
    ld [wNes + $03C4], a
    ld [wNes + $05D2], a
    ld a, [wNes + $03B1]    ; punches he's landed against the table's mark
    cp [hl]
    inc hl
    ld a, $7F
    jp c, .macMark
    ld a, [hl]
.macMark:
    ld [wNes + $03C3], a
    ld a, [wNes + $03C1]    ; STY: two bytes on
    add 2
    ld [wNes + $03C1], a
    ld a, $43
    ld [wNes + $70], a
    ret
.opp:                       ; him
    ld hl, KdCountOpp
    ld de, wNes + $C0
    ld b, 11
    call .copy
    ld hl, wNes + $03CA
    inc [hl]
    ld hl, wNes + $03D1
    inc [hl]
    ld a, [wNes + $03CA]
    cp 3
    jp z, .tko
    ld a, [wNes + $BA]      ; caught in the charge's first frames ($FF): he stays down
    ld b, a
    xor a
    ld [wNes + $BA], a
    inc b
    ret z
    ld a, [wNes + $05D5]    ; his refill table (a NES pointer)
    ld l, a
    ld a, [wNes + $05D6]
    sub NES_BANK_DELTA
    ld h, a
    push hl
    ld a, [wNes + $03C9]
    ld c, a
    ld e, a
    ld d, 0
    add hl, de
    ld a, [hl]
    and a
    jp nz, .entry
    ld a, [wNes + nMacStatus]
    cp $0D                  ; a star punch put him down
    jp z, .next
    jp .random
.entry:
    bit 7, a
    jp z, .hp
    ld a, [wNes + nRoundNumber]
    cp 1
    jp nz, .random
    ld a, [wNes + $0302]
    and a
    jp nz, .random
    ld a, [hl]
    and $7F
.hp:                        ; $B338: Mac's HP against it
    ld hl, wNes + $0391
    cp [hl]
    jp z, .next
    jp nc, .random
.next:                      ; $B33F
    inc c
    jp .pick
.random:                    ; $B342
    call NesRandom
    and 7
    cp 6
    jp c, .r
    and 1
.r:
    add 2
    ld hl, wNes + $03C9
    add [hl]
    ld c, a
.pick:                      ; $B356
    pop hl
    ld e, c
    ld d, 0
    add hl, de
    ld a, [hl]
    and a
    ret z
    ld b, a
    ld a, [wNes + $0398]    ; $B439: his HP to come back with
    ld [wNes + $039E], a
    ld a, [wNes + $0391]
    ld [wNes + $0397], a
    ld a, b
    and $0F
    add a
    add a
    add a
    ld [wNes + $039E], a
    ld a, b
    swap a
    and $0F
    jp z, .anyCount
    cp 1
    jp z, .special
    cp 7
    jp z, .special
    cp 9
    jp nz, .count
.special:
    ld [wNes + nSpecialKD], a
.count:
    add $99                 ; the count he gets up at ($9A = 1)
    jp .getUp
.anyCount:                  ; $B37A: one of his random get-up counts
    call NesRandom
    swap a
    and $0F
    srl a
    ld e, a
    ld d, 0
    ld hl, wNes + $05E0
    add hl, de
    ld a, [hl]
.getUp:
    ld [wNes + $C4], a
    ld a, [wNes + $03C9]
    add 8
    ld [wNes + $03C9], a
    ret
.tko:                       ; $B2E2: the third this round
    xor a
    ld [wNes + $C0], a
    ret
.copy:
    ld a, [hl+]
    ld [de], a
    inc de
    dec b
    jp nz, .copy
    ret

KdCountOpp:                 ; $B393: the referee's count, at $C0
    db $0F, $99, $E3, $C1, $00, $07, $EA, $FA, $7D, $05, $EA
KdCountMac:                 ; $B39E
    db $0F, $99, $80, $05, $EA

; $B549: the fight phase's check, after the exchange: a fighter whose script has run out goes back to
; waiting when the other is ready for it (both done: both reset); in a knockdown ($05), the one still
; standing goes to his knockdown wait ($C1).
NesFightPhase::
    ld a, [wNes + nRoundTmrCntrl]
    bit 7, a
    jp nz, .roundOver
    ld a, [wNes + nOppCurState]
    and a
    ret z
    ld a, [wNes + $0343]
    and a
    jp z, .check
    bit 7, a
    ret z
.check:
    ld a, [wNes + nKnockdownSts]
    and a
    jp nz, .knockdown
    ld a, [wNes + nOppStateStatus]
    ld hl, wNes + $51
    and [hl]
    bit 0, a
    jp z, .macOnly
    cp $83                  ; both done: both back to waiting
    ret nz
    call .oppWait
    jp .macWait
.macOnly:                   ; $B564: he's ready ($82) and Mac's done
    ld a, [wNes + nOppStateStatus]
    cp $82
    ret nz
    ld a, [hl]
    cp $83
    ret nz
    jp .macWait
.roundOver:                 ; $B581
    ld a, $40
    ld [wNes + $00], a
    ret
.knockdown:                 ; $B586
    cp 2
    jp z, .macDown
    ld a, [wNes + $51]      ; he's down: Mac, when done, to his wait
    cp $83
    ret nz
    ld a, $C1
    ld [wNes + nMacStatus], a
    ld a, $81
    ld [wNes + $51], a
    ret
.macDown:                   ; $B599: Mac's down: him, when done, to his
    ld a, [wNes + nOppStateStatus]
    cp $83
    ret nz
    ld a, $C1
    ld [wNes + nOppCurState], a
    ld a, $81
    ld [wNes + nOppStateStatus], a
    ret
.oppWait:                   ; $B651
    xor a
    ld [wNes + nOppStateStatus], a
    ld a, $81
    ld [wNes + nOppCurState], a
    ret
.macWait:                   ; $B65A: back to waiting ($81), or worn out ($82)
    ld a, [wNes + nMacCanPunch]
    ld b, a
    ld a, $82
    sub b
    ld [wNes + nMacStatus], a
    ld a, $80
    ld [wNes + $51], a
    ret

; ==== The round: clock, points, Mac's get-up, the phase machine ====================================

; Bank 7 $8759: the round clock. The round's rate ($0308/$0309) is added each frame; every $6400 is a
; second: $0311 counts down (the timeline's clock), the digits ($0302 min, $0304/$0305 sec) count up.
; At 3:00 the round is over: he holds still, Mac goes to his round-over state ($C2), the clock flashes.
NesClock::
    ld a, [wNes + nRoundTmrStart]
    and a
    ret z
    bit 7, a
    jp nz, .reset
    ld a, [wNes + nRoundTmrCntrl]
    and a
    jp z, .run
    bit 7, a
    jp nz, .flash
    cp 1
    ret z                   ; stopped
    ld a, [wNes + $030A]    ; time's up: start flashing once the display's caught up
    and a
    ret nz
    ld a, $81
    ld [wNes + nRoundTmrCntrl], a
    ld a, $10
    ld [wNes + $0306], a
    ld a, 8
    ld [wNes + $0307], a
    ret
.flash:                     ; $8725
    ld hl, wNes + $0307
    dec [hl]
    ret nz
    ld [hl], 8
    ld hl, wNes + $0306
    dec [hl]
    ld b, 0
    jp nz, .blink
    xor a
    ld [wNes + nRoundTmrStart], a
    ld b, 4
    jp .show
.blink:
    ld a, [wNes + $030B]
    cp 4
    jp nz, .show
    ld b, 4
.show:                      ; $873F: the display, blank or "-:--"
    ld hl, ClockFlash
    ld a, l
    add b
    ld l, a
    adc h
    sub l
    ld h, a
    ld de, wNes + $030B
    REPT 4
        ld a, [hl+]
        ld [de], a
        inc e
    ENDR
    jp .dirty
.run:                       ; $8780
    ld a, [wNes + $0309]
    ld hl, wNes + $0307
    add [hl]
    ld [hl], a
    ld a, [wNes + $0308]
    ld hl, wNes + $0306
    adc [hl]
    ld [hl], a
    cp $64
    ret c
    sub $64
    ld [hl], a
    ld hl, wNes + nSecondsLeft
    dec [hl]
    ld hl, wNes + $0305
    inc [hl]
    ld a, [hl]
    cp 10
    jp nz, .digits
    ld [hl], 0
    ld hl, wNes + $0304
    inc [hl]
    ld a, [hl]
    cp 6
    jp nz, .digits
    ld [hl], 0
    ld hl, wNes + $0302
    inc [hl]
    ld a, [hl]
    cp 3
    jp nz, .digits
    ld a, 2                 ; 3:00
    ld [wNes + nRoundTmrCntrl], a
    xor a
    ld [wNes + nOppCurState], a
    ld [wNes + nOppStateStatus], a
    ld [wNes + $51], a
    ld a, $C2
    ld [wNes + nMacStatus], a
.digits:                    ; $87D6
    ld hl, wNes + $0302
    ld de, wNes + $030B
    REPT 4
        ld a, [hl+]
        inc a
        ld [de], a
        inc e
    ENDR
.dirty:
    ld a, $80
    ld [wNes + $030A], a
    ret
.reset:                     ; $87EA
    xor a
    ld hl, wNes + nRoundTmrStart
    REPT 8
        ld [hl+], a
    ENDR
    ld a, $2B
    ld [wNes + $0303], a
    jp .digits

ClockFlash:                 ; $87FE
    db $04, $2C, $01, $01, $28, $28, $28, $28

; Bank 7 $86D0: points. New points (digits at $03E1-$03E6, set when he's hit) into the score ($03E8-$03ED).
NesPoints::
    ld a, [wNes + $03E7]
    and a
    ret z
    bit 7, a
    jp nz, .start
    ld a, [wNes + $03E0]
    and a
    ret z
.sum:
    and a                   ; (carry clear)
    ld b, 6
    ld hl, wNes + $03ED
    ld de, wNes + $03E6
.add:
    ld a, [de]
    adc [hl]
    cp 10
    jp c, .digit
    sub 10
    scf
    jp .store
.digit:
    and a
.store:
    ld [hl-], a
    dec e
    dec b
    jp nz, .add
    xor a
    ld hl, wNes + $03E0
    REPT 7
        ld [hl+], a
    ENDR
    ld a, $80               ; $8719: to be drawn
    ld [wNes + $03F0], a
    ret
.start:                     ; $86A9: $80 a new fight (the total from 0), else a new round
    ld b, a
    ld a, 1
    ld [wNes + $03E7], a
    ld [wNes + $03E0], a
    xor a
    ld hl, wNes + $03E1
    REPT 6
        ld [hl+], a
    ENDR
    ld a, b
    cp $80
    jp nz, .sum
    xor a
    ld hl, wNes + $03E8
    REPT 6                  ; ($03E8-$03ED)
        ld [hl+], a
    ENDR
    jp .sum

; $B457: Mac down and the get-up window open ($CF): each punch button press fills his meter ($03C3);
; full, he's up, with HP and hearts from his table for this count; his floor pose follows the meter.
NesMacGetup::
    ld a, [wNes + $CF]
    and a
    ret z
    ld a, [wNes + $03C3]
    bit 7, a
    jp nz, .redraw
    and a
    ret z
    ld a, [wNes + $D5]      ; A just pressed?
    bit 7, a
    jp z, .tryB
    and $7F
    ld [wNes + $D5], a
    ld a, [wNes + $D7]
    jp .used
.tryB:
    ld a, [wNes + $D7]
    bit 7, a
    jp z, .idle
.used:
    and $7F
    ld [wNes + $D7], a
    ld hl, wNes + $03C3
    dec [hl]
    ld a, [hl]
    and a
    jp z, .up
    cp 5
    jp c, .pose
    ld a, $3A
    ld [wNes + $70], a
    jp .show
.up:                        ; $B489: up! HP by the count he made it at
    ld a, [wNes + $C1]
    sub $99
    ld hl, wNes + $03C1
    add [hl]
    ld c, a
    ld a, [wNes + $05D0]
    ld l, a
    ld a, [wNes + $05D1]
    sub NES_BANK_DELTA
    ld h, a
    ld b, 0
    add hl, bc
    ld a, [wNes + $0398]    ; $B439 (X = 0): his HP set aside, Mac's from the table
    ld [wNes + $039E], a
    ld a, [wNes + $0391]
    ld [wNes + $0397], a
    ld a, [hl]
    and $0F
    add a
    add a
    add a
    ld [wNes + $0397], a
    ld a, [hl]              ; hearts: from bits 4-5
    and $30
    srl a
    srl a
    srl a
    ld b, a
    srl a
    add b
    jp nz, .hearts
    inc a
.hearts:
    ld [wNes + $0322], a
    xor a
    ld [wNes + $0321], a
    ld a, [hl]              ; bit 6: $03C5; bit 7: $03CB (the 6502 rotates through carry: ROL x3 = bit 6)
    rlca
    rlca
    and 1
    ld [wNes + $03C5], a
    ld a, [hl]
    rlca
    and 1
    jp z, .noSpecial
    ld [wNes + nSpecialKD], a
.noSpecial:
    ld a, 2
    ld [wNes + $36], a
    ld a, [wNes + $03C1]
    add 10
    ld [wNes + $03C1], a
.pose:                      ; $B4DC: his pose: $48 - the meter
    ld a, [wNes + $03C3]
    ld b, a
    ld a, $48
    sub b
    ld [wNes + $70], a
.show:                      ; $B4E4
    ld a, [wNes + $60]
    and a
    jp nz, .later
    ld a, [wNes + $70]
    ld [wNes + $61], a
    ld a, 1                 ; $81, and bank B $8280 readies it at once ($AA96): 1
    ld [wNes + $60], a
    ret
.later:                     ; $B526: drawn next frame
    ld hl, wNes + $03C3
    set 7, [hl]
    ret
.redraw:                    ; $B4F4
    and $7F
    ld [wNes + $03C3], a
    jp .show
.idle:                      ; $B4FB: no press: the meter slips back
    ld a, [wNes + $03C3]
    cp 5
    jp c, .slip
    ld a, [wNes + $D4]
    and a
    ret nz
    ld a, [wNes + $D6]
    and a
    ret nz
    ld a, [wNes + $70]
    cp $3A
    ret nz
    ld a, $43
    ld [wNes + $70], a
    jp .show
.slip:
    ld hl, wNes + $03C4
    dec [hl]
    ret nz
    ld a, [wNes + $05D2]
    ld [hl], a
    ld hl, wNes + $03C3
    inc [hl]
    jp .pose

; $B530: the phase machine (by $00's high nibble): 0 the fight's check (NesFightPhase), 3 a new round's
; setup, 4 the round's time running out. $00 with bit 7: the fight's over ($FC TKO, $FD Mac out, $FE KO,
; $FF time) and the game moves on (the fight kit's ending).
NesPhase::
    ld a, [wNes + $00]
    bit 7, a
    ret nz
    swap a
    and $0F
    jp z, NesFightPhase
    cp 3
    jp z, NesRoundSetup
    cp 4
    ret nz
    ld a, [wNes + $0306]    ; $B63E: the clock's done flashing: time
    and a
    ret nz
    ld a, [wNes + $030A]
    and a
    ret nz
    ld a, 3
    ld [wNes + nKnockdownSts], a
    ld a, $FF
    ld [wNes + $00], a
    ret

; $B5A9: a round begins ($06 = its number): Mac can punch, his hearts (no fewer than he has, unless it's
; the first), what comes back when he's worn out, the clock's rate, the combo pattern, both to their
; pre-round states ($C0).
NesRoundSetup::
    ld a, 1
    ld [wNes + nMacCanPunch], a
    ld a, [wNes + nRoundNumber]
    cp 4
    jp nc, .start
    ld b, a
    add a
    add b
    ld c, a                 ; X
    ld e, a
    ld d, 0
    ld hl, wNes + $05A3
    add hl, de
    ld a, c
    cp 3
    jp z, .set              ; round 1: as the table says
    ld a, [hl]
    swap a
    and $0F
    ld b, a
    ld a, [wNes + $0323]
    cp b
    jp z, .ones
    jp c, .set              ; fewer than the table: up to it
    jp .recover             ; more: kept
.ones:
    ld a, [hl]
    and $0F
    ld b, a
    ld a, [wNes + $0324]
    cp b
    jp nc, .recover
    ld a, b
    ld [wNes + $0324], a
    jp .recover
.set:
    ld a, [hl]
    swap a
    and $0F
    ld [wNes + $0323], a
    ld a, [hl]
    and $0F
    ld [wNes + $0324], a
.recover:                   ; $B5EC
    inc hl
    ld de, wNes + $032D
    REPT 2
        ld a, [hl]
        swap a
        and $0F
        ld [de], a
        inc e
        ld a, [hl+]
        and $0F
        ld [de], a
        inc e
    ENDR
    ld a, [wNes + nRoundNumber]
    add a
    ld e, a
    ld d, 0
    ld hl, wNes + $05D8
    add hl, de
    ld a, [hl+]
    ld [wNes + $0308], a
    ld a, [hl]
    ld [wNes + $0309], a
    ld a, [wNes + $05C0]
    ld [wNes + $4E], a
    ld a, [wNes + $05C1]
    ld [wNes + $4F], a
.start:                     ; $B621
    ld a, $80
    ld [wNes + nRoundTmrStart], a
    ld [wNes + $0340], a
    inc a
    ld [wNes + $0320], a
    ld a, $C0
    ld [wNes + nMacStatus], a
    ld [wNes + nOppCurState], a
    ld a, $81
    ld [wNes + $51], a
    ld [wNes + nOppStateStatus], a
    ld a, 1
    ld [wNes + $00], a
    ret

; $AAC1: the decision: Mac's points ($03E8...) against his mark ($05C8...): 1 Mac wins, 2 he does.
NesDecision::
    ld hl, wNes + $03E8
    ld de, wNes + $05C8
    ld b, 4
.cmp:
    ld a, [de]
    ld c, a
    ld a, [hl+]
    inc de
    cp c
    jp nz, .done
    dec b
    jp nz, .cmp
.done:                      ; carry (6502: clear) = fewer points
    ld a, 1
    ret nc
    inc a
    ret
