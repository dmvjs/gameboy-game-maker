# The Glass Joe Animation & Sprite Engine Algorithm

This document defines the complete state machine, frame data, memory flags, and sprite cycle logic for **Glass Joe** in *Mike Tyson's Punch-Out!!* (NES). Use this specification to train or prompt LLMs to perfectly simulate, analyze, or decompose Glass Joe's game logic.

---

## 1. Global Memory Flags & Addressing
The NES CPU tracks Glass Joe’s current tactical state via specific RAM memory addresses. To manipulate or understand his animation sequences, monitor these variables:

*   **`$003A` – Action State Identifier:** Defines the exact sprite animation loop currently active.
*   **`$003B` – Phase / AI Routine:** Track's Joe's behavior archetype (Phase 1 vs Phase 2 after a knockdown).
*   **`$008C` – Visual Cue Timer / Flash Counter:** Tracks frame countdowns for eye blinks and telegraph flashes.
*   **`$00A1` – Guard State Configuration:** Determines which vertical bounding boxes are active (`$00` = High/Face Open, `$01` = Low/Stomach Open, `$02` = Total Block).

---

## 2. Sprite Sheet Mapping & Allocation (CHR-ROM)
To save memory on the NES cartridge, Glass Joe utilizes dynamic sprite assembly. His body is constructed from a shared structural template (shared with Don Flamenco), while his head graphics occupy distinct CHR-ROM banks.

### Core Character Sprite Configurations

| Sprite ID | Common Name | Visual Composition Details |
| :--- | :--- | :--- |
| **`SP_IDLE_01`** | Neutral Guard Up | Hands high, chin protected, body shifted left. Pink midriff exposed. |
| **`SP_IDLE_02`** | Neutral Guard Down | Hands low, stomach protected. Chin/jaw pixels completely exposed. |
| **`SP_TE_JAB`** | Left Jab Telegraph | Right eye undergoes a palette-swap flash; left glove drops by 4 pixels. |
| **`SP_ATK_JAB`** | Left Jab Extension | Glove tile size scales up (`8x16` tiles combined to simulate depth toward screen). |
| **`SP_TE_TAUNT`** | Taunt Stance | Body shifted to top of the screen out of Mac's horizontal reach. Mouth tile open. |
| **`SP_ATK_HOOK`** | Right Hook Forward | Full body lunges down-left. Frame-perfect intercept pixels exposed. |
| **`SP_HIT_FACE`** | Jaw Hit Stun | Head tile shifted 8 pixels up-right. Mouth wide open, eyes rolled back. |
| **`SP_HIT_BODY`** | Stomach Hit Stun | Torso tile hunched down 6 pixels. Arms spread wide horizontally. |
| **`SP_DODGE_SEC`** | Anti-Spam Step | Full sprite bounding box shifted 16 pixels to the left. Whiff trigger. |

---

## 3. The Core Loop State Machine Algorithm
The core loop evaluates inputs and increments animation frames every **1/60th of a second (1 Frame)**.

```
       [ START: Match Initialization ]
                     │
                     ▼
             ┌───────────────┐
             │  STATE_IDLE   │◄────────────────────────┐
             └───────┬───────┘                         │
                     │                                 │
         ┌───────────┴───────────┐                     │
         ▼                       ▼                     │
 ┌───────────────┐       ┌───────────────┐             │
 │  Guard High   │       │   Guard Low   │             │
 │ (Stomach Open)│       │  (Face Open)  │             │
 └───────┬───────┘       └───────┬───────┘             │
         │                       │                     │
         └───────────┬───────────┘                     │
                     │ Timer Expired / Punch Trigger   │
                     ▼                                 │
         ┌───────────────────────┐                     │
         │   EVALUATE ATTACK     │                     │
         └───────┬───────────┬───┘                     │
                 │           │                         │
     Left Jab    │           │ Right Hook (Taunt)      │
     Selection   ▼           ▼ Selection               │
 ┌──────────────────┐    ┌──────────────────┐          │
 │  STATE_TELE_JAB  │    │ STATE_TELE_HOOK  │          │
 └───────┬──────────┘    └───────┬──────────┘          │
         │ Frame 7               │ Frame 160           │
         ▼                       ▼                     │
 ┌──────────────────┐    ┌──────────────────┐          │
 │  STATE_EXEC_JAB  │    │ STATE_EXEC_HOOK  │          │
 └───────┬──────────┘    └───────┬──────────┘          │
         │                       │                     │
         └───────────┬───────────┘                     │
                     │ Intercept Frame / Input Checked  │
                     ├─────────────────────────────────┤
                     ▼ Intercept Success               ▼ Intercept Whiff
             ┌───────────────┐                 ┌───────────────┐
             │  STATE_STUN   │                 │ RETURN_IDLE   │
             └───────┬───────┘                 └───────────────┘
                     │ Animation Complete
                     ▼
             [ Reset Loops ] ──────────────────────────┘
```

---

## 4. Animation Sequence Frame Data
The following timelines break down exactly how frames advance inside the state machine.

### A. The Left Jab Loop (`STATE_EXEC_JAB`)
*   **Total Duration:** 24 Frames
*   **Frame Breakdown:**
    *   `Frames 01-06` (`STATE_TELE_JAB`): Left glove lowers. Eye tile switches to a bright palette variant (Blink cue). **Vulnerability: None.**
    *   `Frames 07-10` (`STATE_EXEC_JAB`): Glove sprite extends forward. **Vulnerability: Intercepting with a Left Face Jab triggers a Star Punch.**
    *   `Frames 11-14` (Impact Window): Punch sprite fully overlaps Little Mac's default coordinates. Player must have completed a dodge or block.
    *   `Frames 15-24` (Recovery): Glove sprite scales down and returns to `SP_IDLE_01`.

### B. The Special Right Hook Loop ("Vive La France" Taunt)
*   **Total Duration:** ~184 Frames
*   **Frame Breakdown:**
    *   `Frames 001-040`: Retracted movement vector to top of ring (`SP_TE_TAUNT`).
    *   `Frames 041-160`: Rhythmic loop. Shakes head and pumps arms up and down twice (30 frames per pump cycle).
    *   `Frames 161-164` (The Lunge Phase A): Begins forward charge. **Vulnerability: Direct counter inputs instantly force an Instant Knockout (One-Hit KO).**
    *   `Frames 165-176` (The Lunge Phase B): Nearing the bottom of the ring. **Vulnerability: Direct counter inputs force an Instant Knockdown (One-Hit KD).**
    *   `Frames 177-180` (Impact Window): Hook lands on Mac if not dodged to the left or right.
    *   `Frames 181-184`: Recovery frames resetting to neutral layout.

### C. The Anti-Spam Star Punch Step (`STATE_ANTI_SPAM`)
*   **Trigger Condition:** Evaluated on Frame 1 of Little Mac initiating a Star Punch *if and only if* Glass Joe has taken 4 consecutive Star Punches prior without an intervening reset.
*   **Execution Loop:**
    *   `Frames 01-12`: Sprite swaps cleanly to `SP_DODGE_SEC`. Bounding box shifts horizontal coordinates out of the alignment zone. Little Mac's animation goes to a "Whiff Stun".
    *   `Frames 13-18`: Joe returns to center stage and taunts, leaving his jaw open.

---

## 5. Hit Stun Overrides & Animation Traps

### The Alternating Stomach Stutter Loop
When Glass Joe is hit in an open stomach guard, his normal execution loop instantly terminates via **Animation Cancellation**.

1.  **Interrupt Trigger:** Punch lands during `SP_IDLE_01` with an open stomach flag.
2.  **Stun Injection:** System forces `$003A` to `STATE_STUN_BODY` (`SP_HIT_BODY`), executing a fixed **18-frame recovery lag**.
3.  **The Stutter Exploit Algorithm:**
    *   If Mac delivers an alternating punch (Left then Right) on exactly **Frame 16, 17, or 18** of the stun cycle, Joe's state machine resets to Frame 1 of `STATE_STUN_BODY`.
    *   If the user uses the *same* hand twice, the animation frame jumps immediately to a block state (`SP_IDLE_02` with total block flags raised), breaking the chain.
