; Punch-Out!!'s career on the cartridge's battery-backed RAM (MBC5+RAM+BATTERY, 8 KB at $A000), kept as a pass key
; would keep it, and Mac's fastest KO or TKO of each fight. One block, at its start:
;   $00 "PO!!", then its format (SAVE_VERSION)
;   $05 the scene the career goes on at ($FF: none -- not begun, or over), then wRecWins-wAw as they stood
;   $0B on, SAVE_FIGHTS fights in the game's order, each his best: the round, then M:SS.CC's five digits ($FF: none
;       yet) -- in the order that says which is faster, compared byte by byte
;   then its check: the 16-bit sum of the bytes before it, low byte first.
; Anything else there (a new cartridge, another format, a bad check) is no save. The RAM is on only while one of
; these reads or writes it, as a screen loads (never in a fight's frames).

DEF SRAM_ENABLE EQU $0A     ; (MBC5: $0A to $0000-$1FFF turns its RAM on, anything else off; $4000 its bank)
DEF sSave EQU $A000
DEF SAVE_VERSION EQU 1
DEF SAVE_CAREER EQU 5
DEF SAVE_RECORD EQU 5       ; (wRecWins, wRecLosses, wRecKOs, wRecLost, wAw)
DEF SAVE_BEST EQU SAVE_CAREER + 1 + SAVE_RECORD
DEF SAVE_CHECK EQU SAVE_BEST + SAVE_FIGHTS * 6
ASSERT SAVE_CHECK + 2 <= 256, "the save's offsets are 8-bit"

SECTION "Code: Save, from any bank", ROM0
; (the save's bank mapped, then the caller's again: PwBack)
SaveResult::                ; SaveResultIn: A = the fight
    ld b, a
    ld a, BANK(SaveResultIn)
    ld [$2100], a
    ld a, b
    call SaveResultIn
    jp PwBack
SaveContinue::              ; SaveContinueIn: A = its scene ($FF: none)
    ld a, BANK(SaveContinueIn)
    ld [$2100], a
    call SaveContinueIn
    jp PwBack
BestDraw::                  ; BestDrawIn: A = the fight, HL and DE its place and glyphs
    ld b, a
    ld a, BANK(BestDrawIn)
    ld [$2100], a
    ld a, b
    call BestDrawIn
    jp PwBack

SECTION FRAGMENT "Screens far", ROMX
; A fight's result kept, as its screen loads (A = the fight): where the career goes on (wRecNext; none if that's
; game over or the ending) and Mac's record; a KO or TKO won faster than his best for this fight, his best (A = 1:
; it was, NEW RECORD!; else 0).
SaveResultIn:
    push af
    call SaveOn
    call SaveCheck
    call nz, SaveNew
    ld a, [wRecNext]
    call SaveGoesOn
    jr z, .career
    ld a, $FF
.career:
    ld hl, sSave + SAVE_CAREER
    ld [hl+], a
    ld de, wRecWins
    ld b, SAVE_RECORD
.record:
    ld a, [de]
    inc de
    ld [hl+], a
    dec b
    jr nz, .record
    pop bc                  ; (B: the fight; C: a new best)
    ld c, 0
    ld a, [wFtResult]
    cp FT_WIN_SCENE
    jr nz, .check
    ld a, [wFtCount]
    cp COUNT_TKO
    jr c, .check            ; (won on points: no time)
    add sp, -6              ; the fight's time, as TimeDrawIn writes it: round, M:SS, its hundredths
    ld hl, sp + 0
    ld a, [wNes + $06]
    ld [hl+], a
    ld a, [wNes + $0302]
    ld [hl+], a
    ld a, [wNes + $0304]
    ld [hl+], a
    ld a, [wNes + $0305]
    ld [hl+], a
    ld a, [wNes + $0306]
    swap a
    and $0F
    cp 7
    jr c, .cents
    ld a, 6
.cents:
    add a
    add LOW(TimeCents)
    ld e, a
    adc HIGH(TimeCents)
    sub e
    ld d, a
    ld a, [de]
    ld [hl+], a
    inc de
    ld a, [de]
    ld [hl], a
    ld hl, sp + 0
    ld d, h
    ld e, l
    ld a, b
    call SaveBestOf
    ld b, 6
.compare:                   ; faster: the first byte that differs is less (and on from it, the rest)
    ld a, [de]
    cp [hl]
    jr c, .new
    jr nz, .kept
    inc de
    inc hl
    dec b
    jr nz, .compare
    jr .kept
.new:
    inc c
.faster:
    ld a, [de]
    inc de
    ld [hl+], a
    dec b
    jr nz, .faster
.kept:
    add sp, 6
.check:
    call SaveSum
    ld a, e
    ld [hl+], a
    ld [hl], d
    ld a, c
    jr SaveOffA

; The saved career, if there's one to go on with: Mac's record as it stood (wRecWins-wAw), A = its scene ($FF: none).
SaveContinueIn:
    call SaveOn
    call SaveCheck
    ld a, $FF
    jr nz, SaveOffA
    ld hl, sSave + SAVE_CAREER
    ld a, [hl+]
    call SaveGoesOn
    ld a, $FF
    jr nz, SaveOffA
    ld de, wRecWins
    ld b, SAVE_RECORD
.record:
    ld a, [hl+]
    ld [de], a
    inc de
    dec b
    jr nz, .record
    ld a, [sSave + SAVE_CAREER]
SaveOffA:                   ; the RAM off, A kept
    ld b, a
    call SaveOff
    ld a, b
    ret

; His best for fight A (the save's), "BEST M:SS.CC,RN" as the NES writes a time, over its place -- nothing there
; without one: HL = its first cell in the map, DE = its glyphs ("B", "E", "S", "T", " ", M's 0-9, ":", S's, S's, ".",
; C's, C's, ",", "R", N's). Its digits read out first (onto the stack, as they're written), the RAM off before the
; screen's written (in a VBlank, the display on).
BestDrawIn:
    push hl
    push de
    ld c, a
    call SaveOn
    push bc
    call SaveCheck
    pop bc
    jr nz, .none
    ld a, c
    call SaveBestOf
    ld a, [hl]
    inc a
    jr z, .none
    ld a, [hl+]             ; (the round, last: BC = M, S; DE = S, C; HL = C, the round)
    ld d, a
    ld a, [hl+]
    ld c, a
    ld a, [hl+]
    ld b, a
    ld a, [hl+]
    ld e, a
    ld a, [hl+]
    ld l, [hl]
    ld h, d
    ld d, a
    call SaveOff
    push hl
    push de
    push bc
    ld hl, sp + 0
    ld b, h
    ld c, l                 ; (BC: the six digits)
    ld hl, sp + 6
    ld a, [hl+]
    ld e, a
    ld a, [hl+]
    ld d, a
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    call VWait              ; (the display on: in a VBlank)
    REPT 5                  ; BEST, a space
        call .word
    ENDR
    call .digit
    call .word              ; ":"
    call .digit
    call .digit
    call .word              ; "."
    call .digit
    call .digit
    call .word              ; ","
    call .word              ; "R"
    call .digit
    add sp, 10
    ret
.none:
    call SaveOff
    pop de
    pop hl
    ret
.word:                      ; [HL+] = the glyph at DE
    ld a, [de]
    inc de
    ld [hl+], a
    ret
.digit:                     ; [HL+] = digit [BC+]'s glyph (DE's ten), DE on to the next cell's
    ld a, [bc]
    inc bc
    push de
    add e
    ld e, a
    adc d
    sub e
    ld d, a
    ld a, [de]
    ld [hl+], a
    pop de
    ld a, e
    add 10
    ld e, a
    ret nc
    inc d
    ret

SaveOn:
    ld a, SRAM_ENABLE
    ld [$0000], a
    xor a
    ld [$4000], a
    ret
SaveOff:
    xor a
    ld [$0000], a
    ret

; Z: the save is good -- its tag, its format, its check (the RAM on).
SaveCheck:
    ld hl, sSave
    ld de, SaveTag
    ld b, SAVE_CAREER
.tag:
    ld a, [de]
    inc de
    cp [hl]
    ret nz
    inc hl
    dec b
    jr nz, .tag
    call SaveSum
    ld a, [hl+]
    cp e
    ret nz
    ld a, [hl]
    cp d
    ret

; DE = the sum of the block's bytes before its check, HL -> its check.
SaveSum:
    ld hl, sSave
    ld de, 0
    ld b, SAVE_CHECK
.add:
    ld a, [hl+]
    add e
    ld e, a
    jr nc, .next
    inc d
.next:
    dec b
    jr nz, .add
    ret

; A new save: no career, no bests (its check written after, by its caller).
SaveNew:
    ld hl, sSave
    ld de, SaveTag
    ld b, SAVE_CAREER
.tag:
    ld a, [de]
    inc de
    ld [hl+], a
    dec b
    jr nz, .tag
    ld a, $FF
    ld b, SAVE_CHECK - SAVE_CAREER
.none:
    ld [hl+], a
    dec b
    jr nz, .none
    ret
SaveTag:
    db "PO!!", SAVE_VERSION

; HL -> fight A's best.
SaveBestOf:
    ld l, a
    add a
    add l
    add a
    add LOW(sSave + SAVE_BEST)
    ld l, a
    ld h, HIGH(sSave)
    ret

; Z: scene A is one a career goes on at (SaveResumes); A kept.
SaveGoesOn:
    push hl
    ld hl, SaveResumes
    ld b, [hl]
    inc b
.scene:
    dec b
    jr z, .no
    inc hl
    cp [hl]
    jr nz, .scene
    pop hl
    ret
.no:
    inc b
    pop hl
    ret
