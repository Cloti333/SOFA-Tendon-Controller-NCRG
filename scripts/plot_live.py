"""Finestra separata con la traiettoria X-Y e i grafici temporali di SOFA."""
import csv
import os
import sys
import tkinter as tk


CSV_COLUMNS = (
    'tempo_s', 'X_punta_mm', 'Y_punta_mm', 'DeltaY_punta_mm', 'u_mm', 'T_N',
    'DeltaLs_mm', 'fase_traiettoria'
)
PLOTS = (
    ('\u0394Y punta', 'tempo_s', 'DeltaY_punta_mm', 'tempo [s]', '\u0394Y [mm]',
     '#6fda8c', False, ((5.625, 'DYmax 5.625 mm'), (4.5, 'riferimento 80% = 4.5 mm'))),
    ('Attuazione motore u', 'tempo_s', 'u_mm', 'tempo [s]', 'u [mm]',
     '#c792ea', False, ()),
    ('Tensione tendine T', 'tempo_s', 'T_N', 'tempo [s]', 'T [N]',
     '#ffad5c', False, ((10.0, 'Tmax 10 N'),)),
    ('\u0394Ls allungamento molla', 'tempo_s', 'DeltaLs_mm', 'tempo [s]', '\u0394Ls [mm]',
     '#55d6d0', False, ((15.0, '\u0394Ls max 15 mm'),)),
    ('Velocita variazione tensione dT/dt', 'tempo_s', 'dTdt_N_s',
     'tempo [s]', 'dT/dt [N/s]', '#ffd166', False,
     ((5.0, 'limite +5 N/s'), (-5.0, 'limite -5 N/s'))),
)
PLOT_POSITIONS = ((0, 0, 1), (0, 1, 1), (1, 0, 1), (1, 1, 1), (2, 0, 2))
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
        self.root.title('SOFA - Andamento temporale PI')
        self.root.geometry('1100x900')
        self.root.minsize(850, 700)
        self.root.configure(bg=COLORS['window'])

        header = tk.Frame(self.root, bg=COLORS['window'])
        header.pack(fill='x', padx=12, pady=(10, 3))
        tk.Label(header, text='Andamento temporale', font=('Segoe UI', 15, 'bold'),
                 bg=COLORS['window'], fg=COLORS['text']).pack(side='left')
        self.status = tk.Label(header, text='In attesa dei campioni SOFA…',
                               font=('Segoe UI', 9), bg=COLORS['window'], fg=COLORS['muted'])
        self.status.pack(side='right')

        grid = tk.Frame(self.root, bg=COLORS['window'])
        grid.pack(fill='both', expand=True, padx=8, pady=8)
        self.canvases = []
        for index, plot in enumerate(PLOTS):
            title, _x_column, _y_column, _x_label, _y_label, color, _equal_aspect, _limits = plot
            frame = tk.Frame(grid, bg=COLORS['panel'], highlightbackground=COLORS['border'],
                             highlightthickness=1)
            row, column, span = PLOT_POSITIONS[index]
            frame.grid(row=row, column=column, columnspan=span,
                       sticky='nsew', padx=5, pady=5)
            grid.rowconfigure(row, weight=1)
            for grid_column in range(2):
                grid.columnconfigure(grid_column, weight=1)
            canvas = tk.Canvas(frame, bg=COLORS['panel'], height=205, highlightthickness=0)
            canvas.pack(fill='both', expand=True)
            self.canvases.append((canvas, plot))

        footer = tk.Label(self.root, text=os.path.basename(csv_path), anchor='w',
                          font=('Segoe UI', 9), bg=COLORS['window'], fg=COLORS['muted'])
        footer.pack(fill='x', padx=14, pady=(0, 8))
        self.root.after(100, self.refresh)

    def read_rows(self):
        if not os.path.isfile(self.csv_path):
            return []
        rows = []
        previous_time = None
        previous_tension = None
        try:
            with open(self.csv_path, 'r', newline='', encoding='utf-8') as data_file:
                for row in csv.DictReader(data_file):
                    try:
                        sample = {key: float(row[key]) for key in CSV_COLUMNS[:-1]}
                        # CSV precedenti alla fase di carico/scarico restano leggibili.
                        phase = row.get('fase_traiettoria',
                                        row.get('comando_attivo', row.get('direzione', 1)))
                        sample['fase_traiettoria'] = int(float(phase or 1))
                        if previous_time is None or sample['tempo_s'] <= previous_time:
                            sample['dTdt_N_s'] = 0.0
                        else:
                            sample['dTdt_N_s'] = ((sample['T_N'] - previous_tension) /
                                                 (sample['tempo_s'] - previous_time))
                        rows.append(sample)
                        previous_time = sample['tempo_s']
                        previous_tension = sample['T_N']
                    except (KeyError, TypeError, ValueError):
                        continue
        except (OSError, csv.Error):
            return []
        if not rows:
            return []
        latest_time = rows[-1]['tempo_s']
        return [row for row in rows if latest_time - row['tempo_s'] <= HISTORY_SECONDS]

    @staticmethod
    def draw_plot(canvas, plot, rows):
        title, x_column, y_column, x_label, y_label, color, equal_aspect, limits = plot
        canvas.delete('all')
        width = max(canvas.winfo_width(), 300)
        height = max(canvas.winfo_height(), 150)
        left, right, top, bottom = 55, width - 16, 36, height - 30
        if right <= left or bottom <= top:
            return
        canvas.create_text(12, 10, anchor='nw', text=title,
                           font=('Segoe UI', 10, 'bold'), fill=COLORS['text'])
        canvas.create_text(right, 10, anchor='ne', text=f'{x_label} vs {y_label}',
                           font=('Segoe UI', 9), fill=COLORS['muted'])
        if not rows:
            for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
                y = bottom - fraction * (bottom - top)
                canvas.create_line(left, y, right, y, fill=COLORS['grid'])
            canvas.create_text((left + right) / 2, (top + bottom) / 2,
                               text='In attesa dei dati…', fill=COLORS['muted'])
            return

        x_values = [row[x_column] for row in rows]
        y_values = [row[y_column] for row in rows]
        if limits:
            y_values += [value for value, _label in limits]
        x_min, x_max = min(x_values), max(x_values)
        y_min, y_max = min(y_values), max(y_values)

        def padded_range(low, high):
            span = high - low
            pad = max(span * 0.08, 0.05)
            return low - pad, high + pad

        x_min, x_max = padded_range(x_min, x_max)
        y_min, y_max = padded_range(y_min, y_max)
        if equal_aspect:
            center_x = (x_min + x_max) / 2.0
            center_y = (y_min + y_max) / 2.0
            scale = min((right - left) / (x_max - x_min),
                        (bottom - top) / (y_max - y_min))
            visible_x = (right - left) / scale
            visible_y = (bottom - top) / scale
            x_min, x_max = center_x - visible_x / 2.0, center_x + visible_x / 2.0
            y_min, y_max = center_y - visible_y / 2.0, center_y + visible_y / 2.0

        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            gx = left + fraction * (right - left)
            gy = bottom - fraction * (bottom - top)
            canvas.create_line(gx, top, gx, bottom, fill=COLORS['grid'])
            canvas.create_line(left, gy, right, gy, fill=COLORS['grid'])
            x_tick = x_min + fraction * (x_max - x_min)
            y_tick = y_min + fraction * (y_max - y_min)
            canvas.create_text(gx, height - 5, anchor='s', text=f'{x_tick:.3g}',
                               font=('Segoe UI', 8), fill=COLORS['muted'])
            canvas.create_text(left - 5, gy, anchor='e', text=f'{y_tick:.3g}',
                               font=('Segoe UI', 8), fill=COLORS['muted'])
        canvas.create_line(left, top, left, bottom, fill=COLORS['axis'])
        canvas.create_line(left, bottom, right, bottom, fill=COLORS['axis'])

        for value, label in limits:
            line_y = bottom - (value - y_min) / (y_max - y_min) * (bottom - top)
            canvas.create_line(left, line_y, right, line_y, fill='#ff5c64',
                               dash=(1, 3), width=1)
            canvas.create_text(right - 4, line_y - 3, anchor='se', text=label,
                               font=('Segoe UI', 8), fill='#ff777e')

        points = []
        for x_value, y_value in zip(x_values, y_values):
            px = left + (x_value - x_min) / (x_max - x_min) * (right - left)
            py = bottom - (y_value - y_min) / (y_max - y_min) * (bottom - top)
            points.extend((px, py))
        if equal_aspect and len(points) >= 4:
            for index in range(2, len(points), 2):
                phase = rows[index // 2].get('fase_traiettoria', 1)
                segment_color = color if phase >= 0 else '#ff4d9d'
                canvas.create_line(points[index - 2], points[index - 1],
                                   points[index], points[index + 1], fill=segment_color, width=2)
            legend_x, legend_y = right - 155, top + 12
            canvas.create_line(legend_x, legend_y, legend_x + 26, legend_y,
                               fill=color, width=2)
            canvas.create_text(legend_x + 32, legend_y, anchor='w',
                               text='Carico \u2191', font=('Segoe UI', 8),
                               fill=COLORS['text'])
            canvas.create_line(legend_x, legend_y + 18, legend_x + 26, legend_y + 18,
                               fill='#ff4d9d', width=2)
            canvas.create_text(legend_x + 32, legend_y + 18, anchor='w',
                               text='Scarico \u2193', font=('Segoe UI', 8),
                               fill=COLORS['text'])
        elif len(points) >= 4:
            canvas.create_line(*points, fill=color, width=2, smooth=False)
        elif points:
            canvas.create_oval(points[0] - 2, points[1] - 2,
                               points[0] + 2, points[1] + 2, fill=color, outline=color)

    def refresh(self):
        rows = self.read_rows()
        for canvas, plot in self.canvases:
            self.draw_plot(canvas, plot, rows)
        if rows:
            rate = rows[-1].get('dTdt_N_s', 0.0)
            self.status.configure(text=(f"t = {rows[-1]['tempo_s']:.2f} s  |  "
                                        f"dT/dt = {rate:.2f} N/s (limite \u00b15 N/s)  |  "
                                        f"riferimento DY = 4.5 mm (80%)"))
        else:
            self.status.configure(text='In attesa dei campioni SOFA…')
        self.root.after(POLL_MS, self.refresh)

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit('Uso: python scripts/plot_live.py data/dati_simulazione.csv')
    LivePlotWindow(os.path.abspath(sys.argv[1])).run()
