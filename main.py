import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
from datetime import datetime, timedelta
from itertools import cycle

class WorkScheduler:
    SHIFT_TYPES = [
        "Day Shift (09-21)",
        "Day Shift (12-24)",
        "Night Shift (21-09)",
        "Developer Shift (09-18)",
        "Daily Work Day (09-18)",
        "Rest",
    ]
    PATTERN = [2, 2]  # 2 work days, 2 rest days
    SHIFT_HOURS = {
        "Day Shift (09-21)": "09:00-21:00",
        "Day Shift (12-24)": "12:00-24:00",
        "Night Shift (21-09)": "21:00-09:00",
        "Developer Shift (09-18)": "09:00-18:00",
        "Daily Work Day (09-18)": "09:00-18:00",
        "Rest": ""
    }
    
    def __init__(self):
        self.colleagues = []
        self.schedule = {}
        # per-colleague metadata: default, offset, can_fill
        self.meta = {}
        
    def add_colleague(self, name, default_shift=None, offset=0, can_fill=False):
        if name and name not in self.colleagues:
            self.colleagues.append(name)
            if default_shift and default_shift in self.SHIFT_TYPES:
                default = default_shift
            else:
                default = self.SHIFT_TYPES[0]
            self.meta[name] = {"default": default, "offset": int(offset), "can_fill": bool(can_fill)}
            
    def generate_schedule(self, start_date, num_weeks=1):
        # Generate base schedule per colleague using pattern + offset
        self.schedule = {}

        # boolean pattern for work/rest days (e.g. [True, True, False, False])
        pattern_bool = []
        for i, count in enumerate(self.PATTERN):
            pattern_bool.extend([i % 2 == 0] * count)

        for colleague in self.colleagues:
            colleague_schedule = []
            default_shift = self.meta.get(colleague, {}).get("default", self.SHIFT_TYPES[0])
            offset = int(self.meta.get(colleague, {}).get("offset", 0))

            pattern_cycle = cycle(pattern_bool)
            for _ in range(offset % len(pattern_bool)):
                next(pattern_cycle)

            current_date = start_date
            for _ in range(num_weeks * 7):
                is_work = next(pattern_cycle)
                date_str = current_date.strftime("%Y-%m-%d")

                if is_work:
                    # weekday-only shifts should not be scheduled on weekends
                    if default_shift in ("Daily Work Day (09-18)", "Developer Shift (09-18)") and current_date.weekday() >= 5:
                        shift = "Rest"
                    else:
                        shift = default_shift
                else:
                    shift = "Rest"

                colleague_schedule.append({"date": date_str, "shift": shift})
                current_date += timedelta(days=1)

            self.schedule[colleague] = colleague_schedule

        # Post-process to enforce staffing constraints and balance hours
        hours_map = self.compute_hours_for_period(start_date, num_weeks)
        days = num_weeks * 7

        for day_idx in range(days):
            date_obj = start_date + timedelta(days=day_idx)
            weekday = date_obj.weekday()

            def count_shift_types():
                counts = {k: 0 for k in self.SHIFT_TYPES}
                for c in self.colleagues:
                    sched = self.schedule.get(c, [])
                    if day_idx < len(sched):
                        s = sched[day_idx].get('shift', '')
                        if s in counts:
                            counts[s] += 1
                return counts

            counts = count_shift_types()

            def find_candidate(preferred_defaults=None, require_can_fill=False):
                candidates = []
                for c in self.colleagues:
                    sched = self.schedule.get(c, [])
                    if day_idx < len(sched) and sched[day_idx]['shift'] == 'Rest':
                        meta = self.meta.get(c, {})
                        default = meta.get('default', '')
                        can_fill = meta.get('can_fill', False)
                        if preferred_defaults:
                            prefs = list(preferred_defaults) if not isinstance(preferred_defaults, (list, tuple, set)) else preferred_defaults
                            if default not in prefs:
                                continue
                        if require_can_fill and not can_fill:
                            continue
                        candidates.append(c)
                if not candidates:
                    return None
                candidates.sort(key=lambda x: hours_map.get(x, 0.0))
                return candidates[0]

            # Ensure at least one night shift exists
            if counts.get("Night Shift (21-09)", 0) == 0:
                cand = find_candidate(preferred_defaults=("Night Shift (21-09)",))
                if not cand:
                    cand = find_candidate()
                if cand:
                    self.schedule[cand][day_idx]['shift'] = 'Night Shift (21-09)'
                    hours_map[cand] = hours_map.get(cand, 0.0) + self._duration_hours('Night Shift (21-09)')

            if weekday < 5:
                # Weekday: ensure one Daily/Developer and one Day Shift
                daily_count = counts.get('Daily Work Day (09-18)', 0) + counts.get('Developer Shift (09-18)', 0)
                if daily_count == 0:
                    cand = find_candidate(require_can_fill=True)
                    if not cand:
                        cand = find_candidate(preferred_defaults=("Daily Work Day (09-18)", "Developer Shift (09-18)"))
                    if not cand:
                        cand = find_candidate()
                    if cand:
                        default = self.meta.get(cand, {}).get('default', 'Daily Work Day (09-18)')
                        self.schedule[cand][day_idx]['shift'] = default
                        hours_map[cand] = hours_map.get(cand, 0.0) + self._duration_hours(default)

                day_count = sum(counts.get(k, 0) for k in self.SHIFT_TYPES if k.startswith('Day Shift'))
                if day_count == 0:
                    prefs = [s for s in self.SHIFT_TYPES if s.startswith('Day Shift')]
                    cand = find_candidate(preferred_defaults=prefs)
                    if not cand:
                        cand = find_candidate()
                    if cand:
                        default = self.meta.get(cand, {}).get('default', 'Day Shift (09-21)')
                        if not default.startswith('Day Shift'):
                            default = 'Day Shift (09-21)'
                        self.schedule[cand][day_idx]['shift'] = default
                        hours_map[cand] = hours_map.get(cand, 0.0) + self._duration_hours(default)

            else:
                # Weekend: ensure two Day Shifts
                day_count = sum(counts.get(k, 0) for k in self.SHIFT_TYPES if k.startswith('Day Shift'))
                while day_count < 2:
                    cand = find_candidate(require_can_fill=True)
                    if not cand:
                        cand = find_candidate(preferred_defaults=[s for s in self.SHIFT_TYPES if s.startswith('Day Shift')])
                    if not cand:
                        cand = find_candidate()
                    if not cand:
                        break
                    default = self.meta.get(cand, {}).get('default', 'Day Shift (09-21)')
                    if not default.startswith('Day Shift'):
                        default = 'Day Shift (09-21)'
                    self.schedule[cand][day_idx]['shift'] = default
                    hours_map[cand] = hours_map.get(cand, 0.0) + self._duration_hours(default)
                    day_count += 1

    def compute_hours_for_period(self, start_date: datetime, num_weeks: int) -> dict:
        """Compute assigned hours per colleague for period starting at start_date for num_weeks weeks."""
        days = num_weeks * 7
        hours = {c: 0.0 for c in self.colleagues}
        for c in self.colleagues:
            sched = self.schedule.get(c, [])
            for d in range(days):
                date_str = (start_date + timedelta(days=d)).strftime("%Y-%m-%d")
                entry = next((e for e in sched if e.get('date') == date_str), None)
                if entry:
                    shift = entry.get('shift', '')
                    hours[c] += self._duration_hours(shift)
        return hours


class SchedulerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Work Day Scheduler")
        self.root.geometry("1200x650")
        
        self.scheduler = WorkScheduler()
        self.current_date = datetime.now()
        # view controls
        self.view_start_date = self.current_date
        self.weeks_view = 2
        
        self.setup_ui()
        
    def setup_ui(self):
        # Top control panel
        control_frame = ttk.Frame(self.root)
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(control_frame, text="Colleague Name:").pack(side=tk.LEFT, padx=5)
        self.colleague_entry = ttk.Entry(control_frame, width=20)
        self.colleague_entry.pack(side=tk.LEFT, padx=5)

        ttk.Label(control_frame, text="Default Shift:").pack(side=tk.LEFT, padx=5)
        self.default_shift_combo = ttk.Combobox(control_frame, values=self.scheduler.SHIFT_TYPES, width=25)
        self.default_shift_combo.set(self.scheduler.SHIFT_TYPES[0])
        self.default_shift_combo.pack(side=tk.LEFT, padx=5)

        ttk.Label(control_frame, text="Offset:").pack(side=tk.LEFT, padx=5)
        self.offset_spin = tk.Spinbox(control_frame, from_=0, to=6, width=3)
        self.offset_spin.pack(side=tk.LEFT, padx=5)

        self.can_fill_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(control_frame, text="Can Fill Day", variable=self.can_fill_var).pack(side=tk.LEFT, padx=5)

        ttk.Button(control_frame, text="Add Colleague", command=self.add_colleague).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Remove Selected", command=self.remove_colleague).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Edit Default", command=self.edit_selected_default).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(control_frame, text="Generate Schedule", command=self.generate_schedule).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Save", command=self.save_schedule).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Load", command=self.load_schedule).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Export List", command=self.export_colleagues).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Import List", command=self.import_colleagues).pack(side=tk.LEFT, padx=5)
        
        # view navigation
        ttk.Button(control_frame, text="◀ Prev", command=self.prev_week).pack(side=tk.RIGHT, padx=5)
        ttk.Button(control_frame, text="Next ▶", command=self.next_week).pack(side=tk.RIGHT, padx=5)
        ttk.Label(control_frame, text="Weeks:").pack(side=tk.RIGHT, padx=(5,0))
        self.weeks_spin = tk.Spinbox(control_frame, from_=1, to=4, width=3, command=self.on_weeks_change)
        self.weeks_spin.delete(0, tk.END)
        self.weeks_spin.insert(0, str(self.weeks_view))
        self.weeks_spin.pack(side=tk.RIGHT, padx=5)
        
        # Main content frame with sidebar
        main_content = ttk.Frame(self.root)
        main_content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left sidebar with colleagues list
        sidebar_frame = ttk.LabelFrame(main_content, text="Active Colleagues", width=150)
        sidebar_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 10))
        sidebar_frame.pack_propagate(False)
        
        # Scrollbar for sidebar
        sidebar_scrollbar = ttk.Scrollbar(sidebar_frame)
        sidebar_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.colleagues_listbox = tk.Listbox(sidebar_frame, yscrollcommand=sidebar_scrollbar.set, width=20, height=30)
        self.colleagues_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sidebar_scrollbar.config(command=self.colleagues_listbox.yview)
        
        # Main schedule frame with scrollbar (container)
        schedule_frame = ttk.LabelFrame(main_content, text="Schedule")
        schedule_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree_container = schedule_frame
        # build tree for first time
        self.build_tree()
        # Bind click event for editing (tree is created inside build_tree)
        try:
            self.tree.bind("<Button-1>", self.on_tree_click)
        except Exception:
            pass

    def build_tree(self):
        # clear existing tree if present
        for child in self.tree_container.winfo_children():
            child.destroy()

        days = int(self.weeks_spin.get()) * 7 if hasattr(self, 'weeks_spin') else self.weeks_view * 7
        start = self.view_start_date

        columns = ["Colleague", "Hours"] + [(start + timedelta(days=i)).strftime("%a\n%m/%d") for i in range(days)]

        scrollbar = ttk.Scrollbar(self.tree_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree = ttk.Treeview(self.tree_container, columns=columns, height=20, yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.tree.yview)

        self.tree.column("#0", width=0, stretch=tk.NO)
        self.tree.column("Colleague", anchor=tk.W, width=160)
        self.tree.column("Hours", anchor=tk.CENTER, width=80)

        for col in columns[2:]:
            self.tree.column(col, anchor=tk.CENTER, width=110)

        self.tree.heading("#0", text="", anchor=tk.W)
        self.tree.heading("Colleague", text="Colleague", anchor=tk.W)
        self.tree.heading("Hours", text="Hours", anchor=tk.CENTER)

        for col in columns[2:]:
            self.tree.heading(col, text=col, anchor=tk.CENTER)

        self.tree.pack(fill=tk.BOTH, expand=True)

        # Setup simple tag styles for row coloring by default shift
        style_map = {
            'Day Shift (09-21)': '#ffd7a6',
            'Day Shift (12-24)': '#ffd7a6',
            'Night Shift (21-09)': '#cfe8ff',
            'Developer Shift (09-18)': '#d6f5d6',
            'Daily Work Day (09-18)': '#d6f5d6',
            'Rest': '#f0f0f0'
        }
        for k, color in style_map.items():
            try:
                self.tree.tag_configure(k, background=color)
            except Exception:
                pass

        try:
            self.tree.bind("<Button-1>", self.on_tree_click)
        except Exception:
            pass
        
    def add_colleague(self):
        # Add a colleague from the input fields
        name = self.colleague_entry.get().strip()
        if not name:
            messagebox.showwarning("Input Error", "Please enter a colleague name.")
            return
        default = self.default_shift_combo.get()
        try:
            offset = int(self.offset_spin.get())
        except Exception:
            offset = 0
        can_fill = bool(self.can_fill_var.get())

        self.scheduler.add_colleague(name, default_shift=default, offset=offset, can_fill=can_fill)
        self.refresh_colleagues_listbox()
        self.refresh_schedule_display()

    def edit_selected_default(self):
        selection = self.colleagues_listbox.curselection()
        if not selection:
            messagebox.showwarning("Selection Error", "Please select a colleague to edit.")
            return
        idx = selection[0]
        item = self.colleagues_listbox.get(idx)
        if '  (' in item:
            colleague = item.split('  (', 1)[0]
        else:
            colleague = item

        # dialog to pick default
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edit Default - {colleague}")
        dialog.geometry("320x160")
        ttk.Label(dialog, text=f"Select default shift for {colleague}:").pack(pady=8)
        combo = ttk.Combobox(dialog, values=self.scheduler.SHIFT_TYPES, width=30)
        combo.set(self.scheduler.meta.get(colleague, {}).get('default', self.scheduler.SHIFT_TYPES[0]))
        combo.pack(pady=6)

        ttk.Label(dialog, text="Offset:").pack(pady=4)
        offset_spin = tk.Spinbox(dialog, from_=0, to=6, width=4)
        offset_spin.delete(0, tk.END)
        offset_spin.insert(0, str(self.scheduler.meta.get(colleague, {}).get('offset', 0)))
        offset_spin.pack(pady=2)

        can_fill_var = tk.BooleanVar(value=self.scheduler.meta.get(colleague, {}).get('can_fill', False))
        ttk.Checkbutton(dialog, text="Can Fill Day", variable=can_fill_var).pack(pady=6)

        def save_default():
            val = combo.get()
            if val in self.scheduler.SHIFT_TYPES:
                m = self.scheduler.meta.get(colleague, {})
                m['default'] = val
                try:
                    m['offset'] = int(offset_spin.get())
                except Exception:
                    m['offset'] = 0
                m['can_fill'] = bool(can_fill_var.get())
                self.scheduler.meta[colleague] = m
                self.refresh_colleagues_listbox()
                dialog.destroy()

        ttk.Button(dialog, text="Save", command=save_default).pack(pady=8)

    def remove_colleague(self):
        selection = self.colleagues_listbox.curselection()
        if not selection:
            messagebox.showwarning("Selection Error", "Please select a colleague to remove.")
            return
        idx = selection[0]
        item = self.colleagues_listbox.get(idx)
        colleague = item.split('  (', 1)[0] if '  (' in item else item

        if colleague in self.scheduler.colleagues:
            try:
                self.scheduler.colleagues.remove(colleague)
            except ValueError:
                pass
            self.scheduler.meta.pop(colleague, None)
            self.scheduler.schedule.pop(colleague, None)

        self.refresh_schedule_display()
        self.refresh_colleagues_listbox()
        messagebox.showinfo("Success", f"Colleague '{colleague}' removed successfully!")
            
    def refresh_colleagues_listbox(self):
        self.colleagues_listbox.delete(0, tk.END)
        for colleague in self.scheduler.colleagues:
            m = self.scheduler.meta.get(colleague, {})
            default = m.get('default', '')
            offset = m.get('offset', 0)
            can_fill = m.get('can_fill', False)
            extras = []
            if default:
                extras.append(default)
            if offset:
                extras.append(f"off={offset}")
            if can_fill:
                extras.append("canFill")
            if extras:
                display = f"{colleague}  ({', '.join(extras)})"
            else:
                display = colleague
            self.colleagues_listbox.insert(tk.END, display)
            
    def generate_schedule(self):
        if not self.scheduler.colleagues:
            messagebox.showwarning("Empty List", "Please add colleagues first.")
            return
        self.scheduler.generate_schedule(self.current_date, num_weeks=int(self.weeks_spin.get()) if hasattr(self, 'weeks_spin') else 2)
        self.refresh_schedule_display()
        messagebox.showinfo("Success", "Schedule generated successfully!")
        
    def refresh_schedule_display(self):
        # Rebuild tree (columns) for current view then populate
        self.build_tree()

        # number of days displayed
        days = int(self.weeks_spin.get()) * 7 if hasattr(self, 'weeks_spin') else self.weeks_view * 7
        start = self.view_start_date

        # compute hours per colleague for the displayed window
        hours_map = self.scheduler.compute_hours_for_period(start, int(days / 7))

        # Clear existing items (build_tree already cleared)
        for colleague in self.scheduler.colleagues:
            row_data = [colleague]
            # show hours in Hours column
            h = hours_map.get(colleague, 0)
            row_data.append(f"{h:.1f}h")

            if colleague in self.scheduler.schedule:
                # find entries matching the view window
                sched = self.scheduler.schedule[colleague]
                # compute index of start date in schedule
                # schedule dates are continuous from generation; map by date string
                entries = []
                for d in range(days):
                    date_str = (start + timedelta(days=d)).strftime("%Y-%m-%d")
                    found = next((e for e in sched if e.get('date') == date_str), {"shift": ""})
                    entries.append(found.get('shift', ""))
                row_data.extend(entries)
            else:
                row_data.extend([""] * days)

            default = self.scheduler.meta.get(colleague, {}).get('default', '')
            tags = (default,) if default in self.scheduler.SHIFT_TYPES else ()
            self.tree.insert(parent="", index="end", values=row_data, tags=tags)

        self.refresh_colleagues_listbox()

    def prev_week(self):
        self.view_start_date -= timedelta(weeks=1)
        self.refresh_schedule_display()

    def next_week(self):
        self.view_start_date += timedelta(weeks=1)
        self.refresh_schedule_display()

    def on_weeks_change(self):
        try:
            val = int(self.weeks_spin.get())
            if val < 1:
                val = 1
            if val > 4:
                val = 4
            self.weeks_view = val
        except Exception:
            pass
        self.refresh_schedule_display()
    
    def on_tree_click(self, event):
        """Handle cell click for editing"""
        item = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not item:
            return
        # ignore clicks on the 'Colleague' column (#1)
        # ignore clicks on the 'Colleague' and 'Hours' columns (#1 and #2)
        if col in ('#1', '#2'):
            return
        try:
            # #3 is first date column -> index 0
            col_index = int(col.lstrip('#')) - 3  # 0-based index into schedule list
        except Exception:
            return
        colleague = self.tree.item(item)["values"][0]
        # Open shift selection dialog
        self.show_shift_dialog(colleague, col_index)
    
    def show_shift_dialog(self, colleague, col_index):
        """Show dialog to select shift type"""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edit Shift - {colleague}")
        dialog.geometry("300x200")
        
        ttk.Label(dialog, text=f"Select shift for {colleague}:").pack(pady=10)
        
        shift_var = tk.StringVar()

        # set default to current shift if present
        current_shift = ""
        if colleague in self.scheduler.schedule and col_index < len(self.scheduler.schedule[colleague]):
            current_shift = self.scheduler.schedule[colleague][col_index].get("shift", "")
        if not current_shift:
            current_shift = self.scheduler.SHIFT_TYPES[0]
        shift_var.set(current_shift)

        for shift in self.scheduler.SHIFT_TYPES:
            label = shift
            hours = getattr(self.scheduler, 'SHIFT_HOURS', {}).get(shift, "")
            if hours:
                label = f"{shift} ({hours})"
            ttk.Radiobutton(dialog, text=label, variable=shift_var, value=shift).pack(anchor=tk.W, padx=20)

        def save_shift():
            shift = shift_var.get()
            # ensure schedule list exists and is long enough
            if colleague not in self.scheduler.schedule:
                self.scheduler.schedule[colleague] = []
            sched = self.scheduler.schedule[colleague]
            while len(sched) <= col_index:
                sched.append({"date": "", "shift": ""})
            sched[col_index]["shift"] = shift
            self.refresh_schedule_display()
            dialog.destroy()

        ttk.Button(dialog, text="Save", command=save_shift).pack(pady=10)
    
    def save_schedule(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filename:
            try:
                # ensure meta is saved
                self.scheduler.save_schedule(filename)
                messagebox.showinfo("Success", "Schedule saved successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save schedule: {str(e)}")
    
    def load_schedule(self):
        filename = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filename:
            try:
                self.scheduler.load_schedule(filename)
                self.refresh_schedule_display()
                messagebox.showinfo("Success", "Schedule loaded successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load schedule: {str(e)}")
    
    def export_colleagues(self):
        """Export active colleagues to a text file"""
        if not self.scheduler.colleagues:
            messagebox.showwarning("Empty List", "No colleagues to export.")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'w') as f:
                    for colleague in self.scheduler.colleagues:
                        m = self.scheduler.meta.get(colleague, {})
                        default = m.get('default', '')
                        offset = m.get('offset', 0)
                        can_fill = m.get('can_fill', False)
                        if default or offset or can_fill:
                            f.write(f"{colleague}|{default}|{offset}|{int(bool(can_fill))}\n")
                        else:
                            f.write(colleague + '\n')
                messagebox.showinfo("Success", f"Colleagues exported to {filename} successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export colleagues: {str(e)}")
    
    def import_colleagues(self):
        """Import colleagues from a text file"""
        filename = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'r') as f:
                    raw = [line.strip() for line in f if line.strip()]

                new_colleagues = []
                # support formats:
                # Name
                # Name|DefaultShift
                # Name|DefaultShift|offset|canFill (canFill true/false)
                for line in raw:
                    parts = [p.strip() for p in line.split('|')]
                    name = parts[0] if parts else None
                    default = parts[1] if len(parts) > 1 else None
                    offset = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
                    can_fill = False
                    if len(parts) > 3:
                        can_fill = parts[3].lower() in ('1', 'true', 'yes', 'y')
                    if name and name not in self.scheduler.colleagues:
                        self.scheduler.add_colleague(name, default_shift=default, offset=offset, can_fill=can_fill)
                        new_colleagues.append(name)

                self.refresh_schedule_display()
                self.refresh_colleagues_listbox()
                messagebox.showinfo("Success", f"Imported {len(new_colleagues)} colleagues successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to import colleagues: {str(e)}")


if __name__ == "__main__":
    root = tk.Tk()
    app = SchedulerApp(root)
    root.mainloop()
