; Punch-Out!!'s pass keys, as the NES works them out (bank 7, $8EC1 and $8FF0): ten digits to Mac's record and
; circuit, and back. wPw is laid out as the NES's $0100-$013F, offsets the same: $00-$0F its working bytes, $10
; the digits it writes, $20 the digits it reads, $30-$35 the record (wins, losses, KOs: two decimal digits each),
; $36 the circuit (decoded), $37-$38 its check bytes. gbstage/nestests.py runs both against the NES's own.

SECTION "Pass key work", WRAM0, ALIGN[8]
wPw: ds $40

SECTION "Code: Pass keys", ROMX

PwKey:                      ; ($9101) added to each digit, as it's written; taken off, as it's read
    db 6, 3, 5, 7, 9, 0, 1, 4, 2, 8
PwShifts:                   ; ($90F1) per losses' last digit and circuit: the digits' turns ($FF: no key)
    db $01, $02, $00, $FF, $02, $00, $01, $FF, $00, $01, $02, $FF, $FF, $FF, $FF, $FF

; A = 0: wPw+$20's ten digits are a pass key; the record it stands for at wPw+$30, its circuit at wPw+$36.
; A = 1: not one.
PwDecode::
    ld hl, wPw + $32        ; (the losses' tens: not in a pass key, 0)
    ld [hl], 0
    ld hl, wPw              ; each digit less its key
    ld de, wPw + $20
    ld bc, PwKey
.less:
    ld a, [bc]
    inc bc
    push bc
    ld b, a
    ld a, [de]
    inc de
    sub b
    jr nc, .plus
    add 10
.plus:
    ld [hl+], a
    pop bc
    ld a, l
    cp 10
    jr nz, .less
    ld l, $09               ; turned this many times as it was written: turned back
    ld a, [hl]
    and 3
    ld l, $0E
    ld [hl], a
    jr z, .pack
    ld l, $0D
    ld [hl], a
.turn:
    ld l, 0
.turnDigit:
    ld a, [hl]
    srl a
    ld [hl], a
    ld a, 0                 ; (the bit shifted out: into the next digit's bit 3)
    rla
    rla
    rla
    rla
    inc l
    ld c, a
    ld a, l
    cp 10
    jr z, .turned
    ld a, c
    or [hl]
    ld [hl], a
    jr .turnDigit
.turned:
    ld l, $09
    ld a, [hl]
    and 2
    add a
    ld l, 0
    or [hl]
    ld [hl], a
    ld l, $0D
    dec [hl]
    jr nz, .turn
.pack:                      ; pairs of digits to bytes
    ld de, wPw
    ld l, 0
.packPair:
    ld a, [hl+]
    add a
    add a
    add a
    or [hl]
    inc l
    ld [de], a
    inc e
    ld a, l
    cp 10
    jr nz, .packPair
    ld l, $00               ; the record's digits, from their bits spread over the bytes
    ld a, [hl]
    and $0C
    ld b, a
    inc l
    ld a, [hl]
    and 3
    or b
    ld l, $30
    ld [hl], a
    ld l, $03
    ld a, [hl]
    and $0C
    ld b, a
    dec l
    ld a, [hl]
    and 3
    or b
    ld l, $31
    ld [hl], a
    ld l, $02
    ld a, [hl]
    and $0C
    ld b, a
    inc l
    ld a, [hl]
    and 3
    or b
    ld l, $34
    ld [hl], a
    ld l, $01
    ld a, [hl]
    and $0C
    ld b, a
    dec l
    ld a, [hl]
    and 3
    or b
    ld l, $35
    ld [hl], a
    ld l, $02               ; its check byte
    ld a, [hl]
    and $30
    srl a
    srl a
    ld b, a
    dec l
    ld a, [hl]
    and $30
    or b
    srl a
    srl a
    ld b, a
    dec l
    ld a, [hl]
    and $30
    or b
    ld b, a
    ld l, $03
    ld a, [hl]
    and $30
    add a
    add a
    or b
    ld l, $38
    ld [hl], a
    ld l, $04               ; the losses' last digit and the circuit
    ld a, [hl]
    and $0C
    ld b, a
    ld a, [hl]
    swap a
    and $0F
    or b
    ld l, $37
    ld [hl], a
    ld c, a
    and 3
    ld l, $33
    ld [hl], a
    ld a, c
    srl a
    srl a
    ld l, $36
    ld [hl], a
    call PwSum              ; checked
    ld l, $38
    cp [hl]
    jr nz, .no
    ld a, c                 ; turned as its losses and circuit say
    ld de, PwShifts
    add e
    ld e, a
    adc d
    sub e
    ld d, a
    ld a, [de]
    bit 7, a
    jr nz, .no
    ld l, $0E
    cp [hl]
    jr nz, .no
    ld l, $30               ; digits all 0-9
.digits:
    ld a, [hl+]
    cp 10
    jr nc, .no
    ld a, l
    cp $36
    jr nz, .digits
    ld l, $30               ; three wins at least, no more KOs than wins (the NES's own way of asking)
    ld a, [hl]
    and a
    jr nz, .tens
    inc l
    ld a, [hl]
    cp 3
    jr c, .no
.tens:
    ld l, $34
    cp [hl]
    jr c, .no
    jr nz, .yes
    ld l, $31
    ld a, [hl]
    ld l, $35
    cp [hl]
    jr c, .no
.yes:
    xor a
    ret
.no:
    ld a, 1
    ret

; A = the record's check byte: its six digits added up ($8EA9: each add's carry into the next), inverted.
PwSum:
    ld hl, wPw + $35
    xor a
    ld b, 6
.add:
    adc [hl]
    dec l
    dec b
    jr nz, .add
    cpl
    ret

; The pass key for the record at wPw+$30 (its losses under 3) and circuit B (0-2): its ten digits at wPw+$10.
PwEncode::
    sla b
    sla b
    ld hl, wPw + $36
    ld [hl], b
    call PwSum
    ld l, $38
    ld [hl], a
    ld l, $33
    ld a, [hl]
    ld l, $36
    or [hl]
    ld l, $37
    ld [hl], a
    ld de, PwShifts         ; its turns
    add e
    ld e, a
    adc d
    sub e
    ld d, a
    ld a, [de]
    ld l, $0D
    ld [hl], a
    xor a
    ld l, 0
    REPT 5
        ld [hl+], a
    ENDR
    ld c, $30               ; the record's digits spread over the bytes
    ld de, $0001
    call .split
    ld c, $31
    ld de, $0302
    call .split
    ld c, $34
    ld de, $0203
    call .split
    ld c, $35
    ld de, $0100
    call .split
    ld l, $38               ; its check byte
    ld a, [hl]
    ld b, a
    ld l, 0
    and $30
    or [hl]
    ld [hl+], a
    ld a, b
    add a
    add a
    ld b, a
    and $30
    or [hl]
    ld [hl+], a
    ld a, b
    add a
    add a
    and $30
    or [hl]
    ld [hl], a
    ld l, $38
    ld a, [hl]
    srl a
    srl a
    and $30
    ld l, $03
    or [hl]
    ld [hl], a
    ld l, $37               ; the losses' last digit and the circuit
    ld a, [hl]
    ld b, a
    swap a
    and $30
    ld c, a
    ld a, b
    and $0C
    or c
    ld l, $04
    ld [hl], a
    ld de, wPw + $19        ; each byte to two digits' top bits
    ld l, $04
.spread:
    ld a, [hl]
    swap a
    add a
    and $E0
    ld [de], a
    dec e
    ld a, [hl]
    add a
    add a
    and $E0
    ld [de], a
    dec e
    dec l
    bit 7, l
    jr z, .spread
    ld l, $0D               ; turned
    ld a, [hl]
    and a
    jr z, .unturned
    ld l, $0B
    ld [hl], a
.turn:
    ld l, $19
.turnDigit:
    sla [hl]
    ld a, 0
    rra
    dec l
    ld b, a
    ld a, l
    cp $0F
    jr z, .turned
    ld a, b
    srl a
    srl a
    srl a
    or [hl]
    ld [hl], a
    jr .turnDigit
.turned:
    ld l, $19
    ld [hl], b
    ld l, $0B
    dec [hl]
    jr nz, .turn
.unturned:
    ld l, $19               ; down to digits
.down:
    ld a, [hl]
    swap a
    srl a
    and 7
    ld [hl], a
    dec l
    ld a, l
    cp $0F
    jr nz, .down
    ld l, $0D
    ld a, [hl]
    ld l, $19
    or [hl]
    ld [hl], a
    ld de, PwKey + 9        ; each plus its key
.plus:
    ld a, [de]
    dec de
    add [hl]
    cp 10
    jr c, .digit
    sub 10
.digit:
    ld [hl], a
    dec l
    ld a, l
    cp $0F
    jr nz, .plus
    ret
.split:                     ; digit [C]'s high bits ($0C) into byte D, its low bits into byte E
    ld h, HIGH(wPw)
    ld l, c
    ld a, [hl]
    and $0C
    ld l, d
    or [hl]
    ld [hl], a
    ld l, c
    ld a, [hl]
    and 3
    ld l, e
    or [hl]
    ld [hl], a
    ret

; The title's pass key, as Punch-Out!!'s CONTINUE (ten digits at wPkDigits): A = the scene it starts at, Mac's record
; set from it; $FF: no pass key; $FE: a busy signal. The Tyson code, the credits' and the Another World Circuit's (Select held), else a pass key's circuit:
; its next one's first challenger (PwStarts: Major, World, the World title bout, Tyson, the ending, Another World).
PwContinue::
    ld de, PwTyson
    call .same
    jr nz, .notTyson
    call RecReset           ; (the NES's: two losses on his record)
    ld a, 2
    ld [wRecLosses], a
    ld a, [PwStarts + 3]
    ret
.notTyson:
    ldh a, [hPad]           ; (the NES's A, B and Select held: here Select held as the last digit's pressed)
    and PADF_SELECT
    jr z, .notCredits
    ld de, PwCredits
    call .same
    ld a, [PwStarts + 4]
    ret z
    ld de, PwAnother        ; the Another World Circuit: 0-0, its first challenger
    call .same
    jr nz, .notCredits
    call RecReset
    ld a, 1
    ld [wAw], a
    ld a, [PwStarts + 5]
    ret
.notCredits:
    ld de, PwBusy           ; the three busy signals: $FE
    ld c, 3
.busy:
    push bc
    call .same
    pop bc
    ld a, $FE
    ret z
    ld a, e                 ; (the next ten: .same left DE B short of them)
    add b
    ld e, a
    jr nc, .busyOn
    inc d
.busyOn:
    dec c
    jr nz, .busy
    ld hl, wPkDigits        ; a pass key?
    ld de, wPw + $20
    ld b, 10
.copy:
    ld a, [hl+]
    ld [de], a
    inc e
    dec b
    jr nz, .copy
    call PwDecode
    and a
    ld a, $FF
    ret nz
    ld hl, wPw + $30        ; its record
    ld de, wRecWins
    REPT 3
        ld a, [hl+]
        ld b, a
        add a
        add a
        add b
        add a
        add [hl]
        inc hl
        ld [de], a
        inc de
    ENDR
    xor a
    ld [wRecLost], a
    ld a, [wPw + $36]       ; its circuit's next
    add LOW(PwStarts)
    ld l, a
    adc HIGH(PwStarts)
    sub l
    ld h, a
    ld a, [hl]
    ret
.same:                      ; Z: wPkDigits are the ten at DE
    ld hl, wPkDigits
    ld b, 10
.digit:
    ld a, [de]
    cp [hl]
    ret nz
    inc de
    inc hl
    dec b
    jr nz, .digit
    ret

PwBusy:                     ; ($8DA2) the busy signals: 075 541 6113, 800 422 2602, 206 882 2040
    db 0, 7, 5, 5, 4, 1, 6, 1, 1, 3
    db 8, 0, 0, 4, 2, 2, 2, 6, 0, 2
    db 2, 0, 6, 8, 8, 2, 2, 0, 4, 0
PwTyson:                    ; ($8DD4) 007 373 5963
    db 0, 0, 7, 3, 7, 3, 5, 9, 6, 3
PwCredits:                  ; ($8DCA) 106 113 0120
    db 1, 0, 6, 1, 1, 3, 0, 1, 2, 0
PwAnother:                  ; ($8DC0) 135 792 4680
    db 1, 3, 5, 7, 9, 2, 4, 6, 8, 0

; Mac's record's pass key for circuit B (the training run's, between circuits): its digits at wPw+$10.
PwKeyFromRecord::
    ld hl, wRecWins
    ld de, wPw + $30
    REPT 3
        ld a, [hl+]
        ld c, -1
.tens\@:
        inc c
        sub 10
        jr nc, .tens\@
        add 10
        push af
        ld a, c
        ld [de], a
        inc e
        pop af
        ld [de], a
        inc e
    ENDR
    jp PwEncode

SECTION "Code: Pass keys, from any bank", ROM0
; (from code in a bank of its own: the pass keys' bank mapped, then the caller's again: hBank)
PwKeyFar::                  ; PwKeyFromRecord: B = the circuit
    ld a, BANK(PwKeyFromRecord)
    ld [$2100], a
    call PwKeyFromRecord
    jr PwBack
PwContinueFar::             ; PwContinue: A = its scene ($FF: none)
    ld a, BANK(PwContinue)
    ld [$2100], a
    call PwContinue
PwBack:
    ld b, a
    ldh a, [hBank]
    ld [$2100], a
    ld a, b
    ret
