# Fusion script: ALTERNATIVE internal layout (see 3d-casing/decisions_alt.md)
# Started as a copy of fusion/Case/Case.py v2 (2026-11-26); the base design stays in decisions.md.
#
# Conventions: U=+Z (top panel), D=-Z (floor), N=+Y, S=-Y, E=+X, W=-X.
#
# Base v2 = print v1 review applied (D14: C1..C5). Alternative changes: A2 (decisions_alt.md).
# - 170 x 140 x 50 mm, 2 mm walls, 5 mm radius on the vertical edges (A2; base 170 x 120 x 80)
# - bottom half 20 mm tall with 3.4 mm side walls + lip on all 4 sides; top half 2 mm walls (D2, D14-C2)
# - 4 corner coupling bosses: M3x10 from D into captive nuts in the top half (D2)
# - Wemos 18650 Battery Shield V3 bolted to D (D10):
#     ports (micro USB, switch) on S, USB-A to E, pushed W up to the SW boss (stays put vs the W wall),
#     standoffs with captive nuts in the floor, screws from above
# - no breadboard platform (A2)
# - buzzer: vertical mount wall on D, 15 mm from the W wall, W-E screw, sound hole in W (D12 rotated, A2)
# - top panel U: mic (S-centre, M2.5 inserts), 4 buttons (W, glued), OLED (E, M3, corner supports) (D13, D14-C5)
# - U stiffening rib N-S between buttons and mic, 2 x 3 mm (A3)
# - optional: imports the component STEP models to check the fit
#
# Run in Fusion: Utilities > Add-Ins > Scripts and Add-Ins > "+" > Script from my computer
#                > pick this folder > Run.
import math, os
import adsk.core, adsk.fusion, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
COMPONENTS_DIR = os.path.normpath(os.path.join(HERE, '..', '..', 'outside_components'))

# ---- Case (mm) ----
LENGTH = 170.0      # X  (W -> E)   v1: 150 (D14-C3)
WIDTH = 140.0       # Y  (S -> N)   base: 120 (A2)
HEIGHT = 50.0       # Z  (D -> U)   base: 80 (A2)
RADIUS = 5.0        # vertical edge rounding (outer)
WALL = 2.0          # walls, floor and top
SPLIT = 20.0        # height of the bottom half

# ---- Coupling (D2) ----
BOSS_D = 11.0
BOSS_INSET = 6.5
HOLE_D = 3.4
CBORE_D = 7.6
CLAMP_LEN = 6.5
NUT_AF = 5.7
NUT_POCKET = 2.5
TIP_CLEAR = 6.0

# ---- Lip ----
LIP_H = 2.5
LIP_T = 1.2
LIP_CLR = 0.2
LIP_BOSS_CLR = 0.3
BOTTOM_WALL = WALL + LIP_CLR + LIP_T   # 3.4

# ---- Battery shield (D10) ----
SHIELD_STEP = os.path.join(COMPONENTS_DIR, 'Wemos Battery Shield V3.step')
SH_STANDOFF = 6.2       # floor top -> PCB underside (underside parts reach 3.0 mm)
SH_BASE_D = 10.0        # wide base around the nut pocket
SH_BASE_H = 1.5         # base height above the floor
SH_POST_D = 6.5         # post diameter (clears the micro USB by ~0.9 mm)
SH_NUT_POCKET = 3.0     # hex pocket depth from the outer D face
SH_SWITCH_CLR = 0.3     # switch face -> S inner wall
SH_BOSS_CLR = 1.0       # PCB W edge -> SW coupling boss
USB_CUT = (16.0, 12.0)  # micro USB opening (X x Z), centred on the port; bottom clipped at the floor top (D14-C1)
SW_CUT_W = 21.0         # switch slot width (X); its height = the clipped micro USB height (D14-C1)
PORT_SHIFT_X = 1.0      # both S openings moved this much E of the port / switch (D14-C1)
PORT_CUT_IN = 0.1       # S openings: cut only this far past the inner wall face (spares standoffs / nut pocket)

# Shield model geometry (its own STEP frame, mm):
#   PCB x 0.7..30.0 (width), z 0..99.3 (length), y 0..1.6 (thickness, cell on +y)
M_HOLES = [(2.7, 2.0), (28.0, 2.0), (2.7, 97.3), (28.0, 97.3)]   # (x, z), Ø3.0
M_PCB_ZMAX = 99.3
M_SWITCH_X = 31.6                         # switch face (S side)
M_SWITCH_Y, M_SWITCH_Z = (1.6, 5.1), (8.91, 17.91)
M_USB_Y, M_USB_Z = (-2.6, 0.8), (85.36, 93.14)

# ---- Buzzer (D12, moved to the W wall in A2) ----
# Same mount as base D12, rotated 90° (seen from above): mount wall stands on D (plane parallel to YZ);
# buzzer PCB bolted to its W face, buzzer facing W. Screw runs W-E: head + washer on the mount wall's E face,
# nut on the PCB's W face. Base "E" (buzzer offset) becomes N, base "W" (pin header) becomes S.
BZ_Y = 0.0              # Y of the screw hole (PCB centre) — on the case centre line
BZ_GAP = 15.0           # mount wall W face -> W inner wall (bottom half)
BZ_WALL_T = 3.0         # mount wall thickness (X)
BZ_WALL_MARGIN = 2.0    # mount wall extends this much past the PCB on each side / above
# Rib on the floor under the PCB bottom edge runs from the mount wall to the W wall (anti-rotation
# + lets the PCB slide W when spaced off the mount wall with extra nuts / spacers on the screw).
BZ_SOUND_D = 13.0       # W wall opening: buzzer (Ø11-12) can poke through it
# Module (FC-07, confirmed by user): PCB back faces E, buzzer toward N, pin header toward S.
BZ_PCB = (32.0, 13.0, 1.6)  # PCB length (Y), height (Z), thickness (X)
BZ_HOLE_Z = 12.0            # Z of the screw hole = PCB centre (PCB bottom edge rests on the rib)
BZ_BUZ_D, BZ_BUZ_H = 12.0, 10.0  # buzzer cylinder diameter (11-12) / height above PCB
BZ_BUZ_DY = 9.0             # buzzer centre Y offset from the screw hole (+ = N)

# ---- Top panel U (D13) — viewed from above: N up, W left ----
# Microphone (D8): S-centre. PCB underside (pins 2 mm, acoustic port) faces U.
MIC_STEP = os.path.join(COMPONENTS_DIR, 'Adafruit I2S Mic SPH0645LM4H v2.step')
MIC_X, MIC_Y = 0.0, -40.0     # PCB centre
MIC_BOSS_D, MIC_BOSS_H = 7.0, 4.0
MIC_INSERT_D, MIC_INSERT_H = 3.2, 3.0   # for the Ø3.5 x 3 mm M2.5 insert
MIC_SCREW_D = 2.8                       # clearance below the insert, through the panel
MIC_PORT_D = 2.5                        # sound hole in U at the inner face (= tube bore)
MIC_FLARE_D = 6.5                       # sound hole at the outer face of U (45° cone)
MIC_TUBE_OD = 4.5                       # acoustic tube from U to the PCB around the port
# model frame: PCB x 140.25..156.76, y -111.35..-98.65, z 1.51..3.02 (underside z = 1.51)
M_MIC_C = (148.505, -105.0)
M_MIC_HOLES = [(142.79, -101.19), (154.22, -101.19)]   # Ø2.5
M_MIC_PORT = (148.50, -103.53)                         # Ø1.03 port through the PCB

# Buttons (D5): W side, 2 x 2 grid, glued from inside, Ø7 holes, locating frame
BUTTON_STEP = os.path.join(COMPONENTS_DIR, '12mm Push Button.STEP')
BTN_C = (-42.0, 5.0)          # grid centre
BTN_PITCH = 22.0              # centre-to-centre
BTN_HOLE_D = 8.0
BTN_BODY = 12.0               # square body
BTN_FRAME_CLR, BTN_FRAME_T, BTN_FRAME_H = 0.2, 1.2, 2.0
M_BTN_BODY_TOP = 3.6          # model: body top (actuator side) at y = 3.6

# U stiffening rib (A3): N-S, full width, centred in the gap between the button frames and the mic bosses
RIB_T, RIB_H = 2.0, 3.0       # thickness (X), height below the U inner face

# OLED (D6, D14-C5): E side. Measured module: PCB 34.5 x 32, glass 34 x 23 (assumed centred on the PCB).
# PCB rests on 4 corner supports, screen sits ~ level with the U inner face.
OLED_X, OLED_Y = 42.0, 5.0      # PCB centre
OLED_PCB = (34.5, 32.0, 1.2)    # X, Y, thickness (thickness from the v1 model)
OLED_GLASS = (34.0, 23.0, 1.9)  # X, Y, height above the PCB (height from the v1 model)
OLED_WIN_CLR = 0.2              # per side around the glass
OLED_HOLE_IN = 2.5              # screw hole: inward along X from its cutout corner (as v1)
OLED_HOLE_OUT = 2.575           # screw hole: outward along Y from its cutout corner (as v1)
OLED_SUP_H = 2.0                # corner supports: height below the U inner face
OLED_SUP_IN = 8.0               # supports end this far inside the nearest E/W cutout side
OLED_SUP_PAST = 0.5             # supports run this far past the PCB edge (into the frame wall)
OLED_FRAME_CLR, OLED_FRAME_T, OLED_FRAME_H = 0.2, 1.2, 3.0   # locating frame around the PCB (like the buttons)

# ---- Export for printing ----
EXPORT_PRINT = True     # write Bottom / Top as STL into 3d-casing/print/alt/
PRINT_DIR = os.path.normpath(os.path.join(HERE, '..', '..', 'print', 'alt'))   # keeps the v2 STLs untouched

# ---- Visualisation ----
SHOW_COMPONENTS = True  # import STEP models of the parts
SHOW_HARDWARE = False   # dummy coupling screws / nuts
EXPLODE = 0.0           # lift the top half; 0 = assembled
TOP_OPACITY = 0.35

SCREW_D, SCREW_L = 3.0, 10.0
HEAD_D, HEAD_H = 5.5, 3.0
WASHER_D, WASHER_ID, WASHER_T = 7.0, 3.2, 0.5
NUT_REAL_AF, NUT_T = 5.5, 2.4


def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        cbore_depth = SPLIT - CLAMP_LEN
        if cbore_depth < HEAD_H + WASHER_T + 0.3:
            ui.messageBox(f'SPLIT too small: counterbore would be {cbore_depth:.1f} mm.')
            return

        app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        root = design.rootComponent
        feats = root.features
        NEW = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        CUT = adsk.fusion.FeatureOperations.CutFeatureOperation
        JOIN = adsk.fusion.FeatureOperations.JoinFeatureOperation

        # ---------- helpers (inputs in mm, API works in cm) ----------
        def P(x, y, z=0.0):
            return adsk.core.Point3D.create(x / 10.0, y / 10.0, z / 10.0)

        def VI(mm):
            return adsk.core.ValueInput.createByReal(mm / 10.0)

        def offset_plane(base, d, name=None):
            pin = root.constructionPlanes.createInput()
            pin.setByOffset(base, VI(d))
            pl = root.constructionPlanes.add(pin)
            pl.isLightBulbOn = False
            if name:
                pl.name = name
            return pl

        def sketch_at(z, name):
            plane = root.xYConstructionPlane if abs(z) < 1e-9 else offset_plane(root.xYConstructionPlane, z)
            sk = root.sketches.add(plane)
            sk.name = name
            return sk

        def rounded_rect(sk, L, W, r, cx=0.0, cy=0.0):
            hx, hy = L / 2.0, W / 2.0
            arcs = sk.sketchCurves.sketchArcs
            corners = [(hx - r, hy - r, 0), (-hx + r, hy - r, 90),
                       (-hx + r, -hy + r, 180), (hx - r, -hy + r, 270)]
            made = []
            for x, y, a in corners:
                sx = x + r * math.cos(math.radians(a))
                sy = y + r * math.sin(math.radians(a))
                made.append(arcs.addByCenterStartSweep(P(cx + x, cy + y), P(cx + sx, cy + sy), math.pi / 2))
            lines = sk.sketchCurves.sketchLines
            for i in range(4):
                lines.addByTwoPoints(made[i].endSketchPoint, made[(i + 1) % 4].startSketchPoint)

        def hexagon(sk, cx, cy, af):
            R = af / math.sqrt(3.0)
            pts = [P(cx + R * math.cos(math.radians(60 * k)), cy + R * math.sin(math.radians(60 * k)))
                   for k in range(6)]
            lines = sk.sketchCurves.sketchLines
            first = prev = lines.addByTwoPoints(pts[0], pts[1])
            for k in range(2, 6):
                prev = lines.addByTwoPoints(prev.endSketchPoint, pts[k])
            lines.addByTwoPoints(prev.endSketchPoint, first.startSketchPoint)

        def circles(sk, centres, d):
            for x, y in centres:
                sk.sketchCurves.sketchCircles.addByCenterRadius(P(x, y), d / 20.0)

        def all_profiles(sk):
            coll = adsk.core.ObjectCollection.create()
            for p in sk.profiles:
                coll.add(p)
            return coll

        def profiles_by_area(sk, keep):
            coll = adsk.core.ObjectCollection.create()
            for p in sk.profiles:
                if keep(p.areaProperties().area * 100.0):
                    coll.add(p)
            return coll

        def extrude(profiles, h, op, targets=None):
            inp = feats.extrudeFeatures.createInput(profiles, op)
            inp.setDistanceExtent(False, VI(h))
            if targets:
                inp.participantBodies = targets
            return feats.extrudeFeatures.add(inp)

        def combine(target, tools, op):
            coll = adsk.core.ObjectCollection.create()
            for t in tools:
                coll.add(t)
            inp = feats.combineFeatures.createInput(target, coll)
            inp.operation = op
            inp.isKeepToolBodies = False
            return feats.combineFeatures.add(inp)

        def bodies_of(feature):
            return [feature.bodies.item(i) for i in range(feature.bodies.count)]

        def name_bodies(feature, base):
            for i, b in enumerate(bodies_of(feature)):
                b.name = f'{base} {i + 1}'

        def ring(z, outer, inner, h, name):
            sk = sketch_at(z, name)
            rounded_rect(sk, *outer)
            rounded_rect(sk, *inner)
            areas = [p.areaProperties().area * 100.0 for p in sk.profiles]
            return extrude(profiles_by_area(sk, lambda a: a <= min(areas) + 1e-6), h, NEW).bodies.item(0)

        def xz_extrude(y_mid, shapes, depth, op, targets, name, axis='y'):
            """Extrude shapes drawn on a plane parallel to XZ at y = y_mid, symmetric in Y
            (total `depth`). With axis='x': plane parallel to YZ at x = y_mid, symmetric in X, and the
            shapes' horizontal coordinate (cx / sx) is Y. shapes, model mm:
              ('rect', cx, cz, sx, sz) | ('circle', cx, cz, d) |
              ('teardrop', cx, cz, d, z_max)  — circle with a 45° point on top (prints without
              bridging in a vertical wall); point flattened at z_max if it would go higher."""
            if axis == 'y':
                base = root.xZConstructionPlane
                nrm = base.geometry.normal.y       # +1 or -1 depending on Fusion's convention
                Q = lambda u, _m, z: P(u, y_mid, z)
            else:
                base = root.yZConstructionPlane
                nrm = base.geometry.normal.x
                Q = lambda u, _m, z: P(y_mid, u, z)
            sk = root.sketches.add(offset_plane(base, y_mid / nrm))
            sk.name = name
            lines = sk.sketchCurves.sketchLines
            for s in shapes:
                if s[0] == 'rect':
                    _, cx, cz, sx, sz = s
                    pts = [sk.modelToSketchSpace(Q(cx + dx * sx / 2, y_mid, cz + dz * sz / 2))
                           for dx, dz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                    first = prev = lines.addByTwoPoints(pts[0], pts[1])
                    for k in (2, 3):
                        prev = lines.addByTwoPoints(prev.endSketchPoint, pts[k])
                    lines.addByTwoPoints(prev.endSketchPoint, first.startSketchPoint)
                elif s[0] == 'teardrop':
                    _, cx, cz, d, z_max = s
                    r = d / 2.0
                    t = r * math.sqrt(0.5)                      # tangent points at ±45° from the top
                    to_sk = lambda x, z: sk.modelToSketchSpace(Q(x, y_mid, z))
                    p_r, p_l = to_sk(cx + t, cz + t), to_sk(cx - t, cz + t)
                    arc = sk.sketchCurves.sketchArcs.addByThreePoints(p_l, to_sk(cx, cz - r), p_r)
                    a, b = arc.startSketchPoint, arc.endSketchPoint
                    e_r, e_l = (a, b) if a.geometry.distanceTo(p_r) < b.geometry.distanceTo(p_r) else (b, a)
                    apex = cz + r * math.sqrt(2.0)
                    if apex <= z_max:
                        ln = lines.addByTwoPoints(e_r, to_sk(cx, apex))
                        lines.addByTwoPoints(ln.endSketchPoint, e_l)
                    else:                                       # flat top at z_max
                        half = apex - z_max                     # 45° sides: half-width = drop from apex
                        l1 = lines.addByTwoPoints(e_r, to_sk(cx + half, z_max))
                        l2 = lines.addByTwoPoints(l1.endSketchPoint, to_sk(cx - half, z_max))
                        lines.addByTwoPoints(l2.endSketchPoint, e_l)
                else:
                    _, cx, cz, d = s
                    sk.sketchCurves.sketchCircles.addByCenterRadius(
                        sk.modelToSketchSpace(Q(cx, y_mid, cz)), d / 20.0)
            inp = feats.extrudeFeatures.createInput(all_profiles(sk), op)
            inp.setSymmetricExtent(VI(depth), True)
            if targets:
                inp.participantBodies = targets
            return feats.extrudeFeatures.add(inp)

        def wall_cut(y_wall_mid, rects, depth, target, name):
            return xz_extrude(y_wall_mid, [('rect',) + tuple(r) for r in rects], depth, CUT, [target], name)

        bx, by = LENGTH / 2.0 - BOSS_INSET, WIDTH / 2.0 - BOSS_INSET
        bosses = [(bx, by), (-bx, by), (-bx, -by), (bx, -by)]
        in_L, in_W, in_R = LENGTH - 2 * WALL, WIDTH - 2 * WALL, max(RADIUS - WALL, 0.1)

        # ================= SHELL + COUPLING (D2) =================
        sk = sketch_at(0, 'Outer')
        rounded_rect(sk, LENGTH, WIDTH, RADIUS)
        shell = extrude(sk.profiles.item(0), HEIGHT, NEW).bodies.item(0)

        sk = sketch_at(WALL, 'Cavity')
        rounded_rect(sk, in_L, in_W, in_R)
        cavity = extrude(sk.profiles.item(0), HEIGHT - 2 * WALL, NEW).bodies.item(0)

        sk = sketch_at(WALL, 'Bosses')
        circles(sk, bosses, BOSS_D)
        combine(cavity, bodies_of(extrude(all_profiles(sk), HEIGHT - 2 * WALL, NEW)), CUT)
        combine(shell, [cavity], CUT)

        split_plane = offset_plane(root.xYConstructionPlane, SPLIT, 'Split plane')
        feats.splitBodyFeatures.add(feats.splitBodyFeatures.createInput(shell, split_plane, True))
        bottom = top = None
        for b in root.bRepBodies:
            if b.boundingBox.maxPoint.z <= SPLIT / 10.0 + 1e-4:
                bottom = b
            else:
                top = b
        bottom.name, top.name = 'Bottom', 'Top'

        bw_rect = (LENGTH - 2 * BOTTOM_WALL, WIDTH - 2 * BOTTOM_WALL, max(RADIUS - BOTTOM_WALL, 0.1))
        thick = ring(WALL, (in_L, in_W, in_R), bw_rect, SPLIT - WALL, 'Bottom wall thickening')
        lip_outer = (in_L - 2 * LIP_CLR, in_W - 2 * LIP_CLR, max(in_R - LIP_CLR, 0.1))
        lip = ring(SPLIT, lip_outer, bw_rect, LIP_H, 'Lip')
        sk = sketch_at(SPLIT, 'Lip boss clearance')
        circles(sk, bosses, BOSS_D + 2 * LIP_BOSS_CLR)
        combine(lip, bodies_of(extrude(all_profiles(sk), LIP_H, NEW)), CUT)
        # the boss cut splits the lip into 4 pieces (one per side): join them all (v1 joined only W, D14-C2)
        lip_pieces = [b for b in root.bRepBodies
                      if b.name not in ('Bottom', 'Top') and abs(b.boundingBox.minPoint.z - SPLIT / 10.0) < 1e-4]
        if len(lip_pieces) != 4:
            ui.messageBox(f'Lip: expected 4 pieces, got {len(lip_pieces)}.')
        combine(bottom, [thick] + lip_pieces, JOIN)

        sk = sketch_at(0, 'Coupling counterbores')
        circles(sk, bosses, CBORE_D)
        extrude(all_profiles(sk), cbore_depth, CUT, [bottom])
        sk = sketch_at(0, 'Coupling holes')
        circles(sk, bosses, HOLE_D)
        extrude(all_profiles(sk), SPLIT, CUT, [bottom])

        sk = sketch_at(SPLIT, 'Coupling nut pockets')
        for x, y in bosses:
            hexagon(sk, x, y, NUT_AF)
        extrude(all_profiles(sk), NUT_POCKET, CUT, [top])
        sk = sketch_at(SPLIT, 'Coupling tip holes')
        circles(sk, bosses, HOLE_D)
        extrude(all_profiles(sk), NUT_POCKET + TIP_CLEAR, CUT, [top])

        # ================= BATTERY SHIELD (D10) =================
        # model frame -> case frame:  X = -z + ox,  Y = -x + oy,  Z = y + oz
        s_inner = -WIDTH / 2.0 + BOTTOM_WALL
        oy = s_inner + SH_SWITCH_CLR + M_SWITCH_X
        w_edge = -bx + BOSS_D / 2.0 + SH_BOSS_CLR          # PCB W edge just clear of the SW boss
        ox = w_edge + M_PCB_ZMAX
        oz = WALL + SH_STANDOFF

        def to_case(xm, ym, zm):
            return (-zm + ox, -xm + oy, ym + oz)

        holes = [to_case(x, 0, z)[:2] for x, z in M_HOLES]

        # standoffs: wide base (holds the nut pocket) + post up to the PCB
        sk = sketch_at(WALL, 'Shield standoff bases')
        circles(sk, holes, SH_BASE_D)
        extrude(all_profiles(sk), SH_BASE_H, JOIN, [bottom])
        sk = sketch_at(WALL, 'Shield standoff posts')
        circles(sk, holes, SH_POST_D)
        extrude(all_profiles(sk), SH_STANDOFF, JOIN, [bottom])
        # captive nuts from the outside (D face), screws go in from above through the PCB
        sk = sketch_at(0, 'Shield nut pockets')
        for x, y in holes:
            hexagon(sk, x, y, NUT_AF)
        extrude(all_profiles(sk), SH_NUT_POCKET, CUT, [bottom])
        sk = sketch_at(0, 'Shield screw holes')
        circles(sk, holes, HOLE_D)
        extrude(all_profiles(sk), WALL + SH_STANDOFF, CUT, [bottom])

        # S wall openings: micro USB + switch
        usb_x = -(M_USB_Z[0] + M_USB_Z[1]) / 2.0 + ox + PORT_SHIFT_X
        usb_zc = (M_USB_Y[0] + M_USB_Y[1]) / 2.0 + oz
        usb_z0 = max(usb_zc - USB_CUT[1] / 2.0, WALL)          # never into the floor
        usb_z1 = usb_zc + USB_CUT[1] / 2.0
        cut_h = usb_z1 - usb_z0
        sw_x = -(M_SWITCH_Z[0] + M_SWITCH_Z[1]) / 2.0 + ox + PORT_SHIFT_X
        sw_z = (M_SWITCH_Y[0] + M_SWITCH_Y[1]) / 2.0 + oz
        # from 1 mm outside the outer face to PORT_CUT_IN past the inner face
        y_out, y_in = -WIDTH / 2.0 - 1.0, -WIDTH / 2.0 + BOTTOM_WALL + PORT_CUT_IN
        wall_cut((y_out + y_in) / 2.0,
                 [(usb_x, (usb_z0 + usb_z1) / 2.0, USB_CUT[0], cut_h), (sw_x, sw_z, SW_CUT_W, cut_h)],
                 y_in - y_out, bottom, 'S wall openings')

        # ================= BUZZER MOUNT (D12, on the W wall: A2) =================
        w_inner = -LENGTH / 2.0 + BOTTOM_WALL
        bz_xw = w_inner + BZ_GAP                        # mount wall W face = PCB back face
        bz_xe = bz_xw + BZ_WALL_T
        pcb_l, pcb_h, pcb_t = BZ_PCB
        pcb_z0 = BZ_HOLE_Z - pcb_h / 2.0                # PCB bottom edge
        wall_l = pcb_l + 2 * BZ_WALL_MARGIN
        wall_h = pcb_z0 + pcb_h + BZ_WALL_MARGIN - WALL  # from floor top

        sk = sketch_at(WALL, 'Buzzer mount wall')
        sk.sketchCurves.sketchLines.addTwoPointRectangle(P(bz_xw, BZ_Y - wall_l / 2), P(bz_xe, BZ_Y + wall_l / 2))
        extrude(sk.profiles.item(0), wall_h, JOIN, [bottom])
        sk = sketch_at(WALL, 'Buzzer rib')
        sk.sketchCurves.sketchLines.addTwoPointRectangle(P(w_inner, BZ_Y - pcb_l / 2), P(bz_xw, BZ_Y + pcb_l / 2))
        extrude(sk.profiles.item(0), pcb_z0 - WALL, JOIN, [bottom])

        # W-E screw hole through the mount wall, sound hole through the W wall
        xz_extrude((bz_xw + bz_xe) / 2.0, [('circle', BZ_Y, BZ_HOLE_Z, HOLE_D)],
                   BZ_WALL_T + 1.0, CUT, [bottom], 'Buzzer screw hole', axis='x')
        buz_y, buz_z = BZ_Y + BZ_BUZ_DY, BZ_HOLE_Z
        # teardrop: no bridge over the opening; top kept 1 mm below the split so the wall's top edge
        # and the lip stay intact
        xz_extrude(-LENGTH / 2.0 + BOTTOM_WALL / 2.0, [('teardrop', buz_y, buz_z, BZ_SOUND_D, SPLIT - 1.0)],
                   BOTTOM_WALL + 2.0, CUT, [bottom], 'Buzzer sound hole', axis='x')

        # ================= TOP PANEL U (D13) =================
        u_in = HEIGHT - WALL          # inner face of U (Z = 48 in A2)

        def rect_c(sk, cx, cy, sx, sy):
            sk.sketchCurves.sketchLines.addCenterPointRectangle(P(cx, cy), P(cx + sx / 2.0, cy + sy / 2.0))

        def through_u(draw, name):
            """Cut shapes through the U panel."""
            sk = sketch_at(u_in - 1.0, name)
            draw(sk)
            extrude(all_profiles(sk), WALL + 2.0, CUT, [top])

        # --- microphone: insert bosses, acoustic tube, sound hole ---
        def mic_to_case(xm, ym):
            return (xm - M_MIC_C[0] + MIC_X, -(ym - M_MIC_C[1]) + MIC_Y)
        mic_holes = [mic_to_case(*h) for h in M_MIC_HOLES]
        mic_port = mic_to_case(*M_MIC_PORT)
        mic_pcb_z = u_in - MIC_BOSS_H     # PCB underside

        sk = sketch_at(mic_pcb_z, 'Mic bosses')
        circles(sk, mic_holes, MIC_BOSS_D)
        extrude(all_profiles(sk), MIC_BOSS_H, JOIN, [top])
        sk = sketch_at(mic_pcb_z + 0.1, 'Mic acoustic tube')
        circles(sk, [mic_port], MIC_TUBE_OD)
        circles(sk, [mic_port], MIC_PORT_D)
        disc = math.pi * (MIC_PORT_D / 2.0) ** 2
        extrude(profiles_by_area(sk, lambda a: a > disc * 1.5), MIC_BOSS_H - 0.1, JOIN, [top])
        sk = sketch_at(mic_pcb_z, 'Mic insert holes')
        circles(sk, mic_holes, MIC_INSERT_D)
        extrude(all_profiles(sk), MIC_INSERT_H, CUT, [top])
        sk = sketch_at(mic_pcb_z, 'Mic screw holes')
        circles(sk, mic_holes, MIC_SCREW_D)
        extrude(all_profiles(sk), MIC_BOSS_H + WALL + 1.0, CUT, [top])
        through_u(lambda s: circles(s, [mic_port], MIC_PORT_D), 'Mic sound hole')
        # flare: cone from Ø MIC_PORT_D at the inner face to Ø MIC_FLARE_D at the outer face
        over = 0.5                                               # run past the outer face
        d_top = MIC_FLARE_D + (MIC_FLARE_D - MIC_PORT_D) * over / WALL
        sk1 = sketch_at(u_in, 'Mic flare inner')
        circles(sk1, [mic_port], MIC_PORT_D)
        sk2 = sketch_at(HEIGHT + over, 'Mic flare outer')
        circles(sk2, [mic_port], d_top)
        li = feats.loftFeatures.createInput(NEW)
        li.loftSections.add(sk1.profiles.item(0))
        li.loftSections.add(sk2.profiles.item(0))
        li.isSolid = True
        combine(top, [feats.loftFeatures.add(li).bodies.item(0)], CUT)

        # --- buttons: Ø7 holes + locating frames for gluing ---
        h = BTN_PITCH / 2.0
        btns = [(BTN_C[0] + dx * h, BTN_C[1] + dy * h) for dx in (-1, 1) for dy in (-1, 1)]
        through_u(lambda s: circles(s, btns, BTN_HOLE_D), 'Button holes')
        sk = sketch_at(u_in - BTN_FRAME_H, 'Button frames')
        fi = BTN_BODY + 2 * BTN_FRAME_CLR
        for x, y in btns:
            rect_c(sk, x, y, fi + 2 * BTN_FRAME_T, fi + 2 * BTN_FRAME_T)
            rect_c(sk, x, y, fi, fi)
        ring_area = (fi + 2 * BTN_FRAME_T) ** 2 - fi ** 2
        extrude(profiles_by_area(sk, lambda a: a <= ring_area * 1.01), BTN_FRAME_H, JOIN, [top])

        # --- U stiffening rib (A3): N-S between the buttons and the mic, ends merge into the N/S walls ---
        btn_e = max(x for x, _ in btns) + fi / 2.0 + BTN_FRAME_T            # E edge of the button frames
        mic_w = min(x for x, _ in mic_holes) - MIC_BOSS_D / 2.0              # W edge of the mic bosses
        rib_x = (btn_e + mic_w) / 2.0
        rib_y = WIDTH / 2.0 - WALL / 2.0                                     # half into the side walls
        sk = sketch_at(u_in - RIB_H, 'U rib')
        rect_c(sk, rib_x, 0.0, RIB_T, 2 * rib_y)
        extrude(sk.profiles.item(0), RIB_H, JOIN, [top])

        # --- OLED: window for the glass, 4 corner supports, 4 M3 through holes (D14-C5) ---
        win_x = OLED_GLASS[0] / 2.0 + OLED_WIN_CLR       # window half sizes
        win_y = OLED_GLASS[1] / 2.0 + OLED_WIN_CLR
        oled_holes = [(OLED_X + sx * (win_x - OLED_HOLE_IN), OLED_Y + sy * (win_y + OLED_HOLE_OUT))
                      for sx in (-1, 1) for sy in (-1, 1)]
        through_u(lambda s: rect_c(s, OLED_X, OLED_Y, 2 * win_x, 2 * win_y), 'OLED window')
        sup_x0, sup_x1 = win_x - OLED_SUP_IN, OLED_PCB[0] / 2.0 + OLED_SUP_PAST
        sup_y0, sup_y1 = win_y, OLED_PCB[1] / 2.0 + OLED_SUP_PAST
        sk = sketch_at(u_in - OLED_SUP_H, 'OLED supports')
        for sx in (-1, 1):
            for sy in (-1, 1):
                sk.sketchCurves.sketchLines.addTwoPointRectangle(
                    P(OLED_X + sx * sup_x0, OLED_Y + sy * sup_y0), P(OLED_X + sx * sup_x1, OLED_Y + sy * sup_y1))
        extrude(all_profiles(sk), OLED_SUP_H, JOIN, [top])
        # locating frame around the PCB; the supports run into its wall
        sk = sketch_at(u_in - OLED_FRAME_H, 'OLED frame')
        fx, fy = OLED_PCB[0] + 2 * OLED_FRAME_CLR, OLED_PCB[1] + 2 * OLED_FRAME_CLR
        rect_c(sk, OLED_X, OLED_Y, fx + 2 * OLED_FRAME_T, fy + 2 * OLED_FRAME_T)
        rect_c(sk, OLED_X, OLED_Y, fx, fy)
        ring_area = (fx + 2 * OLED_FRAME_T) * (fy + 2 * OLED_FRAME_T) - fx * fy
        extrude(profiles_by_area(sk, lambda a: a <= ring_area * 1.01), OLED_FRAME_H, JOIN, [top])
        sk = sketch_at(u_in - OLED_SUP_H - 1.0, 'OLED screw holes')
        circles(sk, oled_holes, HOLE_D)
        extrude(all_profiles(sk), OLED_SUP_H + WALL + 2.0, CUT, [top])

        # ================= OPTIONAL: hardware + component models =================
        moving = adsk.core.ObjectCollection.create()
        moving.add(top)
        if SHOW_HARDWARE:
            washer_z = cbore_depth - WASHER_T
            sk = sketch_at(washer_z - HEAD_H, 'HW heads')
            circles(sk, bosses, HEAD_D)
            name_bodies(extrude(all_profiles(sk), HEAD_H, NEW), 'Screw head')
            sk = sketch_at(washer_z, 'HW shanks')
            circles(sk, bosses, SCREW_D)
            name_bodies(extrude(all_profiles(sk), SCREW_L, NEW), 'Screw shank')
            sk = sketch_at(washer_z, 'HW washers')
            circles(sk, bosses, WASHER_D)
            circles(sk, bosses, WASHER_ID)
            disc = math.pi * (WASHER_ID / 2.0) ** 2
            name_bodies(extrude(profiles_by_area(sk, lambda a: a > disc * 1.5), WASHER_T, NEW), 'Washer')
            sk = sketch_at(SPLIT + NUT_POCKET - NUT_T, 'HW nuts')
            for x, y in bosses:
                hexagon(sk, x, y, NUT_REAL_AF)
            circles(sk, bosses, SCREW_D)
            disc = math.pi * (SCREW_D / 2.0) ** 2
            nuts = extrude(profiles_by_area(sk, lambda a: a > disc * 1.5), NUT_T, NEW)
            name_bodies(nuts, 'Nut')
            for b in bodies_of(nuts):
                moving.add(b)

        # ================= EXPORT (before explode, so halves are in assembled position) =================
        if EXPORT_PRINT:
            os.makedirs(PRINT_DIR, exist_ok=True)
            em = design.exportManager
            written = []
            for body, fname in ((bottom, 'case_bottom.stl'), (top, 'case_top.stl')):
                path = os.path.join(PRINT_DIR, fname)
                opt = em.createSTLExportOptions(body, path)
                opt.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementHigh
                opt.isBinaryFormat = True
                em.execute(opt)
                written.append(path)

        if EXPLODE > 0:
            mv = feats.moveFeatures.createInput2(moving)
            mv.defineAsTranslateXYZ(VI(0), VI(0), VI(EXPLODE), True)
            feats.moveFeatures.add(mv)
        top.opacity = TOP_OPACITY
        for s in root.sketches:
            s.isVisible = False

        if SHOW_COMPONENTS:
            # buzzer stand-in (assumed dims): PCB + buzzer cylinder
            f = xz_extrude(bz_xw - pcb_t / 2.0, [('rect', BZ_Y, BZ_HOLE_Z, pcb_l, pcb_h)],
                           pcb_t, NEW, None, 'Buzzer PCB (dummy)', axis='x')
            f.bodies.item(0).name = 'Buzzer PCB (dummy)'
            f = xz_extrude(bz_xw - pcb_t - BZ_BUZ_H / 2.0, [('circle', buz_y, buz_z, BZ_BUZ_D)],
                           BZ_BUZ_H, NEW, None, 'Buzzer (dummy)', axis='x')
            f.bodies.item(0).name = 'Buzzer (dummy)'
            # OLED stand-in (measured module, D14-C5): PCB on the supports, glass toward U
            oled_pcb_top = u_in - OLED_SUP_H
            sk = sketch_at(oled_pcb_top - OLED_PCB[2], 'OLED PCB (dummy)')
            rect_c(sk, OLED_X, OLED_Y, OLED_PCB[0], OLED_PCB[1])
            circles(sk, oled_holes, HOLE_D)
            f = extrude(profiles_by_area(sk, lambda a: a > 100.0), OLED_PCB[2], NEW)
            f.bodies.item(0).name = 'OLED PCB (dummy)'
            sk = sketch_at(oled_pcb_top, 'OLED glass (dummy)')
            rect_c(sk, OLED_X, OLED_Y, OLED_GLASS[0], OLED_GLASS[1])
            f = extrude(sk.profiles.item(0), OLED_GLASS[2], NEW)
            f.bodies.item(0).name = 'OLED glass (dummy)'
            for s in root.sketches:
                s.isVisible = False

            missing = []

            def matrix(rows, t):
                m = adsk.core.Matrix3D.create()
                m.setWithArray([rows[0][0], rows[0][1], rows[0][2], t[0] / 10.0,
                                rows[1][0], rows[1][1], rows[1][2], t[1] / 10.0,
                                rows[2][0], rows[2][1], rows[2][2], t[2] / 10.0,
                                0, 0, 0, 1])
                return m

            def import_step(path, m):
                if not os.path.exists(path):
                    missing.append(path)
                    return None
                before = root.occurrences.count
                im = app.importManager
                im.importToTarget(im.createSTEPImportOptions(path), root)
                if root.occurrences.count == before:
                    return None
                occ = root.occurrences.item(root.occurrences.count - 1)
                occ.transform2 = m
                return occ

            # battery shield: X = -z + ox, Y = -x + oy, Z = y + oz
            import_step(SHIELD_STEP, matrix([(0, 0, -1), (-1, 0, 0), (0, 1, 0)], (ox, oy, oz)))
            # mic: flipped (rotate 180° about X), PCB underside at mic_pcb_z
            import_step(MIC_STEP, matrix([(1, 0, 0), (0, -1, 0), (0, 0, -1)],
                                         (MIC_X - M_MIC_C[0], MIC_Y + M_MIC_C[1], mic_pcb_z + 1.51)))
            # buttons: model +y (actuator) -> +Z, body top against U
            rot = [(1, 0, 0), (0, 0, -1), (0, 1, 0)]
            first = import_step(BUTTON_STEP, matrix(rot, (btns[0][0], btns[0][1], u_in - M_BTN_BODY_TOP)))
            if first:
                for x, y in btns[1:]:
                    root.occurrences.addExistingComponent(
                        first.component, matrix(rot, (x, y, u_in - M_BTN_BODY_TOP)))
            design.snapshots.add()
            if missing:
                ui.messageBox('Component model(s) not found:\n' + '\n'.join(missing))

        app.activeViewport.fit()
        if EXPORT_PRINT:
            ui.messageBox('Exported for printing:\n' + '\n'.join(written) +
                          '\n\nIn the slicer: print Bottom floor-down; flip Top so panel U is on the bed.')

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))
