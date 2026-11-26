# Casing — Design Decisions

3D-printed enclosure for the device, split into two parts (top and bottom).
Material: PLA / Hyper PLA.

Components (models in `outside_components/`): Wemos Battery Shield V3 (18650), OLED 128×64,
Adafruit I2S mic SPH0645, 12 mm push buttons, FC-07 active buzzer.
ESP32 DevKit sits on a breadboard; all other parts are wired to the breadboard (dimensions TBD).

## Hardware reference

| Item | Spec |
|---|---|
| M3 screw | 10 mm long; case coupling uses socket head (imbus), head Ø5.5 × 3 mm |
| M3 washer | Ø7 mm OD, ~0.5 mm thick |
| M3 nut | measured 5–5.5 mm across flats (standard M3 = 5.5 AF), 2.4 mm thick |
| M2.5 screw | ~9 mm long (mic only) |
| M2.5 heat-set insert | 3 mm tall, **Ø3.5 mm** OD (mic only) |

**Design priority:** simplest, most effective solution. Aesthetics are not a concern.

## Conventions

**Wall names** (Fusion axes):

| Name | Wall | Axis |
|---|---|---|
| **U** | up — top panel | +Z |
| **D** | down — floor | −Z |
| **N** | north | +Y |
| **S** | south | −Y |
| **E** | east | +X |
| **W** | west | −X |

**Internal layers** (from D up to U):
1. **Bottom layer** — components bolted to the bottom half (floor D and the lower parts of N/S/E/W).
2. **Middle layer** — breadboard only (with ESP32 DevKit), raised off the floor so parts can sit under it and the case stays smaller.
3. **Top layer** — components bolted to the top half / top panel U.

---

## D9 — Overall case size

**Date:** 2026-11-21
**Status:** Accepted — length to change, see D14 (C3)

- **Outer: 150 (E–W, X) × 120 (N–S, Y) × 80 (D–U, Z) mm.** (E–W grown from 140 → 150 on 2026-11-21 to give the USB-A plug room, see D10.)
- Interior (walls per D0):
  - top half: 146 × 116 mm
  - bottom half: 143.2 × 113.2 mm (3.4 mm side walls)
  - height floor → ceiling: 76 mm
- **Bottom half height (split): 20 mm** → coupling counterbore 13.5 mm deep. Top half: 60 mm.

---

## D10 — Battery shield (Wemos 18650 Battery Shield V3)

**Date:** 2026-11-21
**Status:** Accepted (proposal — verify in Fusion) — verified on print v1 (placement, screws); S openings to change, see D14 (C1, C3)

Script: `fusion/Case/Case.py`. Geometry from `outside_components/Wemos Battery Shield V3.step`:
PCB 99.3 × 29.3 × 1.6, 4× Ø3.0 holes at 25.3 × 95.3 mm spacing; micro USB on the **underside**,
switch overhangs the board edge by 1.6 mm, underside parts reach 3.0 mm, USB-A overhangs the end by 5.75 mm.

### Placement
- Bolted to **D**, long axis E–W. **Micro USB + switch face S**, **USB-A faces E**.
- Pushed **W** until the PCB is 1 mm from the SW coupling boss (PCB W edge X = −62.0). Holes at
  X = −60.0 / 35.3, Y = −52.7 / −27.4.
- Switch face 0.3 mm from the S inner wall.
- PCB underside **6.2 mm above the floor** (Z = 8.2); cell top at Z ≈ 29 (reaches into the top half).

### Mounting (variant of D3 for the floor)
- Screw **from above** through the PCB (washer + head on the PCB) into a **captive M3 nut** in a hex pocket
  (5.7 AF, 3 mm deep) opened from the outer D face. Keeps D flat — no protruding heads, so the case doesn't rock.
- Standoff: Ø10 × 1.5 mm base (holds the pocket) + Ø6.5 post to the PCB (clears the micro USB by ~0.9 mm).
- Budget: 10 mm screw − 0.5 washer − 1.6 PCB = 7.9 mm below PCB → tip ends 0.3 mm inside the D face, full nut engagement.
- Ø3.0 PCB holes are tight for M3 — drill to 3.2 if needed.

### S wall openings
- **Micro USB:** 12 × 8 mm (X × Z), centre X −51.95, Z 7.3. Sized for the plug overmold (receptacle sits ~4.7 mm behind the outer face).
- **Switch:** 11 × 4.5 mm slot, centre X 23.9, Z 11.55. Actuator ~3.7 mm behind the outer face → operate with a pen tip / fingernail.

### USB-A
- **~28.5 mm** from the USB-A receptacle face (X = 43.05) to the E inner wall (X = 71.6), after growing the case to 150 mm.
- Enough for a compact straight plug with the cable bending right after it; a long-bodied plug may still be tight — check with the real cable.

---

## D11 — Breadboard platform (middle layer)

**Date:** 2026-11-21
**Status:** Accepted — to be replaced by two boxes, see D14 (C4)

- **Open rectangular frame of 2 mm walls, 80 (X) × 40 (Y) outer, 30 mm tall**, on the floor D, **centred** in the case (X −40..40, Y −20..20).
- Breadboard is **glued** on the top rim at **Z = 32** (floor top 2 + 30).
- Clearances: S face of the frame (Y −20) is ~3.9 mm from the nearest battery-shield washer (Y −23.9).
  Cell top is at Z ≈ 29.2, so a breadboard wider than 40 mm overhanging S still clears the cell by ~2.8 mm.
- The frame rises 12 mm above the split (Z 20) — part of the bottom half; nothing in the top half collides.

---

## D12 — Buzzer mount (supersedes D7 placement)

**Date:** 2026-11-21
**Status:** Accepted — dimensions confirmed by user; verified on print v1 (D14)

- **Vertical mount wall** printed from the floor D: 3 mm thick (Y), PCB length + 2 mm each side, up to 2 mm above the PCB.
  Its **N face is 15 mm from the N inner wall** (Y = 41.6). Centred at X = 0.
- Buzzer PCB bolted to the mount wall's **N face**, buzzer **facing N**. One M3×10 **N–S**:
  head + washer on the mount wall's S face, nut on the PCB's N face (0.5 + 3 + 1.6 + 2.4 = 7.5 mm → 2.5 mm spare).
- **Anti-rotation:** a rib on the floor under the PCB's bottom edge (PCB rests on it). The rib runs the **full
  15 mm from the mount wall to the N wall**, so the PCB stays supported wherever it sits along Y.
- **N wall opening Ø13** (buzzer Ø11–12 + clearance), aligned with the buzzer centre — the buzzer can poke
  **through** the wall. **Teardrop shape** (45° point on top) so it prints without a sagging bridge; the point is
  flattened at Z = 19 (1 mm below the split, ~4.4 mm flat — trivial bridge), keeping the wall's top edge and the lip intact.
  Opening spans Z 5.5..19.
- **Adjustable Y position:** space the PCB off the mount wall with extra nuts / a spacer on the screw.
  Default (PCB on the mount wall): buzzer front 3.4 mm behind the N inner wall. Flush with the outer face:
  ~6.8 mm of spacing; any spacing needs a longer screw (e.g. M3×20 instead of ×10).

**Module (confirmed):** PCB 32 × 13 × 1.6 mm, hole at PCB centre, buzzer Ø11–12 sticking out **10 mm**,
between the hole and the **E** edge (centre ~9 mm E of the hole). PCB back faces S. **Pin header points W** —
Dupont plugs extend ~15 mm W of the PCB edge (X ≈ −16 → −31); keep that zone free.

**Nut vs buzzer:** buzzer edge is ~3–4 mm from the hole centre. Turn the nut so a **flat faces the buzzer**
(flat = 2.75 mm from centre) — the buzzer then also stops the nut spinning while you tighten the screw from S.
Fallback if it still hits: head on the PCB's N face (no washer), nut on the mount wall's S face.

---

## D13 — Top panel U layout

**Date:** 2026-11-21
**Status:** Accepted (positions are first proposal — adjust `MIC_*`, `BTN_*`, `OLED_*` in `Case.py`)

Viewed from above (N up, W left):

```
 N  ┌──────────────────────────────────────────┐
    │                                          │
    │   [B] [B]                ┌──────────┐    │
 W  │                          │   OLED   │    │  E
    │   [B] [B]                └──────────┘    │
    │                                          │
    │                 (mic)                    │
 S  └──────────────────────────────────────────┘
```

| Part | Centre (X, Y) | Mounting |
|---|---|---|
| Microphone | (0, −40) | 2× M2.5 into inserts (D8), header toward N |
| Buttons | 2×2 grid, centre (−42, 5), pitch 22 mm | glued (D5) |
| OLED | (42, 5), header toward N | 4× M3 (D6) |

All hang ≤ ~15 mm below U (Z ≥ ~63) — clear of the breadboard layer.

---

## D14 — Print v1 review (PLA) and changes for v2

**Date:** 2026-11-25
**Status:** Implemented in `Case.py` (2026-11-26) — not yet run in Fusion / printed; `print/*.stl` are still v1

Reviewed: first PLA print of both halves (`print/case_bottom.stl`, `print/case_top.stl`, exported 2026-11-21).

### Verified on the print — DO NOT CHANGE

| # | Item | Related |
|---|---|---|
| OK1 | Overall design | D9 |
| OK2 | Screw clearances: battery shield and top/bottom coupling | D2, D10 |
| OK3 | Buttons: placement, spacing, clearances | D5, D13 |
| OK4 | Microphone: spacing, fits | D8, D13 |
| OK5 | Buzzer mount: buzzer fits comfortably through the N opening | D12 |

### To change in v2

| # | Change | Related | State |
|---|---|---|---|
| C1 | **S wall openings are too small.** Charge hole (W): +2 mm in each direction, but stopping at the floor top (12 × 8 → **16 × 11.3 mm**). Switch hole (E): +5 mm on each side, same height as the charge hole (11 × 4.5 → **21 × 11.3 mm**). Both centres move **1 mm E**. No recess. | D10 | Ready |
| C2 | **Lip only present on W; must be on all sides (N/S/E/W) of the bottom half** (the reason its walls are 3.4 mm). | D2 | Ready |
| C3 | **Case +20 mm in W–E (150 → 170 mm)**, added on the **E side**: not enough space for the internal cable from the battery shield to the board. Battery shield, its mounts and S holes keep their position relative to the W wall; everything else is re-centred. | D9, D10 | Ready |
| C4 | **Replace the breadboard frame with two boxes**, 20 (E–W) × 40 (N–S) × 30 mm each, centred, **50 mm gap** E–W (the single box was too obstructive). | D11 | Ready |
| C5 | **OLED: cutout too big; screen must sit deeper.** Cutout from the measured glass (34 × 23), 2 mm supports in the 4 corners. Screw hole size and position relative to the nearest cutout corner stay as in v1. | D6, D13 | Ready |

### Notes for implementation

- **C2 cause (confirmed in the v1 STL: lip top face only at X −72.8..−71.6):** cutting the boss clearance splits the lip into
  4 separate bodies; `Case.py` then joins only the one the `lip` variable still points to (W). Fix: join all lip pieces.
  The other three were left as loose bodies and not exported.
- **C1 (from user, 2026-11-25)** — in v2 coordinates (case centre, 170 mm long), X × Z:

  | Hole | Size | Centre X | X span | Centre Z | Z span |
  |---|---|---|---|---|---|
  | Charge (micro USB) | 16 × 11.3 | −60.95 | −68.95..−52.95 | 7.65 (was 7.3) | 2.0..13.3 |
  | Switch | 21 × 11.3 | 14.9 | 4.4..25.4 | 11.55 (unchanged) | 5.9..17.2 |

  - The 1 mm E shift is on top of the C3 coordinates (−61.95 → −60.95, 13.9 → 14.9).
  - Both stay below the split (Z 20), so the S lip is unaffected. Openings print as 16 / 21 mm bridges.
  - Charge hole must not cut into the floor: its bottom edge stops at the floor top (Z 2), so it grows 1.3 mm down instead of 2;
    top and sides keep the full +2 mm.
  - **Cut the wall thickness only.** v1 cut 1 mm past the inner face; with the larger holes that would nick both S standoff posts
    and leave ~0.05 mm between the charge hole and the SW nut pocket. Limit the inward overshoot to 0.1 mm → ~1 mm of wall remains.
  - Assumption: "same height" = same vertical size (11.3 mm, follows the trimmed charge hole), switch hole still centred on the switch.
- **C3 (confirmed by user):** everything is re-centred in the 170 mm case **except the battery shield, its mounts and its
  S wall holes**, which keep their distance from the W wall. So buzzer (mount + N opening), mic, buttons, OLED and the
  breadboard boxes keep their v1 offsets from the case centre (C4 replaces D11's frame) and end up 10 mm further from the W wall.
  In `Case.py` this is `LENGTH = 170`: the shield is positioned from the SW coupling boss, the rest from the centre.
  The shield's centre-based X values in D10 then all shift by −10 mm (PCB W edge −62.0 → −72.0, holes −60.0 / 35.3 → −70.0 / 25.3,
  micro USB −51.95 → −61.95, switch 23.9 → 13.9). USB-A to E inner wall: ~28.5 → **~48.5 mm**.
- **C4 (confirmed by user):** each box 20 mm E–W (X) × 40 mm N–S (Y) outer, 30 mm tall, 50 mm free gap between them along E–W:
  X −45..−25 and 25..45, Y −20..20 (pair spans 90 × 40). Walls (2 mm, open) and top rim (Z 32) as in D11.
  Clearance to the shield's washers stays 3.9 mm (S face still at Y −20).
- **C5 (from user, 2026-11-26)** — measured on the physical module (1.3" class):
  - **PCB 34.5 (E–W) × 32 (N–S) mm**, **glass 34 × 23 mm**, assumed centred on the PCB.
  - **Cutout = glass + 0.2 mm per side = 34.4 × 23.4 mm** (v1: 42.4 × 27.6), centre unchanged (42, 5).
  - **Screw holes:** Ø3.4, each 2.5 mm inward (E–W) and 2.575 mm outward (N–S) from its cutout corner, as in v1
    → ±14.7 × ±14.275 from the OLED centre (spacing 29.4 × 28.55); hole edge ~0.03 mm inside the PCB edge.
  - **Supports:** 4 rectangles on the U inner face, **2 mm tall**, along the N and S cutout edges, long side E–W.
    Each runs from **8 mm inside the nearest E/W cutout side** outward to 0.5 mm past the PCB edge; across (N–S) from the cutout edge to 0.5 mm
    past the PCB edge: **~8.55 × 4.8 mm**. Middle 18.4 mm left free for the header pins (N) and the screen tape (S).
    The screw hole passes through the support (allowed: "need not support the hole"), so the PCB doesn't bend when the nut is tightened.
  - **Locating frame** (added 2026-11-26, like the buttons' frames, D5): rectangular, around the PCB, **3 mm tall** from the U inner face,
    0.2 mm clearance, 1.2 mm wall → inner 34.9 × 32.4, outer 37.3 × 34.8 mm. The supports run 0.3 mm into its wall (joined).
    PCB back is 3.2 mm below the U inner face, so the frame stops 0.2 mm short of it and stays clear of the nuts
    (they overhang the PCB edge by ~1.4 mm).
  - Screen front ≈ level with the U inner face (~2 mm below the outer face; glass height 1.9 from the v1 model, not measured).
  - Screw budget: 0.5 washer + 2 U + 2 support + 1.2 PCB + 2.4 nut = 8.1 mm of 10.
  - The v1 OLED STEP model (42 mm glass) no longer matches → `Case.py` shows a box stand-in instead.

---

## D0 — Wall thickness

**Date:** 2026-11-21
**Status:** Accepted

- **2.0 mm everywhere** (walls, floor, top) — 5 perimeters at 0.4 mm line width.
- **Exception: bottom-half side walls 3.4 mm** (2.0 + 0.2 lip clearance + 1.2 lip) so the lip is a straight vertical extension of the wall (see D2).

---

## D1 — Coupling method: M3 heat-set threaded inserts

**Date:** 2026-11-20
**Status:** Superseded by D2 (2026-11-21) — hardware set changed to screws + nuts; inserts reserved for the mic only (D8).

---

## D2 — Top/bottom coupling: 4× M3×10 socket screws into captive nuts

**Date:** 2026-11-21
**Status:** Accepted (proposal — verify with test print) — screw clearances verified on print v1; lip missing on N/E/S, see D14 (C2)

### Design
Four corner bosses, merged into the walls. Screw enters from the **bottom**, nut is captive in the **top** half.

```
        TOP HALF
   ┌──────────────┐
   │   Ø3.4 tip   │  ← 1.5 mm extra depth for screw tip
   │  ┌────────┐  │
   │  │hex nut │  │  ← hex pocket 5.7 AF, open at mating face, nut pressed in
───┴──┴────────┴──┴───  mating face (lip/groove from D1 kept, interrupted at bosses)
   │    │Ø3.4 │    │
   │    │     │    │  ← A = 6.5 mm clearance hole
   │  ┌─┘     └─┐  │
   │  │ washer+ │  │  ← counterbore Ø7.6, depth C
   │  │  head   │  │
   └──┴─────────┴──┘
        BOTTOM HALF (outer bottom face)
```

### Parameters
- **Bottom boss:** through hole Ø3.4, counterbore **Ø7.6** (7 mm washer + clearance), boss Ø ≥ 10.5 mm.
- **Length A** (counterbore floor → mating face): **6.5 mm**. Budget: washer 0.5 + A 6.5 + nut 2.4 = 9.4 → ~0.6 mm of screw past the nut.
- **Counterbore depth C = H_bottom − 6.5 mm**, where H_bottom = bottom-half height at the boss. Minimum H_bottom ≈ 10.3 mm (head 3 + washer 0.5 + 0.3 recess + 6.5). Taller bottom → deeper counterbore (an Allen key fits a Ø7.6 hole).
- **Top boss:** hex pocket **5.7 mm across flats** (for the 5–5.5 AF nut; if loose, 5.6 or glue), 2.5 mm deep, open at the mating face; then **Ø3.4 × 6 mm** for leftover screw length (fits screws up to ~15 mm). Boss Ø11 mm.
- **Bosses are full-height corner columns** (floor → ceiling), merged into the rounded corners. Kept deliberately: print without supports (a short top boss would start mid-air when the top is printed ceiling-down), stiffen the corners, and use corner space that can't hold components anyway. Cost ≈ a few grams.
- **Lip:** bottom-half side walls are **3.4 mm**; the inner 1.2 mm continues **2.5 mm** above the mating face as the lip, 0.2 mm clearance to the top half's 2 mm wall. Lip is cut away around the top bosses (0.3 mm clearance).
- Nut retention: press fit (pull in with a screw from the other side); a drop of CA glue if loose. Hex stops it spinning.

### Rationale
- Uses the same M3×10 + washer + nut hardware as the rest of the build.
- Captive nut means only an Allen key is needed to open; screw heads recessed in the bottom.
- Brass/steel threads → unlimited open/close cycles.

---

## D3 — General component mounting: through-hole + M3×10 + washer + nut

**Date:** 2026-11-21
**Status:** Accepted

- Through hole **Ø3.4** in the case wall; screw from outside with Ø7 washer under the head, nut on the inside over the component PCB.
- **Screw length budget (10 mm):** washer 0.5 + wall 2.0 + standoff S + PCB 1.6 + nut 2.4 + ~0.5 margin → **standoff S ≤ 3.0 mm**.
- Standoffs: printed rings/bosses, Ø6–7 mm OD, Ø3.4 hole.
- Heads + washers sit on the outside surface, no recess (~3.5 mm proud) — accepted, aesthetics not a concern.

## D4 — Edge rounding

**Date:** 2026-11-21
**Status:** Accepted

- **5 mm radius on the 4 vertical outer edges only.** No fillets on horizontal edges. (Corrected 2026-11-21; earlier "0.5 mm" was a mistake.)
- Inner cavity corners follow: 5 − 2 mm wall = 3 mm radius.

## D5 — Push buttons

**Date:** 2026-11-21
**Status:** Accepted — verified on print v1 (D14)

- Glued to the inside of the case. Hole **Ø8.0 mm** for the actuator (was 7.0, changed 2026-11-21; model: Ø6.7 actuator, protrudes ~3.3 mm above 12×12×3.8 body).
- Body top glued flat against U → actuator sticks ~1.3 mm out of the panel.
- **Locating frame** on the U inner face for each button: 12.4 mm square opening (0.2 clearance), 1.2 mm walls,
  2 mm tall — stops above the side legs (which start ~1 mm further down).

## D6 — OLED display

**Date:** 2026-11-21
**Status:** Accepted — wrong on print v1, to change, see D14 (C5)

- 4× M3, mounted per D3 (head + washer outside, nut on the PCB back). Holes at **±18.7 × ±16.375 mm** from the PCB centre (from model).
- **No standoffs:** PCB lies flat on the U inner face; the glass (42.0 × 27.2, 1.9 mm above the PCB) sits **inside the window**,
  ~0.1 mm below the outer surface. Window = glass + 0.2 mm per side.
  (Standoffs were dropped: at Ø7 they would overlap the glass edge, which is only 2.8 mm from the hole centres.)
- Budget: 0.5 + 2 + 1.2 PCB + 2.4 nut = 6.1 mm → 3.9 mm spare.
- ~0.9 mm of panel between the window edge and each screw hole; washers partly overlap the glass border (inactive area).
- Header on the N edge, pins reach 8 mm into the case.

## D7 — Active buzzer (FC-07)

**Date:** 2026-11-21
**Status:** Accepted

- 1× M3 through the centre hole, per D3.
- Single screw lets it rotate → add an **anti-rotation feature** (pocket or 2 ribs along the PCB edges).
- Mount PCB back to the wall (buzzer inward) — buzzer facing the wall would need a standoff > 7.6 mm, beyond the D3 budget. Add a small grille of holes near it.

## D8 — Microphone (Adafruit SPH0645)

**Date:** 2026-11-21
**Status:** Accepted — verified on print v1 (D14)

- 2× M2.5 into **M2.5 heat-set inserts** (3 mm tall, Ø3.5 mm) in bosses on the inner wall. Only part using inserts.
- **Boss:** Ø7 mm OD, **4 mm tall** above the inner wall surface.
- **Insert hole:** **Ø3.2 mm**, 3 mm deep at the top of the boss (insert set flush).
- **Below the insert:** Ø2.8 mm clearance hole continuing **through the boss and the wall** (open to the outside).
  - Works with the current ~9 mm screws: 9 − 1.5 PCB = 7.5 mm below the board, boss 4 + wall 2 = 6 mm → tip protrudes ~1.5 mm outside (acceptable, aesthetics not a concern).
  - Also works with M2.5×5–6 screws if swapped later (no protrusion).
- Mic PCB sits 4 mm off the wall — clears the **2 mm header pins** on the mounted side.
- Mounted on **U**, PCB **underside toward U** (confirmed from model: bottom-port MEMS, Ø1.03 port through the PCB at the package).
- Mounting holes Ø2.5, 11.43 mm apart, along the S edge; header row along the N edge.
- **Sound hole: 45° cone** in U aligned with the port — **Ø2.5 at the inner face → Ø6.5 at the outer face**
  (enlarged 2026-11-21; was a plain Ø2 hole).
- **Acoustic tube** (Ø4.5 OD / Ø2.5 ID, 3.9 mm tall) from U to the PCB, so sound reaches the port instead of the
  4 mm air gap. Clears the insert bosses by ~0.4 mm.
