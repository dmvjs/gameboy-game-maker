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
DEF COUNT_TKO EQU $FE       ; and "TKO!"
DEF SAY_COUNT EQU 1         ; what the referee is saying
DEF SAY_KO EQU 2
DEF SAY_FIGHT EQU 3
DEF SAY_TKO EQU 4
DEF RF_STAND EQU 0          ; referee poses
DEF RF_COUNT EQU 1
DEF RF_WAVE EQU 2
DEF REF_IN EQU 104          ; his screen x when he's in the ring: beside the action, left of the rival's corner (as the NES)
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
wRvPic: db                  ; Color, his NES pictures: the one to show, the one on the map
wRvPicShown: db
wFtPicGo: db                ; (blocks this time)
wFtPicDrew: db              ; (this VBlank spent on his picture)
wFtStreamN: db              ; (the original: the coming picture's tiles)
wRvPicHidden: db            ; (the original: the picture whole in the copy not shown, $FF none: the last one shown)
wRvPicLoadWanted: db        ; (the original: the one coming in was wanted, not a guess at the next)
wPlPicLoad: db              ; (the original, Mac: the picture coming into his copy not shown, its tiles in, the one
wPlPicDone: db              ; whole in that copy)
wPlPicHidden: db
wFtStreamDone: dw           ; (the job being streamed: its count of tiles in)
wRvPicBuf: db               ; which copy of his tiles the map shows (0: FT_PIC_VRAM, 1: FT_PIC_VRAM2)
wRvPicLoad: db              ; the picture coming into the other, its tiles in so far, where it'll sit
wRvPicDone: db
wRvPicLoadX: db
wRvPicLoadY: db
wRvPicWantX: db             ; (where the wanted one sits)
wRvPicWantY: db
wRvPicSwitch: db            ; up next VBlank: its sprites built
wRvPicHeads: db             ; the picture the sprites are built for, its copy
wRvPicHeadsBuf: db
wPlPic: db                  ; Color, the NES's Mac: his picture wanted, shown, the copy shown (0: tiles 0-31 of bank 1,
wPlPicShown: db             ; 1: 32-63), up next VBlank, and the one the sprites are built for, its copy
wPlPicBuf: db
wPlPicSwitch: db
wPlPicHeads: db
wPlPicHeadsBuf: db
wPlPicGo: db                ; (tiles of his going up next VBlank: room his rival's picture can't have)
wFtPlTileAdd: db
wRvSwBank: db               ; his picture readied (FtPicDecide): its bank, its tiles' DMA (source, destination,
wRvSwTiles: ds 4            ; blocks: 0 none), its rows' and attributes' sources: VBlank only writes them out
wRvSwN: db
wRvSwRows: dw
wRvSwAttr: dw
wPlSwBank: db               ; Mac's: bank, source, destination, blocks
wPlSwTiles: ds 4
wPlSwN: db
wFtCueColor: dw              ; (FtCueBuild's: the cue's color, and palettes to go)
wFtCueN: db
wFtCueBuilt: db             ; (the color they're built in, + 1)
wFtPalCue: ds 8 * 8           ; his palettes in his dodge cue (the NES's outline color): built as it comes
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
wFtSwapPos: dw              ; tiles copied so far toward the wanted set
wFtSwapSizes: ds 6          ; each set's tiles (dw)
wFtSwapGoing: db            ; the set those are of (wanted changes midway: it starts over)
wFtSwapSets: ds 6           ; the three sets' tiles (in wFtBankSwap)
wFtSwapVbk: db              ; the run being copied: its video memory bank
wFtSwapRuns: ds 16          ; the swap area's runs: tiles, where (dw), video memory bank; (0 tiles: no more)
wFtCopyTo: dw               ; (FtSwapSetup's)
wFtCopyN: db
wFtRefX: db                 ; the referee's screen x (signed); off the left edge when he's not needed
wFtRefPose: db
wFtRefShown: db             ; the pose shown (its tiles in his slot wFtRefSlot)
wFtRefSlot: db              ; 0 or 1: his slot shown (FT_REF_TILES tiles each, from FT_REF_SLOT)
wFtRefLoad: db              ; the pose loading into the other slot ($FF: none)
wFtRefDone: db              ; its tiles loaded so far
wPlRareIn: db               ; the player's rare pose whose tiles are in its area ($FF: none)
wPlRareWant: db             ; the one asked for ($FF: none)
wPlRareLoad: db             ; the one loading ($FF: none)
wPlRareDone: db             ; its tiles loaded so far
wPlRegular: db              ; his last pose of the rest (shown while a rare one loads)
wFtSay: db
wFtFight:                   ; this fight's own (FtFights, loaded by FightLoad)
wFtBankData: db             ; its data bank (RivalMaps...), mapped while it runs
wFtBankMaps: db             ; its pose rows
wFtBankSwap: db             ; its swap sets
wFtBankNes: db              ; its NES fighter bank
wFtNesOffset: db            ; his entry in it
wFtSwapCount: db            ; tiles in the shared area, and its first run's (the rest in the second)
wFtSwapACount: db
wFtSwapVramA: dw
wFtSwapVramB: dw
wFtFlashTile: db
wFtWinScene: db             ; where it goes: won, won on a TKO ($FF: as won), lost, the corner ($FF: none)
wFtTkoScene: db
wFtLoseScene: db
wFtCornerScene: db
wFtBankMapsCgb: db          ; Color's finer poses: their map rows' bank, their tiles' (0: none, the original's)
wFtBankSwapCgb: db
wFtBankHeads: db            ; his top rows as sprites (a rope row: he stands in front of it), their bank (0: none)
wFtBankPics: db             ; Color, an NES fighter: his pictures' bank (their header at $4000: FT_PIC_*; 0: none)
wFtBankPicsDmg: db          ; the original's: those pictures in greys (FT_DPIC_*; 0: none; their frame map: the above)
wFtCareer: db               ; Punch-Out!!'s circuits: CAREER_* (a title bout, a circuit's first, the last fight)
wFtRematchScene: db         ; lost: the rematch; lost it (or a title bout), down the ranks to this scene ($FF: none)
wFtDropScene: db
wFtOverScene: db            ; the third loss (or the last fight's): game over
wFtWinNext: db              ; won: on to (the win screen's way on)
wFtAwCareer: db             ; Punch-Out!!'s Another World Circuit (bit 7: in it): its first, its last (CAREER_*);
wFtAwNext: db               ; won there: on to; lost (a rematch lost): down to
wFtAwDrop: db
wFtCueTile: db              ; Punch-Out!!'s crowd tell: its tile moving (0: none), at rest, its column in the rope row
wFtCueOld: db
wFtCueCol: db
wFtHearts0: db              ; Mac's hearts as the fight starts (the NES's, by opponent)
wFtFightEnd:
wRvNesX: db                 ; NES rival: his offset from his place (pixels right, down)
wRvNesY: db
wFtRiseCap: db              ; (how far up his band may go: the picture showing's pose's)
wFtHeadX: db                ; (his top rows' sprites: OAM x of his area's left, this frame)
wFtHeadIn: db               ; (and in this frame's yet)
wFtHeadTile: db             ; (added to its tiles: his pictures' second copy)
wFtHeadKey: ds 5            ; his top rows' sprites as last built: their picture, its copy, his band's x and y, where
wFtHeadEnd: db              ; they began (the upper list's low byte; $FF none) -- and where they ended
wFtMacKey: ds 16            ; per lower list (wFtOAM2, wFtOAM3): Mac's sprites as last built there -- where they
                            ; began ($FF none), his picture, its tiles' copy, his y and x, his palette's mask and
                            ; bits -- and where they ended
wFtMacPath: db              ; (his sprites built from the key this frame)
wFtRefKey: ds 16            ; per list: the referee's sprites and words as last built -- where they began ($FF none),
                            ; his pose shown, his x, his tiles' slot, what he says, his count -- and where they ended
wFtTwinkleX: db             ; a star just earned: where it twinkles (OAM x, y), from the NES's ($0344, $0345)
wFtTwinkleY: db
wPlNesY: db                 ; NES Mac: pixels down his frame sits (bit 7: knocked-down colors)
wRvPlaceX: db               ; and his pose's own offset from it (each NES frame sits where the NES draws it)
wRvPlaceY: db
wFtFreeze: db               ; hit stop: frames both fighters hold still after a clean hit
wFtExcite: db               ; frames the crowd's cameras keep flashing
wFtRand: db
wFtCue: db                  ; the Bull Charge camera's cell: its tile now (FtCrowdDraw puts it)
wFtCueHold: db              ; (the original: frames his dodge cue stays shown after the NES's ends -- its LCD smears a
                            ;  frame or two away)
wFtBulbs: ds 4 * 2          ; per flash: map address, the tile it covers, state (0 free, frames left, $FF restore)
wFtOAMEnd: ds 3             ; per sprite list (wFtOAM, wFtOAM2, wFtOAM3): where it ended last time (slots past it hidden)
wRvPicPrev: db              ; (the original: the picture shown before the shown one)
wFtEnd:

SECTION "Fight between rounds", WRAM0   ; kept while the corner scene shows
wFtResume: db               ; coming back from the corner: carry on, don't start a new fight
wFtSelectUsed: db           ; the corner's Select refill is once per match
wFtDocFast: db              ; Punch-Out!!'s corner: Select pressed, Doc rubs faster
wDocN: db                   ; Punch-Out!!'s corner: the cells Doc's states change, the state (bit 0 his mouth open,
wDocState: db               ; bit 1 his hand up), frames till his mouth and his hand move, VBlank's to put it up
wDocMouth: db
wDocHand: db
wDocDirty: db
wDocAddr: ds 32
wDocTile: ds 64
wTalkN: db                  ; and the rival talking: his cells, his state (0 his first), frames till it turns, and
wTalkState: db              ; where his cells' addresses, tiles and frames are (DocLoadIn's bank, as these run in)
wTalkTimer: db
wTalkPtr: dw
wOvlDoc: dw                 ; (Color) Doc's and the rival's sprites: each its OAM place, how many, every state's
wOvlTalk: dw
wOvlStill: dw               ; (Color) the scene's own sprites, while it slides in (high byte 0: none, or done)
wObp1Mode: db               ; (the original) OBP1: 0 as BGP, 1 white for 1 (close-ups' sprites), 2 light grey for 2 (a fight)
wRemap: ds 4                ; (DmgRemap: a row's pixels of each slot, its batch: count, tiles, addresses, source)
wRemapN: db
wRemapLeft: db
wRemapSrc: dw
wRemapDst: ds 12
wRemapBuf: ds 96
wFtRoom: db                 ; loading with the display on (FT_LOAD_ON): this VBlank's time left (FtRoom)
wFtRoomN: db                ; (FtCopy: blocks this time, their bytes)
wFtRoomBytes: dw

SECTION "Career", WRAM0       ; Mac's record, kept from fight to fight (the title clears it: RecReset)
wRecWins: db
wRecLosses: db
wRecKOs: db
wRecLost: db                ; lost to the one he faces: his next loss to him is a rematch lost
wAw: db                     ; Punch-Out!!'s Another World Circuit on (its pass key)
wRecNext: db                ; where the result's screen goes: on, the rematch, down the ranks, or game over

SECTION "Fight OAM", WRAM0, ALIGN[8]
wFtOAM: ds 256              ; 40 sprites go to OAM; a busy frame's extras land in the spare room and aren't shown
IF DEF(FT_ROPE)
wFtOAM2: ds 256             ; (a rope row: the screen's lower part's own 40, copied in at FT_DMA_LINE mid-frame; the
wFtOAM3: ds 256             ; upper part's, his top rows over the ropes, in wFtOAM from VBlank. Two of them: one
ENDC                        ; built while the other's copied in, swapped at VBlank: never half built)

SECTION "Code: Fight", ROM0

OAMDMACode:                 ; copied to HRAM: OAM DMA needs the CPU to wait off the main bus
    ldh [rDMA], a
    ld a, 40
.wait:
    dec a
    jr nz, .wait
    ret
OAMDMACodeEnd:

; ---- loading (the screen off; on Color, on and black: FT_LOAD_ON, each piece in a VBlank) ----

; Loading with the display on, each piece of it goes in a VBlank: FtRoom, with its time (8 cycles a unit, a DMA
; block's), waits for the next VBlank's start unless this one has room left for it. A VBlank is 1,140 cycles, room
; for FT_ROOM units (the rest a margin): the lines it's been going (15 units a line) and the DMAs done in it
; (wFtRoom: they stop the CPU, and on hardware count in both: room to spare) are gone. A DMA piece's time counts
; what comes before it (FT_ROOM_OVER).
DEF FT_ROOM EQU 128
DEF FT_ROOM_OVER EQU 12
DEF FT_ROOM_ALL EQU FT_ROOM - 1     ; (a VBlank of its own)
MACRO FT_VWAIT              ; \1: its time (units)
IF DEF(FT_LOAD_ON)
    ld a, \1
    call FtRoom
IF (\1) == FT_ROOM_ALL
    xor a                   ; (it takes the VBlank)
    ld [wFtRoom], a
ENDC
ENDC
ENDM

IF DEF(FT_LOAD_ON)
FtRoomLeft:                 ; A: this VBlank's room left; carry: not in VBlank, or none
    push bc
    ldh a, [rLY]
    sub 144
    jr c, .none
    ld c, a
    swap a
    sub c                   ; (15 units a line)
    ld c, a
    ld a, [wFtRoom]
    sub c
.none:
    pop bc
    ret

FtRoom:                     ; A: the piece's time (HL, BC, DE kept)
    push bc
    ld b, a
    call FtRoomLeft
    jr c, .wait
    cp b
    jr nc, .fits
.wait:
    call VWait
    ld a, FT_ROOM
    ld [wFtRoom], a
.fits:
    pop bc
    ret
ENDC

FightLoad:
    ld a, 2                 ; (the original: OBP1's 2 the lightest grey, the referee's shirt and words over the mat)
    ld [wObp1Mode], a
    xor a                   ; (no VBlank's room yet: the first piece waits for one)
    ld [wFtRoom], a
    ld a, [wFtResume]       ; back from the corner: the fight carries on
    and a
    jr nz, .keep
    ld [wFtSelectUsed], a
IF DEF(FT_NES)
    ld [wNes + $03D8], a    ; (Punch-Out!!'s corner Select: unused this fight)
ENDC
    ld hl, wFtStart
    ld bc, wFtEnd - wFtStart    ; (more than 255 bytes: a 16-bit count)
.clear:
    xor a
    ld [hl+], a
    dec bc
    ld a, b
    or c
    jr nz, .clear
.keep:
    ld a, 160               ; (every sprite list hidden whole the first time)
    ld [wFtOAMEnd], a
    ld [wFtOAMEnd + 1], a
    ld [wFtOAMEnd + 2], a
IF DEF(FT_NES)
    ld a, $30               ; (back from the corner: his colors normal again, as the NES's corner leaves them, MacPal)
    ld [wNes + $048D], a
    ld a, $8F
    ld [wNes + $048E], a
ENDC
    ld hl, OAMDMACode
    ld de, hOAMDMA
    ld b, OAMDMACodeEnd - OAMDMACode
.dma:
    ld a, [hl+]
    ld [de], a
    inc e
    dec b
    jr nz, .dma
    ld a, BANK(FtFights)    ; (their bank: read only here)
    ld [$2000], a
    ldh a, [hScene]         ; this fight's own values (FtFights: scene, then wFtFight's)
    ld hl, FtFights
.find:
    cp [hl]
    jr z, .found
    ld de, wFtFightEnd - wFtFight + 1
    add hl, de
    jr .find
.found:
    inc hl
    ld de, wFtFight
    ASSERT wFtFightEnd - wFtFight < 256, "a fight's row is copied with an 8-bit count"
    ld b, wFtFightEnd - wFtFight
.fight:
    ld a, [hl+]
    ld [de], a
    inc de
    dec b
    jr nz, .fight
    ld a, [wFtBankData]     ; (its data bank, as before)
    ld [$2000], a
    ld a, [wFtCueOld]       ; (the Bull Charge camera: unlit)
    ld [wFtCue], a
    call FtSwapSetup
    ld a, [wFtBankData]     ; the fight's data stays mapped while it runs
    ld [$2000], a
    ld a, [FtObjBytes]      ; player and count sprites (this fight's: their count its own)
    ld c, a
    ld a, [FtObjBytes + 1]
    ld b, a
    ld de, FtObjTiles
    ld hl, $8000 + FT_OBJ_FIRST * 16
    call FtCopy             ; (Color: by DMA)
IF DEF(FT_PL_CGB)
    ldh a, [hIsCGB]         ; Color: the player's own poses' tiles, unshared, into bank 1's sprite tiles
    and a
    jr z, .plDone
    ld a, 1
    ldh [rVBK], a
    ld de, PlayerCgbTiles
    ld hl, $8000
    ld bc, FT_PL_CGB_TILES * 16
    call FtCopy
    xor a
    ldh [rVBK], a
.plDone:
ENDC
IF DEF(FT_NES)
    call FtDmgPicsStart     ; (the original: his first grey picture)
    ld a, $FF               ; (his top rows' sprites, Mac's: none built yet)
    ld [wFtHeadKey + 4], a
    ld [wFtMacKey], a
    ld [wFtMacKey + 8], a
    ld [wFtRefKey], a
    ld [wFtRefKey + 8], a
    ld a, [wFtBankData]
    ld [$2000], a
    xor a                   ; (the original with his grey pictures: his ring's greys from the mat's line)
    ldh [hFtRingBgp], a
    ldh a, [hIsCGB]
    and a
    jr nz, .ringDone
    ld a, [wFtBankPicsDmg]
    and a
    jr z, .ringDone
    ld a, [RivalRingBgp + 1]
    ldh [hFtObpRaw], a
    ld a, [RivalRingBgp + 2]
    ldh [hFtObpRaw + 1], a
    ld a, [RivalRingBgp]
    ldh [hFtRingBgp], a
    ldh a, [rBGP]
    call FtRingBase
.ringDone:
ENDC
IF DEF(FT_MAC_PICS)
    call FtPlPicsStart      ; (Color: Mac's first picture)
    ld a, [wFtBankData]
    ld [$2000], a
ENDC
    xor a                   ; the referee standing, his tiles in
    call FtRefFirst
    ld a, $FF               ; no rare pose of the player's in yet
    ld [wPlRareIn], a
    ld [wPlRareWant], a
    ld [wPlRareLoad], a
    xor a
    ld [wPlRegular], a
IF DEF(FT_NES)
    ld a, REF_IN            ; the referee is in the ring as the round opens, as in Punch-Out!!
ELSE
    ld a, REF_OUT
ENDC
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
    ld [wFtSwapPos + 1], a
    ld [wFtSwapGoing], a
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
    ld a, [wFtHearts0]
    ld [wPlHearts], a
IF DEF(FT_NES)
    ld a, [wFtBankNes]  ; his fight data and AI, as the NES game starts a fight
    ld [$2000], a
    call NesFightStart
    ld a, [wFtBankData]
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
IF DEF(FT_ROPE)
    call FtRingSetupDmg     ; the bottom rope's row (DE: its map row; the original with a grey mat: its copies,
                            ; outside the ring, the side ropes' tiles -- the fight's data bank's own code)
.ropeRow:
    ld hl, $9800 + FT_ROPE_ROW * 32
    ld bc, 32
    call FtCopy
    ldh a, [hIsCGB]
    and a
    jr z, .ropeDone
    ld a, 1
    ldh [rVBK], a
    ld de, FtRopeAttr
    ld hl, $9800 + FT_ROPE_ROW * 32
    ld bc, 32
    call FtCopy
    xor a
    ldh [rVBK], a
.ropeDone:
ENDC
    ld de, FtTailTiles      ; the background below him, for his band's end when he's raised
    ld hl, $9800 + FT_TAIL_ROW * 32
    ld bc, FT_TAIL_ROWS * 32
    call FtCopy
    ldh a, [hIsCGB]
    and a
    jr z, .tailDone
    ld a, 1
    ldh [rVBK], a
    ld de, FtTailAttr
    ld hl, $9800 + FT_TAIL_ROW * 32
    ld bc, FT_TAIL_ROWS * 32
    call FtCopy
    xor a
    ldh [rVBK], a
.tailDone:
    call FtOffColumnsFar    ; and his rows' columns off the right edge: the mat, for when he's far to one side
    ldh a, [hIsCGB]
    and a
    jr z, .offDone
    ld a, 1
    ldh [rVBK], a
    call FtOffColumnsFar
    xor a
    ldh [rVBK], a
.offDone:
ENDC
IF DEF(FT_NES_SOUND)
    ldh a, [hNesSound]      ; the NES's sound engine takes the sound hardware for the fight (already playing,
    and a                   ; the crowd from the screen before: it carries on)
    jr nz, .soundOn
    ld a, BANK(NesSnd)
    ld [$2000], a
    call ApuInit
.soundOn:
    call PcmLoad            ; (the crowd's recording in now, while it loads: not when it first cheers)
    ld a, 1
    ldh [hNesSound], a
ENDC
IF DEF(FT_NES)
    xor a                   ; Mac standing till his script's first pose
    ld [wPlPose], a
    ld [wPlFlip], a
    ld [wRvPlaceX], a
    ld [wRvPlaceY], a
    ld a, FT_MAC_START_Y    ; (low, as the NES has him before his walk up: the round's first frames too)
    ld [wPlNesY], a
    ld a, [wFtBankNes]  ; the round, as the NES game starts one
    ld [$2000], a
    ld a, [wFtRound]
    call NesRoundStart
    ld a, [wFtBankData]
    ld [$2000], a
    call FtNesHud           ; (the HUD as the NES's round starts it, not the last fight's, from its first frame)
    ld a, [wNes + $0302]
    ld [wFtMin], a
    ld a, [wNes + $0304]
    swap a
    ld hl, wNes + $0305
    or [hl]
    ld [wFtSec], a
ENDC
    call FtHudCompute
    FT_VWAIT FT_ROOM_ALL
    call FtHudDraw
    xor a
    ldh [hFtHudReady], a
    ldh [hFtScx], a
IF DEF(FT_ROPE)
    ld a, HIGH(wFtOAM3)     ; (the lower list's two: built in one, shown from the other)
    ldh [hFtOamShown], a
    ld a, HIGH(wFtOAM2)
    ldh [hFtOamBuild], a
ENDC
    ld a, 1
    ldh [hFtActive], a
    xor a
    ldh [hFtBandX], a
    ldh [hFtBandY], a
    ldh [hFtShowX], a
    ldh [hFtShowY], a

    ldh [hFtBandOn], a
    ldh [hFtBandGap], a
    ldh [hFtFlash], a       ; (not flashing: his palettes come up with the fade)
    ldh [hFtFlashShown], a
    ldh [hFtCueSrc], a      ; (nor his cue's greys up: HRAM's random at power-on)
    ldh [hFtCueOn], a
    ld [wFtCueHold], a
    ld a, FT_BAND_BOTTOM
    ldh [hFtBandBottom], a
    ldh [hFtShowBottom], a
IF DEF(FT_ROPE)
    ld a, FT_ROPE_LINE      ; the bottom rope's row over his area's first, then his band: interrupts there
ELSE
    ld a, FT_BAND_TOP       ; the rival's band scrolls on its own: an interrupt at its top and bottom lines
ENDC
    ldh [hFtBandTop], a
IF DEF(FT_NES)
    ld a, [wFtBankNes]  ; where the round puts him (his corner), from the first frame shown
    ld [$2000], a
    call FtNesShow
    ld a, [wFtBankData]
    ld [$2000], a
    call FtAnimate
ENDC
    call FtBuildOAM
IF DEF(FT_ROPE)
    ld hl, wFtOAM2          ; (the one shown first: the same, not the last fight's, its KO bubble and all)
    ld de, wFtOAM3
    ld b, 0
.oamPage:
    ld a, [hl+]
    ld [de], a
    inc de
    dec b
    jr nz, .oamPage
ENDC
    FT_VWAIT 20 + FT_ROOM_OVER  ; (OAM: the screen off, or VBlank)
    ld a, HIGH(wFtOAM)
    call hOAMDMA
    ldh a, [hFtBandTop]
    ldh [rLYC], a
    ld a, STATF_LYC
    ldh [rSTAT], a
    ld a, %00000011         ; VBlank (wakes HALT) and STAT
    ldh [rIE], a
    xor a
    ldh [rIF], a
    ei
    ldh [hVblank], a        ; (no VBlank noted yet: the setup's own run into one isn't the fight's first)
    ret

IF DEF(FT_NES)
FtOffColumnsFar:            ; (setup, his data bank in: FtOffColumns from its own bank, his data back after)
    ld a, BANK(FtOffColumns)
    ld [$2000], a
    call FtOffColumns
    ld a, [wFtBankData]
    ld [$2000], a
    ret

PUSHS
SECTION "Code: Fight setup, far", ROMX
; His map rows' 12 columns past the screen's right edge, each the row's first (the mat): his band scrolls
; sideways with him, and far over (his corner, as the round opens) it brings them in. (Color: VBK picks tiles
; or their attributes.)
FtOffColumns:
    FT_VWAIT FT_PIC_ROWS / 2 * 13 + FT_ROOM_OVER   ; (in halves, loading with the display on: a row's 100 cycles)
    ld hl, FT_REGION_ROW
    ld c, FT_PIC_ROWS / 2
    call .rows
    FT_VWAIT (FT_PIC_ROWS + 1) / 2 * 13 + FT_ROOM_OVER
    ld c, FT_PIC_ROWS - FT_PIC_ROWS / 2
.rows:
    ld a, [hl]
    push hl
    ld de, 20
    add hl, de
    ld b, 12
.col:
    ld [hl+], a
    dec b
    jr nz, .col
    pop hl
    ld de, 32
    add hl, de
    dec c
    jr nz, .rows
    ret
POPS
ENDC

; Mid-frame: at the band's top line, scroll by the rival's offset; at its bottom line, back to normal.
; The band moves with his height, so its scroll never brings in what's below it: shown higher, it
; starts higher (over the lines above it), and the lines it leaves at its old bottom show the background
; there without him (two map rows kept off screen, FT_TAIL_ROW).
FtStat:
    push af
.drawing:                   ; the line before is still being drawn: change the scroll once it's done (or VBlank's
    ldh a, [rSTAT]          ; begun: a split at the screen's last line, his band moved down to it, mustn't wait out
    and 2                   ; VBlank for an HBlank and miss it)
    jr nz, .drawing
    ldh a, [hFtBandOn]
    and a
    jp z, .top
    cp 3
    jp z, .band
IF DEF(FT_ROPE)
    cp 4
    jp z, .dma
ENDC
    dec a
    jp nz, .bottom
.end:
IF DEF(FT_NES)
    call FtCueOff           ; (his cue's greys: his lines only)
ENDC
    ldh a, [hFtShowY]       ; his band's end: raised (scrolled down), the background below him down to its
    and a                   ; usual end
    jp z, .bottom
    bit 7, a
    jp nz, .bottom
    ldh a, [rLY]            ; (only if that end is still to come: his height can change mid-frame, and a
    cp FT_BAND_BOTTOM       ; missed end would leave the tail's scroll on to the bottom, wrapping to the HUD)
    jp nc, .bottom
    ldh a, [hFtScx]
    ldh [rSCX], a
    ld a, FT_TAIL_SCY
    ldh [rSCY], a
    ld a, FT_BAND_BOTTOM
    ldh [rLYC], a
    ld a, 2
    ldh [hFtBandOn], a
    ldh a, [rLY]            ; that end reached while this was set up (late, behind another interrupt): its
    cp FT_BAND_BOTTOM       ; line has gone by without a match, so end the tail now
    jp nc, .bottom
    pop af
    reti
.top:
IF DEF(FT_ROPE)
    ldh a, [hFtScx]         ; the bottom rope's row (its own map row) over his area's first, his band after
    ldh [rSCX], a
    ld a, FT_ROPE_SCY
    ldh [rSCY], a
IF DEF(FT_NES)
    ldh a, [hFtRingBgp]     ; (the original, a grey mat: the ring's greys from here down, the frame's top lines'
    and a                   ;  back at its next)
    jr z, .ringOff
    ldh a, [hFtRingNow]
    ldh [rBGP], a
.ringOff:
ENDC
    ld a, FT_BAND_TOP
    ldh [rLYC], a
    ld a, 3
    ldh [hFtBandOn], a
    ldh a, [rLY]            ; (late, its line gone by while something held this off: on now, not next frame)
    cp FT_BAND_TOP
    jp nc, .band
    pop af
    reti
ENDC
    ldh a, [hFtBandGap]     ; moved down: the lines his band has left, plain mat (the screen's last row)
    and a                   ; till it starts (unscrolled, they'd show his top rows again over him)
    jp z, .band
    ldh [rLYC], a
    ld a, FT_GAP_SCY
    ldh [rSCY], a
    ld a, 3
    ldh [hFtBandOn], a
    pop af
    reti
.band:
    ldh a, [hFtShowX]
    ldh [rSCX], a
    ldh a, [hFtShowY]
    ldh [rSCY], a
IF DEF(FT_NES)
    ldh a, [hFtCueSrc]      ; (the original, his dodge cue: his black lighter in his band's lines)
    and a
    call nz, .cueBand
ENDC
IF DEF(FT_ROPE)
    ld a, FT_DMA_LINE       ; then the lower part's sprites, where none are
    ldh [rLYC], a
    ld a, 4
    ldh [hFtBandOn], a
    ldh a, [rLY]            ; (late: now)
    cp FT_DMA_LINE
    jp nc, .dma
    pop af
    reti
.dma:                       ; mid-frame: the lower part's 40 sprites in (his top rows' have all been drawn)
IF DEF(FT_DMG_WHITE)
    ldh a, [hFtObp1]        ; (OBP1 as the referee's again)
    ldh [rOBP1], a
ENDC
IF DEF(FT_NES)
    ldh a, [hFtCueOn]       ; (his cue's OBP0 back: Mac's and the referee's below)
    and 2
    call nz, .cueObjOff
    ldh a, [hFtRingBgp]     ; (a grey mat: OBP0 his top rows' greys above; Mac's and the referee's, the base, below)
    and a
    jr z, .ringObj
    ldh a, [hFtObpLow]
    ldh [rOBP0], a
    ldh a, [hFtObpLow + 1]
    ldh [rOBP1], a
.ringObj:
ENDC
    ldh a, [hFtOamShown]
    call hOAMDMA
    ldh a, [hFtShowBottom]
    ldh [rLYC], a
    ld a, 1
    ldh [hFtBandOn], a
    push bc                 ; (late, his band's end gone by: its end now; an interrupt keeps what it uses)
    ldh a, [hFtShowBottom]
    ld b, a
    ldh a, [rLY]
    cp b
    pop bc
    jp nc, .end
    pop af
    reti
ENDC
    ldh a, [hFtShowBottom]
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
IF DEF(FT_NES)
    call FtCueOff
ENDC
    pop af
    reti
IF DEF(FT_NES)
.cueBand:                   ; A = hFtCueSrc: BGP's 3 as its 1's or 2's for his band
    push bc
    ld c, a
    ldh a, [rBGP]
    ldh [hFtBgp], a
    call FtCueMap
    ldh [rBGP], a
    ldh a, [hFtCueOn]
    or 1
    ldh [hFtCueOn], a
    pop bc
    ret
.cueObj:                    ; and OBP0's for his top rows' sprites
    push bc
    ld c, a
    ldh a, [rOBP0]
    ldh [hFtObp], a
    call FtCueMap
    ldh [rOBP0], a
    ldh a, [hFtCueOn]
    or 2
    ldh [hFtCueOn], a
    pop bc
    ret
.cueObjOff:
    ldh a, [hFtObp]
    ldh [rOBP0], a
    ldh a, [hFtCueOn]
    and ~2
    ldh [hFtCueOn], a
    ret
ENDC

IF DEF(FT_NES)
; His palettes in his dodge cue, for VBlank to put up (FtFlashPalettes, 2): each palette's outline
; (RivalCueOutline) in the color the game holds now ($05EC, an NES color: NesRgb). Out of VBlank, when that
; color's another than they were built in (Color only: the original has no such palettes).
FtCueBuild:
    ldh a, [hIsCGB]
    and a
    ret z
    ld a, [wNes + $5EC]
    and $3F
    inc a                   ; (+1: 0, never built)
    ld hl, wFtCueBuilt
    cp [hl]
    ret z
    ld [hl], a
    dec a
    add a
    add LOW(NesRgb)
    ld l, a
    adc HIGH(NesRgb)
    sub l
    ld h, a
    ld a, [hl+]
    ld [wFtCueColor], a
    ld a, [hl]
    ld [wFtCueColor + 1], a
    ld a, [RivalPalSlots]
    ld [wFtCueN], a
    ld hl, RivalPalNormal
    ld bc, wFtPalCue
    ld de, RivalCueOutline
.pal:
    ld a, [de]
    inc de
    push de
    ld d, a                 ; its outline's color number
    ld e, 0
.col:
    ld a, e
    cp d
    jr z, .ink
    ld a, [hl+]
    ld [bc], a
    inc bc
    ld a, [hl+]
    ld [bc], a
    inc bc
    jr .next
.ink:
    inc hl
    inc hl
    ld a, [wFtCueColor]
    ld [bc], a
    inc bc
    ld a, [wFtCueColor + 1]
    ld [bc], a
    inc bc
.next:
    inc e
    ld a, e
    cp 4
    jr nz, .col
    pop de
    ld a, [wFtCueN]
    dec a
    ld [wFtCueN], a
    jr nz, .pal
    ret

ENDC

; His palettes late (hFtPalLate): wait for a line's HBlank, interrupts off (none may push the bytes past it); else
; at once. FtPalDone: interrupts back after.
FtPalWait:
    ldh a, [hFtPalLate]
    and a
    ret z
.drawing:
    ldh a, [rSTAT]
    and 3
    cp 3
    jr nz, .drawing
    di
    ldh a, [rSTAT]          ; (still drawing, interrupts off: else one just ran past this line's HBlank)
    and 3
    cp 3
    jr z, .wait
    ei
    jr .drawing
.wait:
    ldh a, [rSTAT]
    and 3
    jr nz, .wait
    ret
FtPalDone:
    ldh a, [hFtPalLate]
    and a
    ret z
    ei
    ret

IF DEF(FT_NES)
; (VBlank) the original: no palettes of his own, so his dodge cue goes in the screen's greys for his lines only
; (FtStat): his black as the grey touching it least in his pictures (RivalCueSrc), so it reads. Any left up, back.
FtCueGrey:
    call FtCueOff
    ldh a, [hIsCGB]
    and a
    ret nz
    ld hl, wFtCueHold       ; (up 4 frames at the least: a frame or two of it the LCD would barely show)
    ld a, [wNesCue]
    and a
    jr z, .held
    ld [hl], 3
    jr .up
.held:
    or [hl]
    jr z, .set
    dec [hl]
.up:
    ld a, [RivalCueSrc]
.set:
    ldh [hFtCueSrc], a
    and a                   ; (his top rows' sprites in it from the frame's top: over the crowd too, not only below
    ret z                   ;  the ropes)
    jp FtStat.cueObj

; (FtStat, interrupts) his cue's greys taken down, if up. Keeps BC, DE, HL.
FtCueOff:
    ldh a, [hFtCueOn]
    and a
    ret z
    rra
    jr nc, .obj
    ldh a, [hFtBgp]
    ldh [rBGP], a
.obj:
    ldh a, [hFtCueOn]
    and 2
    jr z, .done
    ldh a, [hFtObp]
    ldh [rOBP0], a
.done:
    xor a
    ldh [hFtCueOn], a
    ret

; (FtStat) A = a palette (BGP, OBP0), C = 2 or 4: its 3's shade made its 1's (2) or 2's (4). Keeps DE, HL.
FtCueMap:
    ld b, a
.shift:
    srl a
    dec c
    jr nz, .shift
    and 3
    rrca
    rrca
    ld c, a
    ld a, b
    and $3F
    or c
    ret

; A = 2 while his dodge cue is up (the NES's $C440: his outline in its color, wNesCue), else 0.
FtTellShown:
    ld a, [wFtCueHold]      ; (the original's: held as its greys are -- Color's never held)
    ld b, a
    ld a, [wNesCue]
    or b
    ret z
    ld a, 2
    ret
ENDC

; ---- VBlank: sprites, then the rival's pose or the HUD ----

DEF FT_PIC_IDLE EQU $4001
DEF FT_PIC_FRAMES EQU $4010
DEF FT_PIC_PLACEX EQU $4210
DEF FT_PIC_PLACEY EQU $4410
DEF FT_PIC_TABLE EQU $4610
DEF FT_PIC_HEADS EQU $4810
DEF FT_PIC_JEWEL EQU $4910     ; (Great Tiger's: per picture where his gem shows: x, y, $FF not)
DEF FT_PIC_VRAM EQU $8800      ; his tiles' two copies (bank 1: tiles 128-191, 192-255)
DEF FT_PIC_VRAM2 EQU $8C00
DEF FT_VBL_LAST EQU 149        ; the last line VBlank's lesser work (a HUD redraw, 4 tiles of the referee's) may start
DEF FT_MAC_PIC_ROOM EQU 32     ; Mac's: each copy's tiles (bank 1's sprite tiles, 0 on)
DEF FT_DMG_MAC_ROOM EQU 18     ; the original's: each copy's (sprite tiles FT_OBJ_FIRST on)
DEF FT_DPIC_NEXT EQU $4310     ; (and per picture its likely next: PicNextDmg)
DEF FT_DPIC_PLACEX EQU $4490   ; (and per NES frame, then mirrored, where its grey picture sits: x, then y 512 on)
DEF FT_DPIC_TABLE EQU $4010    ; the original's grey pictures: per picture its tiles (address, bank, count), sprites
DEF FT_PIC_WHOLE EQU 60        ; a picture of up to this many tiles goes up in one VBlank, its tiles and all

FtVBlank:
IF DEF(FT_NES)
    ld a, [wFtCueTile]      ; (the crowd's tell: its cell, first, on the frame it's due, as the NES's)
    and a
    jr z, .noCue
    ld a, [wFtCueCol]
    ld l, a
    ld h, HIGH($9800 + 30 * 32)
    ld a, l
    add LOW($9800 + 30 * 32)
    ld l, a
    ld a, [wFtCue]
    ld [hl], a
.noCue:
    call FtCueGrey          ; (the original: his dodge cue as greys in his lines, the frame's splits')
    call FtDmgSwitch        ; (the original: his next grey picture's rows, before the sprites built for it)
ENDC
IF DEF(FT_MAC_PICS)
    call FtPlPicSwitch      ; (Mac's next picture, readied: few tiles, first)
ENDC
IF DEF(FT_NES)
    call FtPicSwitch        ; (his rival's: before the sprites built for both)
    ld [wFtPicDrew], a
ENDC
IF DEF(FT_DMG_WHITE)
    ldh a, [hFtObp1]        ; (the original: OBP1's 1 the mat's white over his top rows, his eyes' whites; the
    ld b, a                 ; lower sprites' back at FT_DMA_LINE)
    and %11110011
    ld c, a
    ld a, b
    and %11
    add a
    add a
    or c
    ldh [rOBP1], a
ENDC
    ldh a, [rIE]            ; (the crowd's timer held off through the DMA: mid-DMA the CPU can't fetch from ROM,
    push af                 ; where its handler is; it runs straight after)
    and ~%100
    ldh [rIE], a
    ld a, HIGH(wFtOAM)
    call hOAMDMA
    pop af
    ldh [rIE], a
    ldh a, [hFtScx]
    ldh [rSCX], a
    xor a                   ; (the frame's splits from the top, whatever the last one missed)
    ldh [rSCY], a
    ldh [hFtBandOn], a
    ldh a, [hFtBandTop]
    ldh [rLYC], a
    ldh a, [hFtBandX]       ; his band as this frame shows it: taken now, with the sprites built with it (set
    ldh [hFtShowX], a       ; mid-frame, it would move before them)
    ldh a, [hFtBandY]
    ldh [hFtShowY], a
    ldh a, [hFtBandBottom]
    ldh [hFtShowBottom], a
IF DEF(FT_ROPE)
    ldh a, [hFtOamBuild]    ; the lower list just built: shown from this frame; the next built in the other
    ldh [hFtOamShown], a
    xor HIGH(wFtOAM2) ^ HIGH(wFtOAM3)
    ldh [hFtOamBuild], a
ENDC
    ldh a, [hFtFlash]       ; Color: the rival flashes white when a punch lands
    and a
    jr z, .noFlash
    dec a
    ldh [hFtFlash], a
.noFlash:
    and a
    jr z, .flashOff
    ld a, 1
    jr .flashSet
.flashOff:
IF DEF(FT_NES)
    call FtTellShown        ; (his tell, a palette change in the NES's: while its frame and state are up)
ENDC
.flashSet:
    ld hl, hFtFlashShown    ; (before his picture's tiles: a few bytes, on the frame the NES has them, where
    cp [hl]                 ; his tiles take what's left)
    jr z, .pics
    ld b, a
    ldh a, [rLY]            ; (his palettes and his top rows' sprites': 5 lines at most; too late in this
    sub 144                 ; VBlank, or past it, the next one's)
    cp 149 - 144
    ld a, b
    ld [hl], a
    jr c, .flashNow
    ld a, 1                 ; (missed, his new picture's tiles taking it: in the next frame's top lines, above his
    ldh [hFtPalLate], a     ; rows, on time still)
    call FtFlashPalettes
    xor a
    ldh [hFtPalLate], a
    jr .pics
.flashNow:
    call FtFlashPalettes    ; (and his pose too: his top rows' sprites show the one asked for)
.pics:
IF DEF(FT_NES)
    ld a, [wFtPicDrew]      ; Color, his NES pictures: a big one's tiles, a VBlank's room at a time (NZ: spent)
    and a
    jr nz, .picDone
    call FtPicVBlank
    ld [wFtPicDrew], a
.picDone:
ENDC
.pose:
IF DEF(FT_NES)
    ld a, [wFtPicDrew]      ; (a picture drawn: this VBlank's spent, the rest in the next)
    and a
    ret nz
ENDC
    ldh a, [rLY]            ; (what's left takes a few lines: too late in this VBlank, or past it, the next
    sub 144                 ; one's; a fade's palettes, say, went first)
    cp FT_VBL_LAST - 144
    ret nc
IF DEF(FT_NES)
    ldh a, [hIsCGB]         ; (the original: its pictures' rows leave room for one of these, the HUD first when
    and a                   ;  it's waiting -- the crowd's turn the frame after; else the clock never moved)
    jr nz, .crowd
    ldh a, [hFtHudReady]
    and a
    jr nz, .lesser
.crowd:
ENDC
    call FtCrowdDraw
IF DEF(FT_NES)
    call FtCrowdPulse
ENDC
    ldh a, [rLY]
    sub 144
    cp FT_VBL_LAST - 144
    ret nc
.lesser:
IF DEF(FT_NES)
    ld a, [wFtBankPics]     ; (Color with his pictures: drawn above, no poses; the original with its greys too)
    and a
    jr z, .poses
    ldh a, [hIsCGB]
    and a
    jr nz, .hud
    ld a, [wFtBankPicsDmg]
    and a
    jr nz, .hud
.poses:
ENDC
    ld a, [wRvPose]
    ld hl, wRvShown
    cp [hl]
    jr z, .hud
    ld [hl], a
    jp FtDrawPose
.hud:
    call FtSwapStep
    ret nz
    ld a, [wPlRareLoad]     ; the player's rare pose loading: before the HUD (his star punch's frames come fast)
    cp $FF
    jp nz, FtPlStep
    ldh a, [hFtHudReady]
    and a
    jr z, .ref
    xor a
    ldh [hFtHudReady], a
    jp FtHudDraw
.ref:                       ; nothing else to do: the player's rare pose, or the referee's next one, a few tiles in
    ld a, [wPlRareLoad]
    cp $FF
    jp nz, FtPlStep
    ld a, [wPlRareWant]
    cp $FF
    jr z, .refPose
    ld hl, wPlRareIn
    cp [hl]
    jr z, .rareIn
    ld [wPlRareLoad], a
    ld a, $FF               ; (its area isn't the one in it any more)
    ld [hl], a
    xor a
    ld [wPlRareDone], a
    jp FtPlStep
.rareIn:
    ld a, $FF
    ld [wPlRareWant], a
.refPose:
    ldh a, [rLY]            ; (a step's 4 tiles take about 5 lines: none started past line 147, or past VBlank)
    sub 144
    cp 148 - 144
    ret nc
    ld a, [wFtRefLoad]
    cp $FF
    jp nz, FtRefStep
    ld a, [wFtRefPose]
    ld hl, wFtRefShown
    cp [hl]
    ret z
    ld [wFtRefLoad], a
    xor a
    ld [wFtRefDone], a
    jp FtRefStep

; A = the player's pose to draw: his pose, or (a rare one whose tiles aren't in yet: asked for) his last other.
FtPlShown:
IF DEF(FT_PL_CGB)
    ldh a, [hIsCGB]         ; (Color: every pose's tiles are in, but those it shares with the original: loaded)
    and a
    jr z, .dmg
    ld a, [wPlPose]
    ld e, a
    ld d, 0
    push hl
    ld hl, PlayerCgbShared
    add hl, de
    ld a, [hl]
    pop hl
    and a
    jr nz, .dmg
    ld a, e
    ld [wPlRegular], a
    ret
.dmg:
ENDC
    ld a, [wPlPose]
    ld e, a
    ld d, 0
    push hl
    ld hl, PlayerRare
    add hl, de
    ld a, [hl]
    pop hl
    and a
    jr nz, .rare
    ld a, e
    ld [wPlRegular], a
    ret
.rare:
    ld a, [wPlRareIn]
    cp e
    ld a, e
    ret z
    ld [wPlRareWant], a
    push hl                 ; while it loads: the one in, if both are of one sequence (held, not back to standing)
    push bc
    ld hl, PlayerRareHold
    add hl, de
    ld a, [hl]
    and a
    jr z, .regularBc
    ld b, a
    ld a, [wPlRareIn]
    cp $FF
    jr z, .regularBc
    ld e, a
    ld hl, PlayerRareHold
    add hl, de
    ld a, [hl]
    cp b
    ld a, e
    pop bc
    pop hl
    ret z
    push hl
    jr .regular
.regularBc:
    pop bc
.regular:
    pop hl
    ld a, [wPlRegular]
    ret

; The player's rare pose loading (wPlRareLoad) into its area: FT_REF_STEP tiles a call; once all are in, it shows.
FtPlStep:
    ld a, [wFtBankData]
    ld [$2000], a
    ld a, [wPlRareLoad]
    ld l, a
    add a
    add l                   ; 3 bytes an entry: its tiles' address and count
    ld e, a
    ld d, 0
    ld hl, RareTiles
    add hl, de
    ld a, [hl+]
    ld e, a
    ld a, [hl+]
    ld d, a
    ld a, [hl]
    ld hl, wPlRareDone
    sub [hl]
    jr z, .in
    cp FT_REF_STEP + 1
    jr c, .some
    ld a, FT_REF_STEP
.some:
    ld b, a
    ld a, [hl]
    add b
    ld c, [hl]
    ld [hl], a
    ld l, c
    ld h, 0
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, de
    push hl
    ld a, FT_PL_SLOT
    add c
    ld l, a
    ld h, 0
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, hl
    ld de, $8000
    add hl, de
    ld d, h
    ld e, l
    pop hl
.tile:
    REPT 16
        ld a, [hl+]
        ld [de], a
        inc de
    ENDR
    dec b
    jr nz, .tile
    jr .back
.in:
    ld a, [wPlRareLoad]
    ld [wPlRareIn], a
    ld a, $FF
    ld [wPlRareLoad], a
    ld [wPlRareWant], a
.back:
    ld a, [wFtBankData]
    ld [$2000], a
    ret

; The referee's pose loading (wFtRefLoad) into his slot not shown: FT_REF_STEP tiles a call; once all are in,
; that slot shows it.
DEF FT_REF_STEP EQU 4
FtRefStep:
    ld a, [wFtBankData]
    ld [$2000], a
    ld a, [wFtRefLoad]
    ld l, a
    add a
    add l                   ; 3 bytes an entry: its tiles' address and count
    ld e, a
    ld d, 0
    ld hl, RefTiles
    add hl, de
    ld a, [hl+]
    ld e, a
    ld a, [hl+]
    ld d, a
    ld a, [hl]              ; the count
    ld hl, wFtRefDone
    sub [hl]                ; left to load
    jr z, .shown
    cp FT_REF_STEP + 1
    jr c, .some
    ld a, FT_REF_STEP
.some:
    ld b, a                 ; B = tiles this time
    ld a, [hl]
    add b
    ld c, [hl]              ; C = the first of them
    ld [hl], a
    ld l, c                 ; DE = its data + 16 * C
    ld h, 0
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, de
    push hl
    ld a, [wFtRefSlot]      ; HL = the other slot's tile C
    xor 1
    ld e, FT_REF_SLOT
    jr z, .slot
    ld e, FT_REF_SLOT + FT_REF_TILES
.slot:
    ld a, e
    add c
    ld l, a
    ld h, 0
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, hl
    ld de, $8000
    add hl, de
    ld d, h
    ld e, l
    pop hl
.tile:
    REPT 16
        ld a, [hl+]
        ld [de], a
        inc de
    ENDR
    dec b
    jr nz, .tile
    jr .back
.shown:                     ; all in: that slot shows it (the sprites built from here on)
    ld a, [wFtRefSlot]
    xor 1
    ld [wFtRefSlot], a
    ld a, [wFtRefLoad]
    ld [wFtRefShown], a
    ld a, $FF
    ld [wFtRefLoad], a
.back:
    ld a, [wFtBankData]   ; (the fight's bank back)
    ld [$2000], a
    ret

; The referee's pose A into slot 0, all of it, shown (the screen off: setting up the fight).
FtRefFirst:
    ld [wFtRefPose], a
    ld [wFtRefLoad], a
    ld a, 1                 ; (slot 1 "shown": the load goes to slot 0, then shows)
    ld [wFtRefSlot], a
    xor a
    ld [wFtRefDone], a
.more:
    FT_VWAIT 64 + FT_ROOM_OVER  ; (a step: its 4 tiles, about 500 cycles)
    call FtRefStep
    ld a, [wFtRefLoad]
    cp $FF
    jr nz, .more
    ret

IF DEF(FT_NES)
; ---- Color, an NES fighter: his pictures, exact (each its own tiles, streamed as the game draws it) ----
; Their bank's header ($4000, wFtBankPics): count and the idle one's number, then per NES frame (then drawn
; mirrored) its picture ($FF: keep the one up), its place's x and y offsets; per picture its tiles' address,
; bank and count (its map rows and their attributes right after its tiles); per picture its top rows' sprites.

; Two copies of his area's tiles (bank 1, FT_PIC_VRAM and FT_PIC_VRAM2: wRvPicBuf the one on the map). A new
; picture's tiles go into the other, a VBlank's room at a time (FtPicVBlank); once all are in, the frame's
; sprites are built for it (FtPicDecide: his top rows, his place) and the next VBlank starts with its map rows
; (FtPicSwitch), before those sprites go up: never half drawn, never a head of the last picture's.

; His picture's entry (A): BC its tiles, D their bank, E how many (his pictures' bank mapped).
FtPicEntry:
    ld l, a
    ld a, [wFtBankPics]
    ld [$2000], a
    ld h, 0
    add hl, hl
    add hl, hl
    ld bc, FT_PIC_TABLE
    add hl, bc
    ld a, [hl+]
    ld c, a
    ld a, [hl+]
    ld b, a
    ld a, [hl+]
    ld d, a
    ld e, [hl]
    ret

; In VBlank, after the sprites: the wanted picture's tiles into the copy not shown, as many as there's room for
; (DMA blocks, 8 cycles each: 14 a line, done in its last line, 153). A nonzero: this VBlank's spent.
FtPicVBlank:
    ld a, [wFtBankPics]
    and a
    ret z
    ldh a, [hIsCGB]
    and a
    ret z
    ld a, [wRvPose]         ; (the original's pose kept as shown: it isn't drawn)
    ld [wRvShown], a
    ld a, [wRvPic]
    ld hl, wRvPicShown
    cp [hl]
    jr nz, .want
    ld a, [wRvPicLoad]      ; the one shown: but one left coming in (a frame gone by): its tiles on in, so a frame
    cp [hl]                 ; that flickers back to it finds it whole (wRvPicHidden)
    jr z, .idle
    inc a
    jr z, .idle
    dec a
    ld hl, wRvPicHidden
    cp [hl]
    jr nz, .going
.idle:
    ld a, [wRvPicShown]
    ld [wRvPicLoad], a      ; (none to load)
    xor a
    ret
.want:
    ld hl, wRvPicHidden      ; (whole in the copy not shown: FtPicDecide puts it up, nothing to load)
    cp [hl]
    jr nz, .notSpare
    xor a
    ret
.notSpare:
    ld hl, wRvPicLoad
    cp [hl]
    jr z, .going
    ld [hl], a              ; another: from its first tile, and where it sits
    xor a
    ld [wRvPicDone], a
    ld a, [wRvPicWantX]
    ld [wRvPicLoadX], a
    ld a, [wRvPicWantY]
    ld [wRvPicLoadY], a
.going:
    ld a, [wRvPicLoad]
    call FtPicEntry
    ld a, [wRvPicDone]
    cp e
    jp nc, .none            ; (all in)
    cpl
    inc a
    add e
    ld e, a                 ; E = tiles left
    ldh a, [rLCDC]          ; (the screen off: room for all)
    add a
    ld l, 255
    jr nc, .room
    ldh a, [rLY]
    sub 144
    jp c, .none             ; (VBlank's over: the next one's)
    cp 9
    jp nc, .none            ; (too late: the next VBlank)
    ld l, a
    ld a, 9
    sub l                   ; lines left before 153 (its last: done in it)
    ld l, a
    add a
    add a
    add a                   ; * 14, less 4 for what's between
    sub l
    sub l
    sub 4
    jp c, .none
    ld l, a
.room:                      ; L = blocks of room
    ld a, e
    cp l
    jr c, .some
    ld a, l
.some:
    and a
    jp z, .none
    ld [wFtPicGo], a        ; this time's
    ld a, $FF               ; (the copy not shown written over: its last picture gone)
    ld [wRvPicHidden], a
    ld a, d
    ld [$2000], a
    ld a, [wRvPicDone]      ; from its tile wRvPicDone, into the copy not shown
    ld l, a
    ld h, 0
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, hl
    push hl
    add hl, bc
    ld a, h
    ldh [rHDMA1], a
    ld a, l
    ldh [rHDMA2], a
    pop hl
    ld a, [wRvPicBuf]
    and a
    ld bc, FT_PIC_VRAM2
    jr z, .to
    ld bc, FT_PIC_VRAM
.to:
    add hl, bc
    ld a, 1
    ldh [rVBK], a
    ld a, h
    ldh [rHDMA3], a
    ld a, l
    ldh [rHDMA4], a
    ld a, [wFtPicGo]
    dec a
    ldh [rHDMA5], a
    xor a
    ldh [rVBK], a
    ld a, [wFtPicGo]
    cp e
    jr nz, .part
    ld a, [wRvPicLoad]      ; (its last: whole in the copy not shown)
    ld [wRvPicHidden], a
    ld a, [wFtPicGo]
.part:
    ld hl, wRvPicDone
    add [hl]
    ld [hl], a
    ld a, [wFtBankData]
    ld [$2000], a
    ld a, 1
    ret
.none:
    ld a, [wFtBankData]
    ld [$2000], a
    xor a
    ret

; As the frame's sprites are built (after the NES frame): the picture whose tiles are all in, if not the one shown,
; goes up next VBlank: its top rows' sprites (wRvPicHeads, in wRvPicHeadsBuf's copy) and its place now.
FtPicDecide:
    ld a, [wFtBankPics]
    and a
    ret z
    ldh a, [hIsCGB]
    and a
    ret z
    xor a
    ld [wRvPicSwitch], a
    ld a, [wRvPic]          ; a new one, small enough: all of it next VBlank (its tiles, rows, then the sprites)
    ld hl, wRvPicShown
    cp [hl]
    jp z, .keep
    ld hl, wRvPicHidden      ; the one shown before, whole still in the copy not shown: straight back up (a frame
    cp [hl]                 ; that flickers between two, as the NES's do, keeps up)
    jp z, .spare
    ld hl, wRvPicLoad
    cp [hl]
    jp z, .loading
    call FtPicEntry
    ld a, e
    cp FT_PIC_WHOLE + 1
    jp nc, .loaded          ; (too many: a VBlank's room at a time, FtPicVBlank)
IF DEF(FT_MAC_PICS)
    ld a, [wPlPicGo]        ; Mac's tiles going up in that VBlank too, and no room for both: his wait a frame
    add e                   ; (his rival's on time: his are few, and up the VBlank after)
    cp FT_PIC_WHOLE + 1
    call nc, FtPlPicWait
ENDC
    ld a, [wRvPic]
    ld [wRvPicLoad], a
    xor a
    ld [wRvPicDone], a
    ld a, [wRvPicWantX]
    ld [wRvPicLoadX], a
    ld a, [wRvPicWantY]
    ld [wRvPicLoadY], a
    jp .up
.spare:
    ld [wRvPicLoad], a
    call FtPicEntry
    ld a, e
    ld [wRvPicDone], a
    ld a, [wRvPicWantX]
    ld [wRvPicLoadX], a
    ld a, [wRvPicWantY]
    ld [wRvPicLoadY], a
    jp .up
.loading:                   ; the one wanted, coming in: up with the rest of its tiles, once they fit a VBlank
    call FtPicEntry         ; (FtPicSwitch's: a frame sooner than once they're all in)
    ld a, [wRvPicDone]
    cpl
    inc a
    add e
    cp FT_PIC_WHOLE + 1
    jp nc, .keep
IF DEF(FT_MAC_PICS)
    ld hl, wPlPicGo         ; (Mac's going up then too, and no room for both: his wait a frame)
    add [hl]
    cp FT_PIC_WHOLE + 1
    call nc, FtPlPicWait
ENDC
    jp .up
.loaded:                    ; the one coming in, not wanted now: up once its tiles are
    ld a, [wRvPicLoad]
    ld hl, wRvPicShown
    cp [hl]
    jp z, .keep
    call FtPicEntry
    ld a, [wRvPicDone]
    cp e
    jp c, .keep
.up:
    call FtPicReady
    ld a, 1
    ld [wRvPicSwitch], a
    ld a, [wRvPicLoad]
    ld [wRvPicHeads], a
    ld a, [wRvPicBuf]
    xor 1
    ld [wRvPicHeadsBuf], a
    ld a, [wRvPicLoadX]
    ld [wRvPlaceX], a
    ld a, [wRvPicLoadY]
    ld [wRvPlaceY], a
    jp .out
.keep:
    ld a, [wRvPicShown]
    ld [wRvPicHeads], a
    ld a, [wRvPicBuf]
    ld [wRvPicHeadsBuf], a
.out:
    ld a, [wFtBankNes]
    ld [$2000], a
    ret

; VBlank's first, before the sprites: the picture FtPicDecide readied: its tiles, if not all in (FT_PIC_WHOLE at
; most: under 4.3 lines), then onto the map (his rows, for its tiles' copy, then their attributes: 40 DMA blocks,
; under 3 lines); then the sprites (1.5 lines). A nonzero: done.
FtPicSwitch:
    ld a, [wRvPicSwitch]
    and a
    ret z                   ; (A zero: none)
    xor a
    ld [wRvPicSwitch], a
    ld a, [wRvSwBank]
    ld [$2000], a
    ld hl, wRvSwTiles
    ld a, [wRvSwN]          ; its tiles not all in: the rest, into the copy not shown
    and a
    jr z, .rows
    ld a, 1
    ldh [rVBK], a
    ld a, [hl+]
    ldh [rHDMA1], a
    ld a, [hl+]
    ldh [rHDMA2], a
    ld a, [hl+]
    ldh [rHDMA3], a
    ld a, [hl+]
    ldh [rHDMA4], a
    ld a, [wRvSwN]
    dec a
    ldh [rHDMA5], a
.rows:                      ; then his rows, then their attributes
    xor a
    ldh [rVBK], a
    ld hl, wRvSwRows
    call .copy
    ld a, 1
    ldh [rVBK], a
    call .copy
    xor a
    ldh [rVBK], a
    ld a, [wRvPicBuf]
    xor 1
    ld [wRvPicBuf], a
    ld a, [wRvPicShown]     ; (the one going down: whole in the copy now not shown)
    ld [wRvPicHidden], a
    ld a, [wRvPicLoad]
    ld [wRvPicShown], a
    ld a, [wFtBankData]
    ld [$2000], a
    ld a, 1                 ; (A nonzero: done, this VBlank's spent)
    ret
.copy:                      ; HL: a source's address (HL past it after)
    ld a, [hl+]
    ldh [rHDMA2], a
    ld a, [hl+]
    ldh [rHDMA1], a
    ld a, HIGH(FT_REGION_ROW)
    ldh [rHDMA3], a
    ld a, LOW(FT_REGION_ROW)
    ldh [rHDMA4], a
    ld a, FT_PIC_BYTES / 16 - 1
    ldh [rHDMA5], a
    ret

; The picture going up next VBlank (wRvPicLoad): its copies worked out now, so VBlank's time is all DMA.
FtPicReady:
    ld a, [wRvPicLoad]
    call FtPicEntry         ; BC its tiles, D bank, E count
    ld a, d
    ld [wRvSwBank], a
    ld a, [wRvPicDone]      ; tiles still to come: from the one wRvPicDone on
    ld l, a
    cpl
    inc a
    add e
    ld [wRvSwN], a
    ld a, e
    ld [wRvPicDone], a      ; (all in, once VBlank's done)
    ld h, 0
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, hl
    push hl
    add hl, bc
    ld a, h
    ld [wRvSwTiles], a
    ld a, l
    ld [wRvSwTiles + 1], a
    pop hl
    ld a, [wRvPicBuf]       ; into the copy not shown
    and a
    push bc
    ld bc, FT_PIC_VRAM2
    jr z, .to
    ld bc, FT_PIC_VRAM
.to:
    add hl, bc
    pop bc
    ld a, h
    ld [wRvSwTiles + 2], a
    ld a, l
    ld [wRvSwTiles + 3], a
    ld l, e                 ; its rows (after its tiles): for the first copy's tiles, their attributes, for the
    ld h, 0                 ; second's
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, bc
    push hl
    ld bc, FT_PIC_BYTES
    add hl, bc
    ld a, l
    ld [wRvSwAttr], a
    ld a, h
    ld [wRvSwAttr + 1], a
    pop hl
    ld a, [wRvPicBuf]
    and a
    jr nz, .rowsSet         ; (shown: the second copy; going up: the first)
    ld bc, 2 * FT_PIC_BYTES
    add hl, bc
.rowsSet:
    ld a, l
    ld [wRvSwRows], a
    ld a, h
    ld [wRvSwRows + 1], a
    ret

; The first picture, as the fight sets up (loading, black): NZ if he has pictures (Color), up.
FtPicsStart:
    ld a, [wFtBankPics]
    and a
    ret z
    ldh a, [hIsCGB]
    and a
    ret z
    ld a, [wFtBankPics]
    ld [$2000], a
    ld a, [FT_PIC_IDLE]
    ld [wRvPic], a
    ld a, $FF               ; (none shown, none loading: the second copy's the one not shown)
    ld [wRvPicShown], a
    ld [wRvPicLoad], a
    ld [wRvPicHidden], a
    ld a, 1
    ld [wRvPicBuf], a
.tiles:
    FT_VWAIT FT_ROOM_ALL
    call FtPicVBlank
    ld a, [wRvPicLoad]
    call FtPicEntry
    ld a, [wRvPicDone]
    cp e
    jr c, .tiles
    call FtPicReady
    FT_VWAIT FT_ROOM_ALL
    ld a, 1
    ld [wRvPicSwitch], a
    call FtPicSwitch
    ld a, [wRvPicShown]
    ld [wRvPicHeads], a
    ld a, [wRvPicBuf]
    ld [wRvPicHeadsBuf], a
    or 1
    ret

; His picture for the NES frame just drawn (C = frame, B = drawn mirrored): wRvPic and where it sits (once it's
; up: FtPicDecide). Carry set if he has pictures (Color); the NES bank mapped after.
FtNesPic:
    ld a, [wFtBankPics]
    and a
    ret z
    ldh a, [hIsCGB]
    and a
    jr nz, .pics
    ld a, [wFtBankPicsDmg]  ; (the original: its grey pictures, by the same frames)
    and a
    ret z
.pics:
    ld a, [wFtBankPics]
    ld [$2000], a
    ld hl, FT_PIC_FRAMES
    add hl, bc
    ld a, [hl]
    cp $FF
    jr z, .keep             ; (a frame he has no picture for: the one up stays)
    ld d, a                 ; (bit 7: drawn in his dodge cue's colors, as another's picture: wNesCue's bit 1 while
    and $7F                 ; it's up, the cue's palettes and greys with it)
    ld [wRvPic], a
    ld a, d
    rlca
    and 1
    add a
    ld d, a
    ld a, [wNesCue]
    and 1
    or d
    ld [wNesCue], a
    ld hl, FT_PIC_PLACEX    ; and where it sits (the original: its grey picture's own place, FT_DPIC_PLACEX)
    ldh a, [hIsCGB]
    and a
    jr nz, .place
    ld a, [wFtBankPicsDmg]
    ld [$2000], a
    ld hl, FT_DPIC_PLACEX
.place:
    add hl, bc
    ld a, [hl]
    ld [wRvPicWantX], a
    inc h                   ; (y: 512 on, in both)
    inc h
    ld a, [hl]
    ld [wRvPicWantY], a
.keep:
    ld a, [wFtBankNes]
    ld [$2000], a
    scf
    ret

; ---- the original, an NES fighter: his pictures in greys (FT_DPIC_*), two copies of his tiles as Color's (tiles
; 128-191, 192-255: his top rows' sprites reach them too); a new picture's tiles streamed into the copy not shown
; out of the frame's work, in each line's quiet part (FtDmgStream); once all are in, up at the next VBlank ----

; His grey picture's entry (A): BC its tiles, D their bank, E how many; HL at its sprites' address (header mapped).
FtDmgEntry:
    ld l, a
    ld h, 0
    ld a, [wFtBankPicsDmg]
    ld [$2000], a
    ld b, h
    ld c, l
    add hl, hl
    add hl, bc
    add hl, hl              ; (6 bytes each)
    ld bc, FT_DPIC_TABLE
    add hl, bc
    ld a, [hl+]
    ld c, a
    ld a, [hl+]
    ld b, a
    ld a, [hl+]
    ld d, a
    ld a, [hl+]
    ld e, a
    ret

; As the frame's sprites are built: a new picture wanted starts coming in; one all in goes up next VBlank.
FtDmgDecide:
    ldh a, [hIsCGB]
    and a
    ret nz
    ld a, [wFtBankPicsDmg]
    and a
    ret z
    xor a
    ld [wRvPicSwitch], a
    ld a, [wRvPic]
    ld hl, wRvPicShown
    cp [hl]
    jp z, .shown
    ld hl, wRvPicLoad
    cp [hl]
    jp z, .wanted
    ld b, a
    ld a, [wRvPicHidden]    ; (whole already: straight to it)
    cp b
    jp z, .another
    ld a, [wRvPicLoadWanted] ; one the game drew still coming in: it first, up late, not lost (a frame it shows
    and a                   ; for two, his fists' roll; then the two flicker from the copies, whole)
    jp nz, .loading
.another:
    ld a, b
    ld [hl], a              ; another: from its first tile (the copy not shown), and where it'll sit
    ld a, 1
    ld [wRvPicLoadWanted], a
    ld a, [wRvPicWantX]
    ld [wRvPicLoadX], a
    ld a, [wRvPicWantY]
    ld [wRvPicLoadY], a
    ld a, [wRvPicHidden]    ; (the one whole in the copy not shown, the last one up: all in already)
    ld b, a
    ld a, [hl]
    cp b
    jp z, .whole
    xor a
    ld [wRvPicDone], a
    dec a
    ld [wRvPicHidden], a    ; (that copy's being written over)
    jp .keep
.whole:
    call FtDmgEntry
    ld a, e
    ld [wRvPicDone], a
    jp .loading
.wanted:                    ; (the one coming in, perhaps early: where it sits now it's wanted)
    ld a, 1
    ld [wRvPicLoadWanted], a
    ld a, [wRvPicWantX]
    ld [wRvPicLoadX], a
    ld a, [wRvPicWantY]
    ld [wRvPicLoadY], a
.loading:
    ld a, [wRvPicLoad]      ; (its entry: its count)
    call FtDmgEntry
    ld a, [wRvPicDone]
    cp e
    jp c, .keep             ; (not all in yet)
    xor a
    ld [wRvPicLoadWanted], a
    inc a
    ld [wRvPicSwitch], a
    ld a, [wRvPicLoad]
    ld [wRvPicHeads], a
    ld a, [wRvPicBuf]
    xor 1
    ld [wRvPicHeadsBuf], a
    ld a, [wRvPicLoadX]
    ld [wRvPlaceX], a
    ld a, [wRvPicLoadY]
    ld [wRvPlaceY], a
    jp .out
.shown:
    call FtDmgPrefetch
.keep:
    ld a, [wRvPicShown]
    ld [wRvPicHeads], a
    ld a, [wRvPicBuf]
    ld [wRvPicHeadsBuf], a
.out:
    ld a, [wFtBankNes]
    ld [$2000], a
    ret

; The one wanted up, the copy not shown idle: the picture likely next (FT_DPIC_NEXT) into it, early.
FtDmgPrefetch:
    ld a, [wRvPicLoad]
    ld hl, wRvPicShown
    cp [hl]
    ret nz                  ; (one coming in, or in, already)
    ld a, [wFtBankPicsDmg]
    ld [$2000], a
    ld a, [hl]
    ld l, a
    ld h, 0
    ld b, h
    ld c, l
    add hl, hl
    add hl, bc
    ld bc, FT_DPIC_NEXT
    add hl, bc
    ld a, [hl+]             ; its next; or, after the one before it, the one then
    ld b, a
    ld a, [hl+]
    ld c, a
    ld a, [wRvPicPrev]
    cp c
    ld a, b
    jr nz, .got
    ld a, [hl]
.got:
    cp $FF
    ret z
    ld hl, wRvPicShown
    cp [hl]
    ret z
    ld hl, wRvPicHidden     ; (whole in that copy already)
    cp [hl]
    ret z
    ld [wRvPicLoad], a
    xor a
    ld [wRvPicDone], a
    ld [wRvPicLoadWanted], a
    dec a
    ld [wRvPicHidden], a
    ret

; VBlank's first: the picture readied onto the map (its 12 rows of 8, from its tiles' copy's rows).
FtDmgSwitch:
    ldh a, [hIsCGB]         ; (the original only: Color's is FtPicSwitch)
    and a
    ret nz
    ld a, [wRvPicSwitch]
    and a
    ret z
    xor a
    ld [wRvPicSwitch], a
    ld a, [wRvPicLoad]
    call FtDmgEntry
    ld a, d
    ld [$2000], a
    ld l, e                 ; HL = its rows: after its tiles, for the first copy; the second's after those
    ld h, 0
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, bc
    ld a, [wRvPicBuf]
    and a
    jr nz, .rows            ; (shown: the second copy; going up: the first)
    ld bc, FT_REGION_W * FT_PIC_ROWS
    add hl, bc
.rows:
    call FtDmgRows
    ld a, [wRvPicBuf]
    xor 1
    ld [wRvPicBuf], a
    ld a, [wRvPicShown]     ; (the one going down: whole in the copy now not shown)
    ld [wRvPicHidden], a
    ld [wRvPicPrev], a
    ld a, [wRvPicLoad]
    ld [wRvPicShown], a
    ld a, [wFtBankData]
    ld [$2000], a
    ret

; A picture's 12 rows of 8 from HL onto the map.
FtDmgRows:
    ld de, FT_REGION_ROW + FT_REGION_X
    ld b, FT_DPIC_ROWS
.row:
    REPT FT_REGION_W
        ld a, [hl+]
        ld [de], a
        inc e
    ENDR
    ld a, e
    add 32 - FT_REGION_W
    ld e, a
    jr nc, .same
    inc d
.same:
    dec b
    jr nz, .row
    ret

; His first grey picture, as the fight sets up (the screen off): all of it, in the first copy.
FtDmgPicsStart:
    ldh a, [hIsCGB]
    and a
    ret nz
    ld a, [wFtBankPicsDmg]
    and a
    ret z
    ld a, [wFtBankPics]
    ld [$2000], a
    ld a, [FT_PIC_IDLE]
    ld [wRvPic], a
    ld [wRvPicShown], a
    ld [wRvPicLoad], a
    ld [wRvPicHeads], a
    xor a
    ld [wRvPicBuf], a
    ld [wRvPicHeadsBuf], a
    ld [wRvPicSwitch], a
    ld [wRvPicLoadWanted], a
    dec a
    ld [wRvPicHidden], a
    ld a, [wRvPicLoad]
    call FtDmgEntry
    ld a, e
    ld [wRvPicDone], a
    ld a, d
    ld [$2000], a
    ld h, b
    ld l, c
    ld de, FT_PIC_VRAM
    ld a, [wRvPicDone]
    ld b, a
    swap b                  ; (16 bytes a tile: B * 16, no more than 64 tiles' 1024)
    ld c, b
    ld a, c
    and $F0
    ld c, a
    ld a, b
    and $0F
    ld b, a
.byte:
    ld a, [hl+]
    ld [de], a
    inc de
    dec bc
    ld a, b
    or c
    jr nz, .byte
    call FtDmgRows          ; (HL: his rows for the first copy, after the tiles)
    ld a, [wFtBankData]
    ld [$2000], a
    ret


; The next tiles to stream (Mac's first: his few, then his rival's): HL their source (bank mapped), DE where they
; go, wFtStreamN the picture's count, wFtStreamDone its count in so far. Z: none.
FtDmgJob:
    ldh a, [hIsCGB]
    and a
    jr nz, .none
    ld a, [wFtBankPicsDmg]
    and a
    jr z, .none
IF DEF(FT_MAC_PICS)
    ld a, [wPlPicLoad]      ; Mac's
    ld hl, wPlPicShown
    cp [hl]
    jr z, .rival
    call FtPlPicEntry
    ld a, [wPlPicDone]
    cp e
    jr nc, .rival
    ld hl, wPlPicDone
    call .job
    ld a, [wPlPicBuf]       ; into his copy not shown: sprite tiles FT_OBJ_FIRST on, the second copy 18 on
    and a
    ld a, FT_OBJ_FIRST + FT_DMG_MAC_ROOM
    jr z, .macTo
    ld a, FT_OBJ_FIRST
.macTo:
    ld hl, wPlPicDone
    add [hl]
    ld l, a
    ld h, 0
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, hl
    ld a, h
    add HIGH($8000)
    ld d, a
    ld e, l
    pop hl                  ; (.job's source)
    jr .some
.rival:
ENDC
    ld a, [wRvPicLoad]      ; his rival's
    ld hl, wRvPicShown
    cp [hl]
    jr z, .none
    call FtDmgEntry
    ld a, [wRvPicDone]
    cp e
    jr nc, .none
    ld hl, wRvPicDone
    call .job
    pop hl
    push hl
    ld a, [wRvPicDone]      ; into the copy not shown
    ld l, a
    ld h, 0
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, hl
    ld a, [wRvPicBuf]
    and a
    ld bc, FT_PIC_VRAM2
    jr z, .to
    ld bc, FT_PIC_VRAM
.to:
    add hl, bc
    ld d, h
    ld e, l
    pop hl
.some:
    or 1
    ret
.none:
    xor a
    ret
.job:                       ; HL its count in; BC its tiles, D bank, E count: maps it, pushes the source (under the return)
    ld a, l
    ld [wFtStreamDone], a
    ld a, h
    ld [wFtStreamDone + 1], a
    ld a, e
    ld [wFtStreamN], a
    ld a, d
    ld [$2000], a
    ld a, [hl]              ; source: its tiles + done * 16
    ld l, a
    ld h, 0
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, bc
    pop bc                  ; (the return)
    push hl
    push bc
    ret

; A tile in: its count on (Z: the job's done).
FtDmgTileIn:
    ld a, e                 ; (a tile's 16 bytes: on to the next 256 every 16 tiles)
    and a
    jr nz, .counted
    inc d
.counted:
    push hl
    ld a, [wFtStreamDone]
    ld l, a
    ld a, [wFtStreamDone + 1]
    ld h, a
    inc [hl]
    ld a, [hl]
    pop hl
    ld b, a
    ld a, [wFtStreamN]
    cp b
    ret

; Before the frame's sprites are built (the original): the pictures just wanted streamed in now, while the lines
; to the sprites' last (FT_EARLY_LAST: their building and the frame's rest, 34 lines at the most) allow; all in,
; their decides again: up at the next VBlank, the sprites built for them, as on Color. Otherwise on after the sprites.
DEF FT_EARLY_LAST EQU 100
FtDmgEarly:
    ldh a, [hIsCGB]
    and a
    ret nz
    ld a, [wFtBankPicsDmg]
    and a
    ret z
    ldh a, [hBank]
    push af
    call FtDmgJob
    jr z, .out              ; (nothing coming in)
.tile:
    ldh a, [rLY]
    cp FT_EARLY_LAST
    jr nc, .out
    call FtDmgStream.b0
    call FtDmgTileIn
    jr nz, .tile
    call FtDmgJob           ; (that one in: the next, Mac's first)
    jr nz, .tile
IF DEF(FT_MAC_PICS)
    call FtPlPicDecideDmg
ENDC
    ld a, [wRvPlaceY]       ; (his place before: one going up now sits at its own, and his band, already
    ld b, a                 ; worked out from the last's, moves with it -- not a frame late)
    ld a, [wRvPlaceX]
    ld c, a
    push bc
    call FtDmgDecide
    pop bc
    ld a, [wRvPlaceX]
    sub c
    ld c, a
    ld a, [wRvPlaceY]
    sub b
    ld b, a
    ld a, [wRvNesX]
    add c
    ld [wRvNesX], a
    ld a, [wRvNesY]
    add b
    ld [wRvNesY], a
    pop af
    ld [$2000], a
    ld a, [wRvPicSwitch]    ; (one going up: his band worked out again for it -- its place, how far up it may go)
    and a
    ret z
    jp FtAnimate
.out:
    pop af
    ld [$2000], a
    ret

; VBlank's last: the coming pictures' tiles in what's left of it (whole tiles, about a line each, while it lasts).
FtDmgStreamVBlank:
    call FtDmgJob
    jr z, .stop
.tile:
    di                      ; (from the look at the line to the tile's last byte: no interrupt, the crowd's refill,
    ldh a, [rLY]            ; to carry it past VBlank)
    sub 144
    jr c, .stopEi
    cp 153 - 144            ; (a tile's under a line: done by VBlank's last)
    jr nc, .stopEi
    ld b, 2
.half:
    REPT 8
        ld a, [hl+]
        ld [de], a
        inc e
    ENDR
    dec b
    jr nz, .half
    ei
    call FtDmgTileIn
    jr nz, .tile
    jr FtDmgStreamVBlank    ; (that one in: the next)
.stopEi:
    ei
.stop:
    ld a, [wFtBankData]
    ld [$2000], a
    ret

; Out of the frame's work (its sprites built, the CPU free till VBlank): the coming pictures' tiles into their
; copies not shown, a few bytes in each line's quiet part (HBlank, then the next line's OAM scan: 41 cycles at the
; least, once the line's drawing is done), up to the line before VBlank's.
DEF FT_STREAM_LAST EQU 141     ; the last line a burst may start on
FtDmgStream:
    call FtDmgJob
    jr z, .stop
.tile:                      ; a tile in three lines at the most (.b0)
    ldh a, [rLY]            ; (VBlank's near, or past: the next frame's)
    cp FT_STREAM_LAST - 2
    jr nc, .stop
    call .b0
    call FtDmgTileIn
    jr nz, .tile
    jr FtDmgStream          ; (that one in: the next)
.stop:
    ld a, [wFtBankData]
    ld [$2000], a
IF DEF(FT_ROPE)
    ; his picture all in this late, the frame not yet over: up at this VBlank, not the next -- his top rows'
    ; sprites built again for it, his band where it sits (not when his gem or a star's sparkle, in the lower
    ; list built for the one up now, would be a frame off)
    ldh a, [rLY]
    cp FT_LATE_LAST
    ret nc
    ld a, [wRvPicSwitch]
    and a
    jr z, .notYet
    ldh a, [rLY]            ; (too late in the frame to work it all out again: as it is)
    cp FT_LATE_UNDO
    ret nc
    ldh a, [hFtBandY]       ; (going up already -- its last tiles in just now: his band worked out again for it, how
    ld b, a                 ;  far up it may go, and his top rows' sprites with it if that moved him)
    push bc
    call FtAnimate
    pop bc
    ldh a, [hFtBandY]
    cp b
    ret z
    jp FtBuildOAM.upper
.notYet:
    ld a, [RivalJewel]
    and a
    ret nz
    ld a, [wNes + $0343]
    and a
    ret nz
    ld a, [wRvPic]
    ld hl, wRvPicShown
    cp [hl]
    ret z
    ld a, [wRvPlaceY]       ; (what deciding changes, in case it's too late after all: put back)
    ld b, a
    ld a, [wRvPlaceX]
    ld c, a
    push bc
    ld a, [wRvPicHeads]
    ld b, a
    ld a, [wRvPicHeadsBuf]
    ld c, a
    push bc
    ld a, [wRvPicLoadWanted]
    push af
    call FtDmgDecide
    ld a, [wFtBankData]
    ld [$2000], a
    ld a, [wRvPicSwitch]
    and a
    jr z, .notUp            ; (not all in after all)
    ldh a, [rLY]            ; (decided too late to build his top rows' sprites again before VBlank's work is due:
    cp FT_LATE_UNDO         ;  as it was, up next frame)
    jr c, .lateUp
    pop af
    ld [wRvPicLoadWanted], a
    pop bc
    ld a, b
    ld [wRvPicHeads], a
    ld a, c
    ld [wRvPicHeadsBuf], a
    pop bc
    ld a, b
    ld [wRvPlaceY], a
    ld a, c
    ld [wRvPlaceX], a
    xor a
    ld [wRvPicSwitch], a
    ret
.notUp:
    pop af
    pop bc
    pop bc
    ret
.lateUp:
    pop af
    pop bc
    pop bc
    ld a, [wRvPlaceX]
    sub c
    ld c, a
    ld a, [wRvPlaceY]
    sub b
    ld b, a
    ld a, [wRvNesX]
    add c
    ld [wRvNesX], a
    ld a, [wRvNesY]
    add b
    ld [wRvNesY], a
    call FtAnimate          ; (its place, how far up it may go)
    jp FtBuildOAM.upper
ENDC
    ret
DEF FT_LATE_LAST EQU 127       ; (his top rows' sprites built again: 10 to 14 lines, 18 at the most -- an
DEF FT_LATE_UNDO EQU 124       ;  interrupt or two among them, his band worked out again first -- so begun by 123: done by 145, VBlank's work due by 147)

; A tile's 16 bytes HL -> DE, a line's quiet part at a time: 6 bytes once its drawing's done (30 cycles: the
; line's HBlank and the next's OAM scan are 41 at the least, a line of 10 sprites; finding HBlank's start takes up
; to 8), then 2 more while it's still HBlank (the OAM scan's 20 cycles still to come: 15 used), most lines' HBlank
; being long. .bN: from its Nth byte, on the next line's.
MACRO DMG_BYTES
    REPT \1
        ld a, [hl+]
        ld [de], a
        inc e
    ENDR
ENDM
MACRO DMG_MORE              ; \1: on the next line from here, if HBlank's over
    ldh a, [rSTAT]
    and 3
    jp nz, \1
    DMG_BYTES 2
ENDM
.b0:
    ei
    call .hblank
    DMG_BYTES 6
    DMG_MORE .b6
    DMG_MORE .b8
    DMG_MORE .b10
    DMG_MORE .b12
    DMG_MORE .b14
    ei
    ret
.b6:
    ei
    call .hblank
    DMG_BYTES 6
    DMG_MORE .b12
    DMG_MORE .b14
    ei
    ret
.b8:
    ei
    call .hblank
    DMG_BYTES 6
    DMG_MORE .b14
    ei
    ret
.b10:
    ei
    call .hblank
    DMG_BYTES 6
    ei
    ret
.b12:
    ei
    call .hblank
    DMG_BYTES 4
    ei
    ret
.b14:
    ei
    call .hblank
    DMG_BYTES 2
    ei
    ret
.hblank:                    ; (returns at HBlank's start, interrupts off: none may come between it and the bytes)
.drawing:
    ldh a, [rSTAT]
    and 3
    cp 3
    jr nz, .drawing
    di
    ldh a, [rSTAT]          ; (still drawing, interrupts off: an interrupt just before, the crowd's refill, may
    and 3                   ; have run on past this line's HBlank; then the next line's)
    cp 3
    jr z, .wait
    ei
    jr .drawing
.wait:
    ldh a, [rSTAT]
    and 3
    jr nz, .wait
    ret
ENDC

; A = pose. Game Boy Color: one GDMA of the rival's 10 full map rows, then one for their palettes.
; Original: copy just his 8 tiles of each row with the CPU.
DEF FT_CGB_HEAD EQU $4000     ; Color's finer poses: their banks' headers (CgbMaps, CgbSwap)
IF DEF(FT_ALL_PICS)
FtDrawPose:
    ret                     ; (every fight in pictures: no poses drawn)
ELSE
FtDrawPose:
    add a
    ld e, a
    ld d, 0
    ldh a, [hIsCGB]
    and a
    jr z, .original
    ld a, [wFtBankMapsCgb]  ; Color's finer poses: their rows' table at the start of their bank
    and a
    jr z, .original
    ld [$2000], a
    ld hl, FT_CGB_HEAD
    add hl, de
    ld bc, FT_CGB_HEAD + 2 * RP_COUNT   ; (then each pose's bank)
    jr .table
.original:
    ld hl, RivalMaps
    add hl, de
    ld bc, RivalMapBanks
.table:
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    push hl
    ld a, e                 ; the pose rows' bank (they take two)
    srl a
    add c
    ld l, a
    adc b
    sub l
    ld h, a
    ld a, [hl]
    pop hl
    ld [$2000], a
.go:
    call .draw
    ld a, [wFtBankData]
    ld [$2000], a
    ret
.draw:
    ldh a, [hIsCGB]
    and a
    jr z, .dmg
    call .gdma
    ld hl, FT_PIC_BYTES     ; the palettes follow the map rows
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
    ld a, FT_PIC_BYTES / 16 - 1
    ldh [rHDMA5], a
    ret
.dmg:
    ld de, FT_REGION_X
    add hl, de
    ld de, FT_REGION_ROW + FT_REGION_X
    ld b, FT_PIC_ROWS
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

ENDC
; The swap sets: the original's; or on Color, with finer poses (wFtBankSwapCgb), Color's: their header (CgbSwap,
; at $4000 in their bank) for the swap, their always-there tiles and the attack set loaded (the screen is off),
; and the idle pose drawn in them.
IF DEF(FT_ALL_PICS)
FtSwapSetup:
    ldh a, [hIsCGB]         ; (every fight in pictures: no pose sets; Color: its first picture)
    and a
    ret z
    FT_VWAIT FT_ROOM_ALL
    jp FtPicsStart
ELSE
FtSwapSetup:
    ld hl, wFtSwapSets
    ld a, LOW(FtSwapSet0)
    ld [hl+], a
    ld a, HIGH(FtSwapSet0)
    ld [hl+], a
    ld a, LOW(FtSwapSet1)
    ld [hl+], a
    ld a, HIGH(FtSwapSet1)
    ld [hl+], a
    ld a, LOW(FtSwapSet2)
    ld [hl+], a
    ld a, HIGH(FtSwapSet2)
    ld [hl], a
    ld hl, wFtSwapRuns      ; the original's swap area: its two runs (FtFights), in bank 0
    ld a, [wFtSwapACount]
    ld [hl+], a
    ld a, [wFtSwapVramA]
    ld [hl+], a
    ld a, [wFtSwapVramA + 1]
    ld [hl+], a
    xor a
    ld [hl+], a
    ld a, [wFtSwapACount]
    ld b, a
    ld a, [wFtSwapCount]
    sub b
    ld [hl+], a
    ld a, [wFtSwapVramB]
    ld [hl+], a
    ld a, [wFtSwapVramB + 1]
    ld [hl+], a
    xor a
    ld b, 9
.zero:
    ld [hl+], a
    dec b
    jr nz, .zero
    ld hl, wFtSwapSizes     ; each set the area's tiles
    ld b, 3
.sizes:
    ld a, [wFtSwapCount]
    ld [hl+], a
    xor a
    ld [hl+], a
    dec b
    jr nz, .sizes
    ldh a, [hIsCGB]
    and a
    ret z
IF DEF(FT_NES)
    ld a, [wFtBankPics]     ; (Color with his NES pictures: none of the finer poses' sets, his pictures instead)
    and a
    jr nz, .setsIn
ENDC
    ld a, [wFtBankSwapCgb]
    and a
    ret z
    ld [wFtBankSwap], a
    ld [$2000], a
    ld hl, FT_CGB_HEAD
    ld de, wFtSwapSizes     ; each set's tiles, then the runs (up to four, in both banks), the sets, his
    ld b, 6                 ; always-there runs
    call .bytes
    ld de, wFtSwapRuns
    ld b, 16
    call .bytes
    ld de, wFtSwapSets
    ld b, 6
    call .bytes
    ld a, [hl+]             ; his always-there tiles, run by run
    and a
    jr z, .set
    ld b, a
.run:
    push bc
    call .entry
    pop bc
    dec b
    jr nz, .run
.set:
    ld a, [wFtSwapSets]     ; the attack set into the swap area, run by run
    ld e, a
    ld a, [wFtSwapSets + 1]
    ld d, a
    ld hl, wFtSwapRuns
    ld a, 4
    ld [wFtCopyN], a
.setRun:
    ld a, [hl+]
    and a
    jr z, .setsIn
    call .times16
    ld a, [hl+]
    ld [wFtCopyTo], a
    ld a, [hl+]
    ld [wFtCopyTo + 1], a
    ld a, [hl+]
    ldh [rVBK], a
    push hl
    ld a, [wFtCopyTo]
    ld l, a
    ld a, [wFtCopyTo + 1]
    ld h, a
    call FtCopy             ; (the source runs on)
    pop hl
    ld a, [wFtCopyN]
    dec a
    ld [wFtCopyN], a
    jr nz, .setRun
.setsIn:
    xor a
    ldh [rVBK], a
    FT_VWAIT FT_ROOM_ALL    ; (his first pose: a VBlank of its own, loading with the display on)
IF DEF(FT_NES)
    call FtPicsStart        ; (Color with his NES pictures: the first of them instead)
    ret nz
    xor a
ENDC
    jp FtDrawPose           ; (A = 0: idle, in its tiles)
.bytes:
    ld a, [hl+]
    ld [de], a
    inc de
    dec b
    jr nz, .bytes
    ret
.entry:                     ; HL = source, bytes, where, bank (HL past them after)
    push hl
    ld de, 6
    add hl, de
    ld a, [hl]
    ldh [rVBK], a
    pop hl
    ld a, [hl+]
    ld e, a
    ld a, [hl+]
    ld d, a
    ld a, [hl+]
    ld c, a
    ld a, [hl+]
    ld b, a
    ld a, [hl+]
    push hl
    ld h, [hl]
    ld l, a
    call FtCopy
    pop hl
    inc hl
    inc hl                  ; (past where's high byte and the bank)
    xor a
    ldh [rVBK], a
    ret
.times16:                   ; BC = A * 16
    ld c, a
    ld b, 0
    REPT 4
        sla c
        rl b
    ENDR
    ret

ENDC
; BC bytes from DE to HL (the screen off; or on, as a fight loads on Color: FT_LOAD_ON). DE, HL past them after.
FtCopy:
    ldh a, [hIsCGB]         ; Color: whole tiles into video memory by DMA (a copy as the fight loads: on Color
    and a                   ; it loads with the display on, black, a VBlank's worth at a time)
    jp z, .cpu
    ld a, h
    and $E0
    cp $80
    jp nz, .cpu
    ldh a, [rLCDC]
    bit 7, a
IF DEF(FT_LOAD_ON)
    jr nz, .on
ELSE
    jp nz, .cpu
ENDC
    ld a, e
    or l
    or c
    and 15
    jp nz, .cpu
.dma:                       ; up to 2048 bytes a time
    ld a, b
    or c
    ret z
    call .from
    ld a, b
    cp 8
    jr c, .last
    ld a, $7F               ; (128 blocks: 2048 bytes)
    ldh [rHDMA5], a
    ld a, b
    sub 8
    ld b, a
    call .past8
    jr .dma
.last:                      ; the rest (under 2048 bytes): BC / 16 blocks
    push bc
    ld a, b
    swap a
    ld b, a
    ld a, c
    swap a
    and $0F
    or b
    dec a
    ldh [rHDMA5], a
    pop bc                  ; DE, HL past it, as the CPU's copy leaves them (the source runs on)
    ld a, e
    add c
    ld e, a
    ld a, d
    adc b
    ld d, a
    ld a, l
    add c
    ld l, a
    ld a, h
    adc b
    ld h, a
    ld bc, 0
    ret
.from:                      ; the DMA's source DE, destination HL
    ld a, d
    ldh [rHDMA1], a
    ld a, e
    ldh [rHDMA2], a
    ld a, h
    ldh [rHDMA3], a
    ld a, l
    ldh [rHDMA4], a
    ret
.past8:                     ; DE, HL on 2048 bytes
    ld a, d
    add 8
    ld d, a
    ld a, h
    add 8
    ld h, a
    ret
IF DEF(FT_LOAD_ON)
.on:                        ; the display on: only while it's in VBlank (VWait: then about 1,100 cycles free)
    ldh a, [hLoadOn]
    and a
    jp z, .cpu
    ld a, e
    or l
    or c
    and 15
    jp nz, .onCpu
.onDma:                     ; as many blocks as this VBlank has room for (FtRoom), the rest in the next
    ld a, b
    or c
    ret z
    call FtRoomLeft
    jr c, .noRoom
    cp FT_ROOM_OVER + 8     ; (8 blocks at least, else the next VBlank)
    jr nc, .roomy
.noRoom:
    call VWait
    ld a, FT_ROOM
    ld [wFtRoom], a
.roomy:
    sub FT_ROOM_OVER
    ld [wFtRoomN], a        ; blocks it has room for
    push hl
    ld l, a
    ld h, 0
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, hl
    ld a, l                 ; (their bytes)
    ld [wFtRoomBytes], a
    ld a, h
    ld [wFtRoomBytes + 1], a
    ld a, l
    sub c
    ld a, h
    sbc b
    pop hl
    jr c, .onPiece          ; more left than that: that many now
    ld a, c                 ; the rest, now: the room less its blocks (BC / 16)
    swap a
    and $0F
    ld [wFtRoomN], a
    ld a, b
    swap a
    push hl
    ld hl, wFtRoomN
    or [hl]
    cpl
    inc a
    ld hl, wFtRoom
    add [hl]
    ld [hl], a
    pop hl
    call .from
    jp .last
.onPiece:
    call .from
    ld a, [wFtRoomN]
    dec a
    ldh [rHDMA5], a
    ld a, [wFtRoomN]        ; (their time gone)
    cpl
    inc a
    push hl
    ld hl, wFtRoom
    add [hl]
    ld [hl], a
    pop hl
    ld a, [wFtRoomBytes]    ; HL, DE on by their bytes, BC less
    add l
    ld l, a
    ld a, [wFtRoomBytes + 1]
    adc h
    ld h, a
    ld a, [wFtRoomBytes]
    add e
    ld e, a
    ld a, [wFtRoomBytes + 1]
    adc d
    ld d, a
    push hl
    ld hl, wFtRoomBytes
    ld a, c
    sub [hl]
    ld c, a
    inc hl
    ld a, b
    sbc [hl]
    ld b, a
    pop hl
    jp .onDma
.onCpu:                     ; the CPU: 64 bytes a piece (10 cycles each)
    ld a, b
    or c
    ret z
    ld a, 80 + FT_ROOM_OVER
    call FtRoom
    ld a, b
    and a
    jr nz, .piece64
    ld a, c
    cp 64
    jr c, .piece
.piece64:
    ld a, 64
.piece:                     ; A bytes now
    push bc
    ld b, a
    ld c, a
.byte:
    ld a, [de]
    inc de
    ld [hl+], a
    dec b
    jr nz, .byte
    ld a, c                 ; BC less them
    cpl
    inc a
    pop bc
    add c
    ld c, a
    ld a, b
    adc $FF
    ld b, a
    jr .onCpu
ENDC
.cpu:
    ld a, b
    or c
    ret z
    ld a, [de]
    ld [hl+], a
    inc de
    dec bc
    jr .cpu

; Copy the next few tiles of the wanted set (knockdown or attack) into video memory.
; Returns NZ if it did work this VBlank.
IF DEF(FT_ALL_PICS)
FtSwapStep:
    xor a                   ; (every fight in pictures: no pose sets to swap; Z: no work)
    ret
ELSE
FtSwapStep:
    ld a, [wFtSwapWant]
    ld hl, wFtSwapHave
    cp [hl]
    ret z
    ld hl, wFtSwapGoing
    cp [hl]
    jr z, .going
    ld [hl], a              ; a set that isn't the one under way: from its first tile, and no set whole meanwhile
    xor a
    ld [wFtSwapPos], a
    ld [wFtSwapPos + 1], a
    dec a
    ld [wFtSwapHave], a
.going:
    ld a, [wFtSwapPos]      ; (the first tiles: the set that was there is going)
    ld hl, wFtSwapPos + 1
    or [hl]
    jr nz, .bank
    dec a
    ld [wFtSwapHave], a
    xor a
    ld [wFtSwapPos], a      ; (zeroed both: the line above)
    ld [wFtSwapPos + 1], a
.bank:
    ld a, [wFtBankSwap]      ; the swap tiles have a bank of their own
    ld [$2000], a
    call .step
    push af
    ld a, [wFtBankData]
    ld [$2000], a
    pop af
    ret
.step:
    ld a, [wFtSwapWant]
    add a
    add LOW(wFtSwapSets)
    ld l, a
    adc HIGH(wFtSwapSets)
    sub l
    ld h, a
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    ld a, [wFtSwapPos]      ; HL = source + pos * 16
    ld c, a
    ld a, [wFtSwapPos + 1]
    ld b, a
    REPT 4
        sla c
        rl b
    ENDR
    add hl, bc
    ; how many tiles this VBlank: the per-frame amount, no further than the end of the tile's run
    ldh a, [hIsCGB]
    and a
    ld a, FT_SWAP_PER_FRAME_CGB
    jr nz, .limit
    ld a, FT_SWAP_PER_FRAME
.limit:
    ld [wFtCopyN], a
    push hl                 ; (the source)
    ld hl, wFtSwapRuns
    ld a, [wFtSwapPos]
    ld c, a
    ld a, [wFtSwapPos + 1]
    ld b, a
.find:                      ; the run the next tile's in (BC: its place past the runs before)
    ld a, b
    and a
    jr nz, .past
    ld a, c
    cp [hl]
    jr c, .inRun
.past:
    ld a, c
    sub [hl]
    ld c, a
    jr nc, .next
    dec b
.next:
    inc hl
    inc hl
    inc hl
    inc hl
    jr .find
.inRun:                     ; C = its place in the run
    push hl                 ; no further than the end of the wanted set (its size less the tiles in)
    ld a, [wFtSwapWant]
    add a
    add LOW(wFtSwapSizes)
    ld l, a
    adc HIGH(wFtSwapSizes)
    sub l
    ld h, a
    ld a, [wFtSwapPos]
    ld b, a
    ld a, [hl+]
    sub b
    ld b, a
    ld a, [wFtSwapPos + 1]
    ld e, a
    ld a, [hl]
    sbc e                   ; (left > 255: no limit from it)
    pop hl
    jr nz, .runLeft
    ld a, [wFtCopyN]
    cp b
    jr nc, .runLeft2
.runLeft:
    ld a, [wFtCopyN]
    ld b, a
.runLeft2:
    ld a, [hl+]             ; tiles left in the run
    sub c
    cp b
    jr nc, .lim
    ld b, a
.lim:
    ldh a, [hIsCGB]         ; the original, by CPU: no further than this VBlank has room for (a tile's about a
    and a                   ; line: one a line left before its last, 153)
    jr nz, .room
    ldh a, [rLY]
    sub 144
    jr c, .noRoom           ; (VBlank's over)
    cpl
    add 153 - 144           ; (153 - LY - 1)
    jr c, .roomy
.noRoom:
    pop hl
    or 1                    ; (NZ: this VBlank's spent; the rest in the next)
    ret
.roomy:
    jr z, .noRoom
    cp b
    jr nc, .room
    ld b, a
.room:
    push bc                 ; (B: tiles to copy now)
    ld b, 0
    REPT 4                  ; DE = the run's start + place * 16
        sla c
        rl b
    ENDR
    ld a, [hl+]
    add c
    ld e, a
    ld a, [hl+]
    adc b
    ld d, a
    ld a, [hl]
    ld [wFtSwapVbk], a
    pop bc
    pop hl
.copy:
    ld a, [wFtSwapPos]
    add b
    ld [wFtSwapPos], a
    jr nc, .copied
    ld a, [wFtSwapPos + 1]
    inc a
    ld [wFtSwapPos + 1], a
.copied:
    ldh a, [hIsCGB]
    and a
    jr z, .byCPU
    ld a, [wFtSwapVbk]      ; Color: the whole run in one GDMA (in its video memory bank)
    ldh [rVBK], a
    ld a, h
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
    xor a
    ldh [rVBK], a
    jr .moved
.byCPU:
    REPT 16
        ld a, [hl+]
        ld [de], a
        inc de
    ENDR
    dec b
    jp nz, .byCPU
.moved:                     ; the wanted set's tiles all in?
    ld a, [wFtSwapWant]
    add a
    add LOW(wFtSwapSizes)
    ld l, a
    adc HIGH(wFtSwapSizes)
    sub l
    ld h, a
    ld a, [wFtSwapPos]
    cp [hl]
    jr nz, .more
    inc hl
    ld a, [wFtSwapPos + 1]
    cp [hl]
    jr z, .done
.more:
    or 1                    ; NZ: worked
    ret
.done:
    xor a
    ld [wFtSwapPos], a
    ld [wFtSwapPos + 1], a
    ld a, [wFtSwapWant]
    ld [wFtSwapHave], a
    or 1
    ret

; ---- the frame ----

ENDC
FightUpdate:
    call FtCrowd
IF DEF(FT_NES)
    call FtNesFrame         ; the whole fight, by the NES game's own logic
    ld a, [wFtMatch]
    cp M_END
    jp z, FtNesEnd
    jp FtFrame
ELSE
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
ENDC
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
IF DEF(FT_NES)
    call FtDmgEarly         ; (the original: the pictures just wanted, in now if there's time)
ENDC
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
    cp COUNT_TKO
    jr c, .out
    ld b, RF_WAVE           ; waving it off: KO, or TKO
    ld c, SAY_KO
    jr nz, .in
    ld c, SAY_TKO
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
    cp COUNT_TKO
    jr c, .counting
    ld b, RF_WAVE
    ld c, SAY_KO
    jr nz, .in
    ld c, SAY_TKO
    jr .in
.counting:
IF DEF(FT_WORDS)
    ld a, [wFtCountTimer]   ; the NES's: each number's arm down from 2 frames in to 13, its bubble from 16 on
    cp FT_COUNT - 14        ; (a frame sooner than its: the sprites go up a frame after they're built)
    jr nc, .arm
    ld c, SAY_COUNT
.arm:
    cp FT_COUNT
    jr nc, .in
    cp FT_COUNT - 12
    jr c, .in
    ld b, RF_COUNT
ELSE
    ld c, SAY_COUNT
    ld a, [wFtCountTimer]   ; arm up for a moment on each number
    cp FT_COUNT - 14
    jr c, .in
    ld b, RF_COUNT
ENDC
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

; How far up he's shown standing, per pixel up the NES puts him (0-63): one for one for his bobbing, then
; easing to FT_STAND_UP over a step back (the NES walks him up to 37 pixels away; his band can't follow).
IF !DEF(FT_ROPE)
FtStandUp:
    db $00, $FF, $FE, $FD, $FD, $FD, $FD, $FD, $FD, $FD, $FC, $FC, $FC, $FC, $FC, $FC
    db $FC, $FC, $FC, $FC, $FC, $FC, $FB, $FB, $FB, $FB, $FB, $FB, $FB, $FB, $FB, $FB
    db $FB, $FB, $FA, $FA, $FA, $FA, $FA, $FA, $FA, $FA, $FA, $FA, $FA, $FA, $FA, $FA
    db $FA, $FA, $FA, $FA, $FA, $FA, $FA, $FA, $FA, $FA, $FA, $FA, $FA, $FA, $FA, $FA
ENDC

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
IF DEF(FT_ROPE)
    ld c, a                 ; as far up as the NES puts him (over the ropes and crowd: his top rows are sprites),
    ld hl, wRvPicShown      ; (his new pose's limit only once its picture is up -- or going up at this VBlank: till
    ld a, [wRvPicSwitch]    ;  then the one showing's, kept)
    and a
    jr z, .capPic
    ld hl, wRvPicLoad
.capPic:
    ld a, [wRvPic]
    cp [hl]
    ld a, [wFtRiseCap]
    jr nz, .capKept
    ld a, [wRvPose]         ; his top no higher than the crowd's (a tall pose's head would go over the HUD)
    ld e, a
    ld d, 0
    ld hl, RivalPoseRise
    add hl, de
    ld a, [hl]
    add FT_HEAD_ROOM
    ld e, a
    ld a, [wNes + $90]      ; (his walk in before the bell, $00/$40: his head up over the HUD too, as the NES's)
    and $3F
    ld a, e
    jr nz, .walked
    add 16
.walked:
    ld [wFtRiseCap], a
.capKept:
    cp FT_NES_UP_MAX
    jr c, .room
    ld a, FT_NES_UP_MAX
.room:
    cpl
    inc a
    ld e, a                 ; (E: -how far)
    ld a, c
    cp e
    jr nc, .y
    ld a, e
    jr .y
ELSE                        ; (no ropes: his band alone, eased)
    ld c, a                 ; standing, as far as his band rises (his head's at the top of the frame);
    ld a, [wRvPose]         ; down, his low poses can rise inside it too (either way down: the second's last)
    cp RP_KD2_STAGGER
    jr nc, .low
    cp RP_KD_STAGGER
    jr c, .standing
    cp RP_KD_RISE + 1
    jr nc, .standing
.low:
    ld e, a                 ; (as far as his pose's blank rows on top: his band can't rise past the HUD)
    ld d, 0
    ld hl, RivalPoseRise
    add hl, de
    xor a
    sub [hl]
    ld b, a                 ; (B: -rise; his x is put back below)
    ld a, c
    cp b
    jr nc, .riseOk
    ld a, b
.riseOk:
    ld c, a
    ld a, [wRvNesX]
    ld b, a
    ld a, c
    jr .y
.standing:                  ; standing, he can rise only so far: a step back eases in (FtStandUp)
    ld a, c
    cpl
    inc a
    cp 64
    jr c, .eased
    ld a, 63
.eased:
    ld e, a
    ld d, 0
    ld hl, FtStandUp
    add hl, de
    ld a, [hl]
ENDC
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
IF DEF(FT_NES_DOWN_MAX)
IF FT_BAND_BOTTOM + FT_NES_DOWN_MAX > 141
    cp 142                  ; (its end no later than line 141: a split at the screen's last lines would race
    jr c, .ends             ;  VBlank, and the frame could sleep through it)
    ld a, 141
.ends:
ENDC
ENDC
    ldh [hFtBandBottom], a
IF DEF(FT_ROPE)
    ret                     ; (a rope row: his band's top stays put; what's above it of him is sprites)
ENDC
    ld a, c
    and a
    jr z, .level
    bit 7, a
    jr nz, .raised
    add FT_BAND_TOP         ; down: the band starts that much lower, mat in the gap above it (FtStat)
    ldh [hFtBandGap], a
    ld a, FT_BAND_TOP
    ldh [hFtBandTop], a
    ret
.raised:
IF FT_HEADROOM == 0
.level:
    xor a
ELSE
    cp -FT_HEADROOM
    jr nc, .top
    ld a, -FT_HEADROOM
    jr .top
.level:
    xor a
ENDC
.top:
    add FT_BAND_TOP
    ldh [hFtBandTop], a
    xor a
    ldh [hFtBandGap], a
    ret

Wobble:
    db 0, 1, 2, 1, 0, -1, -2, -1
IdleCycle:
    db RP_IDLE, RP_IDLE2, RP_IDLE3, RP_IDLE2

; ---- the clock ----

IF !DEF(FT_NES)             ; ---- the kit's own fight (the NES game's runs it instead: kit_nes.asm) ----
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
    ld a, [wFtCornerScene]  ; (the corner, if there's one) to the corner; the fight picks up where it was after
    cp $FF
    jr z, :+
    ld a, 1
    ld [wFtResume], a
    ld a, FT_CORNER_RESULT
    jp FtFinish
:
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

ENDC
IF DEF(FT_NES)
; Punch-Out!!'s corner: Select armed as it comes up ($A87B: $03D8 = $80, unless it's been used this fight).
FtCornerArm::
    ld a, [wNes + $03D8]
    and a
    ret nz
    ld a, $80
    ld [wNes + $03D8], a
    xor a
    ld [wFtDocFast], a
    ret

; Doc's step and VBlank, from any bank (they're in a bank of their own: ROM0's full).
DocStep::
    ld a, BANK(DocStepIn)
    ld [$2100], a
    call DocStepIn
    jr DocBack
DocVBlank::
    ld a, BANK(DocVBlankIn)
    ld [$2100], a
    call DocVBlankIn
DocBack:
    ldh a, [hBank]
    ld [$2100], a
    ret

; Doc's states loaded, and the original's greys put in, from any bank (in the far section with their data).
DocLoad::
    ld a, BANK(DocLoadIn)
    ld [$2100], a
    call DocLoadIn
    jr DocBack
OverlayLoad::
    ld a, BANK(OverlayLoadIn)
    ld [$2100], a
    call OverlayLoadIn
    jr DocBack
OvlSlide::
    ld a, BANK(OvlSlideIn)
    ld [$2100], a
    call OvlSlideIn
    jr DocBack

; The original Game Boy, a scene loading: tiles whose palette has its own greys, put in them (HL: how many, then
; each one's number and map, 2 bits a slot; DE: the scene's tiles, all in its bank, mapped). Made from the ROM's
; tiles 6 at a time, outside VBlank, into wRemapBuf; each batch put up in a VBlank (if the screen's on).
DmgRemap::
    ld a, [hl+]
    and a
    ret z
    ld [wRemapLeft], a
    ld a, e
    ld [wRemapSrc], a
    ld a, d
    ld [wRemapSrc + 1], a
.batch:
    xor a
    ld [wRemapN], a
    ld de, wRemapBuf
.tile:
    ld a, [hl+]             ; its number: VRAM address (0-127 from $9000, 128-255 from $8800) and ROM source
    push hl
    push de
    ld c, [hl]              ; (its map)
    ld l, a
    ld h, 0
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, hl
    push hl
    bit 7, a
    ld a, $90
    jr z, .low
    ld a, $80
.low:
    add h
    ld b, a
    ld a, [wRemapN]
    add a
    add LOW(wRemapDst)
    ld e, a
    ld a, 0
    adc HIGH(wRemapDst)
    ld d, a
    ld a, l
    ld [de], a
    inc de
    ld a, b
    ld [de], a
    pop hl
    ld a, [wRemapSrc]
    add l
    ld l, a
    ld a, [wRemapSrc + 1]
    adc h
    ld h, a
    pop de
    ld b, 8
.row:                       ; a row: each slot's pixels, then the greys'
    push bc
    ld a, [hl+]
    ld b, a                 ; (B the low plane, A the high)
    ld a, [hl+]
    push hl
    ld h, a
    ld a, b
    or h
    cpl
    ld [wRemap], a
    ld a, h
    cpl
    and b
    ld [wRemap + 1], a
    ld a, b
    cpl
    and h
    ld [wRemap + 2], a
    ld a, b
    and h
    ld [wRemap + 3], a
    push de
    ld hl, wRemap
    ld de, 0
    ld b, 4
.slot:
    ld a, [hl+]
    rr c
    jr nc, .noLow
    push af
    or e
    ld e, a
    pop af
.noLow:
    rr c
    jr nc, .noHigh
    or d
    ld d, a
.noHigh:
    dec b
    jr nz, .slot
    ld a, d
    ld b, e
    pop de
    push af
    ld a, b
    ld [de], a
    inc de
    pop af
    ld [de], a
    inc de
    pop hl
    pop bc
    dec b
    jr nz, .row
    pop hl
    inc hl
    ld a, [wRemapN]
    inc a
    ld [wRemapN], a
    ld a, [wRemapLeft]
    dec a
    ld [wRemapLeft], a
    jr z, .put
    ld a, [wRemapN]
    cp 6
    jp c, .tile
.put:                       ; the batch up: in a VBlank (the screen on), 16 bytes a tile
    push hl
    ldh a, [rLCDC]
    bit 7, a
    jr z, .copy
.leave:
    ldh a, [rLY]
    cp 144
    jr nc, .leave
.in:
    ldh a, [rLY]
    cp 144
    jr c, .in
.copy:
    ld hl, wRemapBuf
    ld de, wRemapDst
    ld a, [wRemapN]
    ld b, a
.each:
    push bc
    ld a, [de]
    ld c, a
    inc de
    ld a, [de]
    ld b, a
    inc de
    push de
    ld e, 16
.byte:                      ; (10 cycles a byte: 6 tiles a VBlank)
    ld a, [hl+]
    ld [bc], a
    inc bc
    dec e
    jr nz, .byte
    pop de
    pop bc
    dec b
    jr nz, .each
    pop hl
    ld a, [wRemapLeft]
    and a
    jp nz, .batch
    ret

; GET UP!, from any bank (in "Screens far"): HL the next OAM entry, on past its letters.
FtGetUp:
    ld a, BANK(FtGetUpIn)
    ld [$2100], a
    call FtGetUpIn
    jp ScreensBack

; Leaving it ($A8B7): unused, it's armed again next time; used, never again this fight.
FtCornerLeave::
    ld a, [wNes + $03D8]
    and 1
    ld [wNes + $03D8], a
    ret

; Select in the corner ($A7A6, $A800): Doc rubs faster, and the refill Mac's next round carries (NesHpCarry)
; comes from the fight's own table ($05EE): by the round and a random eighth (the game's $18, rotated after).
FtCornerSelect:
    ld a, [wNes + $03D8]
    bit 7, a
    ret z
    ld a, 1
    ld [wNes + $03D8], a
    ld [wFtDocFast], a
    ld a, [wNes + nRoundNumber]   ; (the NES's is the coming round's by now, less one: the port's, as it is)
    add a
    add a
    add a
    ld e, a
    push de                 ; ($AEF1: the game's random byte, $18; the port's NesRandom)
    call NesRandom
    pop de
    and 7
    add e
    ld e, a
    ld d, 0
    ldh a, [hBank]
    push af
    ld a, [wFtBankNes]
    ld [$2000], a
    ld a, [wNes + $05EE]
    ld l, a
    ld a, [wNes + $05EF]
    sub NES_BANK_DELTA
    ld h, a
    add hl, de
    ld a, [hl]
    ld [wNes + $03D9], a
    pop af
    ld [$2000], a
    ret
PUSHS
SECTION FRAGMENT "Screens far", ROMX
; Punch-Out!!'s GET UP!, as the NES writes it while Mac's down (his frame $3A is those words): white, centred at
; the screen's foot. HL = the next OAM entry (on past its six).
FtGetUpIn:
    ld de, .xs
    ld b, 6
    ld c, FT_GETUP_TILE
.letter:
    ld a, 136 + 16
    ld [hl+], a
    ld a, [de]
    inc de
    ld [hl+], a
    ld a, c
    inc c
    ld [hl+], a
    ld a, FT_GETUP_ATTR
    ld [hl+], a
    dec b
    jr nz, .letter
    ret
.xs:                        ; G E T, U P ! (OAM x: the screen's middle)
    db 52 + 8, 60 + 8, 68 + 8, 84 + 8, 92 + 8, 100 + 8
; Punch-Out!!'s Another World Circuit's words over the screen's (HL: how many, then each cell's address and tile);
; the display on, a few a VBlank.
AwPatchIn:
    ld a, [hl+]
    ld b, a
.cell:
    ld a, b
    and 7
    jr nz, .now
    ldh a, [hLoadOn]
    and a
    call nz, VWait
.now:
    ld a, [hl+]
    ld e, a
    ld a, [hl+]
    ld d, a
    ld a, [hl+]
    ld [de], a
    dec b
    jr nz, .cell
    ret

; Mac's record as the challenger screen shows it, the NES's "WW-LL KKKO" (each two wide, a space before one digit),
; over the label it's baked as: HL = its first cell in the map, DE = its glyph tiles (0-9, "-", "K", "O", blank).
RecordDrawIn:
    ldh a, [hLoadOn]        ; (the display on: in a VBlank)
    and a
    call nz, VWait
    ld a, [wRecWins]
    call .num
    ld a, 10
    call .glyph
    ld a, [wRecLosses]
    call .num
    ld a, 13
    call .glyph
    ld a, [wRecKOs]
    call .num
    ld a, 11
    call .glyph
    ld a, 12
    jr .glyph
.num:                       ; A (0-99): two cells, a space for no tens
    ld c, -1
.tens:
    inc c
    sub 10
    jr nc, .tens
    add 10
    push af
    ld a, c
    and a
    jr nz, .tensDigit
    ld a, 13
.tensDigit:
    call .glyph
    pop af
.glyph:                     ; [HL+] = glyph A's tile
    push de
    add e
    ld e, a
    adc d
    sub e
    ld d, a
    ld a, [de]
    ld [hl+], a
    pop de
    ret

; His pass key as PwKeyFar worked it out (wPw + $10, ten digits), over the label it's baked as (Punch-Out!!'s KO
; News): HL = its first cell in the map, DE = its digits' glyphs; spaces after the third and the sixth.
KeyDrawIn:
    ldh a, [hLoadOn]        ; (the display on: in a VBlank)
    and a
    call nz, VWait
    ld bc, wPw + $10
.digit:
    ld a, [bc]
    push de
    add e
    ld e, a
    adc d
    sub e
    ld d, a
    ld a, [de]
    ld [hl+], a
    pop de
    inc bc
    ld a, c
    cp LOW(wPw + $13)
    jr z, .space
    cp LOW(wPw + $16)
    jr z, .space
    cp LOW(wPw + $1A)
    ret z
    jr .digit
.space:
    inc hl
    jr .digit

IF DEF(FT_NES)
; The fight's time as Punch-Out!!'s Another World Circuit gives it after its last win, "TIME M:SS.CC,RN" (the NES's
; clock, $0302-$0305; its hundredths from the sub-second count, $0306's top four bits, by its table; the round, $06),
; over the label it's baked as: HL = its first cell in the map, DE = its digits' glyphs (each cell's 0-9).
TimeDrawIn:
    ldh a, [hLoadOn]        ; (the display on: in a VBlank)
    and a
    call nz, VWait
    push hl
    ld a, [wNes + $0306]
    swap a
    and $0F
    cp 7
    jr c, .cents
    ld a, 6
.cents:
    add a
    ld c, a
    ld b, 0
    ld hl, TimeCents
    add hl, bc
    ld a, [hl+]
    ld b, a
    ld c, [hl]              ; B, C: its hundredths' digits
    pop hl
    ld a, l
    add 5
    ld l, a                 ; (a row's cells: no carry out of the label's row)
    ld a, [wNes + $0302]
    call .put
    inc l
    inc l
    ld a, [wNes + $0304]
    call .put
    inc l
    ld a, [wNes + $0305]
    call .put
    inc l
    inc l
    ld a, b
    call .put
    inc l
    ld a, c
    call .put
    inc l
    inc l
    inc l
    ld a, [wNes + $06]
.put:                       ; [HL] = digit A's glyph (DE's ten), DE on to the next cell's
    push de
    add e
    ld e, a
    adc d
    sub e
    ld d, a
    ld a, [de]
    ld [hl], a
    pop de
    ld a, e
    add 10
    ld e, a
    ret nc
    inc d
    ret
TimeCents:                  ; ($85BB) the hundredths by the sub-second count's top bits: 00 25 48 61 82 97 99
    db 0, 0, 2, 5, 4, 8, 6, 1, 8, 2, 9, 7, 9, 9
ENDC

; Doc's states for this corner (HL: the cells, their addresses, then the four states' tiles), his timers started:
; as the NES's, his mouth opens 16 frames in and his hand comes up 32 in.
DocLoadIn:
    ld a, [hl+]
    ld [wDocN], a
    ld b, a
    add a
    ld c, a
    ld de, wDocAddr
.addr:
    ld a, [hl+]
    ld [de], a
    inc de
    dec c
    jr nz, .addr
    ld a, b
    add a
    add a
    ld c, a
    ld de, wDocTile
.tile:
    ld a, [hl+]
    ld [de], a
    inc de
    dec c
    jr nz, .tile
    ld a, [hl+]             ; then the rival's (none: 0): where they are, his first state's frames
    ld [wTalkN], a
    and a
    jr z, .still
    ld a, l
    ld [wTalkPtr], a
    ld a, h
    ld [wTalkPtr + 1], a
    call TalkTimes
    ld a, [hl+]
    ld [wTalkTimer], a
    inc hl
    inc hl
.still:
    ld a, l                 ; then their sprites, Doc's and the rival's: Color's, then the original's
    ld [wOvlDoc], a
    ld a, h
    ld [wOvlDoc + 1], a
    ld b, 4
    call OvlSkip
    ld a, l
    ld [wOvlTalk], a
    ld a, h
    ld [wOvlTalk + 1], a
    ld b, 2
    call OvlSkip
    ldh a, [hIsCGB]
    and a
    jr nz, .color
    ld a, l
    ld [wOvlDoc], a
    ld a, h
    ld [wOvlDoc + 1], a
    ld b, 4
    call OvlSkip
    ld a, l
    ld [wOvlTalk], a
    ld a, h
    ld [wOvlTalk + 1], a
.color:
    xor a
    ld [wTalkState], a
    ld [wDocState], a
    ld a, 3                 ; (the first VBlanks: their sprites up)
    ld [wDocDirty], a
    ld a, 16
    ld [wDocMouth], a
    ld a, 32
    ld [wDocHand], a
    ret

; HL past a set of sprites for each of B states (its OAM place, how many, then 4 bytes each a state).
OvlSkip:
    inc hl
    ld a, [hl+]
    add a
    add a
    ld e, a
    ld d, 0
.state:
    add hl, de
    dec b
    jr nz, .state
    ret

; (VBlank) HL = a set of sprites by state (its OAM place, how many, every state's), A = the state: put in OAM.
OvlPut:
    ld b, a
    ld a, [hl+]
    ld e, a
    ld d, $FE
    ld a, [hl+]
    and a
    ret z
    add a
    add a
    ld c, a                 ; (bytes a state)
    inc b
.state:
    dec b
    jr z, .copy
    ld a, l
    add c
    ld l, a
    adc h
    sub l
    ld h, a
    jr .state
.copy:
    ld a, [hl+]
    ld [de], a
    inc de
    dec c
    jr nz, .copy
    ret

PUSHS
SECTION FRAGMENT "Overlay far", ROMX   ; (with the sprites' data: codegen _overlays)
; Color: the close-ups' sprites (HL: their tiles, then the scene's own sprites), up as the scene loads; the original
; shows its greys alone.
OverlayLoadIn:
    ldh a, [hIsCGB]
    and a
    jr nz, .color
    ld a, 1
    ld [wObp1Mode], a
    ld a, [hl+]             ; (the original: its own, after Color's tiles and sprites)
    ld e, a
    ld d, 0
    REPT 4
        sla e
        rl d
    ENDR
    add hl, de
    ld a, [hl+]
    add a
    add a
    ld e, a
    ld d, 0
    add hl, de
    jr .load
.color:
    xor a                   ; (sprite tiles: VRAM bank 0)
    ldh [rVBK], a
.load:
    ld a, [hl+]
    and a
    jr z, .tilesIn
    ld b, a
    ld de, $8000 + 16 * 2     ; (sprite tiles from 2: a menu's cursor's first)
.tile:
    push bc
    ld a, b
    and 3
    call z, VWait
    ld c, 16
.byte:
    ld a, [hl+]
    ld [de], a
    inc de
    dec c
    jr nz, .byte
    pop bc
    dec b
    jr nz, .tile
.tilesIn:
    call VWait
    ld a, l                 ; (sliding in: OvlSlideIn moves them with it)
    ld [wOvlStill], a
    ld a, h
    ld [wOvlStill + 1], a
    ld a, [hl+]
    and a
    ret z
    add a
    add a
    ld c, a
    ld de, $FE00 + 4 * 2
.oam:
    ld a, [hl+]
    ld [de], a
    inc de
    dec c
    jr nz, .oam
    ret

; (VBlank) the scene's own sprites as far up as its slide has it (hScrollY: 0 at rest), each hidden till it's on
; the screen; at rest, done.
OvlSlideIn:
    ld hl, wOvlStill
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    ld a, [hl+]
    and a
    jr z, .done
    ld c, a
    ldh a, [hScrollY]       ; (how far it's still to climb: 256 - SCY)
    cpl
    inc a
    ld b, a
    ld de, $FE00 + 4 * 2
.sprite:
    ld a, [hl+]
    add b
    jr c, .hide
    cp 160
    jr c, .put
.hide:
    xor a
.put:
    ld [de], a
    inc hl
    inc hl
    inc hl
    inc e
    inc e
    inc e
    inc e
    dec c
    jr nz, .sprite
    ldh a, [hScrollY]
    and a
    ret nz
.done:
    xor a
    ld [wOvlStill + 1], a
    ret

POPS

; HL = the rival's frames (after his cells' addresses and his two states' tiles: 4 bytes a cell).
TalkTimes:
    ld a, [wTalkN]
    add a
    add a
    ld l, a
    ld h, 0
    ld a, [wTalkPtr]
    add l
    ld l, a
    ld a, [wTalkPtr + 1]
    adc h
    ld h, a
    ret


; A frame of Doc in the corner (the NES's, measured): his mouth open 16 frames, shut 32; his hand up 56, down 32;
; once Select's pressed, faster: his mouth every 9, his hand every 8.
DocStepIn:
    call TalkStep
    ld hl, wDocMouth
    dec [hl]
    jr nz, .hand
    ld a, [wDocState]
    xor 1
    ld [wDocState], a
    ld b, a
    ld a, [wFtDocFast]
    and a
    ld a, 9
    jr nz, .mouth
    bit 0, b
    ld a, 16
    jr nz, .mouth
    ld a, 32
.mouth:
    ld [hl], a
    ld hl, wDocDirty
    set 0, [hl]
.hand:
    ld hl, wDocHand
    dec [hl]
    ret nz
    ld a, [wDocState]
    xor 2
    ld [wDocState], a
    ld b, a
    ld a, [wFtDocFast]
    and a
    ld a, 8
    jr nz, .handSet
    bit 1, b
    ld a, 56
    jr nz, .handSet
    ld a, 32
.handSet:
    ld [hl], a
    ld hl, wDocDirty
    set 0, [hl]
    ret

; The rival talking (the NES's, measured for each): his first state as the screen comes up, then the other and
; his first in turn, each its own frames.
TalkStep:
    ld a, [wTalkN]
    and a
    ret z
    ld hl, wTalkTimer
    dec [hl]
    ret nz
    ld a, [wTalkState]
    xor 1
    ld [wTalkState], a
    ld b, a
    call TalkTimes          ; (first, the other's, then his first's again)
    inc hl
    bit 0, b
    jr nz, .set
    inc hl
.set:
    ld a, [hl]
    ld [wTalkTimer], a
    ld hl, wDocDirty
    set 1, [hl]
    ret

; VBlank: the rival's cells as his state has them, then Doc's as his.
DocVBlankIn:
    ld hl, wDocDirty        ; (Doc's or the rival's, one a VBlank: both's cells, and the words typed after, would
    bit 0, [hl]             ; run past the original's)
    jr z, .rival
    res 0, [hl]
    ld hl, wOvlDoc          ; (his sprites as his state has them)
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    ld a, [wDocState]
    call OvlPut
    ld a, [wDocN]
    and a
    ret z
    ld c, a
    ld a, [wDocState]
    ld b, a
    inc b
    xor a
.offset:                    ; (state * cells)
    dec b
    jr z, .base
    add c
    jr .offset
.base:
    ld e, a
    ld d, 0
    ld hl, wDocTile
    add hl, de
    ld de, wDocAddr
.cell:                      ; [its address] = its tile
    ld a, [hl+]
    push hl
    ld b, a
    ld a, [de]
    inc de
    ld l, a
    ld a, [de]
    inc de
    ld h, a
    ld [hl], b
    pop hl
    dec c
    jr nz, .cell
    ret
.rival:
    res 1, [hl]
    ld hl, wOvlTalk
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    ld a, [wTalkState]
    call OvlPut
.talk:
    ld a, [wTalkN]
    and a
    ret z
    ld c, a
    ld a, [wTalkState]
    and a
    ld a, c
    jr z, .first            ; (his tiles after his cells' addresses, his other state's after his first's)
    add c
.first:
    add c
    ld e, a
    ld d, 0
    ld a, [wTalkPtr]
    ld l, a
    ld a, [wTalkPtr + 1]
    ld h, a
    push hl
    add hl, de
    pop de
    jr .cell

POPS
ELSE
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
ENDC

IF !DEF(FT_NES)
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

ENDC
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

IF !DEF(FT_NES)
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

ENDC
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

IF !DEF(FT_NES)
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

ENDC
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
IF !DEF(FT_NES)
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

ENDC
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

IF !DEF(FT_NES)
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
    cp SET_KNOCKDOWN
    jp nz, FtFrame
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

ENDC
; Show the celebration once its tiles are loaded.
FtCheer:
    ld a, [wFtSwapHave]
    cp SET_SPECIAL
    ret nz
    ld a, RP_TAUNT
    ld [wRvPose], a
    ret

IF !DEF(FT_NES)
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

ENDC                        ; (the kit's own fight: none of it when the NES game runs the fight)
; A = scene to go to after a pause.
; The fight's display ends: back to VBlank-only, no scroll split. LoadScene calls it, the screen faded out
; (till then his band stays where he is, not back to the middle).
; The original with a grey mat: A = BGP as the fade has it (kept), its own above the mat's line; hFtRingNow his
; ring's greys (hFtRingBgp) through it, the mat's line on. Keeps everything.
FtRingBase::
    ldh [hFtBgpBase], a
    push af
    push bc
    push de
    push hl
    ld b, a
    ldh a, [hFtRingBgp]
    and a
    jr z, .done
    call .map
    ldh [hFtRingNow], a
    ldh a, [hFtObpRaw]
    call .map
    ldh [hFtObpLow], a
    ldh a, [hFtObpRaw + 1]
    call .map
    ldh [hFtObpLow + 1], a
.done:
    pop hl
    pop de
    pop bc
    pop af
    ret
.map:                       ; A = four raw greys -> each as the fade shows it (B: BGP)
    ld c, a
    ld e, 0
    ld d, 4
.k:
    ld a, c
    and 3
    ld l, b
    jr z, .got
.shift:
    srl l
    srl l
    dec a
    jr nz, .shift
.got:
    ld a, l
    and 3
    rrca
    rrca
    srl e
    srl e
    or e
    ld e, a
    srl c
    srl c
    dec d
    jr nz, .k
    ld a, e
    ret

FtStop::
    di
    ld a, 1
    ldh [rIE], a
    xor a
    ldh [rSTAT], a
    ldh [hFtActive], a
    ldh [hFtRingBgp], a     ; (the ring's greys: the fight's own)
    ldh [rSCX], a
    ldh [rSCY], a
    ret

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
    ld a, M_END
    ld [wFtMatch], a
IF DEF(FT_NES)
    ld a, FT_NES_END        ; Punch-Out!! fades out on the call itself
ELSE
    ld a, FT_END
ENDC
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
    ; (his band keeps its scroll through the fade: FtStop, as the next scene loads)
    call FtCareerResult
    call FtResultScene
    jp StartTransition

; Mac's record and where a loss takes him, as Punch-Out!!'s: a win counts (a KO or TKO a KO too); a loss
; counts, then the third (or the last fight's) is game over, a title bout's drops him down the ranks, a first
; loss to him is a rematch, a lost rematch drops him a place (not below his circuit's first: a rematch again).
FtCareerResult:
    ld a, [wFtCareer]
    and a
    ret z                   ; (no circuits)
    ld a, [wFtResult]
    cp FT_WIN_SCENE
    jr nz, .notWin
    ld hl, wRecWins
    call .count
    ld a, [wFtCount]
    cp COUNT_TKO
    jr c, .points
    ld hl, wRecKOs
    call .count
.points:
    xor a
    ld [wRecLost], a
    ld a, [wFtWinNext]      ; on: the next (in the Another World Circuit, its next)
    ld b, a
    ld a, [wAw]
    and a
    jr z, .on
    ld a, [wFtAwNext]
    cp $FF
    jr z, .on
    ld b, a
.on:
    ld a, b
    ld [wRecNext], a
    ret
.notWin:
    cp FT_LOSE_SCENE
    ret nz                  ; (the corner)
    ld hl, wRecLosses
    call .count
    ld a, [wFtOverScene]
    ld b, a
    ld a, [wRecLosses]
    cp 3
    jr nc, .next
    ld a, [wAw]             ; (the Another World Circuit's ranks, if it's on)
    and a
    ld a, [wFtCareer]
    ld c, a
    ld a, [wFtDropScene]
    jr z, .ranks
    ld a, [wFtAwCareer]
    ld c, a
    ld a, [wFtAwDrop]
.ranks:
    ld d, a                 ; (D: down to)
    bit CAREER_FINAL, c
    jr nz, .next            ; (B: game over)
    ld b, d
    bit CAREER_TITLE, c
    jr nz, .dropped
    ld hl, wRecLost
    ld a, [wFtRematchScene]
    ld b, a
    ld a, [hl]
    and a
    jr z, .first
    bit CAREER_FIRST, c
    jr nz, .next
    ld b, d
.dropped:
    xor a
    ld [wRecLost], a
    jr .next
.first:
    inc [hl]
.next:
    ld a, b
    ld [wRecNext], a
    ret
.count:                     ; [HL] + 1, at most 99
    ld a, [hl]
    cp 99
    ret nc
    inc [hl]
    ret

; A new career: no wins, no losses.
RecReset::
    xor a
    ld hl, wRecWins
    ld [hl+], a
    ld [hl+], a
    ld [hl+], a
    ld [hl+], a
    ld [hl+], a             ; (Another World off)
    ret

; Mac's record, the Another World Circuit's words, the fight's time, from any bank (in "Screens far", with the
; data they read).
AwPatch::
    ld a, BANK(AwPatchIn)
    jr ScreensFar
RecordDraw::
    ld a, BANK(RecordDrawIn)
    ld [$2100], a
    call RecordDrawIn
    jr ScreensBack
KeyDraw::
    ld a, BANK(KeyDrawIn)
    ld [$2100], a
    call KeyDrawIn
    jr ScreensBack
IF DEF(FT_NES)
TimeDraw::
    ld a, BANK(TimeDrawIn)
    ld [$2100], a
    call TimeDrawIn
    jr ScreensBack
ENDC
ScreensFar:                 ; (AwPatch's: A its bank)
    ld [$2100], a
    call AwPatchIn
ScreensBack:
    ldh a, [hBank]
    ld [$2100], a
    ret

; A = the scene the fight goes on to, from its result (won, lost, the corner): this fight's own (FtFights).
FtResultScene:
    ld a, [wFtResult]
    cp FT_LOSE_SCENE
    ld a, [wFtLoseScene]
    ret z
    ld a, [wFtResult]
    cp FT_CORNER_RESULT
    ld a, [wFtCornerScene]
    ret z
    ld a, [wFtCount]        ; won: on a TKO, its own screen if there's one
    cp COUNT_TKO
    ld a, [wFtWinScene]
    ret nz
    ld a, [wFtTkoScene]
    cp $FF
    ret nz
    ld a, [wFtWinScene]
    ret

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
    jp FtHudMap             ; values -> tiles (unrolled, by its tables, in their bank)
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
IF DEF(FT_NES)
    and 15                  ; a new flash now and then (Punch-Out!!'s: every 16-21 frames)
ELSE
    and 3                   ; a new flash every few frames
ENDC
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
    ld a, [wFtRand]         ; column = 1 + random % 18 (not over the corner posts)
    swap a
.mod:
    cp FT_CROWD_W - 2
    jr c, .col
    sub FT_CROWD_W - 2
    jr .mod
.col:
    inc a
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
IF DEF(FT_NES)
    ld a, [wFtRand]         ; frames lit (Punch-Out!!'s: 2 to 8)
    and 7
    cp 7
    jr c, .lit
    dec a
.lit:
    add 2
    ld [hl], a
ELSE
    ld [hl], 4              ; frames lit
ENDC
    ret

IF DEF(FT_NES)
; During VBlank (Color), his KO: the crowd going wild, as Punch-Out!!'s, its color stepping through CrowdPulse.
FtCrowdPulse:
    ldh a, [hIsCGB]
    and a
    ret z
    ld a, [wNes + $00]      ; him counted out or stopped ($FE, $FC)
    cp $FC
    jr z, .wild
    cp $FE
    ret nz
.wild:
    ld hl, CrowdPulse
    ld a, [hl+]
    ldh [rBCPS], a
    ldh a, [hFrame]         ; a step every 4 frames
    and %1100
    srl a
    add l
    ld l, a
    adc h
    sub l
    ld h, a
    ld a, [hl+]
    ldh [rBCPD], a
    ld a, [hl]
    ldh [rBCPD], a
    ret
ENDC

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
        ld a, [wFtFlashTile]
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
    or FT_SAY_ATTR           ; (white and black, as his bubble)
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
    ld a, FT_SAY_ATTR
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
    cp SET_KNOCKDOWN
    ret nz
.show:
    ld a, [wRvPose]         ; his head's height in this pose (his other way down: as the first)
    cp RP_KD2_STAGGER
    jr c, .firstWay
    sub RP_KD2_STAGGER - RP_KD_STAGGER
.firstWay:
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
    ld a, FT_SAY_ATTR
    ld [hl+], a
    pop af
    add 5                   ; the next star, a third of the way round
    dec c
    jr nz, .star
    ret

IF DEF(FT_TWINKLE_TILE)
DEF TWINKLE_OVER EQU 10     ; (its top this far over his head: a few pixels clear, as the NES's)
; A star just earned: it twinkles beside his head, where the NES's does, while its count runs ($0343: 20
; frames). HL = the next OAM entry.
FtTwinkle:
IF DEF(FT_ROPE)
    ld b, a
    push hl                 ; its height: over his head as his pose shows it (his area's top, his band's offset,
    ld a, [wRvPose]         ; the pose's clear rows above his head), the NES's few pixels over it (the NES's
    ld e, a                 ; own spot is for the NES's pictures: on ours it can land on his face)
    ld d, 0
    ld hl, RivalPoseRise
IF DEF(FT_NES)
    ld a, [wFtBankPics]     ; (his pictures, Color's and the original's alike: the picture showing's own rows)
    and a
    jr z, .rise
    ld a, [wRvPicShown]
    ld e, a
    ld hl, RivalPicRise
.rise:
ENDC
    add hl, de
    ld d, [hl]
    pop hl
    ldh a, [hFtBandY]
    cpl
    inc a
    add FT_HEAD_Y0 - TWINKLE_OVER
    add d
    cp 16 + 24              ; (no higher than the crowd's top: a tall one leaning up would put it in the HUD)
    jr nc, .twinkleY
    ld a, 16 + 24
.twinkleY:
    ld [wFtTwinkleY], a
    ld a, [wFtTwinkleY]     ; which list: the upper if it ends before FT_DMA_LINE, the lower if it starts after
    cp FT_DMA_LINE + 16 - 8 + 1
    ld a, 0
    rla                     ; (carry: it ends above)
    xor 1                   ; A = 1 if it doesn't end above (the lower's)
    cp b
    ret nz
ENDC
    ld a, [wNes + $0343]
    and a
    ret z
    bit 7, a
    ret nz
    ld c, a
    ldh a, [hIsCGB]
    and a
    ld a, 4                 ; on 4 frames, off 4 (the NES's turns between its sparkles)
    jr nz, .mask
    ld a, 6                 ; (the original: on 6, off 2 -- its LCD's smear would all but hide 4 and 4)
.mask:
    and c
    ret z
    ld a, [wFtTwinkleY]
    ld [hl+], a
    ld a, [wFtTwinkleX]
    ld [hl+], a
    ld a, FT_TWINKLE_TILE
    ld [hl+], a
    ld a, FT_SAY_ATTR
    ld [hl+], a
    ret
ENDC

IF DEF(FT_ROPE) && DEF(FT_NES)
; His turban's gem (RivalJewel: Great Tiger's), a sprite of its own where his pose shows it, his band's offsets
; as his top rows'; in his tell, white every few frames (the original: on and off). A = which list (0 upper,
; 1 lower: the one the line it ends on falls in), HL = the next OAM entry.
FtJewel:
    ld b, a
    ld a, [RivalJewel]
    and a
    ret z
    ld a, l
    cp 160
    ret nc
    push hl
IF DEF(FT_NES)
    ld a, [wFtBankPics]     ; his pictures: where the one his sprites are built for shows it (each its own)
    and a
    jr z, .pose
    ldh a, [hIsCGB]
    and a
    jr nz, .pic
    ld a, [wFtBankPicsDmg]
    and a
    jr z, .pose
.pic:
    ldh a, [hBank]
    push af
    ld a, [wFtBankPics]
    ld [$2000], a
    ld a, [wRvPicHeads]
    add a
    ld e, a
    ld d, 0
    ld hl, FT_PIC_JEWEL
    add hl, de
    ld e, [hl]
    inc hl
    ld d, [hl]
    pop af
    ld [$2000], a
    ld a, e
    cp $FF
    jr z, .none
    jr .at
.pose:
ENDC
    ld a, [wRvPose]
    add a
    ld e, a
    ld d, 0
    ld hl, RivalJewel + 3
    add hl, de
    ld a, [hl+]
    cp $FF
    jr z, .none
    ld e, a                 ; E = its x in his area, D = its y
    ld d, [hl]
.at:
    pop hl
    ldh a, [hFtBandY]
    cpl
    inc a
    add FT_HEAD_Y0 - 4
    add d
    ld d, a                 ; OAM y
    cp FT_DMA_LINE + 16 - 8 + 1
    ld a, 0
    rla
    xor 1                   ; (1: it ends past the line the lower list comes in at)
    cp b
    ret nz
    call FtTellShown        ; his tell: white every few frames (the original: on and off)
    ld c, a
    ldh a, [hFrame]
    and 4
    jr z, .colors
    ld a, c
    and a
    jr z, .colors
    ldh a, [hIsCGB]
    and a
    ret z
    ld c, 2                 ; (C: 2 white)
    jr .put
.colors:
    ld c, 1
.put:
    ld a, d
    ld [hl+], a
    ldh a, [hFtBandX]
    cpl
    inc a
    add FT_HEAD_X0 - 4
    add e
    ld [hl+], a
    ld a, [RivalJewel]
    ld [hl+], a
    ld a, c
    dec a
    ld a, [RivalJewel + 1]
    jr z, .attr
    ld a, [RivalJewel + 2]
.attr:
    ld [hl+], a
    ret
.none:
    pop hl
    ret
ENDC

IF DEF(FT_ROPE)
; His rows above his band, as the NES's sprites stand in front of its ropes and crowd: sprites of his top rows'
; tiles (kept where sprites reach them), where his band would show them: the pose VBlank draws next, his band's
; offsets this frame. HL = the next OAM entry.
FtHeadSprites:
    push hl
IF DEF(FT_NES)
    ld a, [wFtBankPics]     ; Color with his pictures: the picture's own
    and a
    jr z, .poses
    ldh a, [hIsCGB]
    and a
    jr nz, .cgbPics
    ld a, [wFtBankPicsDmg]  ; (the original with its greys: that picture's list, in its tiles' copy)
    and a
    jr z, .poses
    call .same
    jr z, .kept
    ld a, [wRvPicHeadsBuf]
    rrca
    rrca
    ld [wFtHeadTile], a
    ld a, [wRvPicHeads]
    call FtDmgEntry         ; (HL: its sprites' address)
    jr .read
.kept:                      ; (as last frame's: the same picture, copy, place and start -- left as they are)
    pop hl
    ld a, [wFtHeadEnd]
    ld l, a
    jp .done
.cgbPics:
    ld a, [wRvPicHeadsBuf]  ; (its tiles' copy: the second, 64 on)
    rrca
    rrca
    ld [wFtHeadTile], a
    ld a, [wFtBankPics]
    ld [$2000], a
    ld a, [wRvPicHeads]
    add a
    ld e, a
    ld d, 0
    ld hl, FT_PIC_HEADS
    add hl, de
    jr .read
.poses:
ENDC
    xor a
    ld [wFtHeadTile], a
    ld a, [wFtBankHeads]
    ld [$2000], a
    ld a, [wRvPose]
    add a
    ld e, a
    ld d, 0
    ldh a, [hIsCGB]         ; (Color: its own, after the original's)
    and a
    jr z, .table
    ld a, e
    add RP_COUNT * 2
    ld e, a
.table:
    ld hl, $4000
    add hl, de
.read:
    ld a, [hl+]
    ld d, [hl]
    ld e, a
.list:                      ; (DE: the list)
    pop hl
    ld a, [de]
    inc de
    and a
    jp z, .done
    ldh [hFtHeadN], a
    ldh a, [hFtBandX]       ; his area's left, top on screen (as OAM x, y): scrolled with his band
    cpl
    inc a
    add FT_HEAD_X0
    ld b, a                 ; B = x, C = y
    ldh a, [hFtBandY]
    cpl
    inc a
    add FT_HEAD_Y0
    ld c, a
    ld a, [wFtHeadTile]     ; (his tiles' copy: 0, or 64 on)
    ldh [hFtPlTile], a
    push hl                 ; (HL his sprites, DE the list being built)
    ld h, d
    ld l, e
    pop de
    ldh a, [hIsCGB]         ; (the original: its own loop, no eyes' whites to keep)
    and a
    jr nz, .sprite
.dmg:
    ld a, e
    cp 160
    jr nc, .full
    ld a, [hl+]             ; y: his band shows this row on (the rest too: top row first)
    add c
    cp FT_HEAD_LIMIT
    jr nc, .full
    ld [de], a
    ld a, [hl+]             ; x: off the right edge, no sprite spent on it
    add b
    cp 168
    jr nc, .dmgSkip
    inc e
    ld [de], a
    inc e
    ldh a, [hFtPlTile]
    add [hl]
    inc hl
    ld [de], a
    inc e
    ld a, [hl+]
    ld [de], a
    inc e
.dmgNext:
    ldh a, [hFtHeadN]
    dec a
    ldh [hFtHeadN], a
    jr nz, .dmg
    jr .full
.dmgSkip:
    xor a
    ld [de], a
    inc hl
    inc hl
    jr .dmgNext
.sprite:
    ld a, e
    cp 160
    jr nc, .full            ; (no room left)
    ld a, [hl+]             ; dy
    add c
    cp FT_HEAD_LIMIT        ; his band shows this row (and every one after: the lists go top row first)
    jr c, .shown
    push af                 ; (nothing written till it's drawn: a slot past the list's end stays hidden)
    inc hl                  ; (Color: an eye's white his tile can't show, bit 4 -- the original's palette bit, not
    inc hl                  ; Color's: drawn wherever it is; the whites come first)
    bit 4, [hl]
    dec hl
    dec hl
    jr z, .fullPop
    ldh a, [hIsCGB]
    and a
    jr z, .fullPop
    pop af
.shown:
    ld [de], a
    ld a, [hl+]             ; dx
    add b
    cp 168                  ; off the right edge (his corner): no sprite spent on it
    jr nc, .skip2
    inc e
    ld [de], a
    inc e
    ldh a, [hFtPlTile]      ; tile
    add [hl]
    inc hl
    ld [de], a
    inc e
    ld a, [hl+]             ; attributes
    ld [de], a
    inc e
    jr .next
.skip2:
    xor a                   ; (its y, written already, undone: past the list's end the slot stays hidden)
    ld [de], a
    inc hl
    inc hl
.next:
    ldh a, [hFtHeadN]
    dec a
    ldh [hFtHeadN], a
    jr nz, .sprite
    jr .full
.fullPop:
    pop af
.full:
    ld h, d
    ld l, e
.done:
    ld a, l                 ; (where they ended: for next frame's, if the same)
    ld [wFtHeadEnd], a
    ld a, [wFtBankData]
    ld [$2000], a
    ret
IF DEF(FT_NES)
; Z: his top rows' sprites as last built -- the same picture, its copy, his band's x and y, from the same place in
; the list (its next entry's low byte at [SP + 2]): there still. Either way, these noted for next frame's.
.same:
    ld hl, sp + 2
    ld a, [hl]
    ld hl, wFtHeadKey + 4
    ld b, [hl]
    ld [hl], a
    xor b
    ld e, a
    ld hl, wFtHeadKey
    ld a, [wRvPicHeads]
    ld b, [hl]
    ld [hl+], a
    xor b
    or e
    ld e, a
    ld a, [wRvPicHeadsBuf]
    ld b, [hl]
    ld [hl+], a
    xor b
    or e
    ld e, a
    ldh a, [hFtBandX]
    ld b, [hl]
    ld [hl+], a
    xor b
    or e
    ld e, a
    ldh a, [hFtBandY]
    ld b, [hl]
    ld [hl], a
    xor b
    or e
    ret
ENDC
ENDC

IF DEF(FT_SIDE_TILE)
; The ring's side ropes, down off the posts to the screen's edges: their ends below the crowd's rows (fixed: the
; lines there scroll with his band). HL = the next OAM entry.
FtSideRopes:
    ld de, FtSideRopeOAM
    ldh a, [hIsCGB]
    and a
    jr nz, .cgb
    ld de, FtSideRopeOAMDmg
.cgb:
    ld b, 4 * 4
.copy:
    ld a, [de]
    inc de
    ld [hl+], a
    dec b
    jr nz, .copy
    ret
FtSideRopeOAM:
    db FT_SIDE_Y, 8, FT_SIDE_TILE, FT_SIDE_ATTR | $80           ; (behind his band's colors: over the mat only)
    db FT_SIDE_Y + 8, 8, FT_SIDE_TILE + 1, FT_SIDE_ATTR | $80
    db FT_SIDE_Y, 160, FT_SIDE_TILE, FT_SIDE_ATTR | $A0
    db FT_SIDE_Y + 8, 160, FT_SIDE_TILE + 1, FT_SIDE_ATTR | $A0
FtSideRopeOAMDmg:           ; (the original: its own copy of the tiles, OBP0 -- his ring's greys up there)
    db FT_SIDE_Y, 8, FT_SIDE_TILE_DMG, $80
    db FT_SIDE_Y + 8, 8, FT_SIDE_TILE_DMG + 1, $80
    db FT_SIDE_Y, 160, FT_SIDE_TILE_DMG, $A0
    db FT_SIDE_Y + 8, 160, FT_SIDE_TILE_DMG + 1, $A0
ENDC

StarOrbit:                  ; an ellipse: dx, dy in 16 steps
    db 0, -4,  5, -4,  9, -3,  12, -1,  13, 1,  12, 3,  9, 5,  5, 6
    db 0, 6,  -5, 6,  -9, 5,  -12, 3,  -13, 1,  -12, -1,  -9, -3,  -5, -4
StarHeadY:                  ; head top, per knockdown pose
    db 8, 16, 24, 8, 8

; The player's vertical motion: A = y offset (down). Bobbing, lunging, recoiling, crouching.
FtPlayerMotion:
IF DEF(FT_NES)
    ld a, [wPlNesY]         ; Mac's scripts move him sideways ($15); his knockdown frames sit lower
    and $7F
    ret
ELSE                        ; (the rest: the kit's own Mac, none of it the NES's)
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

PunchRise:                  ; per frame of a body punch: y offset (a leap up into it)
    db 0, -6, -11, -14, -16, -16, -16, -14, -11, -8, -5, -3, -1, 0, 0
PunchRiseHigh:              ; to the face: right up to his chin
    db 0, -10, -19, -26, -31, -32, -32, -29, -23, -16, -10, -5, -2, 0, 0
ENDC


; The referee's sprites and words, about to be built at HL: Z if they're as last built in this list (D: where they
; ended); NZ otherwise (this key noted, for these). Keeps HL.
FtRefSame:
    push hl
    ld a, h
    and 1
    add a
    add a
    add a
    add LOW(wFtRefKey)
    ld e, a
    adc HIGH(wFtRefKey)
    sub e
    ld d, a
    ld a, l                 ; where they begin
    ld h, d
    ld l, e
    ld b, [hl]
    ld [hl+], a
    xor b
    ld e, a
    ld a, [wFtRefShown]
    ld b, [hl]
    ld [hl+], a
    xor b
    or e
    ld e, a
    ld a, [wFtRefX]
    ld b, [hl]
    ld [hl+], a
    xor b
    or e
    ld e, a
    ld a, [wFtRefSlot]
    ld b, [hl]
    ld [hl+], a
    xor b
    or e
    ld e, a
    ld a, [wFtSay]
    ld b, [hl]
    ld [hl+], a
    xor b
    or e
    ld e, a
    ld a, [wFtCount]
    ld b, [hl]
    ld [hl+], a
    xor b
    or e
    ld d, [hl]
    pop hl
    ret

IF DEF(FT_MAC_PICS) && DEF(FT_NES)
; Mac's sprites, his pictures', about to be built at DE (its list's page in D) from his picture wPlPicHeads with
; hFtPlY/X/Tile, BC his palette's mask and bits: Z if they're as last built in this list (HL: where they ended);
; NZ otherwise (this key noted, for these). Either way, the path noted.
FtMacSame:
    ld a, 1
    ld [wFtMacPath], a
    ld a, d
    and 1
    add a
    add a
    add a
    add LOW(wFtMacKey)
    ld l, a
    adc HIGH(wFtMacKey)
    sub l
    ld h, a
    push bc
    ld a, e                 ; where they begin
    ld b, [hl]
    ld [hl+], a
    xor b
    ld e, a
    ld a, [wPlPicHeads]
    ld b, [hl]
    ld [hl+], a
    xor b
    or e
    ld e, a
    ldh a, [hFtPlTile]
    ld b, [hl]
    ld [hl+], a
    xor b
    or e
    ld e, a
    ldh a, [hFtPlY]
    ld b, [hl]
    ld [hl+], a
    xor b
    or e
    ld e, a
    ldh a, [hFtPlX]
    ld b, [hl]
    ld [hl+], a
    xor b
    or e
    pop bc
    ld e, a
    ld a, b
    ld b, [hl]
    ld [hl+], a
    xor b
    or e
    ld e, a
    ld a, c
    ld b, [hl]
    ld [hl+], a
    xor b
    or e
    ret
ENDC

FtBuildOAM:
IF DEF(FT_MAC_PICS) && DEF(FT_NES)
    xor a
    ld [wFtMacPath], a
ENDC
IF DEF(FT_ROPE)
    ldh a, [hFtOamBuild]    ; (Mac, the referee: the screen's lower part's list, the one not being shown)
    ld h, a
    ld l, 0
ELSE
    ld hl, wFtOAM
ENDC
IF DEF(FT_NES)
    ld a, [wNes + $61]      ; Mac down, his frame Punch-Out!!'s GET UP!: its letters at the screen's foot
    cp $3A
    call z, FtGetUp
ENDC
    call FtPlShown
    add a
    ld e, a
    ld d, 0
    push hl
    ld hl, PlayerPoses
IF DEF(FT_PL_CGB)
    ldh a, [hIsCGB]         ; Color: his own, finer
    and a
    jr z, .dmgPoses
    ld hl, PlayerPosesCgb
.dmgPoses:
ENDC
    add hl, de
    ld a, [hl+]
    ld d, [hl]
    ld e, a
    pop hl
IF DEF(FT_MAC_PICS)
    push hl                 ; his picture's sprites (its bank mapped till they're built), in its copy
    ld a, [wPlPicHeads]
    call FtPlPicEntry
    ld d, h
    ld e, l
    pop hl
    ld a, [wPlPicHeadsBuf]
    ld b, a
    ldh a, [hIsCGB]
    and a
    jr z, .macTilesDmg
    xor a                   ; (Color: bank 1, 0 on, the second copy 32 on)
    dec b
    jr nz, .macTiles
    ld a, FT_MAC_PIC_ROOM
    jr .macTiles
.macTilesDmg:
    ld a, FT_OBJ_FIRST      ; (the original: after the sprite tiles' first two, the second copy 18 on)
    dec b
    jr nz, .macTiles
    ld a, FT_OBJ_FIRST + FT_DMG_MAC_ROOM
.macTiles:
    ld [wFtPlTileAdd], a
ENDC
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
    ld a, b                 ; (a picture of nothing: no sprites)
    and a
    jp z, .refStart
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
IF DEF(FT_MAC_PICS) && DEF(FT_NES)
    ld a, [wPlFlip]         ; his pictures (never flipped): his palette decided once, one loop (y, x and his tiles'
                            ; copy from HRAM, his attributes AND B OR C: the original's own palette bits unused)
    and a
    jp nz, .sprite
    ld a, b
    ldh [hFtHeadN], a
    ld a, [wFtPlayerY]
    ldh [hFtPlY], a
    ld a, c
    ldh [hFtPlX], a
    ld a, [wFtPlTileAdd]
    ldh [hFtPlTile], a
    ld bc, $FF00            ; (as below: hit, knocked down, worn out: his palette; else as is)
    ld a, [wNes + $048E]
    cp $25
    jr z, .macDown
    ld a, [wPlNesY]
    rlca
    jr c, .macDown
    ld a, [wPlTired]
    and a
    jr z, .macGo
    ld bc, $F800 | FT_TIRED_PAL
    jr .macGo
.macDown:
    ld bc, $F800 | FT_DOWN_PAL
.macGo:
    ldh a, [hIsCGB]         ; (Color: built every time, as it was)
    and a
    jr nz, .macBuild
    push bc                 ; (as last built in this list: left as they are)
    push de
    push hl
    ld d, h
    ld e, l
    call FtMacSame
    jr nz, .macMiss
    ld a, [hl]              ; (where they ended)
    pop hl
    ld l, a
    pop de
    pop bc
    jp .refStart
.macMiss:
    pop hl
    pop de
    pop bc
.macBuild:
    push hl                 ; (HL his sprites, DE the list being built)
    ld h, d
    ld l, e
    pop de
    ldh a, [hIsCGB]         ; (the original: its own loop -- y, x in B, C, his attributes as they are, its palette
    and a                   ;  bits unused)
    jr nz, .mac
    ldh a, [hFtPlY]
    ld b, a
    ldh a, [hFtPlX]
    ld c, a
.macDmg:
    ld a, [hl+]
    add b
    ld [de], a
    inc e
    ld a, [hl+]
    add c
    ld [de], a
    inc e
    ldh a, [hFtPlTile]
    add [hl]
    inc hl
    ld [de], a
    inc e
    ld a, [hl+]
    ld [de], a
    inc e
    ldh a, [hFtHeadN]
    dec a
    ldh [hFtHeadN], a
    jr nz, .macDmg
    jr .macEnd
.mac:
    ldh a, [hFtPlY]
    add [hl]
    inc hl
    ld [de], a
    inc e
    ldh a, [hFtPlX]
    add [hl]
    inc hl
    ld [de], a
    inc e
    ldh a, [hFtPlTile]
    add [hl]
    inc hl
    ld [de], a
    inc e
    ld a, [hl+]
    and b
    or c
    ld [de], a
    inc e
    ldh a, [hFtHeadN]
    dec a
    ldh [hFtHeadN], a
    jr nz, .mac
.macEnd:
    ld h, d
    ld l, e
    ldh a, [hIsCGB]         ; (Color: built every time, as it was)
    and a
    jp nz, .refStart
    ld a, h                 ; (where they ended, for next time in this list)
    and 1
    add a
    add a
    add a
    add LOW(wFtMacKey + 7)
    ld e, a
    adc HIGH(wFtMacKey + 7)
    sub e
    ld d, a
    ld a, l
    ld [de], a
    jp .refStart
ENDC
.dmgSprites:
    ldh a, [hIsCGB]         ; the original: no Color palettes to choose (their bits unused), a loop each way
    and a
    jr nz, .sprite
    ld a, b
    ldh [hFtHeadN], a
    ld a, [wFtPlayerY]
    ld b, a
    ld a, [wPlFlip]
    and a
    jr nz, .dmgFlip
.dmgPlain:
    ld a, [de]              ; dy
    inc de
    add b
    ld [hl+], a
    ld a, [de]              ; dx
    inc de
    add c
    ld [hl+], a
    ld a, [de]              ; tile
    inc de
    ld [hl+], a
    ld a, [de]              ; attributes
    inc de
    ld [hl+], a
    ldh a, [hFtHeadN]
    dec a
    ldh [hFtHeadN], a
    jr nz, .dmgPlain
    jp .refStart
.dmgFlip:
    ld a, [de]              ; dy
    inc de
    add b
    ld [hl+], a
    ld a, [de]              ; dx, mirrored: (FT_PLAYER_W - 8) - dx
    inc de
    cpl
    add FT_PLAYER_W - 8 + 1
    add c
    ld [hl+], a
    ld a, [de]              ; tile
    inc de
    ld [hl+], a
    ld a, [de]              ; attributes, mirrored
    inc de
    xor OAMF_XFLIP
    ld [hl+], a
    ldh a, [hFtHeadN]
    dec a
    ldh [hFtHeadN], a
    jr nz, .dmgFlip
    jp .refStart
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
IF DEF(FT_MAC_PICS)
    push hl
    ld hl, wFtPlTileAdd
    add [hl]
    pop hl
ENDC
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
IF DEF(FT_NES)
    ld a, [wNes + $048E]    ; hit: the NES turns his skin pink ($25), as on his knockdown frames (Color)
    cp $25
    jr z, .down
    ld a, [wPlNesY]
    rlca
    jr nc, .up
.down:
    pop af
    and ~7
    or FT_DOWN_PAL
    jr .write
.up:
ENDC
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
IF DEF(FT_MAC_PICS)
    ld a, [wFtBankData]     ; (his pictures' bank was mapped)
    ld [$2000], a
ENDC
IF DEF(FT_MAC_PICS) && DEF(FT_NES)
    ldh a, [hIsCGB]         ; (Color: built every time, as it was)
    and a
    jr nz, .macKeyed
    ld a, [wFtMacPath]      ; (built some other way, or none: this list's key no longer his sprites')
    and a
    jr nz, .macKeyed
    push hl
    ld a, h
    and 1
    add a
    add a
    add a
    add LOW(wFtMacKey)
    ld l, a
    adc HIGH(wFtMacKey)
    sub l
    ld h, a
    ld [hl], $FF
    pop hl
.macKeyed:
ENDC
IF FT_FX_STARS
    call FtStars
ENDC
IF DEF(FT_TWINKLE_TILE)
IF DEF(FT_ROPE)
    ld a, 1                 ; (in the lower list if it's under the line where that list comes in)
ENDC
    call FtTwinkle
ENDC
IF DEF(FT_ROPE) && DEF(FT_NES)
    ld a, 1
    call FtJewel
ENDC
IF FT_FX_SWEAT
    call FtSweatSprites
ENDC
IF FT_FX_SPARK
    call FtSparkSprites
ENDC
    ; the referee, and what he's saying
    ldh a, [hIsCGB]         ; (Color: built every time, as it was)
    and a
    jr nz, .refBuild
    call FtRefSame          ; (as last built in this list, from here: left as they are)
    jr nz, .refBuild
    ld l, d
    jp .clear
.refBuild:
    ld a, [wFtRefX]         ; off screen, his sprites land past the right edge, which hides them
    add 8
    ld c, a                 ; C = OAM x of his left edge
    ld a, [wFtRefShown]     ; (the pose whose tiles are in: the one asked for shows once they are)
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
    ld a, [wFtRefSlot]      ; (his tiles' area shown: slot 0 as they are, slot 1 his own ones moved on)
    and a
    jr nz, .refSprite1
.refSprite:
    ld a, [de]              ; dy
    inc de
    add FT_REF_Y + 16
    ld [hl+], a
    ld a, [de]              ; dx
    inc de
    add c
    ld [hl+], a
    ld a, [de]              ; tile
    inc de
    ld [hl+], a
    ld a, [de]
    inc de
    ld [hl+], a
    dec b
    jr nz, .refSprite
    jr .refDone
.refSprite1:
    ld a, [de]              ; dy
    inc de
    add FT_REF_Y + 16
    ld [hl+], a
    ld a, [de]              ; dx
    inc de
    add c
    ld [hl+], a
    ld a, [de]              ; tile: his own ones in the area shown
    cp FT_REF_SLOT
    jr c, .slot0
    add FT_REF_TILES
.slot0:
    inc de
    ld [hl+], a
    ld a, [de]
    inc de
    ld [hl+], a
    dec b
    jr nz, .refSprite1
.refDone:
    ld a, [wFtSay]          ; his words, in a speech bubble beside his head
    and a
    jp z, .clear
IF DEF(FT_WORDS)
    ld b, 10                ; the NES game's bubble for it: 1-10 (0-9), KO! 10, TKO 11, Fight! 12
    cp SAY_KO
    jr z, .word
    ld b, 11
    cp SAY_TKO
    jr z, .word
    ld b, 12
    cp SAY_FIGHT
    jr z, .word
    ld a, [wFtCount]
    dec a
    ld b, a
.word:
    ld a, b
    add a
    add LOW(FtWords)
    ld e, a
    adc HIGH(FtWords)
    sub e
    ld d, a
    ld a, [de]
    inc de
    push af
    ld a, [de]
    ld d, a
    pop af
    ld e, a
    ld a, [de]              ; its sprites: y, x from his frame, tile
    inc de
    ld b, a
.wordSprite:
    ld a, [de]
    inc de
    add FT_REF_Y + 16
    ld [hl+], a
    ld a, [de]
    inc de
    add c
    ld [hl+], a
    ld a, [de]
    inc de
    ld [hl+], a
    ld a, FT_SAY_ATTR
    ld [hl+], a
    dec b
    jr nz, .wordSprite
    jp .clear
ENDC
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
    cp SAY_TKO
    ld de, SayTKO
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
    ldh a, [hIsCGB]         ; (Color: built every time, as it was)
    and a
    jr nz, .refKeyed
    push hl                 ; (where the referee's ended, for next time in this list)
    ld a, h
    and 1
    add a
    add a
    add a
    add LOW(wFtRefKey + 6)
    ld e, a
    adc HIGH(wFtRefKey + 6)
    sub e
    ld d, a
    ld a, l
    ld [de], a
    pop hl
.refKeyed:
IF DEF(FT_ROPE)
    call .hideRest          ; the lower list done; the upper: his top rows over the ropes (and the star if there)
.upper:
    ld hl, wFtOAM
IF DEF(FT_NES)
    xor a                   ; (his turban's gem first: in front of his top rows' sprites)
    call FtJewel
ENDC
    call FtHeadSprites
IF DEF(FT_SIDE_TILE)
    ldh a, [hIsCGB]         ; the ring's side ropes' ends, past the crowd's rows, behind him (the original: OBP1,
    and a                   ; the referee's, its white; over a white mat only they'd not show)
    jr nz, .sideRopes
    ldh a, [hFtRingBgp]
    and a
.sideRopes:
    call nz, FtSideRopes
ENDC
IF DEF(FT_TWINKLE_TILE)
    xor a
    call FtTwinkle
ENDC
.hideRest:
ENDC
.hide:                      ; the rest hidden: only the slots this list filled last time past where it ends now (the
    ld a, h                 ; rest are hidden already)
    sub HIGH(wFtOAM)
    add LOW(wFtOAMEnd)
    ld e, a
    adc HIGH(wFtOAMEnd)
    sub e
    ld d, a                 ; DE = this list's end last time
    ld a, [de]
    ld b, a
    ld a, l
    cp 160
    jr c, .end160
    ld a, 160
.end160:
    ld [de], a
    ld a, b
    sub l
    ret c
    ret z
    rrca
    rrca
    and $3F
    ld b, a                 ; B = slots to hide
    xor a
.hideSlot:
    ld [hl], a
    ld a, l
    add 4
    ld l, a
    xor a
    dec b
    jr nz, .hideSlot
    ret
.put:                       ; the next piece of the bubble: tile B at wFtSayX, then step right
    ld a, FT_SAY_Y + 16
    ld [hl+], a
    ld a, [wFtSayX]
    ld [hl+], a
    add 8
    ld [wFtSayX], a
    ld a, b
    ld [hl+], a
    ld a, FT_SAY_ATTR
    ld [hl+], a
    ret

SayKO:
    db 10, 11, 12, $FF
SayTKO:
    db 17, 10, 11, 12, $FF
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
    ld a, BANK(NesMac)      ; Mac's pose (first: his picture's tiles go up before his rival's)
    ld [$2000], a
    call FtNesMacShow
    ld a, [wFtBankNes]      ; his pose and place
    ld [$2000], a
    call FtNesShow
    ld a, [wFtBankData]
    ld [$2000], a
    call FtCueBuild         ; (his dodge cue's palettes, ready for VBlank)
    call FtNesCameras
    call FtNesPresent
    jp FtNesHud

; The crowd's cameras, as Punch-Out!!'s: flashing while either is down (and on through the count, his KO) and as he
; walks in. And the crowd's tells: his script's $46 1 (the moment to punch), the fight's spectator moves (its cue,
; $05BE: NES bank 7 $8A2A's tile; a camera for Bald Bull, the bearded man for Piston Honda; wFtCue: FtVBlank puts it).
FtNesCameras:
    ld a, [wNes + $46]
    dec a
    jr nz, .noCue
    ld a, [wFtCueTile]
    jr .cue
.noCue:
    ld a, [wFtCueOld]
.cue:
    ld [wFtCue], a
    ld a, [wNes + $05]      ; down
    and a
    jr nz, .flash
    ld a, [wNes + $90]      ; his walk-in (waiting for the bell)
    and $7F
    cp $40
    jr z, .flash
    cp $41
    ret nz
.flash:
    ld hl, wFtExcite        ; (frames they keep at it: two at least)
    ld a, [hl]
    cp 2
    ret nc
    ld [hl], 2
    ret

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
IF DEF(FT_WORDS)
    ld a, [wFtCount]        ; "Fight!" as the NES's: up with his call (its effect $0D) for 23 frames, then he stands
    and a                   ; (wFtCount: called; the timer: its frames left)
    jr nz, .called
    ld a, [wNes + $F0]
    cp $0D
    jr z, .call
    ld a, [wNes + $F4]
    cp $0D
    ld a, FT_INTRO          ; (not yet: walking in)
    jr nz, .intro
.call:
    ld a, 1
    ld [wFtCount], a
    ld a, 23
    ld [wFtCountTimer], a
.called:
    ld hl, wFtCountTimer
    ld a, [hl]
    and a
    ld a, FT_INTRO - 20     ; (said)
    jr z, .intro
    dec [hl]
    xor a
ELSE
    ld a, [wNes + $BB]      ; "FIGHT!" once the referee's status says go
    and a
    ld a, FT_INTRO
    jr z, .intro
    xor a
ENDC
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
    ld a, [wFtCount]        ; "KO!" or "TKO!" stays up once he's said it
    cp COUNT_TKO
    ret nc
    ld a, [wNes + $F4]      ; he says it with his voice: the KO and TKO effects ($0E, $0F), right after 10
    cp $0E
    ld b, COUNT_KO
    jr z, .ko
    cp $0F
    ld b, COUNT_TKO
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
    ld a, b
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
    ld a, [wFtCount]        ; what the referee calls it, if he hasn't yet: $FE, $FD KO; $FC, $FB TKO
    cp COUNT_TKO
    jr nc, .said
    ld a, [wNes + $00]
    cp $FD
    ld a, COUNT_KO
    jr nc, .call
    ld a, COUNT_TKO
.call:
    ld [wFtCount], a
.said:
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
    ld a, [wFtCornerScene]  ; (the corner, if there's one) to the corner; the next round starts when the fight scene comes back
    cp $FF
    jr z, :+
    ld a, 1
    ld [wFtResume], a
    ld a, FT_CORNER_RESULT
    jp FtFinish
:
    ld a, [wFtBankNes]
    ld [$2000], a
    ld a, [wFtRound]
    call NesRoundStart
    ld a, [wFtBankData]
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
    ; (his band keeps its scroll through the fade: FtStop, as the next scene loads)
IF DEF(FT_NES_SOUND)
    ld a, $80               ; the crowd stops; what's playing (the win or loss music) plays out over the
    ld [wNes + $F3], a      ; next scene (SfxUpdate -> NesSoundAfter)
    ld a, 2
    ldh [hNesSound], a
    xor a
ENDC
    call FtCareerResult
    call FtResultScene
    jp StartTransition

; His pose and place, from his script (the fighter bank is mapped).
FtNesShow:
    ld a, [wNes + nOppBaseAnimIndex]
    ld c, a
    ld a, [wNes + nOppFlip]     ; drawn mirrored: the second half of the maps
    and 1
    ld b, a
    ld a, [wNesAnim]
    bit 7, a
    jr z, .place
    call FtNesPic           ; Color with his pictures: the game's own picture (no tiles to wait for)
    jr nc, .poseOnly
    ld hl, NesPoseMap       ; (and the original's pose, for what goes by it: kept, never waited for)
    add hl, bc
    ld a, [hl]
    ld [wRvPose], a
    xor a
    ld [wNesAnim], a
    ld [wNes + nOppFlip], a
    jr .place
.poseOnly:
    ld hl, NesPoseMap
    add hl, bc
    ld a, [hl]
    ld e, a                 ; the pose; its tiles may have to come in first
    ld d, 0
    ld hl, RivalPoseSet
    add hl, de
    ld a, [hl]
    cp $FF
    jr z, .show             ; always in video memory
    ld hl, wFtSwapHave
    cp [hl]
    jr z, .show
    ld d, a                 ; not yet: he keeps the pose he has, unless its tiles are the ones about to be
    push de                 ; written over: then one always in video memory stands in (set first: FtVBlank
    ld a, [wRvPose]         ; draws a new pose before it copies any tiles)
    ld e, a
    ld d, 0
    ld hl, RivalPoseSet
    add hl, de
    pop de
    ld a, [hl]
    cp $FF
    jr z, .want
    ld e, d
    ld d, 0
    ld hl, FtSwapStandIn
    add hl, de
    ld a, [hl]
    ld [wRvPose], a
.want:
    ld a, d
    ld [wFtSwapWant], a
    jr .place
.show:
    ld a, e
    ld [wRvPose], a
    xor a
    ld [wNesAnim], a
    ld [wNes + nOppFlip], a ; (drawn: the NES's drawing takes "mirrored" for this frame only, $CC9D)
    ld hl, NesPlaceX        ; and where it sits
    add hl, bc
    ld a, [hl]
    ld [wRvPlaceX], a
    ld hl, NesPlaceY
    add hl, bc
    ld a, [hl]
    ld [wRvPlaceY], a
.place:
    call FtPicDecide        ; (Color, his pictures: the one going up, and its place)
    call FtDmgDecide        ; (the original's, in greys)
    ld a, [wNes + nOppBaseX]
    ld l, a
    ld h, 0
    ld de, NesOffsetX
    add hl, de
    ld a, [wRvPlaceX]
    add [hl]
    ld [wRvNesX], a
    ld a, [wNes + nOppBaseY]
    ld l, a
    ld h, 0
    ld de, NesOffsetY
    add hl, de
    ld a, [wRvPlaceY]
    add [hl]
    ld [wRvNesY], a
IF DEF(FT_TWINKLE_TILE)
    ld a, [wNes + $0344]    ; a star just earned: the NES's spot for it (beside his head), as ours
    dec a                   ; (1: no spot of its own -- the NES's sparkle is in his picture, over his head: his
    jr nz, .spot            ;  place, 3 pixels right of it)
    ld a, [wNes + nOppBaseX]
    add 3 - 1
.spot:
    inc a
    ld l, a
    ld h, 0
    ld de, NesOffsetX
    add hl, de
    ld a, [hl]
    add FT_TWINKLE_X0
    ld [wFtTwinkleX], a
    ld a, [wNes + $0345]
    ld l, a
    ld h, 0
    ld de, NesOffsetY
    add hl, de
    ld a, [hl]
    add FT_TWINKLE_Y0
    ld [wFtTwinkleY], a
ENDC
    ret

; Per set being swapped in: the pose in video memory throughout that shows meanwhile (getting up: dazed; going
; down: hit; a taunt or win: standing).
FtSwapStandIn:
    db RP_DAZED, RP_HIT_BODY, RP_IDLE

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
IF DEF(FT_MAC_PICS)
    call FtPlPicFrame       ; (Color: his own picture of the frame, exact: no flip)
ENDC
    ld a, [wNes + $61]      ; and where it sits
    ld l, a
    ld h, 0
    ld de, MacPlaceY
    add hl, de
    ld a, [hl]
    ld [wPlNesY], a
    ld a, [wNes + $61]      ; (his walks, $80-$97: as low as the NES's $70 says -- the frame alone doesn't: the
    sub $80                 ;  same ones walk him up after a getup and stand him low through a count)
    cp $18
    jr nc, .place
    ld a, [wNes + $70]
    sub 72
    cp 13
    ld b, FT_MAC_START_Y
    jr nc, .walkY
    ld l, a
    ld h, 0
    ld de, MacWalkY
    add hl, de
    ld b, [hl]
.walkY:
    ld a, [wPlNesY]
    and $80
    or b
    ld [wPlNesY], a
.place:
    ld a, [wNes + $048E]    ; worn out: the NES turns his skin purple ($14) till he has his breath back
    sub $14
    jr z, .tired
    ld a, 1
.tired:
    xor 1
    ld [wPlTired], a
    ld a, [wNes + nMacX]
    ld l, a
    ld h, 0
    ld de, MacOffsetX
    add hl, de
    ld a, [hl]
    ld [wPlX], a
IF DEF(FT_MAC_PICS)
    jp FtPlPicDecide
ELSE
    ret
ENDC

IF DEF(FT_MAC_PICS)
; ---- Color, the NES's Mac: each frame of his exact (MacPicFrames), two copies of his tiles in bank 1's sprite
; tiles, as his rival's: decided as the frame's sprites are built, up at the next VBlank's start ----

; His picture's entry (A): BC its tiles, D their bank, E how many, HL its sprites' address (their bank mapped).
FtPlPicEntry:
    ld l, a
    ld h, 0
    ld a, BANK(MacPicTable)
    ld [$2000], a
    ld b, h
    ld c, l
    add hl, hl
    add hl, bc
    add hl, hl              ; (6 bytes each)
    ld bc, MacPicTable
    add hl, bc
    ld a, [hl+]
    ld c, a
    ld a, [hl+]
    ld b, a
    ld a, [hl+]
    ld d, a
    ld a, [hl+]
    ld e, a
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    ret

; His NES frame just drawn (wNes + $61): his picture for it, unflipped (NesMac's bank mapped after).
FtPlPicFrame:
    xor a
    ld [wPlFlip], a
    ld a, [wNes + $61]
    ld l, a
    ld h, 0
    ld a, BANK(MacPicFrames)
    ld [$2000], a
    ld de, MacPicFrames
    add hl, de
    ld a, [hl]
    cp $FF
    jr z, .keep
    ld [wPlPic], a
.keep:
    ld a, BANK(NesMac)
    ld [$2000], a
    ret

; As the frame's sprites are built: a new picture of his goes up next VBlank (always room: 32 tiles at most).
FtPlPicDecide:
    ldh a, [hIsCGB]
    and a
    jr z, FtPlPicDecideDmg
    xor a
    ld [wPlPicSwitch], a
    ld [wPlPicGo], a
    ld a, [wPlPic]
    ld hl, wPlPicShown
    cp [hl]
    jr z, .keep
    ld [wPlPicHeads], a
    ld a, [wPlPicBuf]
    xor 1
    ld [wPlPicHeadsBuf], a
    call FtPlPicReady
    ld a, [wPlSwN]
    ld [wPlPicGo], a
    ld a, 1
    ld [wPlPicSwitch], a
    jr .out
.keep:
    ld [wPlPicHeads], a
    ld a, [wPlPicBuf]
    ld [wPlPicHeadsBuf], a
.out:
    ld a, BANK(NesMac)
    ld [$2000], a
    ret

; The original: a new picture of his starts streaming into his copy not shown (or it's whole there already: the
; last one up); one all in goes up next VBlank (sprites only: nothing to copy then).
FtPlPicDecideDmg:
    xor a
    ld [wPlPicSwitch], a
    ld [wPlPicGo], a
    ld a, [wPlPic]
    ld hl, wPlPicShown
    cp [hl]
    jr z, .keep
    ld hl, wPlPicLoad
    cp [hl]
    jr z, .loading
    ld [hl], a
    ld b, a
    ld a, [wPlPicHidden]
    cp b
    jr z, .whole
    xor a
    ld [wPlPicDone], a
    dec a
    ld [wPlPicHidden], a
    jr .keep
.whole:
    ld a, b
    call FtPlPicEntry
    ld a, e
    ld [wPlPicDone], a
.loading:
    ld a, [wPlPicLoad]
    call FtPlPicEntry
    ld a, [wPlPicDone]
    cp e
    jr c, .keep
    ld a, 1
    ld [wPlPicSwitch], a
    ld a, [wPlPicLoad]
    ld [wPlPicHeads], a
    ld a, [wPlPicBuf]
    xor 1
    ld [wPlPicHeadsBuf], a
    jr .out
.keep:
    ld a, [wPlPicShown]
    ld [wPlPicHeads], a
    ld a, [wPlPicBuf]
    ld [wPlPicHeadsBuf], a
.out:
    ld a, BANK(NesMac)
    ld [$2000], a
    ret

; His picture waits a frame (his rival's taking the VBlank's room): the one shown, built as shown.
FtPlPicWait:
    xor a
    ld [wPlPicSwitch], a
    ld [wPlPicGo], a
    ld a, [wPlPicShown]
    ld [wPlPicHeads], a
    ld a, [wPlPicBuf]
    ld [wPlPicHeadsBuf], a
    ret

; His picture going up (wPlPicHeads, into wPlPicHeadsBuf's copy): its DMA worked out now (VBlank only writes it).
FtPlPicReady:
    ld a, [wPlPicHeads]
    call FtPlPicEntry
    ld a, d
    ld [wPlSwBank], a
    ld a, e
    ld [wPlSwN], a
    ld a, b
    ld [wPlSwTiles], a
    ld a, c
    ld [wPlSwTiles + 1], a
    ld a, [wPlPicHeadsBuf]
    and a
    ld a, HIGH($8000)
    jr z, .to
    ld a, HIGH($8000 + FT_MAC_PIC_ROOM * 16)
.to:
    ld [wPlSwTiles + 2], a
    xor a
    ld [wPlSwTiles + 3], a
    ret

; VBlank's first: his readied picture's tiles into the copy not shown (32 DMA blocks at most).
FtPlPicSwitch:
    ld a, [wPlPicSwitch]
    and a
    ret z
    xor a
    ld [wPlPicSwitch], a
    ldh a, [hIsCGB]         ; (the original: his tiles streamed in already, just which copy)
    and a
    jr nz, .cgb
    ld a, [wPlPicShown]
    ld [wPlPicHidden], a
    jr .shown
.cgb:
    ld a, [wPlSwN]
    and a
    jr z, .shown            ; (a picture of nothing: no tiles)
    ld a, [wPlSwBank]
    ld [$2000], a
    ld a, 1
    ldh [rVBK], a
    ld hl, wPlSwTiles
    ld a, [hl+]
    ldh [rHDMA1], a
    ld a, [hl+]
    ldh [rHDMA2], a
    ld a, [hl+]
    ldh [rHDMA3], a
    ld a, [hl+]
    ldh [rHDMA4], a
    ld a, [wPlSwN]
    dec a
    ldh [rHDMA5], a
    xor a
    ldh [rVBK], a
.shown:
    ld a, [wPlPicHeads]
    ld [wPlPicShown], a
    ld a, [wPlPicHeadsBuf]
    ld [wPlPicBuf], a
    ld a, [wFtBankData]
    ld [$2000], a
    ret

; His first picture, as the fight sets up (loading: in a VBlank of its own).
FtPlPicsStart:
    ldh a, [hIsCGB]
    and a
    jr nz, .cgb
    ld a, BANK(MacPicIdle)  ; the original (the screen off): all of it into his first copy
    ld [$2000], a
    ld a, [MacPicIdle]
    ld [wPlPic], a
    ld [wPlPicShown], a
    ld [wPlPicLoad], a
    ld [wPlPicHeads], a
    xor a
    ld [wPlPicBuf], a
    ld [wPlPicHeadsBuf], a
    ld [wPlPicSwitch], a
    dec a
    ld [wPlPicHidden], a
    ld a, [wPlPic]
    call FtPlPicEntry
    ld a, e
    ld [wPlPicDone], a
    and a
    ret z
    ld a, d
    ld [$2000], a
    ld h, b
    ld l, c
    ld b, e                 ; B tiles
    ld de, $8000 + FT_OBJ_FIRST * 16
.tile:
    ld c, 16
.byte:
    ld a, [hl+]
    ld [de], a
    inc de
    dec c
    jr nz, .byte
    dec b
    jr nz, .tile
    ret
.cgb:
    ld a, BANK(MacPicIdle)
    ld [$2000], a
    ld a, [MacPicIdle]
    ld [wPlPic], a
    ld [wPlPicHeads], a
    xor a
    ld [wPlPicHeadsBuf], a
    ld a, $FF
    ld [wPlPicShown], a
    call FtPlPicReady
    FT_VWAIT FT_ROOM_ALL
    ld a, 1
    ld [wPlPicSwitch], a
    jp FtPlPicSwitch
ENDC

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
    ld a, [wNes + $0320]    ; (none set yet this fight -- its first frames, before the NES's round start: the
    ld hl, wNes + $0323     ; ones it starts with stay up, not its 00)
    or [hl]
    inc hl
    or [hl]
    jr z, .stars
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
