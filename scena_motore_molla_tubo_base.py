# -*- coding: utf-8 -*-
"""Scena SOFA dimostrativa: motore - molla - tubo flessibile a uncino.

Avvio da SOFA v26.06.00: runSofa -l SofaPython3 <percorso>\\scena_motore_molla_tubo_base.py
Frecce su/giu: carica e scarica il motore (0.35 mm per tasto); 0: reset.

L'ingombro a riposo e' 100 mm: molla 20 mm, albero rigido 20 mm, tratto
flessibile 60 mm. Il tubo cavo FEM e' lungo 80 mm. Unita' geometriche: mm.
"""
import math
import os
import sys
import csv
import shutil
import subprocess
import numpy as np
import Sofa
import Sofa.Core
from Sofa.constants import Key

# I componenti STLIB/SoftRobots sono distribuiti come moduli Python dei plugin SOFA.
SOFA_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
for plugin_name in ('STLIB', 'SoftRobots'):
    plugin_python = os.path.join(SOFA_ROOT, 'plugins', plugin_name,
                                 'lib', 'python3', 'site-packages')
    if os.path.isdir(plugin_python) and plugin_python not in sys.path:
        sys.path.append(plugin_python)
from stlib3.physics.deformable import ElasticMaterialObject
from stlib3.physics.constraints import FixedBox

TUBE_LENGTH = 80.0
RIGID_LENGTH = 20.0
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
MOTOR_SPHERE_RADIUS = 2.2
N_COILS = 9
N_SPRING_POINTS = 181
TUBE_AXIAL_CELLS = 15
TUBE_RADIAL_CELLS = 2
TUBE_CIRCUMFERENTIAL_CELLS = 8
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
        self.tube = kwargs['tube']
        self.tube_dofs = self.tube.dofs
        self.fem_ff = self.tube.forcefield
        self.cable = kwargs['cable']
        self.spring_ff = kwargs['springFF']
        self.spring_k = SPRING_K
        self.centerline_nodes = kwargs['centerlineNodes']
        self.offset = 0.0
        self.applied_tension = 0.0
        self.direction = 0
        self.plot_phase = 1
        self.simulation_time = 0.0
        self.initial_tip_y = None
        self.csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     'dati_simulazione.csv')
        self.csv_file = open(self.csv_path, 'w', newline='', encoding='utf-8')
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow(['tempo_s', 'X_punta_mm', 'Y_punta_mm', 'DeltaY_punta_mm',
                                 'u_mm', 'T_N', 'DeltaLs_mm', 'fase_traiettoria'])
        self.csv_file.flush()

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

    def centerline(self):
        pos = np.asarray(self.tube_dofs.position.value, dtype=float)
        # Prima di Simulation.init il prefab STLIB espone ancora un placeholder
        # a un solo nodo: in quel momento la linea centrale è quella indeformata.
        last_node = max(nodes[-1] for nodes in self.centerline_nodes)
        if pos.ndim != 2 or len(pos) <= last_node:
            return np.asarray([[x, 0.0, 0.0]
                               for x in np.linspace(0.0, TUBE_LENGTH,
                                                    len(self.centerline_nodes))])
        return np.asarray([np.mean(pos[nodes], axis=0) for nodes in self.centerline_nodes])

    def update_hook(self):
        """Aggiorna il marker di punta a partire dalla deformazione FEM reale."""
        line = self.centerline()
        tip_pos = line[-1]
        self.tip.position.value = [[float(tip_pos[0]), float(tip_pos[1]), float(tip_pos[2]),
                                    0.0, 0.0, 0.0, 1.0]]

    def spring_elongation(self):
        p1 = np.asarray(self.motor.position.value[0][:3], dtype=float)
        p2 = np.asarray(self.anchor.position.value[0][:3], dtype=float)
        return max(0.0, float(np.linalg.norm(p2 - p1)) - SPRING_REST)

    def log_sample(self):
        pos = self.tip.position.value[0]
        x_tip, y_tip = float(pos[0]), float(pos[1])
        if self.initial_tip_y is None:
            self.initial_tip_y = y_tip
        delta_y = y_tip - self.initial_tip_y
        delta_ls = self.spring_elongation()
        self.csv_writer.writerow([f'{self.simulation_time:.6f}', f'{x_tip:.6f}',
                                  f'{y_tip:.6f}', f'{delta_y:.6f}', f'{self.offset:.6f}',
                                  f'{self.applied_tension:.6f}', f'{delta_ls:.6f}',
                                  self.plot_phase])
        self.csv_file.flush()
    def launch_plot_window(self):
        """Avvia il viewer Tkinter esterno che legge il CSV prodotto dalla scena."""
        python_root = os.environ.get('PYTHON_ROOT', '')
        candidates = []
        if python_root:
            candidates.extend([os.path.join(python_root, 'pythonw.exe'),
                               os.path.join(python_root, 'python.exe')])
        candidates.extend([shutil.which('pythonw.exe'), shutil.which('python')])
        python_exe = next((path for path in candidates if path and os.path.isfile(path)), None)
        if python_exe is None:
            print('[Monitor] Python con Tkinter non trovato; avviare manualmente plot_live.py.')
            return
        plot_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plot_live.py')
        try:
            flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if python_exe.lower().endswith('python.exe') else 0
            self.plot_process = subprocess.Popen([python_exe, plot_script, self.csv_path],
                cwd=os.path.dirname(plot_script), creationflags=flags)
            print('[Monitor] Finestra grafici avviata: sei subplot aggiornati dal CSV.')
        except Exception as exc:
            print(f'[Monitor] Avvio finestra grafici non riuscito: {exc}')

    def report(self):
        delta_ls = self.offset
        tension = self.compute_tension(delta_ls)
        motor_x = MOTOR_REST_X - self.offset
        pos = self.tip.position.value[0]
        print(f"[Motore-molla-tubo] u={self.offset:.2f} mm, xmot={motor_x:.2f} mm | "
              f"k={self.spring_k:.1f} N/mm | T={tension:.3f} N | "
              f"DeltaLs={delta_ls:.2f} mm | punta X={pos[0]:.2f}, Y={pos[1]:.2f} mm")

    def onKeypressedEvent(self, event):
        key = event.get('key', '')
        if key in (Key.uparrow, 'w', 'W'):
            self.direction = 1
            self.plot_phase = 1
            self.offset += MOTOR_STEP
        elif key in (Key.downarrow, 's', 'S'):
            self.direction = -1
            self.plot_phase = -1
            self.offset = max(0.0, self.offset - MOTOR_STEP)
        elif key in ('0', 'z', 'Z'):
            self.offset = 0.0
            self.direction = 0
        else:
            return
        # Ogni pressione cambia il comando motore di un singolo passo da 0.35 mm.
        self.report()

    def compute_tension(self, delta_ls):
        hysteresis = (SPRING_HYSTERESIS + MATERIAL_HYSTERESIS) * self.direction
        # Legge del paper: la tensione dipende dall'allungamento e dall'isteresi;
        # il termine viscoso non viene aggiunto al comando del CableConstraint.
        raw_tension = self.spring_k * delta_ls + hysteresis
        return max(0.0, raw_tension)

    def update_mechanics(self):
        p1 = np.asarray(self.motor.position.value[0][:3], dtype=float)
        p2 = np.asarray(self.anchor.position.value[0][:3], dtype=float)
        delta_ls = max(0.0, float(np.linalg.norm(p2 - p1)) - SPRING_REST)
        self.applied_tension = self.compute_tension(delta_ls)
        self.cable.value.value = [self.applied_tension]
        self.fem_ff.youngModulus.value = [E_LOAD_GPA * 1000.0 if self.direction >= 0
                                           else E_UNLOAD_GPA * 1000.0]
        self.update_hook()

    def onAnimateBeginEvent(self, event):
        self.dt = float(event.get('dt', 0.01))
        # Mantiene il carrello sulla posizione comandata anche durante la
        # dinamica, senza lasciare che la forza della molla lo trascini.
        self.move_motor()
        self.update_mechanics()
        self.update_spring_points()

    def onAnimateEndEvent(self, event):
        self.update_hook()
        self.update_spring_points()
        self.simulation_time += float(event.get('dt', getattr(self, 'dt', 0.01)))
        self.log_sample()

    def onSimulationEndEvent(self, event):
        if getattr(self, 'csv_file', None) and not self.csv_file.closed:
            self.csv_file.flush()
            self.csv_file.close()


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
        'Sofa.Component.AnimationLoop', 'Sofa.Component.Collision.Geometry',
        'Sofa.Component.Constraint.Lagrangian.Correction',
        'Sofa.Component.Constraint.Lagrangian.Solver',
        'Sofa.Component.Constraint.Projective', 'Sofa.Component.IO.Mesh',
        'Sofa.Component.Engine.Select',
        'Sofa.Component.LinearSolver.Direct',
        'Sofa.Component.LinearSolver.Iterative', 'Sofa.Component.Mapping.Linear',
        'Sofa.Component.Mapping.NonLinear', 'Sofa.Component.Mass', 'Sofa.Component.ODESolver.Backward',
        'Sofa.Component.SolidMechanics.FEM.Elastic', 'Sofa.Component.SolidMechanics.Spring',
        'Sofa.Component.StateContainer', 'Sofa.Component.Topology.Container.Constant',
        'Sofa.Component.Topology.Container.Dynamic',
        'Sofa.Component.Visual', 'Sofa.GL.Component.Rendering3D', 'Sofa.GL.Component.Shader',
        'SoftRobots', 'STLIB'])
    root.addObject('FreeMotionAnimationLoop')
    root.addObject('BlockGaussSeidelConstraintSolver', maxIterations=20, tolerance=1e-3)
    root.addObject('VisualStyle', displayFlags='showVisualModels showBehaviorModels')
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
    motor_vis.addObject('MeshOBJLoader', name='loader', filename=os.path.join(MESH_DIR, 'sphere.obj'),
        scale3d=[MOTOR_SPHERE_RADIUS] * 3)
    motor_vis.addObject('OglModel', name='visualModel', src='@loader', color=[0.62, 0.20, 0.82, 1.0])
    motor_vis.addObject('RigidMapping')

    anchor_node = root.addChild('TendonAnchor')
    anchor = anchor_node.addObject('MechanicalObject', name='anchorDOF', template='Rigid3d',
        position=[[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]])
    anchor_node.addObject('FixedProjectiveConstraint', indices=[0])
    motor_spring = root.addObject('SpringForceField', name='motorSpring', object1='@Motor/motorDOF',
        object2='@TendonAnchor/anchorDOF', spring=[0, 0, SPRING_K, SPRING_DAMPING, SPRING_REST])
    add_surface(anchor_node, 'TendonAlongShaft', 'tendon_shaft.obj', [0.95, 0.24, 0.20, 1.0])

    # Struttura d'esempio 4: prefab STLIB, mesh tetraedrica, solver iterativo,
    # TetrahedronFEMForceField e superficie visuale/collisione mappate sul volume.
    volume_path = os.path.join(MESH_DIR, 'tube_tetra.vtu')
    surface_path = os.path.join(MESH_DIR, 'tube_surface.obj')
    tube = ElasticMaterialObject(name='FlexibleTubeFEM', volumeMeshFileName=volume_path,
        surfaceMeshFileName=surface_path, collisionMesh=surface_path,
        poissonRatio=POISSON_RATIO, youngModulus=E_LOAD_GPA * 1000.0,
        totalMass=0.76, surfaceColor=[0.12, 0.69, 0.82, 1.0],
        solverName='iterative', withConstrain=True)
    root.addChild(tube)
    tube.addObject('EulerImplicitSolver', name='odesolver', rayleighStiffness=0.02, rayleighMass=0.02)
    # Il solver diretto fornisce a LinearSolverConstraintCorrection la compliance
    # FEM reale, necessaria per trasformare la forza del CableConstraint in flessione.
    tube.addObject('SparseLDLSolver', name='linearsolver',
        template='CompressedRowSparseMatrixMat3x3d')
    FixedBox(applyTo=tube, atPositions=[-0.1, -1.1, -1.1, RIGID_LENGTH + 0.1, 1.1, 1.1],
             name='FixedRigidShaft', doVisualization=False)

    # Tendine guidato sul lato +Y con punti di passaggio lungo il FEM. I punti
    # trasferiscono reazioni distribuite al tubo, evitando una trazione quasi
    # assiale concentrata solo sulla punta. Il primo è oltre l'incastro a x=20.
    # Il cavo meccanico è trasferito alla parete interna della mesh (r=ID/2);
    # il suo asse nominale resta a yt=+0.6 mm dentro il lume.
    cable_guide_y = INNER_DIAMETER / 2.0
    cable_points = [[x, cable_guide_y, 0.0] for x in (30.0, 45.0, 60.0, TUBE_LENGTH)]
    cable_node = tube.addChild('TendonCable')
    cable_node.addObject('MechanicalObject', name='cablePoint', template='Vec3',
        position=cable_points)
    cable = cable_node.addObject('CableConstraint', name='tendon',
        indices=list(range(len(cable_points))),
        pullPoint=[RIGID_LENGTH, TENDON_OFFSET, 0.0], valueType='force', value=[0.0],
        minForce=0.0, color=[0.95, 0.24, 0.20, 1.0])
    cable_node.addObject('BarycentricMapping', name='cableMapping')

    cable_visual_node = tube.addChild('TendonVisualGuide')
    cable_visual_node.addObject('EdgeSetTopologyContainer', name='topology',
        edges=[[i, i + 1] for i in range(len(cable_points) - 1)])
    cable_visual_node.addObject('MechanicalObject', name='tendonGuide', template='Vec3',
        position=cable_points, showObject=True, showObjectScale=1.4,
        showColor=[0.95, 0.24, 0.20, 1.0])
    cable_visual_node.addObject('BarycentricMapping', name='visualMapping')

    distal = root.addChild('TubeDistalTip')
    tip = distal.addObject('MechanicalObject', name='tipDOF', template='Rigid3d',
        position=[[TUBE_LENGTH, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]])
    distal.addObject('UniformMass', totalMass=1e-9)

    spring_points = helix([MOTOR_REST_X, 0.0, 0.0], [0.0, 0.0, 0.0])
    spring_node = root.addChild('VisualSpringPoints')
    spring_node.addObject('EdgeSetTopologyContainer', name='springPointsTopology',
        edges=[[i, i + 1] for i in range(len(spring_points) - 1)])
    spring_visual = spring_node.addObject('MechanicalObject', name='springPoints', template='Vec3d',
        position=spring_points, showObject=False)
    spring_wire = spring_node.addChild('ContinuousSpringWire')
    spring_wire.addObject('OglModel', name='springWireModel', src='@../springPointsTopology',
        lineWidth=5.5, color=[0.62, 0.20, 0.82, 1.0])
    spring_wire.addObject('IdentityMapping')

    # L'indice viene tenuto per riferimento: la posizione marker segue la mesh deformata.
    nodes_per_ring = (TUBE_RADIAL_CELLS + 1) * TUBE_CIRCUMFERENTIAL_CELLS
    centerline_nodes = [list(range(i * nodes_per_ring, (i + 1) * nodes_per_ring))
                        for i in range(TUBE_AXIAL_CELLS + 1)]
    controller = HookSceneController(name='hookController', motor=motor, motorVisual=motor_visual,
        anchor=anchor, tip=tip, springVisual=spring_visual, tube=tube, cable=cable,
        springFF=motor_spring,
        centerlineNodes=centerline_nodes)
    root.addObject(controller)
    controller.move_motor()
    controller.update_hook()
    controller.launch_plot_window()

    print(f"Tubo FEM tetraedrico: {RIGID_LENGTH:.0f} mm rigidi + {FLEX_LENGTH:.0f} mm flessibili; "
          f"OD/parete/ID={OUTER_DIAMETER:.2f}/{WALL_THICKNESS:.2f}/{INNER_DIAMETER:.2f} mm")
    print(f"Lunghezza totale a riposo: {SPRING_REST:.0f} mm molla + {RIGID_LENGTH:.0f} mm albero + "
          f"{FLEX_LENGTH:.0f} mm flessibili = {SPRING_REST + RIGID_LENGTH + FLEX_LENGTH:.0f} mm")
    print(f"Nitinol: E carico/scarico={E_LOAD_GPA:.0f}/{E_UNLOAD_GPA:.0f} GPa, nu={POISSON_RATIO:.2f}; "
          f"molla k={SPRING_K:.1f} N/mm fisso; CableConstraint in forza, percorso guidato +Y, "
          f"offset nominale +{TENDON_OFFSET:.1f} mm")
    print("Controllo manuale senza limite superiore su T o sull'allungamento della molla.")
    print("Controllo manuale: freccia su carica; freccia giu scarica; 0 reset.")
    print("Grafici in finestra separata; CSV per passo: " + os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                                       'dati_simulazione.csv'))
    return root
