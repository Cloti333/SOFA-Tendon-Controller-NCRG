"""Finestra separata per il ciclo di isteresi live DeltaY-u."""
import csv
import os
import sys
import tkinter as tk
from collections import deque


POLL_MS = 500
COLORS = {
    'window': '#11161d',
    'panel': '#1a222c',
    'border': '#303b49',
    'text': '#e6edf3',
    'muted': '#9aa9b8',
    'grid': '#2d3947',
    'axis': '#718096',
    'load': '#62b0ff',
    'unload': '#ff4d9d',
    'difference': '#ffd166',
}


def read_segments(csv_path):
    """Legge tutto il log e conserva le ultime tratte continue di carico/scarico."""
    if not os.path.isfile(csv_path):
        return []

    segments = deque(maxlen=4)
    current_phase = None
    current_points = []
    last_u = None
    try:
        with open(csv_path, 'r', newline='', encoding='utf-8') as data_file:
            for row in csv.DictReader(data_file):
                try:
                    u = float(row['u_mm'])
                    delta_y = float(row['DeltaY_punta_mm'])
                    phase_value = row.get('fase_traiettoria',
                                           row.get('comando_attivo', row.get('direzione', 1)))
                    phase = 1 if float(phase_value or 1) >= 0 else -1
                except (KeyError, TypeError, ValueError):
                    continue

                if phase != current_phase:
                    if current_points:
                        segments.append((current_phase, current_points))
                    current_phase = phase
                    current_points = []
                    last_u = None

                # Ogni posizione del motore compare in molti passi SOFA: si tiene
                # l'ultimo campione a quel valore di u, riducendo il rumore live.
                if last_u == u and current_points:
                    current_points[-1] = (u, delta_y)
                else:
                    current_points.append((u, delta_y))
                    last_u = u
        if current_points:
            segments.append((current_phase, current_points))
    except (OSError, csv.Error):
        return []
    return list(segments)


def read_xy(csv_path):
    """Carica gli ultimi punti della traiettoria della punta nel piano X-Y."""
    points = deque(maxlen=1600)
    try:
        with open(csv_path, 'r', newline='', encoding='utf-8') as data_file:
            for row in csv.DictReader(data_file):
                try:
                    x = float(row['X_punta_mm'])
                    y = float(row['Y_punta_mm'])
                    phase_value = row.get('fase_traiettoria',
                                           row.get('comando_attivo', row.get('direzione', 1)))
                    phase = 1 if float(phase_value or 1) >= 0 else -1
                    points.append((x, y, phase))
                except (KeyError, TypeError, ValueError):
                    continue
    except (OSError, csv.Error):
        return []
    return list(points)


def interpolate(points, x):
    """Interpola linearmente punti ordinati per u; x deve essere nel dominio."""
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            if x1 == x0:
                return y1
            ratio = (x - x0) / (x1 - x0)
            return y0 + ratio * (y1 - y0)
    return points[-1][1]


def latest_cycle(segments):
    """Restituisce l'ultima coppia consecutiva carico-scarico e il valore H."""
    pair = next(((segments[index - 1][1], segments[index][1])
                 for index in range(len(segments) - 1, 0, -1)
                 if segments[index - 1][0] == 1 and segments[index][0] == -1), None)
    if pair is None:
        return None
    load_segment, unload_segment = pair

    # L'interpolazione richiede u crescente; l'ordine temporale dei rami resta
    # visibile perché il viewer disegna ogni ramo come una curva distinta.
    load = sorted({u: y for u, y in load_segment}.items())
    unload = sorted({u: y for u, y in unload_segment}.items())
    if len(load) < 2 or len(unload) < 2:
        return {'load': load, 'unload': unload, 'h': None, 'gap': None,
                'delta_y_max': max((abs(y) for _, y in load + unload), default=0.0)}

    common_min = max(load[0][0], unload[0][0])
    common_max = min(load[-1][0], unload[-1][0])
    if common_max <= common_min:
        return {'load': load, 'unload': unload, 'h': None, 'gap': None,
                'delta_y_max': max((abs(y) for _, y in load + unload), default=0.0)}

    u_values = sorted({common_min, common_max} |
                      {u for u, _ in load if common_min <= u <= common_max} |
                      {u for u, _ in unload if common_min <= u <= common_max})
    delta_y_max = max((abs(y) for _, y in load + unload), default=0.0)
    differences = [(abs(interpolate(load, u) - interpolate(unload, u)), u)
                   for u in u_values]
    max_difference, max_u = max(differences, default=(0.0, common_min))
    h_value = 100.0 * max_difference / delta_y_max if delta_y_max > 0 else None
    return {'load': load, 'unload': unload, 'h': h_value,
            'gap': (max_u, max_difference), 'delta_y_max': delta_y_max}


class HysteresisWindow:
    def __init__(self, csv_path):
        self.csv_path = csv_path
        self.root = tk.Tk()
        self.root.title('SOFA - Traiettoria punta e ciclo di isteresi')
        self.root.geometry('900x850')
        self.root.minsize(650, 650)
        self.root.configure(bg=COLORS['window'])

        header = tk.Frame(self.root, bg=COLORS['window'])
        header.pack(fill='x', padx=14, pady=(12, 4))
        tk.Label(header, text='Ciclo di isteresi', font=('Segoe UI', 15, 'bold'),
                 bg=COLORS['window'], fg=COLORS['text']).pack(side='left')
        self.metric = tk.Label(header, text='H = in attesa del ciclo',
                               font=('Segoe UI', 10, 'bold'), bg=COLORS['window'],
                               fg=COLORS['muted'])
        self.metric.pack(side='right')

        trajectory_frame = tk.Frame(self.root, bg=COLORS['panel'],
                         highlightbackground=COLORS['border'], highlightthickness=1)
        trajectory_frame.pack(fill='both', expand=True, padx=10, pady=(6, 4))
        self.xy_canvas = tk.Canvas(trajectory_frame, bg=COLORS['panel'], height=270,
                                   highlightthickness=0)
        self.xy_canvas.pack(fill='both', expand=True)
        frame = tk.Frame(self.root, bg=COLORS['panel'],
                         highlightbackground=COLORS['border'], highlightthickness=1)
        frame.pack(fill='both', expand=True, padx=10, pady=(4, 8))
        self.canvas = tk.Canvas(frame, bg=COLORS['panel'], height=390,
                                highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        tk.Label(self.root, text=os.path.basename(csv_path), anchor='w',
                 font=('Segoe UI', 9), bg=COLORS['window'], fg=COLORS['muted']).pack(
                     fill='x', padx=14, pady=(0, 8))
        self.root.after(100, self.refresh)

    @staticmethod
    def draw_trajectory(canvas, points):
        canvas.delete('all')
        width = max(canvas.winfo_width(), 320)
        height = max(canvas.winfo_height(), 200)
        left, right, top, bottom = 68, width - 24, 38, height - 42
        canvas.create_text(12, 10, anchor='nw', text='Traiettoria punta X-Y',
                           font=('Segoe UI', 11, 'bold'), fill=COLORS['text'])
        canvas.create_text((left + right) / 2, height - 14, text='X [mm]',
                           font=('Segoe UI', 9), fill=COLORS['text'])
        canvas.create_text(18, (top + bottom) / 2, text='Y [mm]', angle=90,
                           font=('Segoe UI', 9), fill=COLORS['text'])
        if not points:
            HysteresisWindow.draw_grid(canvas, left, right, top, bottom,
                                       -1.0, 1.0, -1.0, 1.0)
            canvas.create_text((left + right) / 2, (top + bottom) / 2,
                               text='In attesa dei campioni SOFA…',
                               font=('Segoe UI', 10), fill=COLORS['muted'])
            return
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        x_min, x_max = HysteresisWindow.padded_range(min(xs), max(xs))
        y_min, y_max = HysteresisWindow.padded_range(min(ys), max(ys))
        # Mantiene la stessa scala sui due assi, così la geometria non si deforma.
        scale = min((right - left) / (x_max - x_min), (bottom - top) / (y_max - y_min))
        cx, cy = (x_min + x_max) / 2.0, (y_min + y_max) / 2.0
        span_x, span_y = (right - left) / scale, (bottom - top) / scale
        x_min, x_max = cx - span_x / 2.0, cx + span_x / 2.0
        y_min, y_max = cy - span_y / 2.0, cy + span_y / 2.0
        HysteresisWindow.draw_grid(canvas, left, right, top, bottom,
                                   x_min, x_max, y_min, y_max)
        coords = []
        for x, y, _phase in points:
            coords.extend((left + (x - x_min) / (x_max - x_min) * (right - left),
                           bottom - (y - y_min) / (y_max - y_min) * (bottom - top)))
        for index in range(2, len(coords), 2):
            phase = points[index // 2][2]
            canvas.create_line(coords[index - 2], coords[index - 1],
                               coords[index], coords[index + 1],
                               fill=COLORS['load'] if phase >= 0 else COLORS['unload'],
                               width=2)

    @staticmethod
    def padded_range(low, high):
        span = high - low
        pad = max(span * 0.08, 0.05)
        return low - pad, high + pad

    def draw(self, result):
        canvas = self.canvas
        canvas.delete('all')
        width = max(canvas.winfo_width(), 320)
        height = max(canvas.winfo_height(), 240)
        left, right, top, bottom = 68, width - 24, 44, height - 52
        if right <= left or bottom <= top:
            return

        canvas.create_text((left + right) / 2, height - 14, text='u [mm]',
                           font=('Segoe UI', 10), fill=COLORS['text'])
        canvas.create_text(17, (top + bottom) / 2, text='ΔY [mm]', angle=90,
                           font=('Segoe UI', 10), fill=COLORS['text'])

        curves = []
        if result:
            curves = [(result['load'], COLORS['load']),
                      (result['unload'], COLORS['unload'])]
        all_points = [point for points, _color in curves for point in points]
        if not all_points:
            self.draw_grid(canvas, left, right, top, bottom, -1.0, 1.0, -1.0, 1.0)
            canvas.create_text((left + right) / 2, (top + bottom) / 2,
                               text='In attesa dei campioni di carico/scarico…',
                               font=('Segoe UI', 10), fill=COLORS['muted'])
            return

        x_min, x_max = self.padded_range(min(u for u, _ in all_points),
                                         max(u for u, _ in all_points))
        y_min, y_max = self.padded_range(min(y for _, y in all_points),
                                         max(y for _, y in all_points))
        self.draw_grid(canvas, left, right, top, bottom, x_min, x_max, y_min, y_max)

        def xy(point):
            x_value, y_value = point
            px = left + (x_value - x_min) / (x_max - x_min) * (right - left)
            py = bottom - (y_value - y_min) / (y_max - y_min) * (bottom - top)
            return px, py

        for points, color in curves:
            if len(points) >= 2:
                coordinates = [coordinate for point in points for coordinate in xy(point)]
                canvas.create_line(*coordinates, fill=color, width=2, smooth=False)
            elif points:
                px, py = xy(points[0])
                canvas.create_oval(px - 3, py - 3, px + 3, py + 3,
                                   fill=color, outline=color)

        legend_x, legend_y = right - 155, top + 12
        for index, (label, color) in enumerate((('Carico', COLORS['load']),
                                                 ('Scarico', COLORS['unload']))):
            y = legend_y + index * 20
            canvas.create_line(legend_x, y, legend_x + 26, y, fill=color, width=2)
            canvas.create_text(legend_x + 33, y, anchor='w', text=label,
                               font=('Segoe UI', 9), fill=COLORS['text'])

        if result and result['gap']:
            max_u, _max_difference = result['gap']
            px = left + (max_u - x_min) / (x_max - x_min) * (right - left)
            canvas.create_line(px, top, px, bottom, fill=COLORS['difference'],
                               dash=(4, 4), width=1)

    @staticmethod
    def draw_grid(canvas, left, right, top, bottom, x_min, x_max, y_min, y_max):
        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            gx = left + fraction * (right - left)
            gy = bottom - fraction * (bottom - top)
            x_tick = x_min + fraction * (x_max - x_min)
            y_tick = y_min + fraction * (y_max - y_min)
            canvas.create_line(gx, top, gx, bottom, fill=COLORS['grid'])
            canvas.create_line(left, gy, right, gy, fill=COLORS['grid'])
            canvas.create_text(gx, bottom + 13, text=f'{x_tick:.3g}',
                                    font=('Segoe UI', 8), fill=COLORS['muted'])
            canvas.create_text(left - 7, gy, anchor='e', text=f'{y_tick:.3g}',
                                    font=('Segoe UI', 8), fill=COLORS['muted'])
        canvas.create_line(left, top, left, bottom, fill=COLORS['axis'])
        canvas.create_line(left, bottom, right, bottom, fill=COLORS['axis'])

    def refresh(self):
        segments = read_segments(self.csv_path)
        result = latest_cycle(segments)
        self.draw_trajectory(self.xy_canvas, read_xy(self.csv_path))
        self.draw(result)
        if result is None:
            self.metric.configure(text='H = in attesa del ramo di scarico',
                                  fg=COLORS['muted'])
        elif result['h'] is None:
            self.metric.configure(text='H = non calcolabile: intervallo u comune insufficiente',
                                  fg=COLORS['muted'])
        else:
            self.metric.configure(text=f"H = {result['h']:.2f}%  |  ΔYmax = "
                                  f"{result['delta_y_max']:.3g} mm",
                                  fg=COLORS['text'])
        self.root.after(POLL_MS, self.refresh)

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit('Uso: python scripts/plot_hysteresis.py data/dati_simulazione.csv')
    HysteresisWindow(os.path.abspath(sys.argv[1])).run()
