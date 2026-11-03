# -*- coding: utf-8 -*-
"""Scena SOFA dimostrativa: motore - molla - tubo flessibile a uncino.

Avvio: ..\\bin\\runSofa.exe .\\scena_motore_molla_tubo.py
Frecce su/giu: carica e scarica il motore (0.35 mm per tasto); 1: auto;
0: reset.

Il tubo ha 40 mm di albero rigido e 60 mm flessibili. La forma a uncino e'
resa con segmenti visuali orientabili; e' una dimostrazione geometrica, non
ancora il FEM Nitinol con CableConstraint richiesto dalla baseline.
Unita' geometriche: mm.
"""
import math
import os
import numpy as np
import Sofa
import Sofa.Core
from Sofa.constants import Key

TUBE_LENGTH = 100.0
RIGID_LENGTH = 40.0
FLEX_LENGTH = 60.0
OUTER_DIAMETER = 1.93
WALL_THICKNESS = 0.22
INNER_DIAMETER = OUTER_DIAMETER - 2.0 * WALL_THICKNESS
TENDON_OFFSET = 0.6
SPRING_REST = 20.0
SPRING_K = 1.2
SPRING_DAMPING = 1.5
SPRING_HYSTERESIS = 0.45
E_LOAD_GPA = 77.0
E_UNLOAD_GPA = 65.0
POISSON_RATIO = 0.33
MATERIAL_HYSTERESIS = 0.40
MOTOR_STEP = 0.35
MOTOR_MAX_STROKE = 12.0
HOOK_STROKE = 12.0
HOOK_MAX_ANGLE = math.pi / 2.0
N_FLEX_SEGMENTS = 6
MOTOR_SPHERE_RADIUS = 2.2
N_COILS = 9
N_SPRING_POINTS = 181
MOTOR_REST_X = -SPRING_REST
MESH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mesh')


def helix(p1, p2):
    """Punti della spirale parametrica, con estremi sul motore e sul tubo."""
    p1 = np.asarray(p1, dtype=float)
    p2 = np.asarray(p2, dtype=float)
    axis = p2 - p1
    length = np.linalg.norm(axis)
    if length < 1e-9:
        axis = np.array([1.0, 0.0, 0.0])
    unit = axis / np.linalg.norm(axis)
    ref = np.array([0.0, 0.0, 1.0])
    u = np.cross(unit, ref)
    u /= np.linalg.norm(u)
    v = np.cross(unit, u)
    points = []
    taper = 0.045
    for i in range(N_SPRING_POINTS):
        s = i / (N_SPRING_POINTS - 1)
        angle = 2.0 * math.pi * N_COILS * s
        radius_factor = min(1.0, s / taper, (1.0 - s) / taper)
        point = p1 + s * axis + 2.5 * radius_factor * (
            math.cos(angle) * u + math.sin(angle) * v)
        points.append(point.tolist())
    points[0] = p1.tolist()
    points[-1] = p2.tolist()
    return points


class HookSceneController(Sofa.Core.Controller):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.motor = kwargs['motor']
        self.motor_visual = kwargs['motorVisual']
        self.anchor = kwargs['anchor']
        self.tip = kwargs['tip']
        self.spring_vis = kwargs['springVisual']
        self.flex_segments = kwargs['flexSegments']
        self.offset = 0.0
        self.direction = 0
        self.auto_mode = False
        self.auto_time = 0.0

    def move_motor(self):
        x = MOTOR_REST_X - self.offset
        pose = [[x, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]]
        # Il cursore e' cinematico, non bloccato da FixedProjectiveConstraint:
        # reimpostiamo posa e velocita' per imporre la corsa del motore.
        self.motor.position.value = pose
        self.motor.velocity.value = [[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]]
        # La posa visuale non riceve la forza della molla: sfera e spirale
        # restano quindi solidali anche dopo l'integrazione del solver.
        self.motor_visual.position.value = pose
        self.update_spring_points()

    def update_spring_points(self):
        p1 = self.motor_visual.position.value[0][:3]
        p2 = self.anchor.position.value[0][:3]
        self.spring_vis.position.value = helix(p1, p2)

    def update_hook(self):
        """Approssima l'arco del tratto flessibile con sei mesh orientate."""
        theta = HOOK_MAX_ANGLE * min(self.offset / HOOK_STROKE, 1.0)
        ds = FLEX_LENGTH / N_FLEX_SEGMENTS
        for i, dof in enumerate(self.flex_segments):
            s = (i + 0.5) * ds
            phi = theta * s / FLEX_LENGTH
            if abs(theta) < 1e-8:
                x, y = RIGID_LENGTH + s, 0.0
            else:
                radius = FLEX_LENGTH / theta
                x = RIGID_LENGTH + radius * math.sin(phi)
                y = radius * (1.0 - math.cos(phi))
            qz, qw = math.sin(phi / 2.0), math.cos(phi / 2.0)
            dof.position.value = [[x, y, 0.0, 0.0, 0.0, qz, qw]]

        if abs(theta) < 1e-8:
            tip_x, tip_y = TUBE_LENGTH, 0.0
        else:
            radius = FLEX_LENGTH / theta
            tip_x = RIGID_LENGTH + radius * math.sin(theta)
            tip_y = radius * (1.0 - math.cos(theta))
        self.tip.position.value = [[tip_x, tip_y, 0.0, 0.0, 0.0,
                                    math.sin(theta / 2.0), math.cos(theta / 2.0)]]

    def report(self):
        p1 = np.asarray(self.motor.position.value[0][:3], dtype=float)
        p2 = np.asarray(self.anchor.position.value[0][:3], dtype=float)
        delta_ls = max(0.0, float(np.linalg.norm(p2 - p1)) - SPRING_REST)
        hysteresis_sign = self.direction
        tension = max(0.0, SPRING_K * delta_ls + hysteresis_sign * SPRING_HYSTERESIS)
        pos = self.tip.position.value[0]
        print(f"[Motore-molla-tubo] u={self.offset:.2f} mm, xmot={p1[0]:.2f} mm | "
              f"T~={tension:.3f} N | "
              f"DeltaLs={delta_ls:.2f} mm | punta X={pos[0]:.2f}, Y={pos[1]:.2f} mm")

    def onKeypressedEvent(self, event):
        key = event.get('key', '')
        if key in (Key.uparrow, 'w', 'W'):
            self.auto_mode = False
            self.direction = 1
            self.offset = min(MOTOR_MAX_STROKE, self.offset + MOTOR_STEP)
        elif key in (Key.downarrow, 's', 'S'):
            self.auto_mode = False
            self.direction = -1
            self.offset = max(0.0, self.offset - MOTOR_STEP)
        elif key == '1':
            self.auto_mode = not self.auto_mode
            self.auto_time = 0.0
            print(f"[Controller] Modalita' {'autonoma' if self.auto_mode else 'manuale'}")
            return
        elif key in ('0', 'z', 'Z'):
            self.auto_mode = False
            self.offset = 0.0
            self.direction = 0
        else:
            return
        self.move_motor()
        self.update_hook()
        self.report()

    def onAnimateBeginEvent(self, event):
        if self.auto_mode:
            dt = float(event.get('dt', 0.01))
            self.auto_time += dt
            phase = 2.0 * math.pi * self.auto_time / 6.0
            self.offset = 0.5 * MOTOR_MAX_STROKE * (1.0 - math.cos(phase))
            self.direction = 1 if math.sin(phase) >= 0 else -1
        # Mantiene il carrello sulla posizione comandata anche durante la
        # dinamica, senza lasciare che la forza della molla lo trascini.
        self.move_motor()
        self.update_hook()
        self.update_spring_points()

    def onAnimateEndEvent(self, event):
        self.update_hook()
        self.update_spring_points()


def add_surface(parent, child_name, mesh_name, color):
    visual = parent.addChild(child_name)
    visual.addObject('MeshOBJLoader', name='loader',
                     filename=os.path.join(MESH_DIR, mesh_name))
    visual.addObject('OglModel', name='visualModel', src='@loader',
                     color=color)
    visual.addObject('RigidMapping')
    return visual


def createScene(root):
    root.gravity.value = [0.0, 0.0, 0.0]
    root.dt.value = 0.01
    root.addObject('RequiredPlugin', pluginName=[
        'Sofa.Component.AnimationLoop', 'Sofa.Component.Constraint.Projective',
        'Sofa.Component.IO.Mesh', 'Sofa.Component.LinearSolver.Iterative',
        'Sofa.Component.Mapping.Linear', 'Sofa.Component.Mapping.NonLinear',
        'Sofa.Component.Mass', 'Sofa.Component.MechanicalLoad',
        'Sofa.Component.ODESolver.Backward', 'Sofa.Component.SolidMechanics.Spring',
        'Sofa.Component.StateContainer', 'Sofa.Component.Topology.Container.Dynamic',
        'Sofa.Component.Visual', 'Sofa.GL.Component.Rendering3D',
        'Sofa.GL.Component.Shader'])
    root.addObject('DefaultAnimationLoop')
    root.addObject('VisualStyle', displayFlags='showVisualModels showBehaviorModels')
    root.addObject('EulerImplicitSolver', rayleighStiffness=0.01, rayleighMass=0.01)
    root.addObject('CGLinearSolver', iterations=35, tolerance=1e-5, threshold=1e-18)
    root.addObject('LightManager', ambient=[0.55, 0.55, 0.55, 1.0])
    root.addObject('DirectionalLight', direction=[0.4, -0.8, -1.0], color=[0.9, 0.9, 0.9, 1.0])

    motor_node = root.addChild('Motor')
    motor = motor_node.addObject('MechanicalObject', name='motorDOF', template='Rigid3d',
        position=[[MOTOR_REST_X, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]])
    motor_node.addObject('UniformMass', totalMass=1e-6)
    motor_visual_node = root.addChild('MotorVisualAnchor')
    motor_visual = motor_visual_node.addObject('MechanicalObject', name='visualDOF',
        template='Rigid3d', position=[[MOTOR_REST_X, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]])
    motor_visual_node.addObject('UniformMass', totalMass=1e-9)
    motor_vis = motor_visual_node.addChild('VisualMotor')
    motor_vis.addObject('MeshOBJLoader', name='loader',
        filename=os.path.join(MESH_DIR, 'sphere.obj'),
        scale3d=[MOTOR_SPHERE_RADIUS, MOTOR_SPHERE_RADIUS, MOTOR_SPHERE_RADIUS])
    motor_vis.addObject('OglModel', name='visualModel', src='@loader',
        color=[1.0, 0.72, 0.12, 1.0])
    motor_vis.addObject('RigidMapping')

    # Punto fisso di ingresso del tendine e attacco diretto molla-tubo.
    anchor_node = root.addChild('TendonAnchor')
    anchor = anchor_node.addObject('MechanicalObject', name='anchorDOF', template='Rigid3d',
        position=[[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]])
    anchor_node.addObject('FixedProjectiveConstraint', indices=[0])
    root.addObject('SpringForceField', name='motorSpring', object1='@Motor/motorDOF',
        object2='@TendonAnchor/anchorDOF', spring=[0, 0, SPRING_K, SPRING_DAMPING, SPRING_REST])

    # Albero rigido orizzontale 0-40 mm; la superficie coincide con l'ancoraggio.
    add_surface(anchor_node, 'RigidShaft40mm', 'shaft_surface.obj',
        [0.58, 0.65, 0.74, 1.0])
    add_surface(anchor_node, 'TendonAlongShaft', 'tendon_shaft.obj',
        [0.95, 0.24, 0.20, 1.0])

    flex_dofs = []
    for i in range(N_FLEX_SEGMENTS):
        ds = FLEX_LENGTH / N_FLEX_SEGMENTS
        center_x = RIGID_LENGTH + (i + 0.5) * ds
        segment = root.addChild(f'FlexibleTubeSegment{i + 1}')
        dof = segment.addObject('MechanicalObject', name='segmentDOF', template='Rigid3d',
            position=[[center_x, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]])
        segment.addObject('UniformMass', totalMass=1e-9)
        flex_dofs.append(dof)
        add_surface(segment, 'TubeSurface', 'flex_segment.obj',
            [0.12, 0.69, 0.82, 1.0])
        add_surface(segment, 'TendonSurface', 'tendon_segment.obj',
            [0.95, 0.24, 0.20, 1.0])

    distal = root.addChild('TubeDistalTip')
    tip = distal.addObject('MechanicalObject', name='tipDOF', template='Rigid3d',
        position=[[TUBE_LENGTH, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]])
    distal.addObject('UniformMass', totalMass=1e-9)
    tip_vis = distal.addChild('VisualTip')
    tip_vis.addObject('MeshOBJLoader', name='loader',
        filename=os.path.join(MESH_DIR, 'sphere.obj'), scale3d=[1.3, 1.3, 1.3])
    tip_vis.addObject('OglModel', name='visualModel', src='@loader',
        color=[0.95, 0.25, 0.20, 1.0])
    tip_vis.addObject('RigidMapping')

    spring_points = helix([MOTOR_REST_X, 0.0, 0.0], [0.0, 0.0, 0.0])
    spring_node = root.addChild('VisualSpringPoints')
    spring_node.addObject('EdgeSetTopologyContainer', name='springPointsTopology',
        edges=[[i, i + 1] for i in range(len(spring_points) - 1)])
    spring_visual = spring_node.addObject('MechanicalObject', name='springPoints',
        template='Vec3d', position=spring_points, showObject=True,
        showObjectScale=1.8, showColor=[0.12, 0.82, 0.95, 1.0])

    controller = HookSceneController(name='hookController', motor=motor,
        motorVisual=motor_visual, anchor=anchor,
        tip=tip, springVisual=spring_visual, flexSegments=flex_dofs)
    root.addObject(controller)
    controller.move_motor()
    controller.update_hook()

    print(f"Tubo: {RIGID_LENGTH:.0f} mm rigidi + {FLEX_LENGTH:.0f} mm flessibili; "
          f"OD/parete/ID={OUTER_DIAMETER:.2f}/{WALL_THICKNESS:.2f}/{INNER_DIAMETER:.2f} mm")
    print(f"Molla: L0={SPRING_REST:.0f} mm, k={SPRING_K:.1f} N/mm, "
          f"c={SPRING_DAMPING:.1f} N*s/mm; passo motore={MOTOR_STEP:.2f} mm")
    print(f"Baseline Nitinol da usare nel FEM: E carico/scarico={E_LOAD_GPA:.0f}/{E_UNLOAD_GPA:.0f} GPa, "
          f"nu={POISSON_RATIO:.2f}, isteresi materiale=+/-{MATERIAL_HYSTERESIS:.2f} N")
    print("Carico: freccia su; scarico: freccia giu; 1: auto; 0: reset.")
    print("La curvatura a segmenti e' una resa visiva provvisoria; FEM e CableConstraint da integrare.")
    return root
