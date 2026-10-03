; ---- Puzzle grid kit: falling capsules, match 4 of a color, clear every virus ---------------
; The rules match gbstage/puzzle.py (the reference the golden tests check this against).
; Cell byte: shape << 2 | color, 0 = empty. wGrid is page aligned, so L is the cell index; the
; tile for each cell sits one page up (wGridTiles) and match marks two pages up (wMark).

DEF PZ_SPAWN EQU 0
DEF PZ_FALL EQU 1
DEF PZ_CHECK EQU 2
DEF PZ_CLEARING EQU 3
DEF PZ_SETTLE EQU 4
DEF PZ_END EQU 5

DEF SH_VIRUS EQU 1
DEF SH_SINGLE EQU 2
DEF SH_LEFT EQU 3
DEF SH_RIGHT EQU 4
DEF SH_TOP EQU 5
DEF SH_BOTTOM EQU 6
DEF SH_POP EQU 7

DEF CLEAR_FRAMES EQU 20     ; how long cleared cells show as pops
DEF FALL_FRAMES EQU 6       ; frames per row when loose pieces fall
DEF END_FRAMES EQU 90       ; pause before the win / game over scene
DEF MIN_DROP EQU 4
DEF SPEEDUP_EVERY EQU 10

SECTION "Puzzle grid", WRAM0, ALIGN[8]
wGrid: ds 256               ; cell bytes, index = row * PZ_W + column
wGridTiles: ds 256          ; the tile shown for each cell
wMark: ds 256               ; cells matched this pass (1 = matched)
wMarkList: ds 256           ; ... and the same cells as a list, hMarkCount long
wDirtyRows: ds PZ_H         ; rows to redraw during VBlank
wTouchRows: ds PZ_H         ; rows and columns where a piece landed since the last check:
wTouchCols: ds PZ_W         ; a new match has to pass through one of them
wScore: ds 3                ; BCD, highest digits first
wHudTiles: ds 8             ; score (6) and virus count (2) tiles, ready for VBlank

SECTION "Code: Puzzle grid", ROM0

; Store A in the cell at HL and update its tile; mark the row for redrawing. Keeps BC, DE, HL.
SetCell:
    ld [hl], a
    push de
    push hl
    push bc
    ld b, a                 ; B = the new cell
    ld e, a
    ld d, HIGH(KitTileLUT)
    ld a, [de]
    inc h
    ld [hl], a              ; wGridTiles
    ld e, l
    ld d, HIGH(RowOf)
    ld a, [de]
    ld c, a                 ; C = row
    add LOW(wDirtyRows)
    ld l, a
    adc HIGH(wDirtyRows)
    sub l
    ld h, a
    ld a, 1
    ld [hl], a
    ldh [hGridDirty], a
    ld a, b
    and a
    jr z, .done             ; emptying a cell can't make a match
    ldh a, [hPzState]
    cp PZ_FALL
    jr z, .done             ; nor can a capsule in mid-air: landing marks its cells (TouchPiece)
    ld a, c
    add LOW(wTouchRows)
    ld l, a
    adc HIGH(wTouchRows)
    sub l
    ld h, a
    ld [hl], 1
    inc d                   ; ColOf is the page after RowOf
    ld a, [de]
    add LOW(wTouchCols)
    ld l, a
    adc HIGH(wTouchCols)
    sub l
    ld h, a
    ld [hl], 1
.done:
    pop bc
    pop hl
    pop de
    ret

; HL = the cell at row B, column C.
CellPtr:
    ld a, b
    add LOW(RowStart)
    ld l, a
    adc HIGH(RowStart)
    sub l
    ld h, a
    ld a, [hl]
    add c
    ld l, a
    ld h, HIGH(wGrid)
    ret

; A = the cell at row B, column C, or $FF outside the grid (rows above the top count as outside).
GetCell:
    ld a, b
    cp PZ_H
    jr nc, .outside
    ld a, c
    cp PZ_W
    jr nc, .outside
    call CellPtr
    ld a, [hl]
    ret
.outside:
    ld a, $FF
    ret

; Z if a capsule fits with its first half at row B, column C (D = 1 for vertical). Keeps BCDE.
Fits:
    call GetCell
    and a
    ret nz
    ld a, d
    and a
    jr nz, .vertical
    inc c
    call GetCell
    dec c
    and a
    ret
.vertical:
    dec b
    call GetCell
    inc b
    and a
    ret

LoadPos:
    ldh a, [hPzRow]
    ld b, a
    ldh a, [hPzCol]
    ld c, a
    ret

; Write the falling capsule into the grid (DrawPiece) or remove it (ErasePiece).
DrawPiece:
    call LoadPos
    call CellPtr
    ldh a, [hPzVert]
    and a
    jr nz, .vertical
    ldh a, [hPzC1]
    or SH_LEFT << 2
    call SetCell
    inc l
    ldh a, [hPzC2]
    or SH_RIGHT << 2
    jp SetCell
.vertical:
    ldh a, [hPzC1]
    or SH_BOTTOM << 2
    call SetCell
    ld a, l
    sub PZ_W
    ld l, a
    ldh a, [hPzC2]
    or SH_TOP << 2
    jp SetCell

ErasePiece:
    call LoadPos
    call CellPtr
    xor a
    call SetCell
    ldh a, [hPzVert]
    and a
    jr nz, .vertical
    inc l
    xor a
    jp SetCell
.vertical:
    ld a, l
    sub PZ_W
    ld l, a
    xor a
    jp SetCell

; Move the capsule to row B, column C, vertical D, swapping its colors if E is 1.
; Carry set if it moved; otherwise it stays where it was.
TryMove:
    push bc
    push de
    call ErasePiece
    pop de
    pop bc
    call Fits
    jr nz, .blocked
    ld a, b
    ldh [hPzRow], a
    ld a, c
    ldh [hPzCol], a
    ld a, d
    ldh [hPzVert], a
    ld a, e
    and a
    jr z, .draw
    ldh a, [hPzC1]
    ld b, a
    ldh a, [hPzC2]
    ldh [hPzC1], a
    ld a, b
    ldh [hPzC2], a
.draw:
    call DrawPiece
    scf
    ret
.blocked:
    call DrawPiece
    and a                   ; clear carry
    ret

; A rotates one way, B the other. Turning a vertical capsule flat next to a wall nudges it left.
RotateA:
    call LoadPos
    ldh a, [hPzVert]
    and a
    jr nz, .flat
    call TopRoom
    ld de, $0100            ; upright, colors stay (first half at the bottom)
    jp TryMove
.flat:
    ld de, $0001            ; flat, colors swap (the top half goes left)
    call TryMove
    ret c
    call LoadPos
    dec c
    ld de, $0001
    jp TryMove

RotateB:
    call LoadPos
    ldh a, [hPzVert]
    and a
    jr nz, .flat
    call TopRoom
    ld de, $0101            ; upright, colors swap
    jp TryMove
.flat:
    ld de, $0000
    call TryMove
    ret c
    call LoadPos
    dec c
    ld de, $0000
    jp TryMove

; Turning upright in the top row: stand on row 1 so the top half stays inside the bottle.
TopRoom:
    ld a, b
    and a
    ret nz
    inc b
    ret

MoveSideways:               ; C = column change (+1 / -1)
    ld a, c
    ldh [hPzStep], a
    call LoadPos
    ldh a, [hPzStep]
    add c
    ld c, a
    ldh a, [hPzVert]
    ld d, a
    ld e, 0
    jp TryMove

; A = a random byte (16-bit xorshift).
Random:
    ldh a, [hRandHi]
    ld h, a
    ldh a, [hRandLo]
    ld l, a
    ld a, h
    rra
    ld a, l
    rra
    xor h
    ld h, a
    ld a, l
    rra
    ld a, h
    rra
    xor l
    ld l, a
    xor h
    ld h, a
    ld a, l
    ldh [hRandLo], a
    ld a, h
    ldh [hRandHi], a
    ret

; A = a random number from 0 to B - 1.
RandBelow:
    push bc
    push de
    call Random
    ld c, a
    ld e, b
    ld d, 0
    ld hl, 0
    ld a, 8
.bit:
    add hl, hl
    sla c
    jr nc, .skip
    add hl, de
.skip:
    dec a
    jr nz, .bit
    ld a, h
    pop de
    pop bc
    ret

; ---- per frame ----------------------------------------------------------------------------

PuzzleUpdate:
    ldh a, [hPzState]
    add a
    add LOW(.states)
    ld l, a
    adc HIGH(.states)
    sub l
    ld h, a
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    jp hl
.states:
    dw PzSpawn, PzFall, PzCheck, PzClearing, PzSettle, PzEnd

PzSpawn:
    ldh a, [hPzNext1]
    ldh [hPzC1], a
    ldh a, [hPzNext2]
    ldh [hPzC2], a
    call NewNext
    xor a
    ldh [hPzVert], a
    ldh [hPzRow], a
    ld a, PZ_W / 2 - 1
    ldh [hPzCol], a
    ld b, 0
    ld c, PZ_W / 2 - 1
    ld d, 0
    call Fits
    jr nz, .blocked
    call DrawPiece
    ldh a, [hPzDrop]
    ldh [hPzTimer], a
    ld a, 1                 ; a Down still held from the last capsule doesn't drop this one
    ldh [hPzDownLock], a
    ldh a, [hPzSpeed]
    add LOW(PointsBySpeed)
    ld l, a
    adc HIGH(PointsBySpeed)
    sub l
    ld h, a
    ld a, [hl]
    ldh [hPzBase], a        ; this capsule's first virus is worth this much
    ld a, PZ_FALL
    ldh [hPzState], a
    ret
.blocked:                   ; the neck is full: game over
    PZ_SFX SFX_LOSE
    ld a, PZ_LOSE_SCENE
    jp PzFinish

PzFall:
    ldh a, [hPadNew]
    bit PAD_A, a
    jr z, .noA
    call RotateA
    jr nc, .noA
    PZ_SFX SFX_ROTATE
.noA:
    ldh a, [hPadNew]
    bit PAD_B, a
    jr z, .noB
    call RotateB
    jr nc, .noB
    PZ_SFX SFX_ROTATE
.noB:
    ldh a, [hPadRepeat]
    bit PAD_LEFT, a
    jr z, .noLeft
    ld c, -1
    call MoveSideways
    call c, MoveSound
.noLeft:
    ldh a, [hPadRepeat]
    bit PAD_RIGHT, a
    jr z, .noRight
    ld c, 1
    call MoveSideways
    call c, MoveSound
.noRight:
    ld hl, hPzTimer
    dec [hl]
    jr z, .step
    ldh a, [hPad]           ; holding down drops faster, once it's been pressed for this capsule
    bit PAD_DOWN, a
    jr nz, .down
    xor a
    ldh [hPzDownLock], a
    ret
.down:
    ldh a, [hPzDownLock]
    and a
    ret nz
    ld a, [hl]
    cp 3
    ret c
    ld [hl], 2
    ret
.step:
    ldh a, [hPzDrop]
    ld [hl], a
    call LoadPos
    inc b
    ldh a, [hPzVert]
    ld d, a
    ld e, 0
    call TryMove
    ret c
    ld hl, hPzCapsules      ; landed: every 10 capsules the drop gets faster
    inc [hl]
    ld a, [hl]
    cp SPEEDUP_EVERY
    jr c, .lock
    ld [hl], 0
    ldh a, [hPzDrop]
    cp MIN_DROP + 1
    jr c, .lock
    dec a
    ldh [hPzDrop], a
.lock:
    PZ_SFX SFX_LAND
    xor a
    ldh [hPzChain], a
    call TouchPiece
    ld a, PZ_CHECK
    ldh [hPzState], a
    ret

; A tap clicks; holding the direction gives a lighter tick.
MoveSound:
    ldh a, [hPadNew]
    and PADF_LEFT | PADF_RIGHT
    ld a, SFX_MOVE
    jr nz, .play
    ld a, SFX_MOVE_HELD
.play:
    PZ_SFX_A
    ret

; Mark the landed capsule's rows and columns for the match check.
TouchPiece:
    ldh a, [hPzRow]
    call .row
    ldh a, [hPzCol]
    call .col
    ldh a, [hPzVert]
    and a
    jr nz, .upright
    ldh a, [hPzCol]
    inc a
    jr .col
.upright:
    ldh a, [hPzRow]
    dec a
.row:
    add LOW(wTouchRows)
    ld l, a
    adc HIGH(wTouchRows)
    sub l
    ld h, a
    ld [hl], 1
    ret
.col:
    add LOW(wTouchCols)
    ld l, a
    adc HIGH(wTouchCols)
    sub l
    ld h, a
    ld [hl], 1
    ret

PzCheck:
    call FindMatches
    and a
    jr z, .noMatches
    call ApplyClear
    ldh a, [hPzChain]       ; each step of a chain plays the clear a whole step higher
    cp 6
    jr nc, .high
    inc a
    ldh [hPzChain], a
.high:
    dec a
    add a
    PZ_CLEAR_SFX
    ldh a, [hPzCleared]
    and a
    jr z, .noVirus
    PZ_SFX SFX_VIRUS
.noVirus:
    ld a, CLEAR_FRAMES
    ldh [hPzTimer], a
    ld a, PZ_CLEARING
    ldh [hPzState], a
    ret
.noMatches:
    ldh a, [hPzViruses]
    and a
    jr z, .won
    ld a, PZ_SPAWN
    ldh [hPzState], a
    ret
.won:
    PZ_SFX SFX_WIN
    ld a, PZ_WIN_SCENE
    ; fall through
PzFinish:                   ; A = the scene to go to after a pause
    ldh [hPzEndScene], a
    ld a, END_FRAMES
    ldh [hPzTimer], a
    ld a, PZ_END
    ldh [hPzState], a
    ret

PzEnd:
    ld hl, hPzTimer
    dec [hl]
    ret nz
    ldh a, [hPzEndScene]
    jp StartTransition

PzClearing:
    ld hl, hPzTimer
    dec [hl]
    ret nz
    ldh a, [hMarkCount]     ; remove the pops
    ld c, a
    ld de, wMarkList
.remove:
    ld a, [de]
    inc e
    ld l, a
    ld h, HIGH(wMark)
    ld [hl], 0
    ld h, HIGH(wGrid)
    xor a
    call SetCell
    dec c
    jr nz, .remove
    ldh [hMarkCount], a     ; A = 0
    ld a, FALL_FRAMES
    ldh [hPzTimer], a
    ld a, PZ_SETTLE
    ldh [hPzState], a
    ret

PzSettle:
    ld hl, hPzTimer
    dec [hl]
    ret nz
    ld [hl], FALL_FRAMES
    call SettleStep
    ldh a, [hPzMoved]
    and a
    ret nz
    ld a, PZ_CHECK          ; everything has landed: look for chains
    ldh [hPzState], a
    ret

; ---- rules ----------------------------------------------------------------------------------

; Mark every run of 4+ cells of one color that passes through a touched row or column.
; A = how many cells matched (0 = none).
FindMatches:
    xor a
    ldh [hMarkCount], a
    ld b, 0                 ; rows
.row:
    ld hl, wTouchRows
    ld a, l
    add b
    ld l, a
    adc h
    sub l
    ld h, a
    ld a, [hl]
    and a
    jr z, .nextRow
    ld [hl], 0
    push bc
    ld a, b
    add LOW(RowStart)
    ld l, a
    adc HIGH(RowStart)
    sub l
    ld h, a
    ld l, [hl]
    ld h, HIGH(wGrid)
    ld b, PZ_W
    call ScanRow
    pop bc
.nextRow:
    inc b
    ld a, b
    cp PZ_H
    jr c, .row
    ld b, 0                 ; columns
.col:
    ld hl, wTouchCols
    ld a, l
    add b
    ld l, a
    adc h
    sub l
    ld h, a
    ld a, [hl]
    and a
    jr z, .nextCol
    ld [hl], 0
    push bc
    ld l, b
    ld h, HIGH(wGrid)
    ld b, PZ_H
    call ScanCol
    pop bc
.nextCol:
    inc b
    ld a, b
    cp PZ_W
    jr c, .col
    ldh a, [hMarkCount]
    ret

; Scan B cells from HL (one row, or one column) for runs of 4+. D = run length, E = run color.
MACRO SCAN_LINE             ; \1 = Row or Col
Scan\1:
    ld d, 0
    ld e, $FF
.cell:
    ld a, [hl]
    and a
    jr z, .empty
    and 3
    cp e
    jr nz, .newRun
    inc d
    jr .step
.newRun:
    ld c, a
    ld a, d
    cp 4
    call nc, Mark\1
    ld e, c
    ld d, 1
    ld a, l
    ldh [hRunStart], a
    jr .step
.empty:
    ld a, d
    cp 4
    call nc, Mark\1
    ld d, 0
    ld e, $FF
.step:
    IF STRCMP("\1", "Row") == 0
        inc l
    ELSE
        ld a, l
        add PZ_W
        ld l, a
    ENDC
    dec b
    jr nz, .cell
    ld a, d
    cp 4
    ret c
    ; fall through to mark the last run

; Mark D cells from hRunStart, adding each new one to wMarkList.
Mark\1:
    push hl
    push bc
    ldh a, [hRunStart]
    ld l, a
.mark:
    ld h, HIGH(wMark)
    ld a, [hl]
    and a
    jr nz, .already
    ld [hl], 1
    ldh a, [hMarkCount]
    ld c, a
    inc a
    ldh [hMarkCount], a
    ld b, l
    ld l, c
    ld h, HIGH(wMarkList)
    ld [hl], b
    ld l, b
.already:
    IF STRCMP("\1", "Row") == 0
        inc l
    ELSE
        ld a, l
        add PZ_W
        ld l, a
    ENDC
    dec d
    jr nz, .mark
    pop bc
    pop hl
    ret
ENDM

    SCAN_LINE Row
    SCAN_LINE Col

; Turn matched cells into pops, unpair their partners, count viruses and score them.
ApplyClear:
    xor a
    ldh [hPzCleared], a
    ldh [hIdx], a           ; position in wMarkList
.cell:
    ldh a, [hIdx]
    ld l, a
    ld h, HIGH(wMarkList)
    ld l, [hl]
    ld h, HIGH(wGrid)
    ld a, [hl]
    ld e, a                 ; E = the matched cell
    srl a
    srl a
    cp SH_VIRUS
    jr nz, .notVirus
    ldh a, [hPzCleared]
    inc a
    ldh [hPzCleared], a
    jr .pop
.notVirus:
    ld d, 0                 ; D = partner offset
    cp SH_LEFT
    jr nz, .notLeft
    ld d, 1
.notLeft:
    cp SH_RIGHT
    jr nz, .notRight
    ld d, -1
.notRight:
    cp SH_TOP
    jr nz, .notTop
    ld d, PZ_W
.notTop:
    cp SH_BOTTOM
    jr nz, .notBottom
    ld d, -PZ_W
.notBottom:
    ld a, d
    and a
    jr z, .pop
    push hl
    add l
    ld l, a
    inc h
    inc h                   ; is the partner matched too?
    ld a, [hl]
    dec h
    dec h
    and a
    jr nz, .partnerDone
    ld a, [hl]              ; no: it becomes a single of its own color
    and 3
    or SH_SINGLE << 2
    call SetCell
.partnerDone:
    pop hl
.pop:
    ld a, e
    and 3
    or SH_POP << 2
    call SetCell
    ldh a, [hIdx]
    inc a
    ldh [hIdx], a
    ld b, a
    ldh a, [hMarkCount]
    cp b
    jr nz, .cell
    ; Fewer viruses; points double with each one this capsule clears.
    ldh a, [hPzCleared]
    and a
    ret z
    ld b, a
    ldh a, [hPzViruses]
    sub b
    ldh [hPzViruses], a
.score:
    ldh a, [hPzBase]        ; BCD hundreds
    ld c, a
    ld a, [wScore + 1]
    add c
    daa
    ld [wScore + 1], a
    ld a, [wScore]
    adc 0
    daa
    jr nc, .noCap
    ld a, $99               ; 999999 is the most it shows
    ld [wScore + 1], a
    ld [wScore + 2], a
.noCap:
    ld [wScore], a
    ld a, c                 ; double the next virus's points, at most 99 hundred
    cp $50
    ld a, $99
    jr nc, .capped
    ld a, c
    add a
    daa
.capped:
    ldh [hPzBase], a
    dec b
    jr nz, .score
    jp UpdateHud

; Drop every unsupported loose piece by one row, bottom-up. hPzMoved = 1 if anything moved.
; Cell bytes sort by shape, so most cells (empty, viruses, halves riding on a partner) skip fast.
SettleStep:
    xor a
    ldh [hPzMoved], a
    ld hl, wGrid + (PZ_H - 1) * PZ_W - 1    ; the second-to-last row, right to left, upwards
.cell:
    ld a, [hl]
    cp SH_SINGLE << 2
    jr c, .next             ; empty or a virus: never falls
    cp SH_RIGHT << 2
    jr c, .loose            ; a single or a left half
    cp SH_BOTTOM << 2
    jr c, .next             ; a right or top half: moves with its partner
    cp SH_POP << 2
    jr nc, .next
    jr .one                 ; a bottom half
.loose:
    cp SH_LEFT << 2
    jr nc, .pair
.one:                       ; a single or an upright capsule: falls if the cell below is empty
    ld e, a
    ld a, l
    add PZ_W
    ld l, a
    ld a, [hl]
    and a
    jr nz, .back
    ld a, e
    call SetCell            ; below = this piece
    ld a, l
    sub PZ_W
    ld l, a
    ld a, e
    cp SH_BOTTOM << 2
    jr c, .vacate
    ld a, l                 ; an upright capsule: its top half comes down into this cell
    sub PZ_W
    ld l, a
    ld d, [hl]
    xor a
    call SetCell
    ld a, l
    add PZ_W
    ld l, a
    ld a, d
    call SetCell
    jr .moved
.vacate:
    xor a
    call SetCell
.moved:
    ld a, 1
    ldh [hPzMoved], a
    jr .next
.back:                      ; supported: return to this cell
    ld a, l
    sub PZ_W
    ld l, a
    jr .next
.pair:                      ; a flat capsule falls if both cells below are empty
    ld e, a
    ld a, l
    add PZ_W
    ld l, a
    ld a, [hl+]
    or [hl]
    jr nz, .backPair
    ld a, l                 ; to the right half
    sub PZ_W
    ld l, a
    ld d, [hl]
    xor a
    call SetCell
    dec l
    xor a
    call SetCell
    ld a, l
    add PZ_W
    ld l, a
    ld a, e
    call SetCell
    inc l
    ld a, d
    call SetCell
    ld a, l
    sub PZ_W + 1
    ld l, a
    jr .moved
.backPair:
    ld a, l
    sub PZ_W + 1
    ld l, a
.next:
    ld a, l
    and a
    ret z
    dec l
    jp .cell

; ---- setup and display --------------------------------------------------------------------

; Random colors for the next capsule, shown in the preview.
NewNext:
    ld b, 3
    call RandBelow
    ldh [hPzNext1], a
    call RandBelow
    ldh [hPzNext2], a
    ld a, 1
    ldh [hNextDirty], a
    ret

; Tiles for the score and virus count, for VBlank to show.
UpdateHud:
    ld hl, wHudTiles
    ld de, wScore
    ld bc, HudScoreDigits
    REPT 3
        ld a, [de]          ; high digit
        swap a
        and $0F
        call .digit
        ld a, [de]          ; low digit
        and $0F
        call .digit
        inc de
    ENDR
    ldh a, [hPzViruses]     ; virus count, 0-99
    ld d, -1
.tens:
    inc d
    sub 10
    jr nc, .tens
    add 10
    ld e, a
    ld a, d
    ld bc, HudVirusDigits
    call .digit
    ld a, e
    call .digit
    ld a, 1
    ldh [hHudDirty], a
    ret
.digit:                     ; [HL+] = tile for digit A of the HUD cell BC points at; BC += 10
    push hl
    add c
    ld l, a
    adc b
    sub l
    ld h, a
    ld a, [hl]
    pop hl
    ld [hl+], a
    ld a, c
    add 10
    ld c, a
    ret nc
    inc b
    ret

; Set up a new game (the screen is off): seed, speed, viruses, score, next capsule.
PuzzleStart:
    ldh a, [hFrame]
    ldh [hRandLo], a
    xor $5A
    or 1
    ldh [hRandHi], a
    ld hl, wGrid            ; empty grid
    ld b, PZ_SIZE
    xor a
.clearGrid:
    ld [hl+], a
    dec b
    jr nz, .clearGrid
    ld hl, wGridTiles
    ld b, PZ_SIZE
    ld a, [KitTileLUT]
.clearTiles:
    ld [hl+], a
    dec b
    jr nz, .clearTiles
    xor a
    ld [wScore], a
    ld [wScore + 1], a
    ld [wScore + 2], a
    ldh [hPzCapsules], a
    ldh [hPzState], a       ; PZ_SPAWN
    PZ_READ_SPEED           ; A = 0-2
    ldh [hPzSpeed], a
    add LOW(SpeedFrames)
    ld l, a
    adc HIGH(SpeedFrames)
    sub l
    ld h, a
    ld a, [hl]
    ldh [hPzDrop], a
    PZ_READ_LEVEL           ; A = level
    inc a                   ; viruses = 4 * (level + 1), up to what the board allows
    add a
    add a
    cp PZ_MAX_VIRUSES + 1
    jr c, .count
    ld a, PZ_MAX_VIRUSES
.count:
    ldh [hPzViruses], a
    ld c, a
.virus:
    push bc
    call PlaceVirus
    pop bc
    dec c
    jr nz, .virus
    ld hl, wMark            ; RAM powers on with random contents: no cell is marked yet
    xor a
    ld b, a                 ; 256 bytes
.unmark:
    ld [hl+], a
    dec b
    jr nz, .unmark
    ld hl, wTouchRows       ; a fresh board has no runs of 3, so nothing needs checking yet
    xor a
    ld b, PZ_H + PZ_W
.untouch:
    ld [hl+], a
    dec b
    jr nz, .untouch
    ldh [hMarkCount], a
    call NewNext
    call UpdateHud
    ret

; Put one virus on a random empty cell in the lower part of the grid, avoiding three of a color in a row.
PlaceVirus:
    ld b, PZ_H - PZ_VIRUS_TOP
    call RandBelow
    add PZ_VIRUS_TOP
    ld d, a                 ; row
    ld b, PZ_W
    call RandBelow
    ld e, a                 ; column
.find:
    ld b, d
    ld c, e
    call CellPtr
    ld a, [hl]
    and a
    jr z, .free
    inc e                   ; taken: try the next cell, wrapping around the virus area
    ld a, e
    cp PZ_W
    jr c, .find
    ld e, 0
    inc d
    ld a, d
    cp PZ_H
    jr c, .find
    ld d, PZ_VIRUS_TOP
    jr .find
.free:
    push hl
    ld b, 3
    call RandBelow
    pop hl
    ld c, 3                 ; try each color until one doesn't make three in a row
.color:
    ld b, a
    call ThreeInRow
    jr nz, .place
    ld a, b
    inc a
    cp 3
    jr c, .ok
    xor a
.ok:
    dec c
    jr nz, .color
    inc e                   ; every color would make three in a row here: try the next cell
    ld a, e
    cp PZ_W
    jr c, .find
    ld e, 0
    inc d
    ld a, d
    cp PZ_H
    jr c, .find
    ld d, PZ_VIRUS_TOP
    jr .find
.place:
    ld a, b
.store:
    or SH_VIRUS << 2
    jp SetCell

; NZ if color B at cell HL would NOT make three in a row with two neighbors in any direction.
ThreeInRow:
    push de
    ld e, -1
    call .pair
    jr z, .done
    ld e, 1
    call .pair
    jr z, .done
    ld e, -PZ_W
    call .pair
    jr z, .done
    ld e, PZ_W
    call .pair
.done:
    pop de
    ret
.pair:                      ; Z if the next two cells in direction E are both color B viruses... or pieces
    push hl
    ld a, l
    add e
    ld l, a
    call .same
    jr nz, .no
    ld a, l
    add e
    ld l, a
    call .same
.no:
    pop hl
    ret
.same:                      ; Z if [HL] is a piece of color B (and inside the grid)
    ld a, l
    cp PZ_SIZE
    jr nc, .outside
    ld a, [hl]
    and a
    jr z, .outside
    and 3
    cp b
    ret
.outside:
    or 1                    ; NZ
    ret
