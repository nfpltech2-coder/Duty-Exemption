import os
import calendar
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import List, Dict, Any, Optional
import threading

from logic import process_duty_exemption, load_duty_rates, save_duty_rates, MissingCTHError
from zoho_api import ShaktiCreatorAPI

# Brand Colors
PRIMARY_BLUE = "#1F3F6E"
ACCENT_RED = "#D8232A"
DARK_TEXT = "#1E1E1E"
MUTED_GRAY = "#6B7280"
LIGHT_BG = "#F4F6F8"
PANEL_WHITE = "#FFFFFF"
HOVER_BLUE = "#2A528F"


class DutyRatesDialog(tk.Toplevel):
    def __init__(self, parent, missing_cths: List[int] = None):
        super().__init__(parent)
        self.title("Manage Duty Rates")
        self.geometry("450x650")
        self.minsize(450, 600)
        self.configure(bg=LIGHT_BG)
        self.grab_set()

        self.rates = load_duty_rates()

        tk.Label(self, text="Select a rate below to edit or delete it.", bg=LIGHT_BG, font=("Segoe UI", 10)).pack(pady=10)

        # Treeview for rates
        tree_frame = tk.Frame(self, bg=LIGHT_BG)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=20)
        
        self.tree = ttk.Treeview(tree_frame, columns=("CTH", "Duty Rate"), show="headings", height=10)
        self.tree.heading("CTH", text="CTH")
        self.tree.heading("Duty Rate", text="Duty Rate")
        self.tree.column("CTH", anchor=tk.CENTER)
        self.tree.column("Duty Rate", anchor=tk.CENTER)
        
        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        self._populate()
        
        # Action buttons for selected item
        action_frame = tk.Frame(self, bg=LIGHT_BG)
        action_frame.pack(fill=tk.X, padx=20, pady=(5, 10))
        
        self.btn_delete = ttk.Button(action_frame, text="Delete Selected", command=self._on_delete, state=tk.DISABLED)
        self.btn_delete.pack(side=tk.RIGHT)

        # Add/Edit form
        f = tk.Frame(self, bg=LIGHT_BG)
        f.pack(fill=tk.X, padx=20, pady=10)

        tk.Label(f, text="CTH:", bg=LIGHT_BG, font=("Segoe UI", 10)).grid(row=0, column=0, padx=5, pady=5, sticky=tk.E)
        self.e_cth = ttk.Entry(f, font=("Segoe UI", 10))
        self.e_cth.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(f, text="Rate in % (e.g., 20 or 20%):", bg=LIGHT_BG, font=("Segoe UI", 10)).grid(row=1, column=0, padx=5, pady=5, sticky=tk.E)
        self.e_rate = ttk.Entry(f, font=("Segoe UI", 10))
        self.e_rate.grid(row=1, column=1, padx=5, pady=5)

        ttk.Button(f, text="Save Rate", command=self._save_rate).grid(row=2, column=0, columnspan=2, pady=10)
        ttk.Button(f, text="Clear Fields", command=self._clear_fields).grid(row=3, column=0, columnspan=2)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Delete>", self._on_delete)
        
        if missing_cths:
            tk.Label(self, text=f"Missing CTH detected. Please enter its rate.", bg=LIGHT_BG, fg=ACCENT_RED, font=("Segoe UI", 10, "bold")).pack(pady=(0, 10))
            self.e_cth.insert(0, str(missing_cths[0]))
            self.e_rate.focus_set()

    def _populate(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for cth, rate in sorted(self.rates.items()):
            self.tree.insert("", tk.END, values=(cth, f"{rate * 100:g}%"))

    def _save_rate(self):
        cth = self.e_cth.get().strip()
        rate_str = self.e_rate.get().strip()
        if not cth or not rate_str:
            messagebox.showwarning("Incomplete", "Please enter both CTH and Rate.")
            return
            
        if rate_str.endswith('%'):
            rate_str = rate_str[:-1]
        try:
            cth_val = int(cth)
            rate_val = float(rate_str) / 100.0
            
            # Warn if user accidentally typed 0.20 meaning 20%
            if rate_val < 0.01 and rate_str.startswith('0.'):
                if not messagebox.askyesno("Confirm Small Rate", f"You entered {rate_str}%, which is very small. Did you mean {float(rate_str)*100:g}%?"):
                    pass # Continue with the small rate if they insist
                    
            self.rates[cth_val] = rate_val
            save_duty_rates(self.rates)
            self._populate()
            self._clear_fields()
        except ValueError:
            messagebox.showerror("Error", "Invalid CTH or Rate. Ensure CTH is a number and Rate is a percentage (e.g. 20 or 20%).")

    def _on_select(self, event):
        selected = self.tree.selection()
        if not selected:
            self.btn_delete.config(state=tk.DISABLED)
            return
            
        self.btn_delete.config(state=tk.NORMAL)
        item = selected[0]
        cth, rate = self.tree.item(item, "values")
        self.e_cth.delete(0, tk.END)
        self.e_cth.insert(0, cth)
        self.e_rate.delete(0, tk.END)
        self.e_rate.insert(0, rate)
        
    def _clear_fields(self):
        self.e_cth.delete(0, tk.END)
        self.e_rate.delete(0, tk.END)
        self.tree.selection_remove(self.tree.selection())

    def _on_delete(self, event=None):
        selected = self.tree.selection()
        if selected:
            if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this duty rate?"):
                item = selected[0]
                cth, _ = self.tree.item(item, "values")
                del self.rates[int(cth)]
                save_duty_rates(self.rates)
                self._populate()
                self._clear_fields()


class MonthPickerDialog(tk.Toplevel):
    """Modal dialog to pick a Month/Year before syncing."""

    def __init__(self, parent, available_months: List[tuple]):
        super().__init__(parent)
        self.title("Select Month to Sync")
        self.resizable(False, False)
        self.configure(bg=PANEL_WHITE)
        self.grab_set()

        self.selected = None
        self._available_months = available_months

        tk.Label(self, text="Select which month's BE records to sync:",
                 font=("Segoe UI", 11), bg=PANEL_WHITE, fg=DARK_TEXT
                 ).pack(padx=30, pady=(20, 10))

        month_strs = [f"{calendar.month_name[m]} {y}" for y, m in available_months]
        month_strs.insert(0, "All Months")
        self._month_strs = month_strs

        self.combo = ttk.Combobox(self, values=month_strs, state="readonly",
                                  font=("Segoe UI", 11), width=22)
        self.combo.current(0)
        self.combo.pack(padx=30, pady=(0, 20))

        btn_frame = tk.Frame(self, bg=PANEL_WHITE)
        btn_frame.pack(pady=(0, 20))
        ttk.Button(btn_frame, text="Proceed", style="Primary.TButton",
                   command=self._on_proceed).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=8)

        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

    def _on_proceed(self):
        idx = self.combo.current()
        self.selected = "ALL" if idx == 0 else self._available_months[idx - 1]
        self.destroy()


class App:
    # Columns that support click-to-sort and their sort key functions
    SORTABLE_COLUMNS = {
        "Job No.":                   lambda r: r.get("Job No", ""),
        "BE Date":                   lambda r: r.get("BE Date Raw") or "",
        "Exempted Rows":             lambda r: r.get("Row Count", 0),
        "Total Exempted Duty (INR)": lambda r: r.get("Total Exempted Duty", 0.0),
        "Status":                    lambda r: r.get("Status", ""),
    }

    def __init__(self, root):
        self.root = root
        self.root.title("Duty Exemption Updater - Nagarkot Forwarders")
        self.root.state("zoomed")
        self.root.configure(bg=LIGHT_BG)

        self._setup_styles()

        self.api: Optional[ShaktiCreatorAPI] = None
        self.all_preview_data: List[Dict[str, Any]] = []
        self.preview_data: List[Dict[str, Any]] = []
        self.tree_items: Dict[str, str] = {}
        self.input_file_path: str = ""
        self.sheet_name_used: str = ""
        # Sort state: col_name -> bool (True = ascending)
        self._sort_state: Dict[str, bool] = {}

        self._create_header()
        self._create_body()
        self._create_footer()

    # ------------------------------------------------------------------ styles
    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Primary.TButton",
                        background=PRIMARY_BLUE, foreground=PANEL_WHITE,
                        font=("Segoe UI", 11, "bold"), padding=8, borderwidth=0)
        style.map("Primary.TButton", background=[("active", HOVER_BLUE)])
        
        style.configure("Secondary.TButton",
                        background=MUTED_GRAY, foreground=PANEL_WHITE,
                        font=("Segoe UI", 10), padding=6, borderwidth=0)
        style.map("Secondary.TButton", background=[("active", "#4B5563")])

        style.configure("Treeview",
                        background=PANEL_WHITE, fieldbackground=PANEL_WHITE,
                        foreground=DARK_TEXT, rowheight=30, font=("Segoe UI", 10))
        style.configure("Treeview.Heading",
                        background=LIGHT_BG, foreground=PRIMARY_BLUE,
                        font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[('selected', PRIMARY_BLUE)])

    # ------------------------------------------------------------------ header
    def _create_header(self):
        hf = tk.Frame(self.root, bg=PANEL_WHITE, height=80)
        hf.pack(fill=tk.X, side=tk.TOP)
        hf.pack_propagate(False)
        
        # Adding manage duty rates button on the right
        btn_manage = ttk.Button(hf, text="Manage Duty Rates", style="Secondary.TButton", command=self.open_duty_rates)
        btn_manage.pack(side=tk.RIGHT, padx=20, pady=(25, 0))

        tk.Label(hf, text="DUTY EXEMPTION UPDATER",
                 font=("Segoe UI", 22, "bold"), fg=PRIMARY_BLUE, bg=PANEL_WHITE
                 ).pack(pady=(15, 0))
        tk.Label(hf, text="Upload Excel to calculate and sync exempted duty to Shakti",
                 font=("Segoe UI", 12), fg=MUTED_GRAY, bg=PANEL_WHITE).pack()

    # ------------------------------------------------------------------ footer
    def _create_footer(self):
        ff = tk.Frame(self.root, bg=LIGHT_BG, height=30)
        ff.pack(fill=tk.X, side=tk.BOTTOM)
        ff.pack_propagate(False)
        tk.Label(ff, text="Nagarkot Forwarders Pvt. Ltd. ©",
                 font=("Segoe UI", 9), fg=MUTED_GRAY, bg=LIGHT_BG
                 ).pack(side=tk.LEFT, padx=20, pady=5)

    # ------------------------------------------------------------------ body
    def _create_body(self):
        self.body_frame = tk.Frame(self.root, bg=LIGHT_BG)
        self.body_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=20)

        # Controls row
        cf = tk.Frame(self.body_frame, bg=LIGHT_BG)
        cf.pack(fill=tk.X, pady=(0, 20))

        self.btn_upload = ttk.Button(cf, text="Upload Excel File",
                                     style="Primary.TButton", command=self.upload_file)
        self.btn_upload.pack(side=tk.LEFT)

        self.lbl_status = tk.Label(cf, text="Please upload a file.",
                                   font=("Segoe UI", 11), bg=LIGHT_BG, fg=DARK_TEXT)
        self.lbl_status.pack(side=tk.LEFT, padx=20)

        self.btn_sync = ttk.Button(cf, text="Sync to Shakti",
                                   style="Primary.TButton",
                                   command=self.open_month_picker, state=tk.DISABLED)
        self.btn_sync.pack(side=tk.RIGHT)

        # Tree
        columns = ("Job No.", "BE No.", "BE Date", "Exempted Rows",
                   "Total Exempted Duty (INR)", "Status")
        self.tree = ttk.Treeview(self.body_frame, columns=columns,
                                 show="headings", height=15)

        for col in columns:
            if col in self.SORTABLE_COLUMNS:
                # Bind header click for sortable columns
                self.tree.heading(col, text=col,
                                  command=lambda c=col: self._sort_by_column(c))
            else:
                self.tree.heading(col, text=col)

        self.tree.column("Job No.",                   anchor=tk.CENTER, width=120)
        self.tree.column("BE No.",                    anchor=tk.CENTER, width=120)
        self.tree.column("BE Date",                   anchor=tk.CENTER, width=120)
        self.tree.column("Exempted Rows",             anchor=tk.CENTER, width=110)
        self.tree.column("Total Exempted Duty (INR)", anchor=tk.CENTER, width=190)
        self.tree.column("Status",                    anchor=tk.CENTER, width=280)

        self.tree.tag_configure("error",   foreground="red")
        self.tree.tag_configure("success", foreground="#15803d")
        self.tree.tag_configure("syncing", foreground="#1d4ed8")

        self.tree.bind("<Button-3>", self.show_context_menu)

        sb = ttk.Scrollbar(self.body_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        
    def open_duty_rates(self, missing_cths: List[int] = None):
        DutyRatesDialog(self.root, missing_cths=missing_cths)

    # ---------------------------------------------------------- sorting
    def _sort_by_column(self, col: str):
        """Toggle sort order for the given column and repopulate tree."""
        ascending = not self._sort_state.get(col, False)
        self._sort_state[col] = ascending

        key_fn = self.SORTABLE_COLUMNS[col]

        # Sort the active dataset in place
        data = self.preview_data if self.preview_data else self.all_preview_data
        try:
            data.sort(key=lambda r: (key_fn(r) is None or key_fn(r) == "",
                                     key_fn(r)), reverse=not ascending)
        except TypeError:
            # Fallback for mixed types
            data.sort(key=lambda r: str(key_fn(r)), reverse=not ascending)

        # Update heading to show arrow indicator
        arrow = " ▲" if ascending else " ▼"
        for c in self.SORTABLE_COLUMNS:
            label = c + (arrow if c == col else "")
            self.tree.heading(c, text=label,
                              command=lambda cc=c: self._sort_by_column(cc))

        self._repopulate_tree(data)

    # ---------------------------------------------------------- tree helpers
    def _populate_tree(self, data: List[Dict[str, Any]]):
        """Clear and repopulate without changing sort headings."""
        self._repopulate_tree(data)

    def _repopulate_tree(self, data: List[Dict[str, Any]]):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.tree_items = {}

        for row in data:
            row.setdefault("Status", "Pending")
            be_no = row["BE No"]
            tag = self._tag_for_status(row["Status"])
            iid = self.tree.insert("", tk.END, values=(
                row["Job No"],
                be_no,
                row["BE Date"],
                row["Row Count"],
                f"₹{row['Total Exempted Duty']:,.2f}",
                row["Status"]
            ), tags=(tag,) if tag else ())
            self.tree_items[be_no] = iid

    @staticmethod
    def _tag_for_status(status: str) -> str:
        if status == "Updated":
            return "success"
        if status.startswith("Not Updated") or status.startswith("Skipped"):
            return "error"
        if status == "Syncing...":
            return "syncing"
        return ""

    # ---------------------------------------------------------- context menu
    def show_context_menu(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return
        self.tree.selection_set(item_id)
        values = self.tree.item(item_id, "values")
        if not values:
            return
        job_no, be_no = values[0], values[1]
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label=f"Copy Job No: {job_no}",
                         command=lambda: self.copy_to_clipboard(job_no))
        menu.add_command(label=f"Copy BE No: {be_no}",
                         command=lambda: self.copy_to_clipboard(be_no))
        menu.post(event.x_root, event.y_root)

    def copy_to_clipboard(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()

    # ---------------------------------------------------------- upload
    def upload_file(self):
        filepath = filedialog.askopenfilename(
            title="Select Master Data Excel",
            filetypes=[("Excel files", "*.xlsx *.xls")])
        if not filepath:
            return

        self.lbl_status.config(text=f"Processing: {os.path.basename(filepath)}...",
                               fg=PRIMARY_BLUE)
        self.root.update()

        try:
            result, sheet_name = process_duty_exemption(filepath)
            self.all_preview_data = result
            self.preview_data = []
            self.input_file_path = filepath
            self.sheet_name_used = sheet_name
            self._sort_state = {}  # Reset sort on new file

            # Reset headings to plain (no arrows)
            for col in self.SORTABLE_COLUMNS:
                self.tree.heading(col, text=col,
                                  command=lambda c=col: self._sort_by_column(c))

            self._populate_tree(self.all_preview_data)

            if self.all_preview_data:
                self.lbl_status.config(
                    text=f"Found {len(self.all_preview_data)} BE records for exemption.",
                    fg=DARK_TEXT)
                self.btn_sync.config(state=tk.NORMAL)
            else:
                self.lbl_status.config(
                    text="No duty exempted records found in the file.", fg=ACCENT_RED)
                self.btn_sync.config(state=tk.DISABLED)

        except MissingCTHError as e:
            msg = (f"Found missing duty rates for the following CTH(s):\n\n"
                   f"{', '.join(map(str, e.missing_cths))}\n\n"
                   f"Please add their duty rates, then upload the file again.")
            messagebox.showwarning("Missing Duty Rates", msg)
            self.lbl_status.config(text="Missing CTH Duty Rates. Please update and try again.", fg=ACCENT_RED)
            self.btn_sync.config(state=tk.DISABLED)
            # Automatically open the dialog with the missing CTHs pre-filled
            self.open_duty_rates(missing_cths=e.missing_cths)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to process file:\n{str(e)}")
            self.lbl_status.config(text="Error processing file.", fg=ACCENT_RED)
            self.btn_sync.config(state=tk.DISABLED)

    # ------------------------------------------------ month picker dialog
    def open_month_picker(self):
        if not self.all_preview_data:
            return

        import pandas as pd
        seen = set()
        months = []
        for row in self.all_preview_data:
            raw = row.get("BE Date Raw")
            try:
                if raw and not pd.isna(raw):
                    ym = (raw.year, raw.month)
                    if ym not in seen:
                        seen.add(ym)
                        months.append(ym)
            except Exception:
                pass
        months.sort()

        dialog = MonthPickerDialog(self.root, months)
        self.root.wait_window(dialog)

        if dialog.selected is None:
            return  # Cancelled

        import pandas as pd
        if dialog.selected == "ALL":
            self.preview_data = list(self.all_preview_data)
        else:
            year, month = dialog.selected
            self.preview_data = [
                r for r in self.all_preview_data
                if not pd.isna(r.get("BE Date Raw"))
                and r["BE Date Raw"].year == year
                and r["BE Date Raw"].month == month
            ]

        if not self.preview_data:
            messagebox.showinfo("No Records", "No records found for the selected month.")
            return

        # Reset statuses for fresh sync
        for row in self.preview_data:
            row["Status"] = "Pending"

        self._sort_state = {}
        for col in self.SORTABLE_COLUMNS:
            self.tree.heading(col, text=col,
                              command=lambda c=col: self._sort_by_column(c))
        self._populate_tree(self.preview_data)

        month_label = (
            "All Months" if dialog.selected == "ALL"
            else f"{calendar.month_name[dialog.selected[1]]} {dialog.selected[0]}"
        )
        proceed = messagebox.askyesno(
            "Confirm Sync",
            f"Ready to sync {len(self.preview_data)} records for {month_label}.\n\nProceed?"
        )
        if not proceed:
            return

        self._start_sync()

    # ---------------------------------------------------------- sync
    def _start_sync(self):
        self.btn_sync.config(state=tk.DISABLED)
        self.btn_upload.config(state=tk.DISABLED)
        threading.Thread(target=self._sync_thread, daemon=True).start()

    def _sync_thread(self):
        self.root.after(0, lambda: self.lbl_status.config(
            text="Initializing API connection...", fg=PRIMARY_BLUE))

        try:
            if not self.api:
                self.api = ShaktiCreatorAPI()
        except Exception as e:
            self.root.after(0, lambda e=e: messagebox.showerror(
                "API Error", f"Failed to initialize Zoho API:\n{str(e)}"))
            self.root.after(0, self._sync_finished)
            return

        success_count = 0
        error_logs = []
        total = len(self.preview_data)

        for row in self.preview_data:
            be_no = row["BE No"]
            exempted_duty = row["Total Exempted Duty"]

            self.root.after(0, lambda b=be_no:
                            self.update_row_status(b, "Syncing...", "syncing"))

            record_id, find_status, existing_duty = self.api.get_record_by_be(be_no)
            if not record_id:
                reason = ("Duplicate BE No found in Shakti"
                          if find_status == "DUPLICATE_RECORD" else find_status)
                status_msg = f"Not Updated ({reason})"
                error_logs.append(f"BE: {be_no} - {reason}")
                self.root.after(0, lambda b=be_no, s=status_msg:
                                self.update_row_status(b, s, "error"))
                continue

            # Skip if Duty_exempted already has a non-zero value
            if existing_duty is not None:
                status_msg = f"Skipped (Already has value: ₹{existing_duty:,.2f})"
                self.root.after(0, lambda b=be_no, s=status_msg:
                                self.update_row_status(b, s, "error"))
                error_logs.append(f"BE: {be_no} - Already has Duty_exempted = {existing_duty:.2f}")
                continue

            ok, upd_status = self.api.update_duty_exempted(record_id, exempted_duty)
            if ok:
                success_count += 1
                self.root.after(0, lambda b=be_no:
                                self.update_row_status(b, "Updated", "success"))
            else:
                status_msg = f"Not Updated ({upd_status})"
                error_logs.append(f"BE: {be_no} - {upd_status}")
                self.root.after(0, lambda b=be_no, s=status_msg:
                                self.update_row_status(b, s, "error"))

        self.root.after(0, lambda: self._show_summary(success_count, total, error_logs))

    def update_row_status(self, be_no: str, status: str, tag: str = ""):
        for row in self.preview_data:
            if row["BE No"] == be_no:
                row["Status"] = status
                break
        iid = self.tree_items.get(be_no)
        if iid and self.tree.exists(iid):
            self.tree.set(iid, "Status", status)
            self.tree.item(iid, tags=(tag,) if tag else ())
            self.tree.see(iid)

    def _show_summary(self, success_count: int, total: int, error_logs: List[str]):
        msg = f"Sync Complete!\nSuccessfully updated: {success_count} / {total}\n"
        if error_logs:
            msg += "\nErrors:\n" + "\n".join(error_logs[:10])
            if len(error_logs) > 10:
                msg += f"\n...and {len(error_logs) - 10} more errors."
            messagebox.showwarning("Sync Summary (with Errors)", msg)
            self.lbl_status.config(
                text=f"Sync finished with errors. ({success_count}/{total} updated)",
                fg=ACCENT_RED)
        else:
            messagebox.showinfo("Sync Summary", msg)
            self.lbl_status.config(
                text=f"Sync complete. All {total} records updated successfully.",
                fg="#15803d")
        self._sync_finished()

    def _sync_finished(self):
        self.btn_upload.config(state=tk.NORMAL)
        self.btn_sync.config(state=tk.NORMAL)


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
