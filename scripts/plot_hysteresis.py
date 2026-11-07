"""Finestra separata per il ciclo di isteresi live DeltaY-u."""
import csv
import os
import sys
import tkinter as tk
from collections import deque


POLL_MS = 500
BASELINE_K_N_PER_MM = 50.0
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
    current_k = None
    current_points = []
    last_u = None
    try:
        with open(csv_path, 'r', newline='', encoding='utf-8') as data_file:
            for row in csv.DictReader(data_file):
                try:
                    u = float(row['u_mm'])
                    delta_y = float(row['DeltaY_punta_mm'])
                    actuation_k = float(row['k_N_per_mm'])
                    phase_value = row.get('fase_traiettoria',
                                           row.get('comando_attivo', row.get('direzione', 1)))
                    phase = 1 if float(phase_value or 1) >= 0 else -1
                except (KeyError, TypeError, ValueError):
                    continue

                if phase != current_phase or actuation_k != current_k:
                    if current_points:
                        segments.append((current_phase, current_k, current_points))
                    current_phase = phase
                    current_k = actuation_k
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
            segments.append((current_phase, current_k, current_points))
    except (OSError, csv.Error):
        return []
    return list(segments)


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
    pair = next(((segments[index - 1], segments[index])
                 for index in range(len(segments) - 1, 0, -1)
                 if segments[index - 1][0] == 1 and segments[index][0] == -1
                 and segments[index - 1][1] == segments[index][1]), None)
    if pair is None:
        return None
    load_data, unload_data = pair
    _load_phase, actuation_k, load_segment = load_data
    _unload_phase, _unload_k, unload_segment = unload_data

    # L'interpolazione richiede u crescente; l'ordine temporale dei rami resta
    # visibile perché il viewer disegna ogni ramo come una curva distinta.
    load = sorted({u: y for u, y in load_segment}.items())
    unload = sorted({u: y for u, y in unload_segment}.items())
    if len(load) < 2 or len(unload) < 2:
        return {'load': load, 'unload': unload, 'h': None, 'gap': None,
                'delta_y_max': max((abs(y) for _, y in load + unload), default=0.0),
                'k': actuation_k}

    common_min = max(load[0][0], unload[0][0])
    common_max = min(load[-1][0], unload[-1][0])
    if common_max <= common_min:
        return {'load': load, 'unload': unload, 'h': None, 'gap': None,
                'delta_y_max': max((abs(y) for _, y in load + unload), default=0.0),
                'k': actuation_k}

    u_values = sorted({common_min, common_max} |
                      {u for u, _ in load if common_min <= u <= common_max} |
                      {u for u, _ in unload if common_min <= u <= common_max})
    delta_y_max = max((abs(y) for _, y in load + unload), default=0.0)
    differences = [(abs(interpolate(load, u) - interpolate(unload, u)), u)
                   for u in u_values]
    max_difference, max_u = max(differences, default=(0.0, common_min))
    h_value = 100.0 * max_difference / delta_y_max if delta_y_max > 0 else None
    return {'load': load, 'unload': unload, 'h': h_value,
            'gap': (max_u, max_difference), 'delta_y_max': delta_y_max,
            'k': actuation_k}


class HysteresisWindow:
    def __init__(self, csv_path):
        self.csv_path = csv_path
        self.root = tk.Tk()
        self.root.title('SOFA - Ciclo di isteresi DeltaY-u')
        self.root.geometry('820x620')
        self.root.minsize(600, 450)
        self.root.configure(bg=COLORS['window'])

        header = tk.Frame(self.root, bg=COLORS['window'])
        header.pack(fill='x', padx=14, pady=(12, 4))
        tk.Label(header, text='Ciclo di isteresi', font=('Segoe UI', 15, 'bold'),
                 bg=COLORS['window'], fg=COLORS['text']).pack(side='left')
        self.metric = tk.Label(header, text='H = in attesa del ciclo',
                               font=('Segoe UI', 10, 'bold'), bg=COLORS['window'],
                               fg=COLORS['muted'])
        self.metric.pack(side='right')

        frame = tk.Frame(self.root, bg=COLORS['panel'],
                         highlightbackground=COLORS['border'], highlightthickness=1)
        frame.pack(fill='both', expand=True, padx=10, pady=8)
        self.canvas = tk.Canvas(frame, bg=COLORS['panel'], highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        tk.Label(self.root, text=os.path.basename(csv_path), anchor='w',
                 font=('Segoe UI', 9), bg=COLORS['window'], fg=COLORS['muted']).pack(
                     fill='x', padx=14, pady=(0, 8))
        self.root.after(100, self.refresh)

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
            self.draw_grid(left, right, top, bottom, -1.0, 1.0, -1.0, 1.0)
            canvas.create_text((left + right) / 2, (top + bottom) / 2,
                               text='In attesa dei campioni di carico/scarico…',
                               font=('Segoe UI', 10), fill=COLORS['muted'])
            return

        x_min, x_max = self.padded_range(min(u for u, _ in all_points),
                                         max(u for u, _ in all_points))
        y_min, y_max = self.padded_range(min(y for _, y in all_points),
                                         max(y for _, y in all_points))
        self.draw_grid(left, right, top, bottom, x_min, x_max, y_min, y_max)

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

    def draw_grid(self, left, right, top, bottom, x_min, x_max, y_min, y_max):
        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            gx = left + fraction * (right - left)
            gy = bottom - fraction * (bottom - top)
            x_tick = x_min + fraction * (x_max - x_min)
            y_tick = y_min + fraction * (y_max - y_min)
            self.canvas.create_line(gx, top, gx, bottom, fill=COLORS['grid'])
            self.canvas.create_line(left, gy, right, gy, fill=COLORS['grid'])
            self.canvas.create_text(gx, bottom + 13, text=f'{x_tick:.3g}',
                                    font=('Segoe UI', 8), fill=COLORS['muted'])
            self.canvas.create_text(left - 7, gy, anchor='e', text=f'{y_tick:.3g}',
                                    font=('Segoe UI', 8), fill=COLORS['muted'])
        self.canvas.create_line(left, top, left, bottom, fill=COLORS['axis'])
        self.canvas.create_line(left, bottom, right, bottom, fill=COLORS['axis'])

    def refresh(self):
        segments = read_segments(self.csv_path)
        result = latest_cycle(segments)
        self.draw(result)
        k_now = result['k'] if result else (segments[-1][1] if segments else None)
        k_label = (f'k = {k_now:g} N/mm' if k_now is not None else 'k non disponibile')
        baseline_label = ('' if k_now is not None and
                          abs(k_now - BASELINE_K_N_PER_MM) <= 1e-9
                          else f' (baseline: k = {BASELINE_K_N_PER_MM:g})')
        if result is None:
            self.metric.configure(text=f'H = in attesa del ciclo  |  {k_label}{baseline_label}',
                                  fg=COLORS['muted'])
        elif result['h'] is None:
            self.metric.configure(
                text=f'H = non calcolabile: intervallo u comune insufficiente  |  '
                     f'{k_label}{baseline_label}', fg=COLORS['muted'])
        else:
            self.metric.configure(text=f"H = {result['h']:.2f}%  |  ΔYmax = "
                                  f"{result['delta_y_max']:.3g} mm  |  "
                                  f"{k_label}{baseline_label}",
                                  fg=(COLORS['text'] if not baseline_label else
                                      COLORS['difference']))
        self.root.after(POLL_MS, self.refresh)

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit('Uso: python scripts/plot_hysteresis.py data/dati_simulazione.csv')
    HysteresisWindow(os.path.abspath(sys.argv[1])).run()
