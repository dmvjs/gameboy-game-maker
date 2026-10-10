; ---- Fight kit: a boxing match against one rival ----------------------------------------------
; The rival is background tiles: every pose's tiles are already in video memory, so a pose change
; rewrites his 8x10-tile area of the map during VBlank (GDMA on Game Boy Color). The player is
; sprites, copied to OAM by DMA each frame. Numbers come from gbstage/fight.py.

DEF rDMA EQU $FF46
DEF rSTAT EQU $FF41
DEF rLYC EQU $FF45
DEF STATF_LYC EQU $40
DEF OAMF_XFLIP EQU $20

DEF PL_IDLE EQU 0
DEF PL_PUNCH EQU 1
DEF PL_DODGE EQU 2
DEF PL_BLOCK EQU 3
DEF PL_HIT EQU 4
DEF PL_STAR EQU 5
DEF PL_DOWN EQU 6

DEF RV_IDLE EQU 0
DEF RV_GUARD EQU 1
DEF RV_TELL EQU 2
DEF RV_STRIKE EQU 3
DEF RV_OPEN EQU 4
DEF RV_HIT EQU 5
DEF RV_TAUNT EQU 6
DEF RV_FALL EQU 7
DEF RV_DOWN EQU 8
DEF RV_GETUP EQU 9
DEF RV_CHEER EQU 10
DEF RV_POP EQU 12           ; his arm popped out of its socket
DEF RV_SLIP EQU 13          ; slipping a right hand, about to counter
DEF RV_CHARGE EQU 11       ; shuffling back in after the taunt

DEF M_FIGHT EQU 0
DEF M_BREAK EQU 1
DEF M_RIVAL_DOWN EQU 2
DEF M_PLAYER_DOWN EQU 3
DEF M_END EQU 4

DEF OP_IDLE EQU 0
DEF OP_GUARD EQU 1
DEF OP_JAB EQU 2
DEF OP_HOOK EQU 3
DEF OP_TAUNT EQU 4

DEF COUNT_KO EQU $FF        ; wFtCount value that shows "KO!"
DEF SAY_COUNT EQU 1         ; what the referee is saying
DEF SAY_KO EQU 2
DEF SAY_FIGHT EQU 3
DEF RF_STAND EQU 0          ; referee poses
DEF RF_COUNT EQU 1
DEF RF_WAVE EQU 2
DEF REF_IN EQU 118          ; his screen x when he's in the ring, beside the action
DEF REF_OUT EQU 172         ; off the right edge

SECTION "Fight state", WRAM0
wFtStart:
wFtMatch: db
wFtTimer: db                ; break / end pause
wFtRound: db
wFtMin: db
wFtSec: db                  ; BCD
wFtSub: db                  ; frames into the current clock second
wFtPoints: ds 3             ; BCD, high byte first
wFtCount: db                ; referee count on screen (0 = none, COUNT_KO = "KO!")
wFtCountTimer: db
wFtResult: db               ; scene to go to when the match ends
wFtShake: db
wFtHudDirty: db
wPlState: db
wPlTimer: db
wPlSide: db                 ; 0 = left hand / left dodge, 1 = right
wPlHigh: db                 ; nonzero: the punch is aimed at the head
wPlHealth: db
wPlHearts: db
wPlStars: db
wPlDowns: db                ; knockdowns this round
wPlDownsAll: db
wPlMash: db
wPlTired: db
wPlPose: db
wPlFlip: db
wPlX: db                    ; sideways offset while dodging (signed)
wRvState: db
wRvTimer: db
wRvHealth: db
wRvPose: db
wRvShown: db                ; pose currently on the map
wRvAttack: db               ; 0 jab, 1 hook
wRvDowns: db                ; knockdowns this fight
wRvScript: dw
wRvGuard: db                ; 0: gloves low, covering the body; 1: gloves high, covering the face
wRvLanded: db               ; clean hits since he last switched guard
wPlPunches: db              ; landed punches toward the next star
wRvTimed: dw                ; next clock-timed move in RivalTimed
wRvPending: db              ; a timed move waiting for him to be free: op + 1 (0 = none)
wRvPendingArg: db
wFtHudVal: ds FT_HUD_CELLS
wFtHud: ds FT_HUD_CELLS
wFtPlayerY: db
wFtWord: ds 3              ; the count as glyphs, $FF-terminated
wFtSayX: db
wRvOpenHits: db             ; counter punches left before he covers up again
wRvStarKD: db               ; the knockdown was a star punch
wRvGetupAt: db              ; the count he gets up at (0: he stays down)
wRvGetupHP: db
wRvNoGetup: db              ; caught on the charge: he's not getting up
wRvDownsRound: db           ; knockdowns this round (three is a TKO)
wPlStarsEarned: db          ; has the first star come (after it, one every 8th punch)
wPlStarsUsed: db            ; star punches thrown: he starts slipping them
wPlHitTired: db             ; got hit while worn out (fewer hearts back)
wFtSparkT: db               ; frames the impact burst shows
wFtSparkX: db
wFtSparkY: db
wRvRights: db               ; right hands thrown at him: every third one he slips and counters
wPlWhiff: db                ; the punch in flight was slipped
wFtSweatT: db               ; frames the sweat beads keep flying
wFtSweat: ds 3 * 4          ; per bead: x, y, x speed, y speed
wFtSwapWant: db             ; 0: attack poses' tiles in video memory, 1: the knockdown set
wFtSwapHave: db
wFtSwapPos: db              ; tiles copied so far toward the wanted set
wFtRefX: db                 ; the referee's screen x (signed); off the left edge when he's not needed
wFtRefPose: db
wFtSay: db
wRvNesX: db                 ; NES rival: his offset from his place (pixels right, down)
wRvNesY: db
wFtFreeze: db               ; hit stop: frames both fighters hold still after a clean hit
wFtExcite: db               ; frames the crowd's cameras keep flashing
wFtRand: db
wFtBulbs: ds 4 * 2          ; per flash: map address, the tile it covers, state (0 free, frames left, $FF restore)
wFtEnd:

SECTION "Fight between rounds", WRAM0   ; kept while the corner scene shows
wFtResume: db               ; coming back from the corner: carry on, don't start a new fight
wFtSelectUsed: db           ; the corner's Select refill is once per match

SECTION "Fight OAM", WRAM0, ALIGN[8]
wFtOAM: ds 256              ; 40 sprites go to OAM; a busy frame's extras land in the spare room and aren't shown

SECTION "Code: Fight", ROM0

OAMDMACode:                 ; copied to HRAM: OAM DMA needs the CPU to wait off the main bus
    ldh [rDMA], a
    ld a, 40
.wait:
    dec a
    jr nz, .wait
    ret
OAMDMACodeEnd:

; ---- loading (screen off) ----

FightLoad:
    ld a, [wFtResume]       ; back from the corner: the fight carries on
    and a
    jr nz, .keep
    ld [wFtSelectUsed], a
    ld hl, wFtStart
    ld b, wFtEnd - wFtStart
.clear:
    ld [hl+], a
    dec b
    jr nz, .clear
.keep:
    ld hl, OAMDMACode
    ld de, hOAMDMA
    ld b, OAMDMACodeEnd - OAMDMACode
.dma:
    ld a, [hl+]
    ld [de], a
    inc e
    dec b
    jr nz, .dma
    ld a, BANK(RivalMaps)   ; the fight's data stays mapped while it runs
    ld [$2000], a
    ld hl, FtObjTiles       ; player and count sprites
    ld de, $8000 + FT_OBJ_FIRST * 16
    ld bc, FT_OBJ_TILES * 16
.tiles:
    ld a, [hl+]
    ld [de], a
    inc de
    dec bc
    ld a, b
    or c
    jr nz, .tiles
    ld a, REF_OUT
    ld [wFtRefX], a
    ld a, M_BREAK           ; the referee calls the fight first
    ld [wFtMatch], a
    ld a, FT_INTRO
    ld [wFtTimer], a
    xor a                   ; the map shows the idle pose, and the attack set is loaded with the scene
    ld [wRvShown], a
    ld [wRvPose], a
    ld [wFtSwapWant], a
    ld [wFtSwapHave], a
    ld [wFtSwapPos], a
    ld [wFtCount], a
    ld a, [wFtResume]
    and a
    jr z, .newFight
    xor a
    ld [wFtResume], a
    call FtResetBoxers
    jr .ready
.newFight:
    ld a, 1
    ld [wFtRound], a
    ld a, FT_HEALTH
    ld [wPlHealth], a
    ld [wRvHealth], a
    ld a, FT_HEARTS
    ld [wPlHearts], a
IF DEF(FT_NES)
    ld a, BANK(NesFighter)  ; his fight data and AI, as the NES game starts a fight
    ld [$2000], a
    call NesFightStart
    ld a, BANK(RivalMaps)
    ld [$2000], a
ENDC
    ld a, LOW(RivalScript)
    ld [wRvScript], a
    ld a, HIGH(RivalScript)
    ld [wRvScript + 1], a
    ld a, LOW(RivalTimed)
    ld [wRvTimed], a
    ld a, HIGH(RivalTimed)
    ld [wRvTimed + 1], a
    call FtNextOp
.ready:
IF DEF(FT_NES)
    ld hl, FtTailTiles      ; the background below him, for his band's end when he's raised
    ld de, $9800 + FT_TAIL_ROW * 32
    ld b, FT_TAIL_ROWS * 32
.tail:
    ld a, [hl+]
    ld [de], a
    inc de
    dec b
    jr nz, .tail
    ldh a, [hIsCGB]
    and a
    jr z, .tailDone
    ld a, 1
    ldh [rVBK], a
    ld hl, FtTailAttr
    ld de, $9800 + FT_TAIL_ROW * 32
    ld b, FT_TAIL_ROWS * 32
.tailAttr:
    ld a, [hl+]
    ld [de], a
    inc de
    dec b
    jr nz, .tailAttr
    xor a
    ldh [rVBK], a
.tailDone:
ENDC
IF DEF(FT_NES_SOUND)
    ldh a, [hNesSound]      ; the NES's sound engine takes the sound hardware for the fight (already playing,
    and a                   ; the crowd from the screen before: it carries on)
    jr nz, .soundOn
    ld a, BANK(NesSnd)
    ld [$2000], a
    call ApuInit
.soundOn:
    ld a, 1
    ldh [hNesSound], a
ENDC
IF DEF(FT_NES)
    xor a                   ; Mac standing till his script's first pose
    ld [wPlPose], a
    ld [wPlFlip], a
    ld a, BANK(NesFighter)  ; the round, as the NES game starts one
    ld [$2000], a
    ld a, [wFtRound]
    call NesRoundStart
    ld a, BANK(RivalMaps)
    ld [$2000], a
ENDC
    call FtHudCompute
    call FtHudDraw
    xor a
    ldh [hFtHudReady], a
    ldh [hFtScx], a
    call FtBuildOAM
    ld hl, wFtOAM           ; OAM is writable with the screen off
    ld de, $FE00
    ld b, 160
.oam:
    ld a, [hl+]
    ld [de], a
    inc e
    dec b
    jr nz, .oam
    ld a, 1
    ldh [hFtActive], a
    xor a
    ldh [hFtBandX], a
    ldh [hFtBandY], a
    ldh [hFtBandOn], a
    ld a, FT_BAND_BOTTOM
    ldh [hFtBandBottom], a
    ldh [hFtFlash], a
    ldh [hFtFlashShown], a
    ld a, FT_BAND_TOP       ; the rival's band scrolls on its own: an interrupt at its top and bottom lines
    ldh [hFtBandTop], a
    ldh [rLYC], a
    ld a, STATF_LYC
    ldh [rSTAT], a
    ld a, %00000011         ; VBlank (wakes HALT) and STAT
    ldh [rIE], a
    xor a
    ldh [rIF], a
    ei
    ret

; Mid-frame: at the band's top line, scroll by the rival's offset; at its bottom line, back to normal.
; The band moves with his height, so its scroll never brings in what's below it: shown higher, it
; starts higher (over the lines above it), and the lines it leaves at its old bottom show the background
; there without him (two map rows kept off screen, FT_TAIL_ROW).
FtStat:
    push af
    ldh a, [hFtBandOn]
    and a
    jr z, .top
    dec a
    jr nz, .bottom
    ldh a, [hFtBandY]       ; his band's end: raised (scrolled down), the background below him down to its
    and a                   ; usual end
    jr z, .bottom
    bit 7, a
    jr nz, .bottom
    ldh a, [rLY]            ; (only if that end is still to come: his height can change mid-frame, and a
    cp FT_BAND_BOTTOM       ; missed end would leave the tail's scroll on to the bottom, wrapping to the HUD)
    jr nc, .bottom
    ldh a, [hFtScx]
    ldh [rSCX], a
    ld a, FT_TAIL_SCY
    ldh [rSCY], a
    ld a, FT_BAND_BOTTOM
    ldh [rLYC], a
    ld a, 2
    ldh [hFtBandOn], a
    pop af
    reti
.top:
    ldh a, [hFtBandX]
    ldh [rSCX], a
    ldh a, [hFtBandY]
    ldh [rSCY], a
    ldh a, [hFtBandBottom]
    ldh [rLYC], a
    ld a, 1
    ldh [hFtBandOn], a
    pop af
    reti
.bottom:
    ldh a, [hFtScx]
    ldh [rSCX], a
    xor a
    ldh [rSCY], a
    ldh [hFtBandOn], a
    ldh a, [hFtBandTop]
    ldh [rLYC], a
    pop af
    reti

; ---- VBlank: sprites, then the rival's pose or the HUD ----

FtVBlank:
    ld a, HIGH(wFtOAM)
    call hOAMDMA
    ldh a, [hFtScx]
    ldh [rSCX], a
    ldh a, [hFtFlash]       ; Color: the rival flashes white when a punch lands
    and a
    jr z, .noFlash
    dec a
    ldh [hFtFlash], a
.noFlash:
    and a
    jr z, .flashOff
    ld a, 1
.flashOff:
    ld hl, hFtFlashShown
    cp [hl]
    jr z, .pose
    ld [hl], a
    jp FtFlashPalettes
.pose:
    call FtCrowdDraw
    ld a, [wRvPose]
    ld hl, wRvShown
    cp [hl]
    jr z, .hud
    ld [hl], a
    jp FtDrawPose
.hud:
    call FtSwapStep
    ret nz
    ldh a, [hFtHudReady]
    and a
    ret z
    xor a
    ldh [hFtHudReady], a
    jp FtHudDraw

; A = pose. Game Boy Color: one GDMA of the rival's 10 full map rows, then one for their palettes.
; Original: copy just his 8 tiles of each row with the CPU.
FtDrawPose:
    add a
    ld e, a
    ld d, 0
    ld hl, RivalMaps
    add hl, de
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    ld a, BANK(RivalMap_idle)   ; the pose rows have a bank of their own
    ld [$2000], a
    call .draw
    ld a, BANK(RivalMaps)
    ld [$2000], a
    ret
.draw:
    ldh a, [hIsCGB]
    and a
    jr z, .dmg
    call .gdma
    ld hl, FT_POSE_BYTES    ; the palettes follow the map rows
    add hl, bc
    ld a, 1
    ldh [rVBK], a
    call .gdma
    xor a
    ldh [rVBK], a
    ret
.gdma:                      ; HL = source; keeps it in BC
    ld b, h
    ld c, l
    ld a, h
    ldh [rHDMA1], a
    ld a, l
    ldh [rHDMA2], a
    ld a, HIGH(FT_REGION_ROW)
    ldh [rHDMA3], a
    ld a, LOW(FT_REGION_ROW)
    ldh [rHDMA4], a
    ld a, FT_POSE_BYTES / 16 - 1
    ldh [rHDMA5], a
    ret
.dmg:
    ld de, FT_REGION_X
    add hl, de
    ld de, FT_REGION_ROW + FT_REGION_X
    ld b, FT_REGION_H
.dmgRow:
    REPT FT_REGION_W
        ld a, [hl+]
        ld [de], a
        inc e
    ENDR
    ld a, l
    add 32 - FT_REGION_W
    ld l, a
    adc h
    sub l
    ld h, a
    ld a, e
    add 32 - FT_REGION_W
    ld e, a
    adc d
    sub e
    ld d, a
    dec b
    jr nz, .dmgRow
    ret

; Copy the next few tiles of the wanted set (knockdown or attack) into video memory.
; Returns NZ if it did work this VBlank.
FtSwapStep:
    ld a, [wFtSwapWant]
    ld hl, wFtSwapHave
    cp [hl]
    ret z
    ld a, BANK(FtSwapSet0)      ; the swap tiles have a bank of their own
    ld [$2000], a
    call .step
    push af
    ld a, BANK(RivalMaps)
    ld [$2000], a
    pop af
    ret
.step:
    ld a, [wFtSwapWant]
    ld hl, FtSwapSet0
    and a
    jr z, .src
    ld hl, FtSwapSet1
    dec a
    jr z, .src
    ld hl, FtSwapSet2
.src:
    ld a, [wFtSwapPos]
    ld c, a
    ld b, 0
    REPT 4                  ; HL = source + pos * 16
        sla c
        rl b
    ENDR
    add hl, bc
    ; how many tiles this VBlank: the per-frame amount, no further than the end of the set or of this run
    ldh a, [hIsCGB]
    and a
    ld b, FT_SWAP_PER_FRAME_CGB
    jr nz, .limit
    ld b, FT_SWAP_PER_FRAME
.limit:
    ld a, [wFtSwapPos]
    ld c, a
    cp FT_SWAP_A_COUNT
    ld a, FT_SWAP_COUNT
    jr nc, .end
    ld a, FT_SWAP_A_COUNT
.end:
    sub c                   ; tiles left in this run
    cp b
    jr nc, .n
    ld b, a
.n:                         ; B = tiles to copy now
    ld a, c                 ; DE = destination of tile pos
    cp FT_SWAP_A_COUNT
    jr nc, .runB
    ld e, a
    ld d, 0
    REPT 4
        sla e
        rl d
    ENDR
    ld a, e
    add LOW(FT_SWAP_VRAM_A)
    ld e, a
    ld a, d
    adc HIGH(FT_SWAP_VRAM_A)
    ld d, a
    jr .copy
.runB:
    sub FT_SWAP_A_COUNT
    ld e, a
    ld d, 0
    REPT 4
        sla e
        rl d
    ENDR
    ld a, e
    add LOW(FT_SWAP_VRAM_B)
    ld e, a
    ld a, d
    adc HIGH(FT_SWAP_VRAM_B)
    ld d, a
.copy:
    ld a, [wFtSwapPos]
    add b
    ld [wFtSwapPos], a
    ldh a, [hIsCGB]
    and a
    jr z, .byCPU
    ld a, h                 ; Color: the whole run in one GDMA
    ldh [rHDMA1], a
    ld a, l
    ldh [rHDMA2], a
    ld a, d
    ldh [rHDMA3], a
    ld a, e
    ldh [rHDMA4], a
    ld a, b
    dec a
    ldh [rHDMA5], a
    jr .moved
.byCPU:
    REPT 16
        ld a, [hl+]
        ld [de], a
        inc de
    ENDR
    dec b
    jp nz, .byCPU
.moved:
    ld a, [wFtSwapPos]
    cp FT_SWAP_COUNT
    jr z, .done
    or 1                    ; NZ: worked
    ret
.done:
    xor a
    ld [wFtSwapPos], a
    ld a, [wFtSwapWant]
    ld [wFtSwapHave], a
    or 1
    ret

; ---- the frame ----

FightUpdate:
    call FtCrowd
IF DEF(FT_NES)
    call FtNesFrame         ; the whole fight, by the NES game's own logic
    ld a, [wFtMatch]
    cp M_END
    jp z, FtNesEnd
    jp FtFrame
ENDC
    ld a, [wFtFreeze]       ; hit stop
    and a
    jr z, .moving
    dec a
    ld [wFtFreeze], a
    jp FtFrame
.moving:
    ld a, [wFtMatch]
    and a
    jr z, .fight
    cp M_BREAK
    jp z, FtBreak
    cp M_RIVAL_DOWN
    jp z, FtRivalDown
    cp M_PLAYER_DOWN
    jp z, FtPlayerDown
    jp FtEndPause
.fight:
    call FtClock
    ld a, [wFtMatch]        ; the bell may have rung
    and a
    jp nz, FtFrame
    call FtPlayer
    ld a, [wFtMatch]
    and a
    jp nz, FtFrame
    call FtRival
    ; fall through
FtFrame:                    ; every frame: HUD values, sprites, shake
    ld a, [wFtHudDirty]
    and a
    jr z, .hudDone
    xor a
    ld [wFtHudDirty], a
    call FtHudCompute
    ld a, 1
    ldh [hFtHudReady], a
.hudDone:
    ld a, [wFtShake]
    and a
    jr z, .still
    dec a
    ld [wFtShake], a
    and 2
    ld a, 2
    jr nz, .shake
    ld a, -2
    jr .shake
.still:
    xor a
.shake:
    ldh [hFtScx], a
    call FtAnimate
    call FtSweatStep
    call FtReferee
    jp FtBuildOAM

; The referee walks in for the round's start, counts, and waves off a KO; otherwise he steps out.
FtReferee:
    ld b, RF_STAND
    ld c, 0                 ; saying nothing
    ld a, [wFtMatch]
    cp M_BREAK
    jr z, .fightCall
    cp M_RIVAL_DOWN
    jr z, .count
    cp M_PLAYER_DOWN
    jr z, .count
    cp M_END
    jr nz, .out
    ld a, [wFtCount]
    cp COUNT_KO
    jr nz, .out
    ld b, RF_WAVE
    ld c, SAY_KO
    jr .in
.fightCall:
    ld a, [wFtTimer]
    cp FT_INTRO - 20
    jr nc, .in              ; walking in first
    ld b, RF_COUNT
    ld c, SAY_FIGHT
    jr .in
.count:
    ld a, [wFtCount]
    and a
    jr z, .in
    cp COUNT_KO
    jr nz, .counting
    ld b, RF_WAVE
    ld c, SAY_KO
    jr .in
.counting:
    ld c, SAY_COUNT
    ld a, [wFtCountTimer]   ; arm up for a moment on each number
    cp FT_COUNT - 14
    jr c, .in
    ld b, RF_COUNT
.in:
    ld e, REF_IN
    jr .walk
.out:
    ld e, REF_OUT
.walk:
    ld a, b
    ld [wFtRefPose], a
    ld a, c
    ld [wFtSay], a
    ld a, [wFtRefX]         ; 2 pixels a frame toward where he's going
    cp e
    ret z
    jr c, .right
    sub 2
    jr .step
.right:
    add 2
.step:
    ld [wFtRefX], a
    ret

; The rival's motion as a pixel offset: B = x (right), C = y (down). Small, drawn from his state.
FtAnimate:
IF DEF(FT_NES)
    ld a, [wRvState]        ; standing: where his own script has put him
    cp RV_FALL
    jr nc, .scripted
    ld a, [wRvNesX]
    ld b, a
    ld a, [wRvNesY]         ; up as far as the HUD, down a little (his band moves with him)
    bit 7, a
    jr nz, .up
    cp FT_NES_DOWN_MAX + 1
    jr c, .y
    ld a, FT_NES_DOWN_MAX
    jr .y
.up:
    ld c, a                 ; standing, as far as his band rises (his head's at the top of the frame);
    ld a, [wRvPose]         ; down, his low poses can rise inside it too
    cp RP_KD_STAGGER
    jr c, .standing
    cp RP_KD_KNEEL + 1
    jr nc, .standing
    ld a, c
    cp -FT_NES_UP_MAX
    jr nc, .y
    ld a, -FT_NES_UP_MAX
    jr .y
.standing:
    ld a, c
    cp -FT_STAND_UP
    jr nc, .y
    ld a, -FT_STAND_UP
.y:
    ld c, a
    jp .done
.scripted:
ENDC
    ld bc, 0
    ld a, [wRvState]
    and a
    jp z, .idle
    cp RV_TELL
    jp z, .tell
    cp RV_STRIKE
    jp z, .strike
    cp RV_HIT
    jp z, .hit
    cp RV_OPEN
    jp z, .wobble
    cp RV_GETUP
    jp z, .wobble
    cp RV_TAUNT
    jp z, .taunt
    cp RV_CHARGE
    jp z, .shuffle
    cp RV_SLIP
    jp z, .slip
    cp RV_FALL
    jp z, .fall
    jp .done
.idle:                      ; breathing: down a pixel and back
    ldh a, [hFrame]
    and %00110000
    jp z, .done
    cp %00110000
    jp z, .done
    ld c, 1
    jp .done
.tell:                      ; the wind-up shakes; the hook's harder
    ld a, [wRvTimer]
    and 2
    ld b, 1
    jp z, .tellSide
    ld b, -1
.tellSide:
    ld a, [wRvAttack]
    and a
    jp z, .done
    sla b
    jp .done
.strike:                    ; lunging in
    ld a, [wRvTimer]
    cp FT_STRIKE - 5
    jr c, .done
    ld c, 2
    ld a, [wRvAttack]
    and a
    jp z, .done
    ld b, -3
    jp .done
.hit:                       ; knocked back, easing home
    ld a, [wRvTimer]
    srl a
    ld b, a
    ld a, [wRvPose]
    cp RP_HIT_L
    jp z, .left
    cp RP_HIT_R
    jp z, .done
    ld b, 0
    ld c, 2                 ; a body blow doubles him over a little
    jp .done
.left:
    xor a
    sub b
    ld b, a
    jp .done
.wobble:
    ldh a, [hFrame]
    rrca
    rrca
    and 7
    ld hl, Wobble
    add l
    ld l, a
    adc h
    sub l
    ld h, a
    ld b, [hl]
    jp .done
.taunt:                     ; a little hop
    ld a, [wRvTimer]
    and 8
    jp z, .done
    ld c, -2
    jp .done
.shuffle:
    ld a, [wRvTimer]
    and 4
    ld b, 2
    jp z, .done
    ld b, -2
    jp .done
.slip:                      ; slid out of the way
    ld b, 9
    jp .done
.fall:                      ; toppling sideways
    ld a, [wRvTimer]
    cpl
    add FT_FALL + 1
    srl a
    srl a
    ld b, a
    ld c, 2
.done:
    ldh a, [hFtScx]         ; scrolling right moves him left
    sub b
    ldh [hFtBandX], a
    xor a
    sub c
    ldh [hFtBandY], a
    ld a, FT_BAND_BOTTOM    ; the band goes with him: down, all of it; up, its top only as far as
    add c                   ; FT_HEADROOM, its end where the background below him takes over
    ldh [hFtBandBottom], a
    ld a, c
    bit 7, a
    jr z, .top
IF FT_HEADROOM == 0
    xor a
ELSE
    cp -FT_HEADROOM
    jr nc, .top
    ld a, -FT_HEADROOM
ENDC
.top:
    add FT_BAND_TOP
    ldh [hFtBandTop], a
    ret

Wobble:
    db 0, 1, 2, 1, 0, -1, -2, -1
IdleCycle:
    db RP_IDLE, RP_IDLE2, RP_IDLE3, RP_IDLE2

; ---- the clock ----

FtClock:
    ld hl, wFtSub
    inc [hl]
    ld a, [hl]
    cp FT_FRAMES_PER_SECOND
    ret c
    ld [hl], 0
    ld a, 1
    ld [wFtHudDirty], a
    ld a, [wFtSec]
    add 1
    daa
    ld [wFtSec], a
    call FtTimedMoves
    ld a, [wFtSec]
    cp $60
    ret c
    xor a
    ld [wFtSec], a
    ld hl, wFtMin
    inc [hl]
    ld a, [hl]
    cp FT_ROUND_MINUTES
    ret c
    ; the round is over
    ld a, SFX_BELL
    call PlaySfx
    ld a, [wFtRound]
    cp FT_ROUNDS
    jr nc, .decision
    inc a
    ld [wFtRound], a
    cp 3                    ; fresh hearts each round: fewer in the last
    ld a, FT_HEARTS
    jr c, .hearts
    ld a, FT_HEARTS_R3
.hearts:
    ld [wPlHearts], a
    xor a
    ld [wPlTired], a
    ld [wFtMin], a
    ld [wPlDowns], a
    ld [wRvDownsRound], a
    ld a, M_BREAK
    ld [wFtMatch], a
    ld a, FT_BREAK
    ld [wFtTimer], a
    ld hl, wPlHealth        ; both get some health back between rounds
    call .rest
    ld hl, wRvHealth
    call .rest
    call FtResetBoxers
    IF FT_CORNER_SCENE != $FF
        ld a, 1             ; to the corner; the fight picks up where it was after
        ld [wFtResume], a
        ld a, FT_CORNER_SCENE
        jp FtFinish
    ENDC
    ret
.rest:
    ld a, [hl]
    add FT_HEALTH / 3
    cp FT_HEALTH
    jr c, .restOk
    ld a, FT_HEALTH
.restOk:
    ld [hl], a
    ret
.decision:                  ; after the last round: a win on points needs 5000
    ld a, [wFtPoints]
    and a
    jr nz, .won
    ld a, [wFtPoints + 1]
    cp FT_DECISION_POINTS_BCD
    ld a, FT_LOSE_SCENE
    jr c, .lost
.won:
    ld a, FT_WIN_SCENE
.lost:
    jp FtFinish

; ---- the corner, between rounds ----

; Select in the corner: the trainer works faster, and some health comes back (once per match).
FtCornerSelect:
    ld a, [wFtSelectUsed]
    and a
    ret nz
    inc a
    ld [wFtSelectUsed], a
    ld a, [wFtRound]        ; the odds get better in the last round
    cp 3
    ld hl, CornerRefill2
    jr c, .odds
    ld hl, CornerRefill3
.odds:
    ldh a, [hFrame]         ; a roll of 0-7
    ld b, a
    ld a, [wFtRand]
    xor b
    and 7
    add l
    ld l, a
    adc h
    sub l
    ld h, a
    ld a, [wPlHealth]
    add [hl]
    jr c, .full
    cp FT_HEALTH + 1
    jr c, .set
.full:
    ld a, FT_HEALTH
.set:
    ld [wPlHealth], a
    ld a, SFX_STAR_GET
    jp PlaySfx

CornerRefill2:              ; eighths: 1 x 8, 2 x 16, 4 x 32, 1 x 64
    db 8, 16, 16, 32, 32, 32, 32, 64
CornerRefill3:              ; 1 x 8, 2 x 16, 2 x 32, 3 x 64
    db 8, 16, 16, 32, 32, 64, 64, 64

; Clock-timed moves: (round, minute, BCD second, op, argument) in time order, ending with $FF.
FtTimedMoves:
    ld a, [wRvTimed]
    ld l, a
    ld a, [wRvTimed + 1]
    ld h, a
    ld a, [wFtRound]
    cp [hl]
    ret nz
    inc hl
    ld a, [wFtMin]
    cp [hl]
    ret nz
    inc hl
    ld a, [wFtSec]
    cp [hl]
    ret nz
    inc hl
    ld a, [hl+]
    inc a
    ld [wRvPending], a
    ld a, [hl+]
    ld [wRvPendingArg], a
    ld a, l
    ld [wRvTimed], a
    ld a, h
    ld [wRvTimed + 1], a
    ret

FtResetBoxers:              ; both back to neutral
    xor a
    ld [wFtSwapWant], a
    ld [wPlState], a
    ld [wPlX], a
    ld [wPlPose], a
    ld [wPlFlip], a
    ld a, 30
    ld [wRvTimer], a
    jp FtStand

FtBreak:
    ld hl, wFtTimer
    dec [hl]
    jp nz, FtFrame
    xor a
    ld [wFtMatch], a
    ld a, SFX_BELL
    call PlaySfx
    jp FtFrame

; ---- the player ----

FtPlayer:
    ld a, [wPlTired]
    and a
    jr z, .rested
    dec a
    ld [wPlTired], a
    jr nz, .rested
    ld a, [wPlHitTired]
    and a
    ld a, FT_HEARTS_RESTED
    jr z, .notHit
    ld a, FT_HEARTS_RESTED_HIT
.notHit:
    ld b, a
    ld a, [wFtRound]
    cp 3
    ld a, b
    jr c, .r12
    sub FT_HEARTS_R3_LESS
.r12:
    ld [wPlHearts], a
    xor a
    ld [wPlHitTired], a
    ld a, 1
    ld [wFtHudDirty], a
.rested:
    ld a, [wPlState]
    and a
    jr z, PlIdle
    cp PL_PUNCH
    jp z, PlPunch
    cp PL_DODGE
    jp z, PlDodge
    cp PL_BLOCK
    jp z, PlBlock
    cp PL_HIT
    jp z, PlHit
    jp PlStar

PlIdle:
    ld a, [wPlX]            ; drift back to center after stepping aside
    and a
    jr z, .centered
    add 2
    ld [wPlX], a
.centered:
    xor a
    ld [wPlPose], a
    ld [wPlFlip], a
    ldh a, [hPadNew]
    ld b, a
    bit PAD_LEFT, b
    ld c, 0
    jr nz, .dodge
    bit PAD_RIGHT, b
    ld c, 1
    jr nz, .dodge
    ldh a, [hPad]
    bit PAD_DOWN, a
    jr nz, .block
    ld a, [wPlTired]        ; too tired to punch
    and a
    ret nz
    bit PAD_START, b
    jr nz, .star
    bit PAD_A, b
    ld c, 1
    jr nz, .punch
    bit PAD_B, b
    ld c, 0
    ret z
.punch:
    xor a
    ld [wPlWhiff], a
    ld a, c
    and a
    jr z, .thrown           ; lefts never get slipped
    ld a, [wRvState]
    and a                   ; only from his standing guard, with his attack poses in
    jr nz, .thrown
    ld a, [wFtSwapHave]
    and a
    jr nz, .thrown
    ld hl, wRvRights
    inc [hl]
    ld a, [hl]
    cp 3
    jr c, .thrown
    ld [hl], 0
    ld a, 1
    ld [wPlWhiff], a
    ld a, RV_SLIP
    ld [wRvState], a
    ld a, RP_SLIP
    ld [wRvPose], a
    ld a, FT_SLIP
    ld [wRvTimer], a
.thrown:
    ld a, c
    ld [wPlSide], a
    ldh a, [hPad]
    and PADF_UP
    ld [wPlHigh], a

    ld a, PL_PUNCH
    ld [wPlState], a
    ld a, FT_PUNCH
    ld [wPlTimer], a
    ld a, SFX_PUNCH
    jp PlaySfx
.dodge:
    ld a, c
    ld [wPlSide], a
    ld a, PL_DODGE
    ld [wPlState], a
    ld a, FT_DODGE
    ld [wPlTimer], a
    ld a, SFX_DODGE
    jp PlaySfx
.block:
    ld a, PL_BLOCK
    ld [wPlState], a
    ret
.star:
    ld a, [wPlStars]
    and a
    ret z
    dec a
    ld [wPlStars], a
    xor a
    ld [wPlWhiff], a
    ld hl, wPlStarsUsed     ; he's seen enough of them: the 8th gets slipped and countered
    inc [hl]
    ld a, [hl]
    cp FT_STAR_DODGE
    jr c, .starThrown
    ld [hl], 0
    ld a, [wRvState]
    and a
    jr nz, .starThrown
    ld a, 1
    ld [wPlWhiff], a
    ld a, RV_SLIP
    ld [wRvState], a
    ld a, RP_SLIP
    ld [wRvPose], a
    ld a, FT_SLIP
    ld [wRvTimer], a
.starThrown:
    ld a, 1
    ld [wFtHudDirty], a
    ld a, PL_STAR
    ld [wPlState], a
    ld a, FT_STAR
    ld [wPlTimer], a
    ld a, SFX_STAR_WIND
    jp PlaySfx

PlDodge:
    ld a, PP_DODGE
    ld [wPlPose], a
    ld a, [wPlSide]
    ld [wPlFlip], a
    ld hl, wPlTimer
    dec [hl]
    jp z, PlToIdle
    ld a, [hl]              ; slide out, hold, slide back: 4 pixels a frame each way
    cp FT_DODGE / 2
    jr c, .back
    cpl
    add FT_DODGE + 1        ; frames so far
.back:
    add a
    add a
    cp FT_DODGE_X
    jr c, .x
    ld a, FT_DODGE_X
.x:
    ld b, a
    ld a, [wPlSide]
    and a
    ld a, b
    jr nz, .right
    cpl
    inc a
.right:
    ld [wPlX], a
    ret

PlBlock:
    ld a, PP_BLOCK
    ld [wPlPose], a
    ldh a, [hPad]
    bit PAD_DOWN, a
    ret nz
    jp PlToIdle

PlPunch:
    ld a, [wPlHigh]
    and a
    ld a, PP_JAB
    jr z, .low
    ld a, PP_JAB_HIGH
.low:
    ld [wPlPose], a
    ld a, [wPlSide]
    ld [wPlFlip], a
    ld hl, wPlTimer
    dec [hl]
    jp z, PlToIdle
    ld a, [hl]
    cp FT_PUNCH_ACTIVE
    ret nz
    jp FtLandPunch

PlHit:
    ld a, PP_HIT
    ld [wPlPose], a
    ld hl, wPlTimer
    dec [hl]
    ret nz
    jp PlToIdle

PlStar:
    xor a
    ld [wPlFlip], a
    ld hl, wPlTimer
    dec [hl]
    jr z, PlToIdle
    ld a, [hl]
    cp FT_STAR_ACTIVE
    ld a, PP_BLOCK          ; winding up
    jr nc, .pose
    ld a, PP_STAR
.pose:
    ld [wPlPose], a
    ld a, [hl]
    cp FT_STAR_ACTIVE
    ret nz
    jp FtLandStar

PlToIdle:
    xor a
    ld [wPlState], a
    ld [wPlPose], a
    ld [wPlX], a
    ret

; Does the player evade right now? Carry set if so.
FtEvading:
    ld a, [wPlState]
    cp PL_DODGE
    jr nz, .no
    ld a, [wPlTimer]
    cp FT_EVADE_TO
    jr c, .no
    cp FT_EVADE_FROM + 1
    ret                     ; carry = timer <= EVADE_FROM
.no:
    and a
    ret

; ---- punches landing ----

; The impact burst where the glove lands: on his face or his body, on the punching side.
FtSpark:
    ld a, [wPlHigh]
    and a
    ld a, FT_STAR_Y + 12
    jr nz, .y
    ld a, FT_STAR_Y + 36
.y:
    ld [wFtSparkY], a
    ld a, [wPlSide]
    and a
    ld a, FT_STAR_X - 10
    jr z, .x
    ld a, FT_STAR_X + 4
.x:
    ld [wFtSparkX], a
    ld a, 6
    ld [wFtSparkT], a
    ret

; Sweat flies off his head: three beads, thrown up and out.
FtSweat:
    ld hl, wFtSweat
    ld de, SweatStart
    ld b, 3 * 4
.copy:
    ld a, [de]
    inc de
    ld [hl+], a
    dec b
    jr nz, .copy
    ld a, 16
    ld [wFtSweatT], a
    ret

SweatStart:                 ; x, y (OAM, from his mouth), x speed, y speed: spray as his head snaps back
    db FT_STAR_X - 4, FT_STAR_Y + 18, -3, -2
    db FT_STAR_X, FT_STAR_Y + 16, -1, -4
    db FT_STAR_X + 4, FT_STAR_Y + 18, 2, -3

; Move the beads; gravity every other frame.
FtSweatStep:
    ld a, [wFtSweatT]
    and a
    ret z
    dec a
    ld [wFtSweatT], a
    ld hl, wFtSweat
    ld c, 3
.bead:
    ld a, [hl+]             ; x += vx
    ld b, a
    inc hl
    ld a, [hl]
    add b
    dec hl
    dec hl
    ld [hl+], a
    ld a, [hl+]             ; y += vy
    ld b, a
    inc hl
    ld a, [hl]              ; vy
    add b
    dec hl
    dec hl
    ld [hl+], a
    inc hl
    ld a, [wFtSweatT]
    and 1
    jr z, .noGravity
    inc [hl]
.noGravity:
    inc hl
    dec c
    jr nz, .bead
    ret

; Hold still for at least A frames.
FtHitStop:
    ld hl, wFtFreeze
    cp [hl]
    ret c
    ld [hl], a
    ret

; Keep the crowd's cameras flashing for at least A frames.
FtExcite:
    ld hl, wFtExcite
    cp [hl]
    ret c
    ld [hl], a
    ret

FtLandStar:
    ld a, [wPlWhiff]        ; slipped
    and a
    ret nz
    ld a, [wRvState]
    cp RV_STRIKE
    ret z
    cp RV_TAUNT             ; backed off: out of reach
    ret z
    cp RV_FALL
    jr c, .reach
    cp RV_CHARGE
    ret nz
.reach:
    ld a, SFX_STAR_PUNCH
    call PlaySfx
    ld bc, $0100            ; 100 points
    call FtAddPoints
    ld a, 10
    ld [wFtShake], a
    ld a, FT_HITSTOP * 2
    call FtHitStop
    ld a, 60
    call FtExcite
    ld b, FT_DMG_STAR       ; damage: 18 standing, 17 into a hook, 15 into a jab, 23 when he's stunned
    ld a, [wRvState]
    cp RV_TELL
    jr nz, .notTell
    ld a, [wRvAttack]
    and a
    ld b, FT_DMG_STAR_JAB
    jr z, .damage
    ld b, FT_DMG_STAR_HOOK
    jr .damage
.notTell:
    cp RV_OPEN
    jr z, .stunned
    cp RV_HIT
    jr nz, .damage
.stunned:
    ld b, FT_DMG_STAR_STUNNED
.damage:
    ld a, 1
    ld [wRvStarKD], a
    ld a, RP_HIT_BODY
    call FtRivalHurt
    xor a
    ld [wRvStarKD], a
    ld a, [wRvState]
    cp RV_HIT
    ret nz                  ; down
    ld a, RV_POP            ; still up: the punch popped his arm out
    ld [wRvState], a
    ld a, FT_POP
    ld [wRvTimer], a
    ld a, SET_SPECIAL
    ld [wFtSwapWant], a
    ld a, SFX_POP
    jp PlaySfx

FtLandPunch:
    ld a, [wPlWhiff]        ; he slipped it
    and a
    ret nz
    ld a, [wRvState]
    cp RV_IDLE
    jr z, .guarded
    cp RV_STRIKE
    jr z, .blocked
    cp RV_TAUNT
    ret z                   ; backed off to taunt: out of reach
    cp RV_CHARGE
    jr z, .charge
    cp RV_FALL
    ret nc                  ; down or getting up: nothing to hit
    cp RV_TELL
    jr nz, .open            ; open after a miss, or still reeling: lands
    ld a, [wRvAttack]       ; the wind-ups can be interrupted, each by its own punch
    and a
    jr nz, .hookTell
    ld a, [wPlHigh]         ; the jab: by a punch to the gut
    and a
    jp nz, .blocked
    jr .lands
.hookTell:                  ; the hook: by a left to the face, which earns a star
    ld a, [wPlSide]
    and a
    jp nz, .blocked
    ld a, [wPlHigh]
    and a
    jp z, .blocked
    call FtGainStar
    jr .lands
.open:
    cp RV_OPEN
    jr nz, .lands
    ld a, [wRvOpenHits]     ; out of counters: he's covered up
    and a
    jp z, .blocked
.charge:                    ; caught shuffling back in: down he goes; caught early, he stays down
    ld a, [wRvTimer]
    cp FT_CHARGE - FT_CHARGE_KO + 1
    jr c, .knockdown
    ld a, 1
    ld [wRvNoGetup], a
.knockdown:
    ld a, SFX_STAR_PUNCH
    call PlaySfx
    ld a, 12
    ld [wFtShake], a
    ld a, RP_HIT_BODY
    ld b, 255
    jp FtRivalHurt
.guarded:                   ; covering the body (gloves low) or the face (gloves high)
    ld a, [wRvGuard]
    ld b, a
    ld a, [wPlHigh]
    and a
    jr z, .low
    ld a, 1
.low:
    cp b
    jr nz, .lands
.blocked:
    ld a, SFX_BLOCK
    call PlaySfx
    call FtSpark            ; the glove meets his glove: a flash
    ld hl, wPlHearts
    ld a, [hl]
    and a
    jr z, .tired
    dec [hl]
    ld a, 1
    ld [wFtHudDirty], a
    ret nz
.tired:
    ld a, FT_TIRED
    ld [wPlTired], a
    ret
.lands:
    ld a, SFX_HIT
    call PlaySfx
    ld a, 3
    ld [wFtShake], a
    ld hl, wPlPunches       ; the 20th landed punch earns a star, then every 8th
    inc [hl]
    ld a, [wPlStarsEarned]
    and a
    ld a, FT_FIRST_STAR
    jr z, .threshold
    ld a, FT_NEXT_STAR
.threshold:
    cp [hl]
    jr nz, .noStar
    ld [hl], 0
    ld a, 1
    ld [wPlStarsEarned], a
    call FtGainStar
.noStar:
    ld a, [wRvState]        ; a counter punch while holding a star: a coin flip for another
    cp RV_OPEN
    jr nz, .notLucky
    ld a, [wPlStars]
    and a
    jr z, .notLucky
    ld a, [wFtRand]
    and $10
    call nz, FtGainStar
.notLucky:
    ld a, [wRvState]        ; counters use up his opening
    cp RV_OPEN
    jr z, .counter
    cp RV_HIT
    jr nz, .notCounter
.counter:
    ld a, [wRvOpenHits]
    and a
    jr z, .notCounter
    dec a
    ld [wRvOpenHits], a
.notCounter:
    ld hl, wRvLanded        ; three clean hits and he switches his guard
    inc [hl]
    ld a, [hl]
    cp 3
    jr c, .sameGuard
    ld [hl], 0
    ld a, [wRvGuard]
    xor 1
    ld [wRvGuard], a
.sameGuard:
    call FtSpark
    ld a, [wPlHigh]
    and a
    jr z, .body
    call FtSweat
    ld bc, $0020
    call FtAddPoints
    ld a, RP_HIT_BACK       ; his head thrown back first, then turned away (see FtRival)
    ld b, FT_DMG_HEAD
    jr FtRivalHurt
.body:
    ld bc, $0010
    call FtAddPoints
    ld a, RP_HIT_BODY
    ld b, FT_DMG_BODY
    ; fall through
; A = pose to show, B = damage
FtRivalHurt:
    ld [wRvPose], a
    xor a                   ; attack poses back (a knockdown asks for its own set below)
    ld [wFtSwapWant], a
    ld a, 4
    ldh [hFtFlash], a
    ld a, FT_HITSTOP
    call FtHitStop
    ld a, RV_HIT
    ld [wRvState], a
    ld a, FT_RIVAL_HIT
    ld [wRvTimer], a
FtRivalDamage:              ; B = damage: health, and a knockdown when it runs out
    ld a, 1
    ld [wFtHudDirty], a
    ld a, [wRvHealth]
    sub b
    jr nc, .alive
    xor a
.alive:
    ld [wRvHealth], a
    and a
    ret nz
    ; knocked down
    ld hl, wRvDownsRound
    inc [hl]
    ld a, FT_HITSTOP * 3
    call FtHitStop
    ld a, 150
    call FtExcite
    ld hl, wRvDowns
    inc [hl]
    ld a, SFX_KNOCKDOWN
    call PlaySfx
    ld bc, $0500
    call FtAddPoints
    ld a, 12
    ld [wFtShake], a
    ld a, RV_FALL
    ld [wRvState], a
IF DEF(FT_NES)
    xor a                   ; his own script waits while he's down (FtNesRival brings him back)
    ld [wNes + nOppCurState], a
    ld [wNes + nOppPunchSts], a
ENDC
    ld a, RP_HIT_BODY       ; until the knockdown set is in
    ld [wRvPose], a
    ld a, 1
    ld [wFtSwapWant], a
    ld a, FT_FALL
    ld [wRvTimer], a
    ld a, M_RIVAL_DOWN
    ld [wFtMatch], a
    xor a
    ld [wFtCount], a
    ld a, FT_COUNT
    ld [wFtCountTimer], a
    call FtPlanGetup
    jp PlToIdle

; When (and with how much health) he gets up from this knockdown. wRvGetupAt = 0: he stays down.
FtPlanGetup:
    xor a
    ld [wRvGetupAt], a
    ld a, [wRvNoGetup]      ; caught on the charge
    and a
    ret nz
    ld a, [wRvDownsRound]   ; three in a round is a TKO
    cp 3
    ret nc
    ld a, [wRvDowns]        ; the 6th is a KO
    cp 6
    ret nc
    dec a
    ld e, a
    ld d, 0
    ld hl, GetupPlan
    add hl, de
    add hl, de
    ld a, [hl+]
    ld [wRvGetupAt], a
    ld a, [hl]
    ld [wRvGetupHP], a
    ld a, e                 ; the conditions for springing up at 1 with full health
    and a
    jr nz, .second
    ld a, [wFtMin]          ; 1st: the player untouched, under a minute gone
    and a
    ret nz
    jr .fullPlayer
.second:
    cp 1
    jr nz, .later
.fullPlayer:                ; 2nd: the player untouched
    ld a, [wPlHealth]
    cp FT_HEALTH
    ret nz
    jr .springsUp
.later:                     ; 3rd on: a star punch put him down
    ld a, [wRvStarKD]
    and a
    jr nz, .springsUp
    ld a, e
    cp 4                    ; the 5th, otherwise: a coin flip whether he gets up at all
    ret nz
    ld a, [wFtRand]
    and $20
    ret z
    xor a
    ld [wRvGetupAt], a
    ret
.springsUp:
    ld a, 1
    ld [wRvGetupAt], a
    ld a, FT_HEALTH
    ld [wRvGetupHP], a
    ret

FtGainStar:
    ld a, [wPlStars]
    cp 3
    ret nc
    inc a
    ld [wPlStars], a
    ld a, 1
    ld [wFtHudDirty], a
    ld a, SFX_STAR_GET
    jp PlaySfx

; BC = BCD points to add
FtAddPoints:
    ld hl, wFtPoints + 2
    ld a, [hl]
    add c
    daa
    ld [hl-], a
    ld a, [hl]
    adc b
    daa
    ld [hl-], a
    ld a, [hl]
    adc 0
    daa
    ld [hl], a
    ld a, 1
    ld [wFtHudDirty], a
    ret

; ---- the rival ----

FtRival:
    ld a, [wRvState]
    cp RV_TELL
    jp z, RvTell
    cp RV_STRIKE
    jp z, RvStrike
    cp RV_TAUNT
    jp z, RvTaunt
    cp RV_CHARGE
    jp z, RvCharge
    cp RV_POP
    jp z, RvPop
    cp RV_SLIP
    jp z, RvSlip
    and a                   ; standing guard: a timed move goes first
    jr nz, .wait
    call FtStandPose
    ld a, [wRvPending]
    and a
    jr z, .wait
    dec a
    ld b, a
    xor a
    ld [wRvPending], a
    ld a, [wRvPendingArg]
    ld c, a
    jp FtStartOp
.wait:                      ; guarding, open, reeling, getting up: wait, then the next step of the script
    ld hl, wRvTimer
    ld a, [wRvPose]         ; a head hit: after the snap back, the head turns away
    cp RP_HIT_BACK
    jr nz, .notSnap
    ld a, [hl]
    cp FT_RIVAL_HIT - 6
    jr nz, .notSnap
    ld a, [wPlSide]
    add RP_HIT_L
    ld [wRvPose], a
.notSnap:
    dec [hl]
    ld a, [wRvState]
    cp RV_GETUP
    jr nz, .notRising
    ld a, [hl]
    cp FT_GETUP / 2         ; on his feet, wobbly; the attack poses' tiles go back in
    jr nz, .notRising
    ld a, RP_DAZED
    ld [wRvPose], a
    xor a
    ld [wFtSwapWant], a
.notRising:
    ld a, [hl]
    and a
    ret nz
    ld a, [wFtSwapHave]     ; can't swing until his attack tiles are back
    and a
    jr z, .ready
    inc [hl]
    ret
.ready:
    ld a, [wRvState]
    cp RV_HIT               ; done reeling: back on guard, and the script picks up where it was
    jp nz, FtNextOp
    ld a, [wRvOpenHits]     ; still open for more counters
    and a
    jr z, .cover
    ld a, RV_OPEN
    ld [wRvState], a
    ld a, RP_DAZED
    ld [wRvPose], a
    ld [hl], FT_OPEN
    ret
.cover:
    ld [hl], FT_RECOVER
    jp FtStand

RvTaunt:                    ; backed off, taunting; then he shuffles back in
    ld a, [wFtSwapHave]     ; the taunt's tiles are on their way in
    cp SET_SPECIAL
    ret nz
    ld a, RP_TAUNT
    ld [wRvPose], a
    ld hl, wRvTimer
    ld a, [hl]
    and a
    jr z, .count
.yap:                       ; each taunt has its sound
    ld b, a
.mod:
    sub FT_YAP
    jr z, .sound
    jr nc, .mod
    jr .count
.sound:
    ld a, SFX_TAUNT
    call PlaySfx
    ld hl, wRvTimer
.count:
    dec [hl]
    ret nz
    ld a, RV_CHARGE
    ld [wRvState], a
    ld a, FT_CHARGE
    ld [hl], a
    xor a
    ld [wRvPose], a
    ld [wFtSwapWant], a     ; and the attack poses back for the hook
    ret

; Arm popped out: he holds it, snaps it back with a click, and gets on with it.
RvPop:
    ld a, [wFtSwapHave]
    cp SET_SPECIAL
    ret nz
    ld hl, wRvTimer
    ld a, [hl]
    cp FT_POP
    jr nz, .held
    ld a, RP_ARM_POP
    ld [wRvPose], a
.held:
    dec [hl]
    ld a, [hl]
    cp 14
    jr nz, .notYet
    ld a, SFX_CLICK
    call PlaySfx
    xor a
    ld [wFtSwapWant], a
    call FtStand
    ld a, RV_POP
    ld [wRvState], a
    ld hl, wRvTimer
.notYet:
    ld a, [hl]
    and a
    ret nz
    inc [hl]                ; until the attack poses are back
    ld a, [wFtSwapHave]
    and a
    ret nz
    jp FtNextOp

RvSlip:                     ; out of the way of the right hand, then the counter: a quick hook
    ld hl, wRvTimer
    dec [hl]
    ret nz
    ld a, 1
    ld [wRvAttack], a
    ld a, FT_COUNTER_TELL
    ld [hl], a
    ld a, RV_TELL
    ld [wRvState], a
    ld a, RP_HOOK_TELL
    ld [wRvPose], a
    ld a, SFX_TELL
    jp PlaySfx

RvCharge:                   ; back in range, and straight into a hook
    ld hl, wRvTimer
    dec [hl]
    ret nz
    ld a, [wFtSwapHave]     ; the hook's tiles must be back first
    and a
    jr z, .ready
    inc [hl]
    ret
.ready:
    ld a, 1
    ld [wRvAttack], a
    ld a, FT_CHARGE_TELL
    ld [hl], a
    ld a, RV_TELL
    ld [wRvState], a
    ld a, RP_HOOK_TELL
    ld [wRvPose], a
    ld a, SFX_TELL
    jp PlaySfx

RvTell:
    ld hl, wRvTimer
    dec [hl]
    ret nz
    ld a, RV_STRIKE
    ld [wRvState], a
    ld a, FT_STRIKE
    ld [hl], a
    ld a, [wRvAttack]       ; the glove on its way out first
    and a
    ld a, RP_JAB_MID
    jr z, .jab
    ld a, RP_HOOK_MID
.jab:
    ld [wRvPose], a
    ld a, SFX_RIVAL_SWING
    jp PlaySfx

RvStrike:
    ld hl, wRvTimer
    dec [hl]
    jr z, .done
    ld a, [hl]
    cp FT_STRIKE - 2        ; full extension
    jr nz, .extended
    ld a, [wRvAttack]
    and a
    ld a, RP_JAB
    jr z, .full
    ld a, RP_HOOK
.full:
    ld [wRvPose], a
    ld a, [hl]
.extended:
    cp FT_STRIKE - 3        ; the glove arrives
    ret nz
    call FtEvading
    jr c, .whiff
    ld a, [wPlState]
    cp PL_BLOCK
    jr z, .blocked
    cp PL_DOWN
    ret z
    ld a, [wRvAttack]       ; the player is hit
    and a
    ld b, FT_DMG_JAB
    jr z, .hurt
    ld b, FT_DMG_HOOK
.hurt:
    jp FtPlayerHurt
.blocked:
    ld a, SFX_BLOCK
    call PlaySfx
    ld a, FT_OPEN_AFTER_BLOCK   ; blocked: he's left open for 4 counters
    ld [wRvOpenHits], a
    call FtRivalOpen
    ld a, [wRvAttack]
    and a
    ret z                   ; a blocked jab does no harm
    ld b, FT_DMG_HOOK_BLOCKED
    ld a, [wPlHealth]
    sub b
    jr nc, .ok
    xor a
.ok:
    and a
    jr nz, .chip
    inc a                   ; blocking never knocks you down
.chip:
    ld [wPlHealth], a
    ld a, 1
    ld [wFtHudDirty], a
    ret
.whiff:                     ; missed: off balance and open, for 6 counters after a hook, 4 after a jab
    ld a, [wRvAttack]
    and a
    ld a, FT_OPEN_AFTER_JAB
    jr z, .opened
    ld a, FT_OPEN_AFTER_HOOK
.opened:
    ld [wRvOpenHits], a
    jp FtRivalOpen
.done:
    ld a, 24
    ld [hl], a
    jp FtStand

; Off balance: open for counter punches (wRvOpenHits of them).
FtRivalOpen:
    ld a, RV_OPEN
    ld [wRvState], a
    ld a, RP_DAZED
    ld [wRvPose], a
    ld a, FT_OPEN
    ld [wRvTimer], a
    ret

; Start the next step of the rival's script.
FtNextOp:
    ld a, [wFtSwapHave]     ; only with the attack poses in video memory
    and a
    jr z, .go
    xor a
    ld [wFtSwapWant], a
    ld a, 4
    ld [wRvTimer], a
    jp FtStand
.go:
    ld a, [wRvScript]
    ld l, a
    ld a, [wRvScript + 1]
    ld h, a
    ld a, [hl]
    cp $FF                  ; the end: back to the loop (the opening moves play once)
    jr nz, .op
    ld hl, RivalLoop
    ld a, [hl]
.op:
    inc hl
    ld c, [hl]              ; argument
    inc hl
    ld b, a
    ld a, l
    ld [wRvScript], a
    ld a, h
    ld [wRvScript + 1], a
FtStartOp:                  ; B = op, C = argument
    ld a, c
    ld [wRvTimer], a
    ld a, b
    and a
    jr z, FtStand
    cp OP_GUARD
    jr z, .guard
    cp OP_TAUNT
    jr z, .taunt
    ; jab or hook: the tell, shorter in later rounds
    sub OP_JAB
    ld [wRvAttack], a
    and a
    ld a, FT_JAB_TELL + 4
    jr z, .tell
    ld a, FT_HOOK_TELL + 4
.tell:
    ld hl, wFtRound
    ld b, [hl]
.faster:
    sub 4
    dec b
    jr nz, .faster
    ld [wRvTimer], a
    ld a, RV_TELL
    ld [wRvState], a
    ld a, [wRvAttack]
    and a
    ld a, RP_JAB_TELL
    jr z, .tellPose
    ld a, RP_HOOK_TELL
.tellPose:
    ld [wRvPose], a
    ld a, SFX_TELL
    jp PlaySfx
.guard:                     ; switch guard, then stand
    ld a, [wRvGuard]
    xor 1
    ld [wRvGuard], a
    xor a
    ld [wRvLanded], a
    jr FtStand
.taunt:
    ld a, SET_SPECIAL       ; the taunt shows once its tiles are in
    ld [wFtSwapWant], a
    call FtStand
    ld a, RV_TAUNT
    ld [wRvState], a
    ld a, [wFtRand]         ; he taunts 2 or 4 times
    and $08
    ld a, FT_YAP * 2
    jr z, .yaps
    ld a, FT_YAP * 4
.yaps:
    ld [wRvTimer], a
    ret

FtStand:                    ; standing guard: gloves low cover the body, gloves high the face
    ld a, RV_IDLE
    ld [wRvState], a
    ; fall through
FtStandPose:                ; idle (bouncing) or guard; plain idle while another pose set is loaded
    ld a, [wFtSwapHave]
    and a
    ld a, RP_IDLE
    jr nz, .pose
    ld a, [wRvGuard]
    and a
    ld a, RP_GUARD
    jr nz, .pose
    push hl                 ; breathing and bouncing: idle, idle2, idle3, idle2, 16 frames each
    ldh a, [hFrame]
    swap a
    and 3
    add LOW(IdleCycle)
    ld l, a
    adc HIGH(IdleCycle)
    sub l
    ld h, a
    ld a, [hl]
    pop hl
.pose:
    ld [wRvPose], a
    ret

; B = damage to the player
FtPlayerHurt:
    ld a, SFX_PLAYER_HIT
    call PlaySfx
    ld a, FT_HITSTOP
    call FtHitStop
    ld a, 6
    ld [wFtShake], a
    xor a                   ; getting hit costs your stars
    ld [wPlStars], a
    ld [wPlX], a
    ld a, [wPlTired]        ; hit while worn out: fewer hearts come back
    and a
    jr z, .fresh
    ld a, 1
    ld [wPlHitTired], a
.fresh:
    ld a, [wPlHearts]
    sub FT_HEARTS_HIT
    jr nc, .hearts
    xor a
.hearts:
    ld [wPlHearts], a
    and a
    jr nz, .notTired
    ld a, FT_TIRED
    ld [wPlTired], a
.notTired:
    ld a, 1
    ld [wFtHudDirty], a
    ld a, PL_HIT
    ld [wPlState], a
    ld a, FT_PLAYER_HIT
    ld [wPlTimer], a
    ld a, [wPlHealth]
    sub b
    jr nc, .alive
    xor a
.alive:
    ld [wPlHealth], a
    and a
    ret nz
    ; knocked down
    ld hl, wPlDowns
    inc [hl]
    ld hl, wPlDownsAll
    inc [hl]
    ld a, SFX_KNOCKDOWN
    call PlaySfx
    ld a, PL_DOWN
    ld [wPlState], a
    ld a, PP_DOWN
    ld [wPlPose], a
    xor a
    ld [wPlFlip], a
    ld [wPlMash], a
    ld [wFtCount], a
    ld a, FT_COUNT
    ld [wFtCountTimer], a
    ld a, RV_CHEER
    ld [wRvState], a
    ld a, SET_SPECIAL       ; he celebrates once the taunt's tiles are in (see FtCheer)
    ld [wFtSwapWant], a
    ld a, M_PLAYER_DOWN
    ld [wFtMatch], a
    ld a, [wPlDowns]
    cp 3
    ret c
    ld a, FT_LOSE_SCENE     ; three knockdowns in a round
    jp FtFinish

; ---- knockdowns ----

; The referee counts; A = new count. Returns Z when it reaches 10.
FtCountTick:
    ld hl, wFtCountTimer
    dec [hl]
    ret nz
    ld a, FT_COUNT
    ld [hl], a
    ld hl, wFtCount
    inc [hl]
    ld a, SFX_COUNT
    call PlaySfx
    ld a, [wFtCount]
    cp 10
    ret

FtRivalDown:
    ld a, [wPlX]            ; step aside so the fall is in plain view
    cp -FT_ASIDE
    jr z, .aside
    sub 2
    ld [wPlX], a
.aside:
    ld a, [wRvState]
    cp RV_FALL
    jr nz, .counting
    ld a, [wFtSwapHave]     ; the knockdown set is still on its way into video memory
    and a
    jp z, FtFrame
    ld hl, wRvTimer
    dec [hl]
    jr z, .landed
    ld a, [hl]
    cp FT_FALL / 2
    ld a, RP_KD_STAGGER     ; knees buckling...
    jr nc, .falling
    ld a, RP_KD_FALL        ; ...going over
.falling:
    ld [wRvPose], a
    jp FtFrame
.landed:
    ld a, RV_DOWN
    ld [wRvState], a
    ld a, RP_KD_DOWN
    ld [wRvPose], a
    ld a, 6
    ld [wFtShake], a
    jp FtFrame
.counting:
    call FtCountTick
    jr z, .ko
    ld a, [wRvGetupAt]      ; gets up at the planned count (0: stays down)
    and a
    jp z, FtFrame
    ld b, a
    ld a, [wFtCount]
    cp b
    jp nz, FtFrame
    ld a, [wRvGetupHP]
    ld [wRvHealth], a
    xor a
    ld [wFtCount], a
    ld [wFtMatch], a
    ld a, RV_GETUP
    ld [wRvState], a
    ld a, RP_KD_KNEEL       ; up on one knee first
    ld [wRvPose], a
    ld a, FT_GETUP
    ld [wRvTimer], a
    ld a, 1
    ld [wFtHudDirty], a
    jp FtFrame
.ko:
    ld a, 240
    call FtExcite
    ld a, COUNT_KO
    ld [wFtCount], a
    ld a, SFX_KO
    call PlaySfx
    ld bc, $1000
    call FtAddPoints
    ld a, FT_WIN_SCENE
    call FtFinish
    jp FtFrame

; Show the celebration once its tiles are loaded.
FtCheer:
    ld a, [wFtSwapHave]
    cp SET_SPECIAL
    ret nz
    ld a, RP_TAUNT
    ld [wRvPose], a
    ret

FtPlayerDown:
    call FtCheer
    ldh a, [hPadNew]        ; mash A or B to get up
    and PADF_A | PADF_B
    jr z, .noMash
    ld hl, wPlMash
    inc [hl]
.noMash:
    call FtCountTick
    jr z, .out
    ld a, [wFtCount]
    cp 2
    jp c, FtFrame
    ld a, [wPlDownsAll]     ; presses needed: more each time
    ld b, a
    ld a, FT_MASH_BASE - FT_MASH_STEP
.need:
    add FT_MASH_STEP
    dec b
    jr nz, .need
    ld b, a
    ld a, [wPlMash]
    cp b
    jp c, FtFrame
    ld a, [wPlDownsAll]
    cp 2
    ld a, FT_PLAYER_GETUP_1
    jr c, .health
    ld a, FT_PLAYER_GETUP_2
.health:
    ld [wPlHealth], a
    xor a
    ld [wFtCount], a
    ld [wFtMatch], a
    ld a, 1
    ld [wFtHudDirty], a
    call FtResetBoxers
    jp FtFrame
.out:
    ld a, COUNT_KO
    ld [wFtCount], a
    ld a, FT_LOSE_SCENE
    call FtFinish
    jp FtFrame

; A = scene to go to after a pause.
FtFinish:
    ld [wFtResult], a
    ld a, [wFtResume]       ; off to the corner: no bells and celebrations
    and a
    jr z, .final
    ld a, M_END
    ld [wFtMatch], a
    ld a, FT_END / 3
    ld [wFtTimer], a
    ret
.final:
    ld a, [wFtResult]
    ld a, M_END
    ld [wFtMatch], a
    ld a, FT_END
    ld [wFtTimer], a
    ld a, [wFtResult]
    cp FT_WIN_SCENE
    ld a, SFX_WIN
    jr z, .sound
    ld a, SFX_LOSE
.sound:
    jp PlaySfx

FtEndPause:
    ld a, [wFtResume]       ; the round's over: no celebrating
    and a
    jr nz, .wait
    ld a, [wFtResult]       ; the winner celebrates
    cp FT_WIN_SCENE
    jr nz, .lost
    ld a, PP_WIN
    ld [wPlPose], a
    xor a
    ld [wPlX], a
    jr .wait
.lost:
    ld a, SET_SPECIAL
    ld [wFtSwapWant], a
    call FtCheer
.wait:
    ld hl, wFtTimer
    dec [hl]
    jp nz, FtFrame
    di                      ; back to VBlank-only, no scroll split
    ld a, 1
    ldh [rIE], a
    xor a
    ldh [rSTAT], a
    ldh [hFtActive], a
    ldh [rSCX], a
    ldh [rSCY], a
    ld a, [wFtResult]
    jp StartTransition

; ---- HUD ----

; Work out every HUD tile from the current numbers (outside VBlank).
FtHudCompute:
    ld hl, wFtHudVal
    ld a, [wPlStars]
    ld [hl+], a
    ld a, [wPlHearts]
    ld b, -1
.tens:
    inc b
    sub 10
    jr nc, .tens
    add 10
    ld [hl], b
    inc hl
    ld [hl+], a
    ld de, wFtPoints
    REPT 3
        ld a, [de]
        inc de
        ld b, a
        swap a
        and $0F
        ld [hl+], a
        ld a, b
        and $0F
        ld [hl+], a
    ENDR
    ld a, [wFtMin]
    ld [hl+], a
    ld a, [wFtSec]
    ld b, a
    swap a
    and $0F
    ld [hl+], a
    ld a, b
    and $0F
    ld [hl+], a
    ld a, [wFtRound]
    ld [hl+], a
    ld a, [wPlHealth]       ; a pixel per 2 points of health
    srl a
    call .bar
    ld a, [wRvHealth]
    srl a
    call .bar
    ld hl, wFtHudVal        ; values -> tiles, through each cell's own table
    ld de, wFtHud
    ld bc, FtHudLUT
    ld a, FT_HUD_CELLS
.map:
    push af
    ld a, [hl+]
    push hl
    add c
    ld l, a
    adc b
    sub l
    ld h, a
    ld a, [hl]
    ld [de], a
    inc de
    pop hl
    ld a, c
    add 10
    ld c, a
    adc b
    sub c
    ld b, a
    pop af
    dec a
    jr nz, .map
    ret
.bar:                       ; A = health -> FT_BAR_CELLS levels of 0-8
    ld b, FT_BAR_CELLS
.cell:
    cp 8
    jr c, .part
    ld [hl], 8
    inc hl
    sub 8
    dec b
    jr nz, .cell
    ret
.part:
    ld [hl+], a
    xor a
    dec b
    jr nz, .part
    ret

; ---- the crowd: camera flashes while it's excited ----

FtCrowd:
    ld hl, wFtBulbs + 3     ; age the flashes
    REPT 2
        ld a, [hl]
        and a
        jr z, .aged\@      ; free
        cp $FF
        jr z, .aged\@      ; waiting for VBlank to put the tile back
        dec a
        jr nz, .age\@
        ld a, $FF
.age\@:
        ld [hl], a
.aged\@:
        ld de, 4
        add hl, de
    ENDR
    ld a, [wFtExcite]
    and a
    ret z
    dec a
    ld [wFtExcite], a
    ld a, [wFtRand]         ; x5 + 1: every value comes round
    ld b, a
    add a
    add a
    add b
    inc a
    ld [wFtRand], a
    and 3                   ; a new flash every few frames
    ret nz
    ld hl, wFtBulbs + 3
    ld a, [hl]
    and a
    jr z, .free
    ld hl, wFtBulbs + 7
    ld a, [hl]
    and a
    ret nz
.free:
    ld a, [wFtRand]         ; column = random % 20
    swap a
.mod:
    cp FT_CROWD_W
    jr c, .col
    sub FT_CROWD_W
    jr .mod
.col:
    ld e, a
    ld d, 0
    dec hl
    dec hl
    dec hl                  ; HL = the slot
    push hl
    ld hl, CrowdMap
    add hl, de
    ld b, [hl]              ; the tile it covers
    pop hl
    ld a, LOW(FT_CROWD_ROW)
    add e
    ld [hl+], a
    ld a, HIGH(FT_CROWD_ROW)
    adc 0
    ld [hl+], a
    ld a, b
    ld [hl+], a
    ld [hl], 4              ; frames lit
    ret

; During VBlank: light or put back each flash (two map writes at most).
FtCrowdDraw:
    ld hl, wFtBulbs
    REPT 2
        ld a, [hl+]
        ld e, a
        ld a, [hl+]
        ld d, a
        ld a, [hl+]
        ld c, a             ; the covered tile
        ld a, [hl]
        and a
        jr z, :++
        inc a
        jr nz, :+
        ld [hl], a          ; restored: the slot is free again
        ld a, c
        ld [de], a
        jr :++
:
        ld a, FT_FLASH_TILE
        ld [de], a
:
        inc hl
    ENDR
    ret

; ---- sprites ----

; The impact burst: one tile four ways, 16x16. HL = next OAM entry.
FtSparkSprites:
    ld a, [wFtSparkT]
    and a
    ret z
    dec a
    ld [wFtSparkT], a
    ld a, [wFtSparkY]
    ld d, a
    ld a, [wFtSparkX]
    ld e, a
    ld b, 0                 ; flips: none, X, Y, both; each flipped quarter sits 8 pixels over
.quarter:
    ld a, d
    bit 6, b
    jr z, .row
    add 8
.row:
    ld [hl+], a
    ld a, e
    bit 5, b
    jr z, .col
    add 8
.col:
    ld [hl+], a
    ld a, FT_SPARK_TILE
    ld [hl+], a
    ld a, b
    or FT_REF_ATTR
    ld [hl+], a
    ld a, b
    add $20
    ld b, a
    cp $80
    jr nz, .quarter
    ret

; The sweat beads, if any are flying. HL = next OAM entry.
FtSweatSprites:
    ld a, [wFtSweatT]
    and a
    ret z
    ld de, wFtSweat
    ld c, 3
.bead:
    ld a, [de]              ; x, y -> OAM y, x
    inc de
    ld b, a
    ld a, [de]
    inc de
    inc de
    inc de
    ld [hl+], a
    ld a, b
    ld [hl+], a
    ld a, FT_DROP_TILE
    ld [hl+], a
    ld a, FT_REF_ATTR
    ld [hl+], a
    dec c
    jr nz, .bead
    ret

; Stars circling his head while he's down or getting up. HL = next OAM entry.
FtStars:
    ld a, [wRvState]
    cp RV_OPEN              ; dazed after a miss
    jr z, .show
    cp RV_FALL
    jr z, .falling
    cp RV_DOWN
    jr z, .show
    cp RV_GETUP
    ret nz
    jr .show
.falling:
    ld a, [wFtSwapHave]     ; only once the knockdown frames are showing
    and a
    ret z
.show:
    ld a, [wRvPose]         ; his head's height in this pose
    sub RP_KD_STAGGER
    jr nc, .kd
    xor a
    jr .headY
.kd:
    ld e, a
    ld d, 0
    push hl
    ld hl, StarHeadY
    add hl, de
    ld a, [hl]
    pop hl
.headY:
    add FT_STAR_Y
    ld d, a                 ; D = OAM y of the circle's center
    ldh a, [hFtBandX]
    cpl
    inc a
    add FT_STAR_X
    ld e, a                 ; E = OAM x of the center (moves with his band)
    ldh a, [hFrame]
    srl a
    ld c, 3
.star:
    push af
    and 15
    push hl
    add a
    ld hl, StarOrbit
    add l
    ld l, a
    adc h
    sub l
    ld h, a
    ld a, [hl+]             ; dx
    ld b, [hl]              ; dy
    pop hl
    add e
    push af
    ld a, b
    add d
    ld [hl+], a
    pop af
    ld [hl+], a
    ld a, FT_STAR_TILE
    ld [hl+], a
    ld a, FT_REF_ATTR
    ld [hl+], a
    pop af
    add 5                   ; the next star, a third of the way round
    dec c
    jr nz, .star
    ret

StarOrbit:                  ; an ellipse: dx, dy in 16 steps
    db 0, -4,  5, -4,  9, -3,  12, -1,  13, 1,  12, 3,  9, 5,  5, 6
    db 0, 6,  -5, 6,  -9, 5,  -12, 3,  -13, 1,  -12, -1,  -9, -3,  -5, -4
StarHeadY:                  ; head top, per knockdown pose
    db 8, 16, 24, 8

PunchRise:                  ; per frame of a body punch: y offset (a leap up into it)
    db 0, -6, -11, -14, -16, -16, -16, -14, -11, -8, -5, -3, -1, 0, 0
PunchRiseHigh:              ; to the face: right up to his chin
    db 0, -10, -19, -26, -31, -32, -32, -29, -23, -16, -10, -5, -2, 0, 0

; The player's vertical motion: A = y offset (down). Bobbing, lunging, recoiling, crouching.
FtPlayerMotion:
IF DEF(FT_NES)
    xor a                   ; Mac's scripts move him sideways only ($15)
    ret
ENDC
    ld a, [wPlState]
    and a
    jr z, .idle
    cp PL_PUNCH
    jr z, .punch
    cp PL_HIT
    jr z, .hit
    cp PL_BLOCK
    jr z, .crouch
    cp PL_STAR
    jr z, .star
    xor a
    ret
.idle:
    ldh a, [hFrame]
    and %00100000
    ret z
    ld a, 1
    ret
.punch:                     ; a leap up into the punch: fast up, hold at the peak, drop back
    ld a, [wPlTimer]
    cpl
    add FT_PUNCH + 1        ; frames since the punch started
    ld e, a
    ld d, 0
    ld hl, PunchRise
    ld a, [wPlHigh]
    and a
    jr z, .rise
    ld hl, PunchRiseHigh
.rise:
    add hl, de
    ld a, [hl]
    ret
.hit:
    ld a, [wPlTimer]
    srl a
    srl a
    srl a
    ret
.crouch:
    ld a, 2
    ret
.star:
    ld a, [wPlTimer]
    cp FT_STAR_ACTIVE
    ld a, 3
    ret nc
    ld a, -5
    ret
.zero:
    xor a
    ret

FtBuildOAM:
    ld hl, wFtOAM
    ld a, [wPlPose]
    add a
    ld e, a
    ld d, 0
    push hl
    ld hl, PlayerPoses
    add hl, de
    ld a, [hl+]
    ld d, [hl]
    ld e, a
    pop hl
    ld a, [de]              ; sprite count
    inc de
    ld b, a
    push bc
    push de
    push hl
    call FtPlayerMotion     ; A = y offset
    pop hl
    pop de
    pop bc
    add FT_PLAYER_Y
    ld [wFtPlayerY], a
    ld a, [wPlTired]        ; worn out on the original: he blinks
    and a
    jr z, .shown
    ldh a, [hIsCGB]
    and a
    jr nz, .shown
    ldh a, [hFrame]
    and 8
    jp nz, .refStart
.shown:
    ld a, [wPlX]
    add FT_PLAYER_X
    ld c, a                 ; C = left edge (OAM x)
.sprite:
    ld a, [wFtPlayerY]
    push hl
    ld h, d
    ld l, e
    add [hl]                ; + dy
    pop hl
    inc de
    ld [hl+], a
    ld a, [wPlFlip]
    and a
    ld a, [de]              ; dx
    inc de
    jr z, .noFlip
    cpl                     ; mirrored: (FT_PLAYER_W - 8) - dx
    add FT_PLAYER_W - 8 + 1
.noFlip:
    add c
    ld [hl+], a
    ld a, [de]              ; tile
    inc de
    ld [hl+], a
    ld a, [wPlFlip]
    and a
    ld a, [de]              ; attributes
    inc de
    jr z, .attr
    xor OAMF_XFLIP
.attr:
    push af
    ld a, [wPlTired]        ; worn out: the tired palette (Color)
    and a
    jr z, .rested
    pop af
    and ~7
    or FT_TIRED_PAL
    jr .write
.rested:
    pop af
.write:
    ld [hl+], a
    dec b
    jr nz, .sprite
.refStart:
IF FT_FX_STARS
    call FtStars
ENDC
IF FT_FX_SWEAT
    call FtSweatSprites
ENDC
IF FT_FX_SPARK
    call FtSparkSprites
ENDC
    ; the referee, and what he's saying
    ld a, [wFtRefX]         ; off screen, his sprites land past the right edge, which hides them
    add 8
    ld c, a                 ; C = OAM x of his left edge
    ld a, [wFtRefPose]
    add a
    ld e, a
    ld d, 0
    push hl
    ld hl, RefPoses
    add hl, de
    ld a, [hl+]
    ld d, [hl]
    ld e, a
    pop hl
    ld a, [de]
    inc de
    ld b, a
.refSprite:
    ld a, [de]              ; dy
    inc de
    add FT_REF_Y + 16
    ld [hl+], a
    ld a, [de]              ; dx
    inc de
    add c
    ld [hl+], a
    ld a, [de]
    inc de
    ld [hl+], a
    ld a, [de]
    inc de
    ld [hl+], a
    dec b
    jr nz, .refSprite
    ld a, [wFtSay]          ; his words, in a speech bubble beside his head
    and a
    jp z, .clear
    cp SAY_COUNT
    jr nz, .phrase
    ld de, wFtWord          ; the count: one digit, or "10"
    ld a, [wFtCount]
    cp 10
    jr nc, .ten
    ld [de], a
    inc de
    jr .end
.ten:
    ld a, 1
    ld [de], a
    inc de
    xor a
    ld [de], a
    inc de
.end:
    ld a, $FF
    ld [de], a
    ld de, wFtWord
    jr .bubble
.phrase:
    cp SAY_KO
    ld de, SayKO
    jr z, .bubble
    ld de, SayFight
.bubble:
    push de                 ; B = letters
    ld b, 2                 ; plus the two ends
.len:
    ld a, [de]
    inc de
    cp $FF
    jr z, .lenDone
    inc b
    jr .len
.lenDone:
    pop de
    ld a, b                 ; the bubble ends just left of his head: x = C - 8 * (letters + 2)
    add a
    add a
    add a
    ld b, a
    ld a, c
    sub b
    ld [wFtSayX], a
    ld b, FT_BUBBLE_LEFT
    call .put
.letter:
    ld a, [de]
    inc de
    cp $FF
    jr z, .close
    add FT_COUNT_TILE
    ld b, a
    call .put
    jr .letter
.close:
    ld b, FT_BUBBLE_RIGHT
    call .put
.clear:                     ; hide the rest
    ld a, l
    cp 160
    ret nc
    xor a
    ld [hl+], a
    inc l
    inc l
    inc l
    jr .clear
.put:                       ; the next piece of the bubble: tile B at wFtSayX, then step right
    ld a, FT_SAY_Y + 16
    ld [hl+], a
    ld a, [wFtSayX]
    ld [hl+], a
    add 8
    ld [wFtSayX], a
    ld a, b
    ld [hl+], a
    ld a, FT_REF_ATTR
    ld [hl+], a
    ret

SayKO:
    db 10, 11, 12, $FF
SayFight:
    db 13, 14, 15, 16, 17, 12, $FF

IF DEF(FT_NES)
; ---- both fighters, by the NES game's own logic (kit_nes.asm) ----

FtNesFrame:
    xor a
    ld [wRvState], a        ; (the fight kit's own rival and player logic don't run)
    ld [wPlState], a
    call NesJoypad          ; the buttons, then the NES game's frame (kit_nes.asm)
    call NesEngineFrame
    ld a, BANK(NesFighter)  ; his pose and place
    ld [$2000], a
    call FtNesShow
    ld a, BANK(NesMac)      ; Mac's
    ld [$2000], a
    call FtNesMacShow
    ld a, BANK(RivalMaps)
    ld [$2000], a
    call FtNesPresent
    jp FtNesHud

; The fight kit's presentation from the NES state: the referee, the count, the clock, the ending.
FtNesPresent:
    ld a, [wNes + $0302]    ; the clock
    ld b, a
    ld a, [wNes + $0304]
    swap a
    ld hl, wNes + $0305
    or [hl]
    ld c, a
    ld a, [wFtSec]
    cp c
    jr nz, .clock
    ld a, [wFtMin]
    cp b
    jr z, .round
.clock:
    ld a, b
    ld [wFtMin], a
    ld a, c
    ld [wFtSec], a
    ld a, 1
    ld [wFtHudDirty], a
.round:
    ld a, [wNes + $00]      ; over?
    bit 7, a
    jp nz, FtNesOver
    ld a, [wNes + nKnockdownSts]
    cp 1
    ld b, M_RIVAL_DOWN
    jr z, .down
    cp 2
    ld b, M_PLAYER_DOWN
    jr z, .down
    ld a, [wNes + nOppCurState]   ; before the round: the referee calls it
    and $7F
    cp $40
    jr nz, .fighting
    ld a, M_BREAK
    ld [wFtMatch], a
    ld a, [wNes + $BB]      ; "FIGHT!" once the referee's status says go
    and a
    ld a, FT_INTRO
    jr z, .intro
    xor a
.intro:
    ld [wFtTimer], a
    ret
.fighting:
    xor a
    ld [wFtMatch], a
    ld [wFtCount], a
    ret
.down:                      ; the count: $C1 - $99 (1-10)
    ld a, b
    ld [wFtMatch], a
    ld hl, wFtCountTimer
    ld a, [hl]
    and a
    jr z, .counted
    dec [hl]
.counted:
    ld a, [wFtCount]        ; "KO!" stays up once he's said it
    cp COUNT_KO
    ret z
    ld a, [wNes + $F4]      ; he says it with his voice: the KO and TKO effects ($0E, $0F), right after 10
    cp $0E
    jr z, .ko
    cp $0F
    jr z, .ko
    ld a, [wNes + $C1]
    sub $99
    jr nc, .number
    xor a
.number:
    cp 11
    jr c, .ok
    ld a, 10
.ok:
    ld b, a
    ld a, [wFtCount]
    cp b
    ret z
    ld a, b
    ld [wFtCount], a
    ld a, FT_COUNT          ; the referee's arm comes down with each number
    ld [wFtCountTimer], a
    ld a, SFX_COUNT
    jp PlaySfx
.ko:
    ld a, COUNT_KO
    ld [wFtCount], a
    ld a, FT_COUNT
    ld [wFtCountTimer], a
    ret

; $00 negative: the fight's over ($FC TKO, $FD Mac out, $FE KO) or the round's time is up ($FF).
FtNesOver:
    ld a, [wFtMatch]
    cp M_END
    ret z
    ld a, [wNes + $00]
    cp $FF
    jr z, .time
    rra                     ; $FD counted out, $FB three times down: Mac; $FE, $FC: him
    ld a, FT_LOSE_SCENE
    jr c, .ko
    ld a, FT_WIN_SCENE
.ko:
    ld b, a
    ld a, COUNT_KO          ; "KO!"
    ld [wFtCount], a
    ld a, b
    jp FtFinish
.time:
    ld a, SFX_BELL
    call PlaySfx
    ld a, [wFtRound]
    cp FT_ROUNDS
    jr nc, .decision
    inc a
    ld [wFtRound], a
    IF FT_CORNER_SCENE != $FF
        ld a, 1             ; to the corner; the next round starts when the fight scene comes back
        ld [wFtResume], a
        ld a, FT_CORNER_SCENE
        jp FtFinish
    ENDC
    ld a, BANK(NesFighter)
    ld [$2000], a
    ld a, [wFtRound]
    call NesRoundStart
    ld a, BANK(RivalMaps)
    ld [$2000], a
    ret
.decision:
    call NesDecision
    cp 1
    ld a, FT_WIN_SCENE
    jp z, FtFinish
    ld a, FT_LOSE_SCENE
    jp FtFinish

; The ending's pause, the fighters still running their scripts; then the next scene.
FtNesEnd:
    ld hl, wFtTimer
    dec [hl]
    jp nz, FtFrame
    di                      ; back to VBlank-only, no scroll split
    ld a, 1
    ldh [rIE], a
    xor a
    ldh [rSTAT], a
    ldh [hFtActive], a
    ldh [rSCX], a
    ldh [rSCY], a
IF DEF(FT_NES_SOUND)
    ld a, $80               ; the crowd stops; what's playing (the win or loss music) plays out over the
    ld [wNes + $F3], a      ; next scene (SfxUpdate -> NesSoundAfter)
    ld a, 2
    ldh [hNesSound], a
    xor a
ENDC
    ld a, [wFtResult]
    jp StartTransition

; His pose and place, from his script (the fighter bank is mapped).
FtNesShow:
    ld a, [wNesAnim]
    bit 7, a
    jr z, .place
    ld a, [wNes + nOppBaseAnimIndex]
    ld l, a
    ld a, [wNes + nOppFlip]     ; drawn mirrored: the second half of the map
    and 1
    ld h, a
    ld de, NesPoseMap
    add hl, de
    ld a, [hl]
    ld e, a                 ; the pose; its tiles may have to come in first
    ld d, 0
    ld hl, RivalPoseSet
    add hl, de
    ld a, [hl]
    cp $FF
    jr z, .show             ; always in video memory
    ld [wFtSwapWant], a
    ld hl, wFtSwapHave
    cp [hl]
    jr nz, .place           ; not yet: he keeps the pose he has
.show:
    ld a, e
    ld [wRvPose], a
    xor a
    ld [wNesAnim], a
.place:
    ld a, [wNes + nOppBaseX]
    ld l, a
    ld h, 0
    ld de, NesOffsetX
    add hl, de
    ld a, [hl]
    ld [wRvNesX], a
    ld a, [wNes + nOppBaseY]
    ld l, a
    ld h, 0
    ld de, NesOffsetY
    add hl, de
    ld a, [hl]
    ld [wRvNesY], a
    ret

; Mac's pose (bit 7: mirrored) and place, from his script (the Mac bank is mapped).
FtNesMacShow:
    ld a, [wNes + $60]      ; a new pose ($60 goes back to 0 in the NES's vblank, NesVblank)
    and a
    jr z, .place
    ld a, [wNes + $61]
    ld l, a
    ld h, 0
    ld de, MacPoseMap
    add hl, de
    ld a, [hl]
    cp $FF                  ; not him (the referee, a bubble in his place): his pose stays
    jr z, .place
    ld b, a
    and $7F
    ld [wPlPose], a
    ld a, b
    rlca
    and 1
    ld [wPlFlip], a
.place:
    ld a, [wNes + nMacX]
    ld l, a
    ld h, 0
    ld de, MacOffsetX
    add hl, de
    ld a, [hl]
    ld [wPlX], a
    ret

; The HUD from the NES's numbers: HP ($0392 Mac, $0399 him), hearts (BCD $0323/$0324), stars ($0342).
FtNesHud:
    ld a, [wNes + $0393]    ; the bars follow the shown HP (it steps a point a frame)
    ld b, a
    ld a, [wPlHealth]
    cp b
    jr z, .rv
    ld a, b
    ld [wPlHealth], a
    ld a, 1
    ld [wFtHudDirty], a
.rv:
    ld a, [wNes + $039A]
    ld b, a
    ld a, [wRvHealth]
    cp b
    jr z, .hearts
    ld a, b
    ld [wRvHealth], a
    ld a, 1
    ld [wFtHudDirty], a
.hearts:
.show:
    ld a, [wNes + $0323]
    ld b, a
    add a
    add a
    add b
    add a                   ; tens * 10
    ld hl, wNes + $0324
    add [hl]
    ld b, a
    ld a, [wPlHearts]
    cp b
    jr z, .stars
    ld a, b
    ld [wPlHearts], a
    ld a, 1
    ld [wFtHudDirty], a
    ld hl, wNes + $03E8     ; points: six digits -> three BCD bytes
    ld de, wFtPoints
    ld b, 3
.points:
    ld a, [hl+]
    swap a
    or [hl]
    inc hl
    ld c, a
    ld a, [de]
    cp c
    jr z, .samePoints
    ld a, c
    ld [de], a
    ld a, 1
    ld [wFtHudDirty], a
.samePoints:
    inc de
    dec b
    jr nz, .points
.stars:
    ld a, [wNes + $0342]
    ld b, a
    ld a, [wPlStars]
    cp b
    ret z
    ld a, b
    ld [wPlStars], a
    ld a, 1
    ld [wFtHudDirty], a
    ret
ENDC
