# Fusion script: two-part test case showing the top/bottom coupling (decisions.md D2)
#
# - 100 x 100 x 60 mm box, 2 mm walls, rounded VERTICAL edges only
# - split into bottom + top halves
# - 4 corner bosses: bottom = Ø3.4 through hole + Ø7.6 counterbore (washer + head),
#                    top    = hex nut pocket 5.7 AF + Ø3.4 tip clearance
# - bottom half has 3.4 mm side walls; their inner part continues up as a lip
#   that slides inside the top half's 2 mm walls (alignment)
# - optional dummy hardware (M3x10 socket screw, Ø7 washer, M3 nut) to show the joint
#
# Run in Fusion: Utilities > Add-Ins > Scripts and Add-Ins > "+" > Script from my computer
#                > pick this folder > Run.
import math
import adsk.core, adsk.fusion, traceback

# ---- Case (mm) ----
LENGTH = 100.0      # X
WIDTH = 100.0       # Y
HEIGHT = 60.0       # Z, total closed height
RADIUS = 5.0        # vertical edge rounding (outer)
WALL = 2.0          # walls, floor and top
SPLIT = 15.0        # height of the bottom half (must be >= 10.3)

# ---- Coupling (D2) ----
BOSS_D = 11.0       # corner boss diameter
BOSS_INSET = 6.5    # boss centre distance from the outer faces
HOLE_D = 3.4        # M3 clearance
CBORE_D = 7.6       # counterbore for Ø7 washer + head
CLAMP_LEN = 6.5     # material between counterbore floor and the mating face
NUT_AF = 5.7        # hex pocket across flats (nut 5-5.5 AF)
NUT_POCKET = 2.5    # hex pocket depth
TIP_CLEAR = 6.0     # extra Ø3.4 depth above the nut for leftover screw length

# ---- Lip (alignment) ----
LIP_H = 2.5         # height above the mating face
LIP_T = 1.2         # lip thickness
LIP_CLR = 0.2       # clearance to the top half's inner wall (per side)
LIP_BOSS_CLR = 0.3  # clearance around the top bosses
# Bottom-half side walls are thicker so the lip is a straight vertical extension
# of their inner part: 2.0 (under top wall) + 0.2 clearance + 1.2 lip = 3.4 mm
BOTTOM_WALL = WALL + LIP_CLR + LIP_T

# ---- Visualisation ----
SHOW_HARDWARE = True
EXPLODE = 25.0      # lift the top half (and nuts) by this much; 0 = assembled
TOP_OPACITY = 0.6   # 1.0 = solid

# ---- Hardware dims (dummy bodies) ----
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
            ui.messageBox(f'SPLIT too small: counterbore would be {cbore_depth:.1f} mm, '
                          f'need >= {HEAD_H + WASHER_T + 0.3:.1f} mm.')
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
        def P(x, y):
            return adsk.core.Point3D.create(x / 10.0, y / 10.0, 0)

        def VI(mm):
            return adsk.core.ValueInput.createByReal(mm / 10.0)

        def sketch_at(z, name):
            if abs(z) < 1e-9:
                plane = root.xYConstructionPlane
            else:
                pin = root.constructionPlanes.createInput()
                pin.setByOffset(root.xYConstructionPlane, VI(z))
                plane = root.constructionPlanes.add(pin)
                plane.isLightBulbOn = False
            sk = root.sketches.add(plane)
            sk.name = name
            return sk

        def rounded_rect(sk, L, W, r):
            hx, hy = L / 2.0, W / 2.0
            arcs = sk.sketchCurves.sketchArcs
            corners = [(hx - r, hy - r, 0), (-hx + r, hy - r, 90),
                       (-hx + r, -hy + r, 180), (hx - r, -hy + r, 270)]
            made = []
            for cx, cy, a in corners:
                sx = cx + r * math.cos(math.radians(a))
                sy = cy + r * math.sin(math.radians(a))
                made.append(arcs.addByCenterStartSweep(P(cx, cy), P(sx, sy), math.pi / 2))
            lines = sk.sketchCurves.sketchLines
            for i in range(4):
                lines.addByTwoPoints(made[i].endSketchPoint, made[(i + 1) % 4].startSketchPoint)

        def hexagon(sk, cx, cy, af):
            R = af / math.sqrt(3.0)  # circumradius
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
                if keep(p.areaProperties().area * 100.0):  # cm² -> mm²
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

        def name_bodies(feature, base):
            for i in range(feature.bodies.count):
                feature.bodies.item(i).name = f'{base} {i + 1}'

        bx, by = LENGTH / 2.0 - BOSS_INSET, WIDTH / 2.0 - BOSS_INSET
        bosses = [(bx, by), (-bx, by), (-bx, -by), (bx, -by)]
        in_L, in_W, in_R = LENGTH - 2 * WALL, WIDTH - 2 * WALL, max(RADIUS - WALL, 0.1)

        # ---------- 1. closed shell with corner bosses ----------
        sk = sketch_at(0, 'Outer')
        rounded_rect(sk, LENGTH, WIDTH, RADIUS)
        shell = extrude(sk.profiles.item(0), HEIGHT, NEW).bodies.item(0)

        sk = sketch_at(WALL, 'Cavity')
        rounded_rect(sk, in_L, in_W, in_R)
        cavity = extrude(sk.profiles.item(0), HEIGHT - 2 * WALL, NEW).bodies.item(0)

        sk = sketch_at(WALL, 'Bosses')
        circles(sk, bosses, BOSS_D)
        boss_feat = extrude(all_profiles(sk), HEIGHT - 2 * WALL, NEW)
        combine(cavity, [boss_feat.bodies.item(i) for i in range(boss_feat.bodies.count)], CUT)
        combine(shell, [cavity], CUT)

        # ---------- 2. split into bottom / top ----------
        pin = root.constructionPlanes.createInput()
        pin.setByOffset(root.xYConstructionPlane, VI(SPLIT))
        split_plane = root.constructionPlanes.add(pin)
        split_plane.name = 'Split plane'
        sin = feats.splitBodyFeatures.createInput(shell, split_plane, True)
        feats.splitBodyFeatures.add(sin)
        split_plane.isLightBulbOn = False

        bottom = top = None
        for b in root.bRepBodies:
            if b.boundingBox.maxPoint.z <= SPLIT / 10.0 + 1e-4:
                bottom = b
            else:
                top = b
        bottom.name, top.name = 'Bottom', 'Top'

        # ---------- 3. thicker bottom walls + lip as their vertical extension ----------
        def ring(z, outer, inner, h, name):
            sk = sketch_at(z, name)
            rounded_rect(sk, *outer)
            rounded_rect(sk, *inner)
            areas = [p.areaProperties().area * 100.0 for p in sk.profiles]
            prof = profiles_by_area(sk, lambda a: a <= min(areas) + 1e-6)  # the ring
            return extrude(prof, h, NEW).bodies.item(0)

        bw_rect = (LENGTH - 2 * BOTTOM_WALL, WIDTH - 2 * BOTTOM_WALL, max(RADIUS - BOTTOM_WALL, 0.1))
        # inner part of the bottom wall, floor -> mating face
        thick = ring(WALL, (in_L, in_W, in_R), bw_rect, SPLIT - WALL, 'Bottom wall thickening')
        # lip: same inner face, outer face 0.2 mm inside the top half's wall
        lip_outer = (in_L - 2 * LIP_CLR, in_W - 2 * LIP_CLR, max(in_R - LIP_CLR, 0.1))
        lip = ring(SPLIT, lip_outer, bw_rect, LIP_H, 'Lip')

        sk = sketch_at(SPLIT, 'Lip boss clearance')
        circles(sk, bosses, BOSS_D + 2 * LIP_BOSS_CLR)
        clr = extrude(all_profiles(sk), LIP_H, NEW)
        combine(lip, [clr.bodies.item(i) for i in range(clr.bodies.count)], CUT)
        combine(bottom, [thick, lip], JOIN)

        # ---------- 4. bottom: counterbore + through hole ----------
        sk = sketch_at(0, 'Counterbores')
        circles(sk, bosses, CBORE_D)
        extrude(all_profiles(sk), cbore_depth, CUT, [bottom])

        sk = sketch_at(0, 'Through holes')
        circles(sk, bosses, HOLE_D)
        extrude(all_profiles(sk), SPLIT, CUT, [bottom])

        # ---------- 5. top: hex nut pocket + tip clearance ----------
        sk = sketch_at(SPLIT, 'Nut pockets')
        for x, y in bosses:
            hexagon(sk, x, y, NUT_AF)
        extrude(all_profiles(sk), NUT_POCKET, CUT, [top])

        sk = sketch_at(SPLIT, 'Screw tip holes')
        circles(sk, bosses, HOLE_D)
        extrude(all_profiles(sk), NUT_POCKET + TIP_CLEAR, CUT, [top])

        # ---------- 6. dummy hardware ----------
        moving = adsk.core.ObjectCollection.create()
        moving.add(top)
        if SHOW_HARDWARE:
            washer_z = cbore_depth - WASHER_T
            head_z = washer_z - HEAD_H

            sk = sketch_at(head_z, 'HW heads')
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
            for i in range(nuts.bodies.count):
                moving.add(nuts.bodies.item(i))

        # ---------- 7. presentation ----------
        if EXPLODE > 0:
            mv = feats.moveFeatures.createInput2(moving)
            mv.defineAsTranslateXYZ(VI(0), VI(0), VI(EXPLODE), True)
            feats.moveFeatures.add(mv)
        top.opacity = TOP_OPACITY

        for s in root.sketches:
            s.isVisible = False
        app.activeViewport.fit()

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))
