import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
from datetime import datetime, timedelta
from itertools import cycle

class WorkScheduler:
    SHIFT_TYPES = ["Day Shift", "Night Shift", "Development Duty", "Daily Work Day", "Rest"]
    PATTERN = [2, 2]  # 2 work days, 2 rest days
    
    def __init__(self):
        self.colleagues = []
        self.schedule = {}
        
    def add_colleague(self, name):
        if name not in self.colleagues:
            self.colleagues.append(name)
            
    def generate_schedule(self, start_date, num_weeks=1):
        """Generate schedule with pattern: 2 day shifts, 2 rest days"""
        self.schedule = {}
        
        for colleague in self.colleagues:
            colleague_schedule = []
            pattern_cycle = cycle(["Day Shift"] * 2 + ["Rest"] * 2)
            
            current_date = start_date
            for i in range(num_weeks * 7):
                shift = next(pattern_cycle)
                date_str = current_date.strftime("%Y-%m-%d")
                colleague_schedule.append({
                    "date": date_str,
                    "shift": shift
                })
                current_date += timedelta(days=1)
            
            self.schedule[colleague] = colleague_schedule
            
    def save_schedule(self, filename):
        """Save schedule to JSON file"""
        data = {
            "colleagues": self.colleagues,
            "schedule": self.schedule
        }
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
            
    def load_schedule(self, filename):
        """Load schedule from JSON file"""
        with open(filename, 'r') as f:
            data = json.load(f)
            self.colleagues = data["colleagues"]
            self.schedule = data["schedule"]


class SchedulerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Work Day Scheduler")
        self.root.geometry("1200x650")
        
        self.scheduler = WorkScheduler()
        self.current_date = datetime.now()
        
        self.setup_ui()
        
    def setup_ui(self):
        # Top control panel
        control_frame = ttk.Frame(self.root)
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(control_frame, text="Colleague Name:").pack(side=tk.LEFT, padx=5)
        self.colleague_entry = ttk.Entry(control_frame, width=20)
        self.colleague_entry.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(control_frame, text="Add Colleague", command=self.add_colleague).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Remove Selected", command=self.remove_colleague).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(control_frame, text="Generate Schedule", command=self.generate_schedule).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Save", command=self.save_schedule).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Load", command=self.load_schedule).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Export List", command=self.export_colleagues).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Import List", command=self.import_colleagues).pack(side=tk.LEFT, padx=5)
        
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
        
        # Main schedule frame with scrollbar
        schedule_frame = ttk.LabelFrame(main_content, text="Schedule")
        schedule_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(schedule_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Create treeview for schedule display
        columns = ["Colleague"] + [(self.current_date + timedelta(days=i)).strftime("%a\n%m/%d") for i in range(14)]
        
        self.tree = ttk.Treeview(schedule_frame, columns=columns, height=20, yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.tree.yview)
        
        self.tree.column("#0", width=0, stretch=tk.NO)
        self.tree.column("Colleague", anchor=tk.W, width=120)
        
        for col in columns[1:]:
            self.tree.column(col, anchor=tk.CENTER, width=90)
        
        self.tree.heading("#0", text="", anchor=tk.W)
        self.tree.heading("Colleague", text="Colleague", anchor=tk.W)
        
        for col in columns[1:]:
            self.tree.heading(col, text=col, anchor=tk.CENTER)
        
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        # Bind click event for editing
        self.tree.bind("<Button-1>", self.on_tree_click)
        
    def add_colleague(self):
        name = self.colleague_entry.get().strip()
        if name:
            self.scheduler.add_colleague(name)
            self.colleague_entry.delete(0, tk.END)
            self.refresh_schedule_display()
            self.refresh_colleagues_listbox()
            messagebox.showinfo("Success", f"Colleague '{name}' added successfully!")
        else:
            messagebox.showwarning("Input Error", "Please enter a colleague name.")
            
    def remove_colleague(self):
        selection = self.colleagues_listbox.curselection()
        if not selection:
            messagebox.showwarning("Selection Error", "Please select a colleague to remove.")
            return
        
        idx = selection[0]
        colleague = self.colleagues_listbox.get(idx)
        
        if messagebox.askyesno("Confirm Removal", f"Are you sure you want to remove '{colleague}'?"):
            self.scheduler.colleagues.remove(colleague)
            if colleague in self.scheduler.schedule:
                del self.scheduler.schedule[colleague]
            self.refresh_schedule_display()
            self.refresh_colleagues_listbox()
            messagebox.showinfo("Success", f"Colleague '{colleague}' removed successfully!")
            
    def refresh_colleagues_listbox(self):
        self.colleagues_listbox.delete(0, tk.END)
        for colleague in self.scheduler.colleagues:
            self.colleagues_listbox.insert(tk.END, colleague)
            
    def generate_schedule(self):
        if not self.scheduler.colleagues:
            messagebox.showwarning("Empty List", "Please add colleagues first.")
            return
            
        self.scheduler.generate_schedule(self.current_date, num_weeks=2)
        self.refresh_schedule_display()
        messagebox.showinfo("Success", "Schedule generated successfully!")
        
    def refresh_schedule_display(self):
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Add rows for each colleague
        for colleague in self.scheduler.colleagues:
            row_data = [colleague]
            
            if colleague in self.scheduler.schedule:
                for entry in self.scheduler.schedule[colleague][:14]:
                    row_data.append(entry["shift"])
            else:
                row_data.extend([""] * 14)
            
            self.tree.insert(parent="", index="end", values=row_data)
        
        self.refresh_colleagues_listbox()
    
    def on_tree_click(self, event):
        """Handle cell click for editing"""
        item = self.tree.identify("item", event.x, event.y)
        col = self.tree.identify_column(event.x, event.y)
        
        if item and col != "#0" and col != "Colleague":
            col_index = int(col) - 2  # Adjust for 0-based indexing
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
        
        for shift in self.scheduler.SHIFT_TYPES:
            ttk.Radiobutton(dialog, text=shift, variable=shift_var, value=shift).pack(anchor=tk.W, padx=20)
        
        def save_shift():
            shift = shift_var.get()
            if colleague in self.scheduler.schedule and col_index < len(self.scheduler.schedule[colleague]):
                self.scheduler.schedule[colleague][col_index]["shift"] = shift
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
                    new_colleagues = [line.strip() for line in f if line.strip()]
                
                for colleague in new_colleagues:
                    if colleague not in self.scheduler.colleagues:
                        self.scheduler.add_colleague(colleague)
                
                self.refresh_schedule_display()
                messagebox.showinfo("Success", f"Imported {len(new_colleagues)} colleagues successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to import colleagues: {str(e)}")


if __name__ == "__main__":
    root = tk.Tk()
    app = SchedulerApp(root)
    root.mainloop()
