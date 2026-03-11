import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
from datetime import datetime, timedelta
from itertools import cycle
import calendar
import math

class WorkScheduler:
    SHIFT_TYPES = [
        "Day Shift (09-21)",
        "Day Shift (12-24)",
        "Night Shift (21-09)",
        "Daily Work Day (09-18)",
        "Rest",
    ]
    PATTERN = [2, 2]  # 2 work days, 2 rest days
    SHIFT_HOURS = {
        "Day Shift (09-21)": "09:00-21:00",
        "Day Shift (12-24)": "12:00-24:00",
        "Night Shift (21-09)": "21:00-09:00",
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

        # Identify Daily-only and shift workers upfront
        daily_workers_set = set()
        shift_workers_set = set()
        for c in self.colleagues:
            default_shift = self.meta.get(c, {}).get("default", self.SHIFT_TYPES[0])
            if default_shift == "Daily Work Day (09-18)":
                daily_workers_set.add(c)
            elif any(s.startswith('Day Shift') or s.startswith('Night Shift') for s in [default_shift]):
                shift_workers_set.add(c)

        # shift worker rotation: Day x2, Rest x2, Night x2, Rest x2
        shift_cycle_template = ["Day", "Day", "Rest", "Rest", "Night", "Night", "Rest", "Rest"]

        for colleague in self.colleagues:
            colleague_schedule = []
            default_shift = self.meta.get(colleague, {}).get("default", self.SHIFT_TYPES[0])
            offset = int(self.meta.get(colleague, {}).get("offset", 0))

            # Daily workers work only Mon-Fri 09-18, never nights or weekends
            is_daily_only = default_shift in ("Daily Work Day (09-18)",)

            # Determine if this colleague is a rotating shift worker (day/night)
            is_shift_worker = any(s.startswith('Day Shift') or s.startswith('Night Shift') for s in [default_shift])

            if is_shift_worker:
                pattern_cycle = cycle(shift_cycle_template)
                for _ in range(offset % len(shift_cycle_template)):
                    next(pattern_cycle)
            else:
                pattern_cycle = None

            current_date = start_date
            for _ in range(num_weeks * 7):
                date_str = current_date.strftime("%Y-%m-%d")
                weekday = current_date.weekday()

                if is_daily_only:
                    # Daily workers: only Mon-Fri (0-4), always Daily Work Day (09-18) or Rest
                    if weekday < 5:
                        shift = "Daily Work Day (09-18)"
                    else:
                        shift = "Rest"
                elif is_shift_worker and pattern_cycle is not None:
                    elem = next(pattern_cycle)
                    if elem == 'Day':
                        # Day shifts: 09-21 on weekends, 12-24 on weekdays
                        if weekday >= 5:
                            shift = 'Day Shift (09-21)'
                        else:
                            shift = 'Day Shift (12-24)'
                    elif elem == 'Night':
                        shift = 'Night Shift (21-09)'
                    else:
                        shift = 'Rest'
                else:
                    shift = default_shift

                colleague_schedule.append({"date": date_str, "shift": shift})
                current_date += timedelta(days=1)

            self.schedule[colleague] = colleague_schedule

        # Post-process to enforce staffing constraints and balance hours
        # snapshot original generated schedule to prefer preserving planned consecutive blocks
        orig_schedule = {c: [dict(e) for e in self.schedule.get(c, [])] for c in self.colleagues}
        hours_map = self.compute_hours_for_period(start_date, num_weeks)
        days = num_weeks * 7

        for day_idx in range(days):
            # Skip post-processing for this day's Daily workers — lock their schedules
            for daily_c in daily_workers_set:
                if day_idx < len(self.schedule.get(daily_c, [])):
                    weekday = (start_date + timedelta(days=day_idx)).weekday()
                    if weekday < 5:
                        self.schedule[daily_c][day_idx]['shift'] = 'Daily Work Day (09-18)'
                    else:
                        self.schedule[daily_c][day_idx]['shift'] = 'Rest'
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

            def find_candidate(preferred_defaults=None, require_can_fill=False, preferred_next_shift=None, preferred_shift=None):
                """Find a Rest candidate. Prefer those matching preferred_defaults and who have preferred_next_shift the next day.

                Returns the best candidate or None.
                """
                candidates = []
                scored = []
                for c in self.colleagues:
                    sched = self.schedule.get(c, [])
                    if day_idx < len(sched) and sched[day_idx]['shift'] == 'Rest':
                        meta = self.meta.get(c, {})
                        default = meta.get('default', '')
                        can_fill = meta.get('can_fill', False)
                        # Never assign daily workers to night shifts or weekends
                        if default == 'Daily Work Day (09-18)':
                            continue
                        if preferred_defaults:
                            prefs = list(preferred_defaults) if not isinstance(preferred_defaults, (list, tuple, set)) else preferred_defaults
                            if default not in prefs:
                                continue
                        if require_can_fill and not can_fill:
                            continue
                        # check today's and next-day preference using original generated schedule
                        orig_sched = orig_schedule.get(c, [])
                        orig_today = None
                        if day_idx < len(orig_sched):
                            orig_today = orig_sched[day_idx].get('shift')
                        next_shift = None
                        if day_idx + 1 < len(orig_sched):
                            next_shift = orig_sched[day_idx + 1].get('shift')

                        match_today = 1 if (preferred_shift and orig_today == preferred_shift) else 0
                        match_next = 1 if (preferred_next_shift and next_shift == preferred_next_shift) else 0
                        # higher priority: match_today, then match_next, then lower hours
                        scored.append((-match_today, -match_next, hours_map.get(c, 0.0), c))
                if not scored:
                    return None
                scored.sort()
                return scored[0][-1]

            # Enforce night shift: exactly one person, prefer preserving two-night blocks
            night_workers = [c for c in self.colleagues if c not in daily_workers_set and day_idx < len(self.schedule.get(c, [])) and self.schedule[c][day_idx]['shift'] == 'Night Shift (21-09)']

            def has_consecutive_nights(c):
                sched = self.schedule.get(c, [])
                # check previous and next day for night to prefer keeping whole blocks
                prev_is = day_idx - 1 >= 0 and day_idx - 1 < len(sched) and sched[day_idx - 1].get('shift') == 'Night Shift (21-09)'
                next_is = day_idx + 1 < len(sched) and sched[day_idx + 1].get('shift') == 'Night Shift (21-09)'
                return prev_is or next_is

            if len(night_workers) > 1:
                pair_workers = [c for c in night_workers if has_consecutive_nights(c)]
                if pair_workers:
                    keep = min(pair_workers, key=lambda x: hours_map.get(x, 0.0))
                else:
                    keep = min(night_workers, key=lambda x: hours_map.get(x, 0.0))
                for extra in night_workers:
                    if extra != keep:
                        self.schedule[extra][day_idx]['shift'] = 'Rest'
                        hours_map[extra] = max(0.0, hours_map.get(extra, 0.0) - self._duration_hours('Night Shift (21-09)'))

            if len(night_workers) == 0:
                cand = find_candidate(preferred_defaults=("Night Shift (21-09)",), preferred_next_shift='Night Shift (21-09)', preferred_shift='Night Shift (21-09)')
                if not cand:
                    cand = find_candidate(preferred_next_shift='Night Shift (21-09)', preferred_shift='Night Shift (21-09)')
                if not cand:
                    cand = find_candidate(preferred_shift='Night Shift (21-09)')
                if cand:
                    self.schedule[cand][day_idx]['shift'] = 'Night Shift (21-09)'
                    hours_map[cand] = hours_map.get(cand, 0.0) + self._duration_hours('Night Shift (21-09)')
                else:
                    # fallback: if no Rest candidate, convert a Day worker to Night (avoid Daily)
                    day_candidates = [c for c in self.colleagues if day_idx < len(self.schedule.get(c, [])) and self.schedule[c][day_idx].get('shift', '').startswith('Day Shift') and self.meta.get(c, {}).get('default') != 'Daily Work Day (09-18)']
                    if day_candidates:
                        # prefer converting someone who is NOT in a consecutive day pair,
                        # then prefer those that originally had night planned, then lower hours
                        scored_days = []
                        for c in day_candidates:
                            sched = self.schedule.get(c, [])
                            in_pair = 0
                            if day_idx - 1 >= 0 and day_idx - 1 < len(sched) and sched[day_idx - 1].get('shift','').startswith('Day'):
                                in_pair = 1
                            if day_idx + 1 < len(sched) and sched[day_idx + 1].get('shift','').startswith('Day'):
                                in_pair = 1
                            orig_sched = orig_schedule.get(c, [])
                            orig_today = orig_sched[day_idx].get('shift') if day_idx < len(orig_sched) else None
                            orig_next = orig_sched[day_idx+1].get('shift') if day_idx+1 < len(orig_sched) else None
                            pref = 0
                            if orig_today == 'Night Shift (21-09)' or orig_next == 'Night Shift (21-09)':
                                pref = -1
                            scored_days.append((in_pair, pref, hours_map.get(c, 0.0), c))
                        # sort by in_pair (0 preferred), pref (lower preferred), then lower hours
                        scored_days.sort()
                        pick = scored_days[0][3]
                        # convert pick from day to night
                        prev = self.schedule[pick][day_idx].get('shift', '')
                        self.schedule[pick][day_idx]['shift'] = 'Night Shift (21-09)'
                        hours_map[pick] = max(0.0, hours_map.get(pick, 0.0) - self._duration_hours(prev)) + self._duration_hours('Night Shift (21-09)')

            # Recompute counts after night adjustments
            counts = count_shift_types()

            # Day-time staffing constraints
            day_types = ['Day Shift (09-21)', 'Day Shift (12-24)', 'Daily Work Day (09-18)']
            day_workers = [c for c in self.colleagues if day_idx < len(self.schedule.get(c, [])) and self.schedule[c][day_idx].get('shift') in day_types]
            day_count_total = len(day_workers)

            if weekday < 5:
                # Weekday rules: prefer one Daily worker plus one Day Shift
                daily_count = counts.get('Daily Work Day (09-18)', 0)
                day_shift_count = sum(counts.get(k, 0) for k in self.SHIFT_TYPES if k.startswith('Day Shift'))

                if daily_count == 0:
                    # No daily present: ensure two day shifts (one 09-21 and one 12-24) if possible
                    needed = 2 - day_shift_count
                    while needed > 0:
                        assign_shift = 'Day Shift (09-21)' if day_shift_count == 0 else 'Day Shift (12-24)'
                        cand2 = find_candidate(require_can_fill=True, preferred_next_shift=assign_shift, preferred_shift=assign_shift)
                        if not cand2:
                            cand2 = find_candidate(preferred_defaults=[s for s in self.SHIFT_TYPES if s.startswith('Day Shift')], preferred_next_shift=assign_shift, preferred_shift=assign_shift)
                        if not cand2:
                            cand2 = find_candidate(preferred_next_shift=assign_shift, preferred_shift=assign_shift)
                        if not cand2:
                            cand2 = find_candidate(preferred_shift=assign_shift)
                        if not cand2:
                            break
                        assign_shift = 'Day Shift (09-21)' if day_shift_count == 0 else 'Day Shift (12-24)'
                        self.schedule[cand2][day_idx]['shift'] = assign_shift
                        hours_map[cand2] = hours_map.get(cand2, 0.0) + self._duration_hours(assign_shift)
                        day_shift_count += 1
                        needed -= 1
                else:
                    # daily present: ensure at least one day shift (12-24)
                    if day_shift_count == 0:
                        cand = find_candidate(preferred_defaults=[s for s in self.SHIFT_TYPES if s.startswith('Day Shift')], preferred_next_shift='Day Shift (12-24)', preferred_shift='Day Shift (12-24)')
                        if not cand:
                            cand = find_candidate(preferred_next_shift='Day Shift (12-24)', preferred_shift='Day Shift (12-24)')
                        if not cand:
                            cand = find_candidate(preferred_shift='Day Shift (12-24)')
                        if cand:
                            self.schedule[cand][day_idx]['shift'] = 'Day Shift (12-24)'
                            hours_map[cand] = hours_map.get(cand, 0.0) + self._duration_hours('Day Shift (12-24)')

                # After assignments, enforce maximum of 2 day-time workers
                counts = count_shift_types()
                day_workers = [c for c in self.colleagues if day_idx < len(self.schedule.get(c, [])) and self.schedule[c][day_idx].get('shift') in day_types]
                while len(day_workers) > 2:
                    # remove a day worker: prefer removing those not part of a consecutive day pair, then highest-hours
                    removable = [c for c in day_workers if self.schedule[c][day_idx].get('shift') not in ('Daily Work Day (09-18)',)]
                    if not removable:
                        removable = list(day_workers)
                    def removal_score(c):
                        # if colleague is in a day-run (has day previous or next), deprioritize removal
                        sched = self.schedule.get(c, [])
                        in_pair = 0
                        if day_idx - 1 >= 0 and day_idx - 1 < len(sched) and sched[day_idx - 1].get('shift','').startswith('Day'):
                            in_pair = 1
                        if day_idx + 1 < len(sched) and sched[day_idx + 1].get('shift','').startswith('Day'):
                            in_pair = 1
                        return (in_pair, hours_map.get(c, 0.0))
                    # pick removable with minimal in_pair then maximal hours
                    removable.sort(key=lambda x: (removal_score(x)[0], -removal_score(x)[1]))
                    rem = removable[-1]
                    # set to Rest
                    prev_shift = self.schedule[rem][day_idx].get('shift')
                    self.schedule[rem][day_idx]['shift'] = 'Rest'
                    hours_map[rem] = max(0.0, hours_map.get(rem, 0.0) - self._duration_hours(prev_shift))
                    day_workers.remove(rem)

            else:
                # Weekend: ensure exactly two day shifts (both 09-21)
                counts = count_shift_types()
                day_shift_count = sum(counts.get(k, 0) for k in self.SHIFT_TYPES if k.startswith('Day Shift'))
                while day_shift_count < 2:
                    assign = 'Day Shift (09-21)'
                    cand = find_candidate(require_can_fill=True, preferred_next_shift=assign, preferred_shift=assign)
                    if not cand:
                        cand = find_candidate(preferred_defaults=[s for s in self.SHIFT_TYPES if s.startswith('Day Shift')], preferred_next_shift=assign, preferred_shift=assign)
                    if not cand:
                        cand = find_candidate(preferred_next_shift=assign, preferred_shift=assign)
                    if not cand:
                        cand = find_candidate(preferred_shift=assign)
                    if not cand:
                        break
                    assign = 'Day Shift (09-21)'
                    self.schedule[cand][day_idx]['shift'] = assign
                    hours_map[cand] = hours_map.get(cand, 0.0) + self._duration_hours(assign)
                    day_shift_count += 1

                # enforce max 2 day workers
                counts = count_shift_types()
                day_workers = [c for c in self.colleagues if day_idx < len(self.schedule.get(c, [])) and self.schedule[c][day_idx].get('shift') in day_types]
                while len(day_workers) > 2:
                    # prefer removing those not in a consecutive day pair
                    def removal_score_wkend(c):
                        sched = self.schedule.get(c, [])
                        in_pair = 0
                        if day_idx - 1 >= 0 and day_idx - 1 < len(sched) and sched[day_idx - 1].get('shift','').startswith('Day'):
                            in_pair = 1
                        if day_idx + 1 < len(sched) and sched[day_idx + 1].get('shift','').startswith('Day'):
                            in_pair = 1
                        return (in_pair, hours_map.get(c, 0.0))
                    removable = list(day_workers)
                    removable.sort(key=lambda x: (removal_score_wkend(x)[0], -removal_score_wkend(x)[1]))
                    rem = removable[-1]
                    prev_shift = self.schedule[rem][day_idx].get('shift')
                    self.schedule[rem][day_idx]['shift'] = 'Rest'
                    hours_map[rem] = max(0.0, hours_map.get(rem, 0.0) - self._duration_hours(prev_shift))
                    day_workers.remove(rem)

        # Cleanup: prevent anyone having >2 consecutive identical day/night shifts
        # Final pass: ensure every day has exactly one night worker (fallback conversions if needed)
        for day_idx in range(days):
            # Lock daily workers for this day
            for daily_c in daily_workers_set:
                if day_idx < len(self.schedule.get(daily_c, [])):
                    weekday = (start_date + timedelta(days=day_idx)).weekday()
                    if weekday < 5:
                        self.schedule[daily_c][day_idx]['shift'] = 'Daily Work Day (09-18)'
                    else:
                        self.schedule[daily_c][day_idx]['shift'] = 'Rest'
            
            date_obj = start_date + timedelta(days=day_idx)
            # find existing night workers (excluding daily workers)
            night_workers = [c for c in self.colleagues if c not in daily_workers_set and day_idx < len(self.schedule.get(c, [])) and self.schedule[c][day_idx]['shift'] == 'Night Shift (21-09)']
            if night_workers:
                continue

            # try to find a Rest candidate first (shift workers only)
            rest_cands = [c for c in self.colleagues if c not in daily_workers_set and day_idx < len(self.schedule.get(c, [])) and self.schedule[c][day_idx]['shift'] == 'Rest']
            if rest_cands:
                # pick lowest hours
                pick = min(rest_cands, key=lambda x: hours_map.get(x, 0.0))
                self.schedule[pick][day_idx]['shift'] = 'Night Shift (21-09)'
                hours_map[pick] = hours_map.get(pick, 0.0) + self._duration_hours('Night Shift (21-09)')
                continue

            # no Rest candidate: convert a Day worker to Night (shift workers only)
            day_candidates = [c for c in self.colleagues if c not in daily_workers_set and day_idx < len(self.schedule.get(c, [])) and self.schedule[c][day_idx]['shift'].startswith('Day Shift')]
            if day_candidates:
                # prefer those not in a consecutive day pair and with lower hours
                scored = []
                for c in day_candidates:
                    sched = self.schedule.get(c, [])
                    in_pair = 0
                    if day_idx - 1 >= 0 and day_idx - 1 < len(sched) and sched[day_idx - 1].get('shift','').startswith('Day'):
                        in_pair = 1
                    if day_idx + 1 < len(sched) and sched[day_idx + 1].get('shift','').startswith('Day'):
                        in_pair = 1
                    scored.append((in_pair, hours_map.get(c, 0.0), c))
                scored.sort()
                pick = scored[0][2]
                prev = self.schedule[pick][day_idx].get('shift','')
                self.schedule[pick][day_idx]['shift'] = 'Night Shift (21-09)'
                hours_map[pick] = max(0.0, hours_map.get(pick, 0.0) - self._duration_hours(prev)) + self._duration_hours('Night Shift (21-09)')

                # ensure day coverage: if we removed a day worker, fill from Rest if possible
                day_types = ['Day Shift (09-21)', 'Day Shift (12-24)', 'Daily Work Day (09-18)']
                day_workers = [c for c in self.colleagues if day_idx < len(self.schedule.get(c, [])) and self.schedule[c][day_idx].get('shift') in day_types]
                if len(day_workers) < 2:
                    need = 2 - len(day_workers)
                    for _ in range(need):
                        # try to find Rest candidate who can fill (shift workers only)
                        pool = [c for c in self.colleagues if c not in daily_workers_set and day_idx < len(self.schedule.get(c, [])) and self.schedule[c][day_idx]['shift'] == 'Rest']
                        if not pool:
                            break
                        fill = min(pool, key=lambda x: hours_map.get(x,0.0))
                        # assign a day shift type depending on weekday
                        wd = date_obj.weekday()
                        assign = 'Day Shift (09-21)' if wd >= 5 else 'Day Shift (12-24)'
                        self.schedule[fill][day_idx]['shift'] = assign
                        hours_map[fill] = hours_map.get(fill,0.0) + self._duration_hours(assign)

        for c in self.colleagues:
            if c in daily_workers_set:
                # Daily workers are locked to their correct schedule, skip cleanup
                continue
            sched = self.schedule.get(c, [])
            orig = orig_schedule.get(c, [])
            i = 0
            while i < len(sched):
                cur = sched[i].get('shift', '')
                if cur.startswith('Day Shift') or cur.startswith('Night Shift'):
                    j = i
                    while j < len(sched) and sched[j].get('shift', '') == cur:
                        j += 1
                    run_len = j - i
                    if run_len > 2:
                        # prefer reverting days that were originally Rest (we forced them)
                        revert_idxs = [k for k in range(i, j) if k < len(orig) and orig[k].get('shift', '') == 'Rest']
                        while run_len > 2:
                            if revert_idxs:
                                idx_to_revert = revert_idxs.pop()
                            else:
                                idx_to_revert = j - 1
                            prev_shift = sched[idx_to_revert].get('shift', '')
                            if prev_shift:
                                sched[idx_to_revert]['shift'] = 'Rest'
                                hours_map[c] = max(0.0, hours_map.get(c, 0.0) - self._duration_hours(prev_shift))
                            run_len -= 1
                    i = j
                else:
                    i += 1

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

    def _duration_hours(self, shift: str) -> float:
        """Return duration in hours for a given shift string.

        Supports time ranges like '09:00-21:00', '21:00-09:00', and '12:00-24:00'.
        Returns 0.0 for empty or unknown shifts (e.g., 'Rest').
        """
        if not shift:
            return 0.0
        # map named shift to hours specification
        hours_spec = self.SHIFT_HOURS.get(shift, '')
        if not hours_spec:
            return 0.0
        try:
            start_str, end_str = hours_spec.split('-', 1)
            def to_minutes(tstr: str) -> int:
                if tstr == '24:00':
                    return 24 * 60
                h, m = [int(x) for x in tstr.split(':')]
                return h * 60 + m

            start_min = to_minutes(start_str)
            end_min = to_minutes(end_str)
            # wrap across midnight
            delta_min = end_min - start_min
            if delta_min <= 0:
                delta_min += 24 * 60
            return delta_min / 60.0
        except Exception:
            return 0.0

    def save_colleagues_to_file(self, filename: str) -> None:
        """Save colleague list and metadata to a JSON file."""
        import json
        data = {'colleagues': self.colleagues, 'meta': self.meta}
        try:
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving colleagues: {e}")

    def load_colleagues_from_file(self, filename: str) -> None:
        """Load colleague list and metadata from a JSON file."""
        import json
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
            self.colleagues = data.get('colleagues', [])
            self.meta = data.get('meta', {})
        except Exception as e:
            print(f"Error loading colleagues: {e}")


class SchedulerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Work Day Scheduler")
        self.root.geometry("1200x650")
        
        self.scheduler = WorkScheduler()
        self.current_date = datetime.now()
        # view controls: start at first day of current month
        self.view_start_date = self.current_date.replace(day=1)
        self.weeks_view = 2
        
        # Auto-load colleagues from last session
        self.colleagues_file = "colleagues_last.json"
        self.scheduler.load_colleagues_from_file(self.colleagues_file)
        
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
        
        # view navigation (month)
        ttk.Button(control_frame, text="◀ Prev", command=self.prev_month).pack(side=tk.RIGHT, padx=5)
        ttk.Button(control_frame, text="Next ▶", command=self.next_month).pack(side=tk.RIGHT, padx=5)
        self.month_label = ttk.Label(control_frame, text=self.view_start_date.strftime("%B %Y"))
        self.month_label.pack(side=tk.RIGHT, padx=5)
        
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

        # month view: show all days in the current view_start_date's month
        start = self.view_start_date
        days_in_month = calendar.monthrange(start.year, start.month)[1]
        days = days_in_month

        columns = ["Colleague", "Hours"] + [(start + timedelta(days=i)).strftime("%a\n%m/%d") for i in range(days)]

        # Create a Canvas-based month grid (7 columns x rows)
        canvas_frame = ttk.Frame(self.tree_container)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        hbar = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)
        vbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL)

        self.canvas = tk.Canvas(canvas_frame, bg='white', xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        hbar.config(command=self.canvas.xview)
        vbar.config(command=self.canvas.yview)
        hbar.pack(side=tk.BOTTOM, fill=tk.X)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        # styling map for shift colors
        self._style_map = {
            'Day Shift (09-21)': '#ffd7a6',
            'Day Shift (12-24)': '#ffd7a6',
            'Night Shift (21-09)': '#cfe8ff',
            'Daily Work Day (09-18)': '#d6f5d6',
            'Rest': '#f0f0f0'
        }

        # map canvas items to (colleague, day_index)
        self.canvas_item_map = {}
        try:
            self.canvas.tag_bind('assign', '<Button-1>', self.on_canvas_item_click)
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
        self.scheduler.save_colleagues_to_file(self.colleagues_file)
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
        dialog.geometry("400x280")
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
        self.scheduler.save_colleagues_to_file(self.colleagues_file)
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
        # generate schedule for the whole month in view
        start = self.view_start_date
        days_in_month = calendar.monthrange(start.year, start.month)[1]
        num_weeks = math.ceil(days_in_month / 7)
        self.scheduler.generate_schedule(start, num_weeks=num_weeks)
        self.refresh_schedule_display()
        messagebox.showinfo("Success", "Schedule generated successfully!")

    def refresh_schedule_display(self):
        # Rebuild tree (columns) for current view then populate
        self.build_tree()

        # update month label if present
        if hasattr(self, 'month_label'):
            try:
                self.month_label.config(text=self.view_start_date.strftime("%B %Y"))
            except Exception:
                pass

        # month view: number of days displayed
        start = self.view_start_date
        days_in_month = calendar.monthrange(start.year, start.month)[1]
        days = days_in_month

        # compute hours per colleague for the displayed window
        num_weeks = math.ceil(days / 7)
        hours_map = self.scheduler.compute_hours_for_period(start, num_weeks)

        # Draw month-grid into canvas: each day cell shows stacked assignments
        try:
            self.canvas.delete('all')
        except Exception:
            pass

        start_date = start
        rows = math.ceil(days / 7)
        # cell sizing
        cell_w = 140
        cell_h = 120
        header_h = 26

        total_w = cell_w * 7
        total_h = header_h + rows * cell_h
        try:
            self.canvas.config(scrollregion=(0, 0, total_w, total_h))
        except Exception:
            pass

        # draw day cells
        for d in range(days):
            col = d % 7
            row = d // 7
            x0 = col * cell_w
            y0 = header_h + row * cell_h
            x1 = x0 + cell_w
            y1 = y0 + cell_h
            # cell background and border
            self.canvas.create_rectangle(x0, y0, x1, y1, outline='#cccccc', fill='#ffffff')
            # date label
            date_obj = start_date + timedelta(days=d)
            date_label = date_obj.strftime('%a %d')
            self.canvas.create_text(x0 + 6, y0 + 8, anchor='nw', text=date_label, font=('Arial', 9, 'bold'))

            # collect assignments for that day
            assigns = []
            date_str = date_obj.strftime('%Y-%m-%d')
            for colleague in self.scheduler.colleagues:
                sched = self.scheduler.schedule.get(colleague, [])
                entry = next((e for e in sched if e.get('date') == date_str), None)
                if entry:
                    shift = entry.get('shift', '')
                    if shift and shift != 'Rest':
                        assigns.append((colleague, shift))

            if not assigns:
                self.canvas.create_text(x0 + cell_w/2, y0 + cell_h/2, text='-', fill='#888888')
            else:
                # draw stacked boxes for assignments
                for i, (colleague, shift) in enumerate(assigns):
                    box_x0 = x0 + 6
                    box_x1 = x1 - 6
                    box_h = 18
                    box_y0 = y0 + 24 + i * (box_h + 6)
                    box_y1 = box_y0 + box_h
                    color = self._style_map.get(shift, '#eeeeee')
                    rect = self.canvas.create_rectangle(box_x0, box_y0, box_x1, box_y1, fill=color, outline='#666')
                    txt = self.canvas.create_text(box_x0 + 4, box_y0 + 2, anchor='nw', text=f"{colleague} — {shift}", font=('Arial', 9))
                    # tag for click handling
                    try:
                        self.canvas.addtag_withtag('assign', rect)
                        self.canvas.addtag_withtag('assign', txt)
                        self.canvas_item_map[rect] = (colleague, d)
                        self.canvas_item_map[txt] = (colleague, d)
                    except Exception:
                        pass

        self.refresh_colleagues_listbox()

    def prev_month(self):
        year = self.view_start_date.year
        month = self.view_start_date.month - 1
        if month < 1:
            month = 12
            year -= 1
        self.view_start_date = self.view_start_date.replace(year=year, month=month, day=1)
        self.refresh_schedule_display()

    def next_month(self):
        year = self.view_start_date.year
        month = self.view_start_date.month + 1
        if month > 12:
            month = 1
            year += 1
        self.view_start_date = self.view_start_date.replace(year=year, month=month, day=1)
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
        # kept for compatibility; canvas-based view uses on_canvas_item_click
        return

    def on_canvas_item_click(self, event):
        # find canvas item under cursor
        try:
            item = event.widget.find_withtag('current')[0]
        except Exception:
            return
        mapping = self.canvas_item_map.get(item)
        if not mapping:
            return
        colleague, day_index = mapping
        # open shift dialog for that colleague/day index
        self.show_shift_dialog(colleague, day_index)
    
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
            # ensure entries up to col_index exist and have correct dates
            while len(sched) <= col_index:
                idx = len(sched)
                date_obj = self.view_start_date + timedelta(days=idx)
                sched.append({"date": date_obj.strftime("%Y-%m-%d"), "shift": ""})
            # ensure the date for the target index is set to the view start + index
            sched[col_index]["date"] = (self.view_start_date + timedelta(days=col_index)).strftime("%Y-%m-%d")
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
