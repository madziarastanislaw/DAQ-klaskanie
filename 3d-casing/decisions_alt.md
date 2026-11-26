# Casing — Alternative internal layout

Script: `fusion/CaseAlt/CaseAlt.py` → STLs in `print/alt/`.

**Base:** copy of `fusion/Case/Case.py` v2 (2026-11-26), i.e. everything in `decisions.md` up to and including D14.
Conventions (wall names U/D/N/S/E/W, layers) and hardware are the same as in `decisions.md`.
This file records only where the alternative **differs** from the base; anything not listed here is unchanged.

The base design (`fusion/Case/`, `print/case_*.stl`) is kept as is.

---

## A1 — Copy of base

**Date:** 2026-11-26
**Status:** Done. Geometry identical to base v2; only the export folder differs (`print/alt/`).

---

## A2 — Wider and lower case, no breadboard platform, buzzer on the W wall

**Date:** 2026-11-26
**Status:** Implemented in `CaseAlt.py` — not yet run in Fusion

**Premise:** case wider (N–S) but lower (D–U).

| Item | Base v2 | Alternative |
|---|---|---|
| Outer size (X × Y × Z) | 170 × 120 × 80 | **170 × 140 × 50** |
| Split (bottom half height) | 20 | 20 (unchanged) → top half 30 |
| Interior floor → ceiling | 76 | 46 (U inner face at Z 48) |
| Breadboard platform (D14-C4) | two 20 × 40 × 30 boxes | **removed** |
| Buzzer mount (D12) | 15 mm from the N wall, opening in N | **15 mm from the W wall, opening in W** |

### Buzzer on the W wall
- Same mount as D12 (dimensions unchanged), rotated 90° seen from above: mount wall parallel to the W wall,
  its **W face 15 mm from the W inner wall** (X −66.6, wall X −66.6..−63.6), buzzer **facing W**.
  Screw W–E: head + washer on the mount wall's E face, nut on the PCB's W face. Rib from the mount wall to the W wall.
- Along N–S it is **centred on the case centre line** (screw hole Y 0; mount wall Y −18..18) — assumption.
- Rotation maps base E → N and base W → S: **buzzer 9 mm N of the screw** (W opening, teardrop Ø13, at Y 9),
  **pin header toward S**; its Dupont zone reaches Y ≈ −31.
- Clear of the battery shield: shield PCB spans Y −64.7..−35.4 (it moved 10 mm S with the S wall) → ~4.4 mm to the Dupont zone.

### Unchanged / follows automatically
- Battery shield keeps its position relative to the **W and S walls** (as in base), so it moved 10 mm S in case coordinates;
  S wall openings move with it.
- Top panel parts keep their positions relative to the case centre (mic (0, −40), buttons (−42, 5), OLED (42, 5)).
- Coupling, lip, wall thicknesses, S openings, OLED frame/supports: as base v2.

### To check
- **Top panel parts now hang into a 46 mm tall interior.** The mic (0, −40) sits **above the battery shield**:
  mic PCB at Z ≈ 42.5, cell top at Z ≈ 29 → ~13 mm for the mic header / Dupont plugs if they point down.
- **Breadboard + ESP32 have no defined place yet** (review 2026-11-26). Free floor zone:
  X ≈ −60..81.6 (E of the buzzer screw head → E inner wall) × Y ≈ −35..66.6 (N of the shield → N inner wall) ≈ 140 × 100 mm.
  A half-size breadboard (~83 × 55) fits; a full 830 (~165 × 55) does not.
  Height: on the floor its top is at ~Z 11.5, the DevKit at ~Z 25, wire loops ~Z 35. **Lowest points under U:**
  button legs ~Z 40.7, OLED back Z 44.8 (+ header pins/Dupont pointing down at its N edge, Y ≈ 20, reaching ~Z 25),
  rib Z 45. → keep the breadboard out from under the OLED header row, or use right-angle plugs there.
- USB-A plug zone (shield → E): X 33..~60, Y ≈ −57..−41 — clear of the free zone above.
- Reviewed 2026-11-26: no other dimension depends on the old height/width (all derived from LENGTH/WIDTH/HEIGHT);
  coupling (nut pocket + tip hole to Z 28.5 < U inner 48), lip, S openings (< Z 17.2), W buzzer opening (Z 5.5..19, Y 2.5..15.5),
  mount wall vs shield (Y gap 4.4 mm to the Dupont zone) and rib (X −16.4, clear of buttons/mic) all OK.

---

## A3 — U stiffening rib

**Date:** 2026-11-26
**Status:** Implemented in `CaseAlt.py` — not yet run in Fusion

- Reason: U spans ~136 mm N–S (base 116), so it flexes more when the buttons are pressed.
- **One N–S rib on the U inner face, 3 mm tall, 2 mm thick** (thickness = wall thickness; assumption), full width,
  ends merged into the N and S walls of the top half.
- Position: centred between the E edge of the button frames (X −23.6) and the W edge of the mic bosses (X −9.2) → **X ≈ −16.4**.
  ~6.2 mm clear on each side.
- Prints without supports (top half printed U-down, rib grows upward). Hangs to Z 45 — clear of everything below.
- D (floor) gets no reinforcement: it rests flat on the table.
