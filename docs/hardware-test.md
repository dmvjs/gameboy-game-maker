# Joe vs Mac on real hardware

Every fight already runs clean in SameBoy (no video writes outside the time the hardware allows, Color and the
original), but nothing beats a real console. With a flash cart that takes 4 MB MBC5 ROMs with save RAM (EverDrive
GB X5/X7, a GB Operator flash cart, or similar):

1. Build the ROM: `npm start` writes `joe-vs-mac.gb` (or `python3 tools/fight_videos.py rom joe-vs-mac.gb`).
2. Copy it to the cart. Test on as many of these as you have: Game Boy (DMG), Pocket, Color, Advance / SP.

## Checklist

On each console, note anything that looks or sounds different from the emulator.

- [ ] Power-on: the bells, MIKE IS WAITING, the title. No flash of garbage between screens.
- [ ] NEW → Glass Joe's challenger screen slides up; Mac's record reads 0-0 0KO.
- [ ] A whole fight: Joe's pictures change smoothly; no flicker or torn tiles in him, Mac or the referee.
- [ ] Camera flashes in the crowd while he's down; on Color, the crowd pulses after his KO.
- [ ] Get-ups: his head over the crowd, no crowd showing through him.
- [ ] Between rounds (the corner) and back: the fight carries on where it was.
- [ ] The corner: Doc's mouth and hand move as on the NES; press Select once and he rubs faster (once per fight).
- [ ] The crowd on the challenger screen and in the corner: the NES's recorded roar (not a hiss); no clicks or buzz.
- [ ] Challenger and corner close-ups at the NES's full size; on the original Game Boy, no light blocks in them.
- [ ] Lose a fight on purpose: DON'T CRY, MAC!, then REMATCH with 0-1 0KO.
- [ ] Lose three times: the game over screen (Mac on his stool), then the title.
- [ ] Beat Piston Honda: the training run's pass key; write it down.
- [ ] Power off, on, CONTINUE, type that key: Don Flamenco's challenger with your record.
- [ ] 007 373 5963 on CONTINUE: straight to Mike Tyson.
- [ ] 135 792 4680 on CONTINUE, Select held as you enter the last digit: ANOTHER WORLD CIRCUIT, King Hippo.
- [ ] Beat Mike Tyson in the Another World Circuit: his word to Mac ends with TIME (the knockout's, to hundredths) and the round.
- [ ] 075 541 6113 on CONTINUE: the busy signal (ten beeps), then back to the title.
- [ ] Sound: music and effects as on the NES; no clicks or dropouts in a fight.
- [ ] Original Game Boy only: the grey pictures (his frames may run a frame or two behind Color's).
- [ ] Leave a fight running 10 minutes (stand still and let him win): no crash, no slowdown.

If anything's off, a phone video of it is the most useful thing to send back.
