"""Finestra separata con sei grafici aggiornati leggendo il CSV di SOFA."""
import csv
import os
import sys
import tkinter as tk
from collections import deque


SIGNALS = (
    ('X punta', 'X_punta_mm', 'mm', '#62b0ff'),
    ('Y punta', 'Y_punta_mm', 'mm', '#ff7373'),
    ('\u0394Y punta', 'DeltaY_punta_mm', 'mm', '#6fda8c'),
    ('Attuazione motore u', 'u_mm', 'mm', '#c792ea'),
    ('Tensione tendine T', 'T_N', 'N', '#ffad5c'),
    ('\u0394Ls allungamento molla', 'DeltaLs_mm', 'mm', '#55d6d0'),
)
PAPER_LIMITS = {
    'T_N': (10.0, 'limite 10 N'),
    'DeltaLs_mm': (15.0, 'limite 15 mm'),
}
HISTORY_SECONDS = 30.0
POLL_MS = 500
COLORS = {
    'window': '#11161d',
    'panel': '#1a222c',
    'border': '#303b49',
    'text': '#e6edf3',
    'muted': '#9aa9b8',
    'grid': '#2d3947',
    'axis': '#718096',
}


class LivePlotWindow:
    def __init__(self, csv_path):
        self.csv_path = csv_path
        self.root = tk.Tk()
        self.root.title('SOFA - Monitor motore, molla e tubo')
        self.root.geometry('1100x790')
        self.root.minsize(850, 620)
        self.root.configure(bg=COLORS['window'])

        header = tk.Frame(self.root, bg=COLORS['window'])
        header.pack(fill='x', padx=12, pady=(10, 3))
        tk.Label(header, text='Monitor in tempo reale', font=('Segoe UI', 15, 'bold'),
                 bg=COLORS['window'], fg=COLORS['text']).pack(side='left')
        self.status = tk.Label(header, text='In attesa dei campioni SOFA…',
                               font=('Segoe UI', 9), bg=COLORS['window'], fg=COLORS['muted'])
        self.status.pack(side='right')

        grid = tk.Frame(self.root, bg=COLORS['window'])
        grid.pack(fill='both', expand=True, padx=8, pady=8)
        self.canvases = []
        for index, (title, _column, unit, color) in enumerate(SIGNALS):
            frame = tk.Frame(grid, bg=COLORS['panel'], highlightbackground=COLORS['border'],
                             highlightthickness=1)
            frame.grid(row=index // 2, column=index % 2, sticky='nsew', padx=5, pady=5)
            grid.rowconfigure(index // 2, weight=1)
            grid.columnconfigure(index % 2, weight=1)
            canvas = tk.Canvas(frame, bg=COLORS['panel'], height=205, highlightthickness=0)
            canvas.pack(fill='both', expand=True)
            self.canvases.append((canvas, title, unit, color))

        footer = tk.Label(self.root, text=os.path.basename(csv_path), anchor='w',
                          font=('Segoe UI', 9), bg=COLORS['window'], fg=COLORS['muted'])
        footer.pack(fill='x', padx=14, pady=(0, 8))
        self.root.after(100, self.refresh)

    def read_rows(self):
        if not os.path.isfile(self.csv_path):
            return []
        rows = []
        try:
            with open(self.csv_path, 'r', newline='', encoding='utf-8') as data_file:
                for row in csv.DictReader(data_file):
                    try:
                        rows.append({key: float(row[key]) for key in
                                     ('tempo_s',) + tuple(signal[1] for signal in SIGNALS)})
                    except (KeyError, TypeError, ValueError):
                        continue
        except (OSError, csv.Error):
            return []
        if not rows:
            return []
        latest_time = rows[-1]['tempo_s']
        return [row for row in rows if latest_time - row['tempo_s'] <= HISTORY_SECONDS]

    @staticmethod
    def draw_plot(canvas, title, unit, color, rows, column, paper_limit=None):
        canvas.delete('all')
        width = max(canvas.winfo_width(), 300)
        height = max(canvas.winfo_height(), 150)
        left, right, top, bottom = 55, width - 16, 36, height - 30
        if right <= left or bottom <= top:
            return
        canvas.create_text(12, 10, anchor='nw', text=title,
                           font=('Segoe UI', 10, 'bold'), fill=COLORS['text'])
        canvas.create_text(right, 10, anchor='ne', text=unit,
                           font=('Segoe UI', 9), fill=COLORS['muted'])
        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            y = bottom - fraction * (bottom - top)
            canvas.create_line(left, y, right, y, fill=COLORS['grid'])
        canvas.create_line(left, top, left, bottom, fill=COLORS['axis'])
        canvas.create_line(left, bottom, right, bottom, fill=COLORS['axis'])
        if not rows:
            canvas.create_text((left + right) / 2, (top + bottom) / 2,
                               text='In attesa dei dati…', fill=COLORS['muted'])
            return

        times = [row['tempo_s'] for row in rows]
        values = [row[column] for row in rows]
        t_min, t_max = times[0], times[-1]
        if t_max - t_min < 1e-9:
            t_min = max(0.0, t_max - 1.0)
        v_min, v_max = min(values), max(values)
        if v_max - v_min < 1e-9:
            pad = max(abs(v_max) * 0.05, 0.05)
            v_min, v_max = v_min - pad, v_max + pad
        else:
            pad = (v_max - v_min) * 0.08
            v_min, v_max = v_min - pad, v_max + pad

        if paper_limit is not None:
            limit_value, limit_label = paper_limit
            # Mantiene la soglia nel campo visibile anche prima che il segnale la raggiunga.
            v_max = max(v_max, limit_value * 1.05)
            limit_y = bottom - (limit_value - v_min) / (v_max - v_min) * (bottom - top)
            canvas.create_line(left, limit_y, right, limit_y, fill=color, width=1.3,
                               dash=(6, 4))
            canvas.create_text(right - 4, limit_y - 3, anchor='se',
                               text=limit_label, font=('Segoe UI', 8, 'bold'), fill=color)

        points = []
        for time_value, value in zip(times, values):
            px = left + (time_value - t_min) / (t_max - t_min) * (right - left)
            py = bottom - (value - v_min) / (v_max - v_min) * (bottom - top)
            points.extend((px, py))
        if len(points) >= 4:
            canvas.create_line(*points, fill=color, width=2, smooth=False)
        elif points:
            canvas.create_oval(points[0] - 2, points[1] - 2,
                               points[0] + 2, points[1] + 2, fill=color, outline=color)
        canvas.create_text(left - 5, top, anchor='ne', text=f'{max(values):.3g}',
                           font=('Segoe UI', 8), fill=COLORS['muted'])
        canvas.create_text(left - 5, bottom, anchor='se', text=f'{min(values):.3g}',
                           font=('Segoe UI', 8), fill=COLORS['muted'])
        canvas.create_text(left, height - 5, anchor='sw', text=f'{t_min:.1f} s',
                           font=('Segoe UI', 8), fill=COLORS['muted'])
        canvas.create_text(right, height - 5, anchor='se', text=f'{t_max:.1f} s',
                           font=('Segoe UI', 8), fill=COLORS['muted'])

    def refresh(self):
        rows = self.read_rows()
        for canvas, title, unit, color in self.canvases:
            signal = next(item for item in SIGNALS if item[0] == title)
            self.draw_plot(canvas, title, unit, color, rows, signal[1],
                           PAPER_LIMITS.get(signal[1]))
        if rows:
            self.status.configure(text=f"t = {rows[-1]['tempo_s']:.2f} s  |  ultimo aggiornamento live")
        else:
            self.status.configure(text='In attesa dei campioni SOFA…')
        self.root.after(POLL_MS, self.refresh)

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit('Uso: python plot_live.py percorso\dati_simulazione.csv')
    LivePlotWindow(os.path.abspath(sys.argv[1])).run()
