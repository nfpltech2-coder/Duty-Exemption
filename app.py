import os
import sys
import calendar
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from typing import List, Dict, Any, Optional
import threading

from PIL import Image, ImageTk

from logic import process_duty_exemption, load_duty_rates, save_duty_rates, MissingCTHError
from zoho_api import ShaktiCreatorAPI

# Brand colours (matching Nagarkot Skoda app)
BRAND_BLUE = "#0056b3"
ACCENT_RED = "#dc3545"
BG_WHITE = "#ffffff"
TEXT_DARK = "#333333"
TEXT_LIGHT = "#666666"
APP_VERSION = "v1.0.0"


def resource_path(relative_path: str) -> str:
    """Resolve path for both dev and PyInstaller builds."""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class DutyRatesDialog(tk.Toplevel):
    def __init__(self, parent, missing_cths: List[int] = None):
        super().__init__(parent)
        self.title("Manage Duty Rates")
        self.geometry("450x650")
        self.minsize(450, 600)
        self.configure(bg=BG_WHITE)
        self.grab_set()

        self.rates = load_duty_rates()

        tk.Label(self, text="Select a rate below to edit or delete it.", bg=BG_WHITE, font=("Segoe UI", 10)).pack(pady=10)

        # Treeview for rates
        tree_frame = tk.Frame(self, bg=BG_WHITE)
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
        action_frame = tk.Frame(self, bg=BG_WHITE)
        action_frame.pack(fill=tk.X, padx=20, pady=(5, 10))
        
        self.btn_delete = ttk.Button(action_frame, text="Delete Selected", command=self._on_delete, state=tk.DISABLED)
        self.btn_delete.pack(side=tk.RIGHT)

        # Add/Edit form
        f = tk.Frame(self, bg=BG_WHITE)
        f.pack(fill=tk.X, padx=20, pady=10)

        tk.Label(f, text="CTH:", bg=BG_WHITE, font=("Segoe UI", 10)).grid(row=0, column=0, padx=5, pady=5, sticky=tk.E)
        self.e_cth = ttk.Entry(f, font=("Segoe UI", 10))
        self.e_cth.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(f, text="Rate in % (e.g., 20 or 20%):", bg=BG_WHITE, font=("Segoe UI", 10)).grid(row=1, column=0, padx=5, pady=5, sticky=tk.E)
        self.e_rate = ttk.Entry(f, font=("Segoe UI", 10))
        self.e_rate.grid(row=1, column=1, padx=5, pady=5)

        ttk.Button(f, text="Save Rate", command=self._save_rate).grid(row=2, column=0, columnspan=2, pady=10)
        ttk.Button(f, text="Clear Fields", command=self._clear_fields).grid(row=3, column=0, columnspan=2)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Delete>", self._on_delete)
        
        if missing_cths:
            tk.Label(self, text=f"Missing CTH detected. Please enter its rate.", bg=BG_WHITE, fg=ACCENT_RED, font=("Segoe UI", 10, "bold")).pack(pady=(0, 10))
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
        self.configure(bg=BG_WHITE)
        self.grab_set()

        self.selected = None
        self._available_months = available_months

        tk.Label(self, text="Select which month's BE records to sync:",
                 font=("Segoe UI", 11), bg=BG_WHITE, fg=TEXT_DARK
                 ).pack(padx=30, pady=(20, 10))

        month_strs = [f"{calendar.month_name[m]} {y}" for y, m in available_months]
        month_strs.insert(0, "All Months")
        self._month_strs = month_strs

        self.combo = ttk.Combobox(self, values=month_strs, state="readonly",
                                  font=("Segoe UI", 11), width=22)
        self.combo.current(0)
        self.combo.pack(padx=30, pady=(0, 20))

        btn_frame = tk.Frame(self, bg=BG_WHITE)
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
        self.root.configure(bg=BG_WHITE)

        self._setup_styles()

        self.api: Optional[ShaktiCreatorAPI] = None
        self.all_preview_data: List[Dict[str, Any]] = []
        self.preview_data: List[Dict[str, Any]] = []
        self.tree_items: Dict[str, str] = {}
        self.input_file_path: str = ""
        self.sheet_name_used: str = ""
        self.applied_rates: Dict[int, float] = {}
        # Sort state: col_name -> bool (True = ascending)
        self._sort_state: Dict[str, bool] = {}

        self._create_header()
        self._create_body()
        self._create_footer()

    # ------------------------------------------------------------------ styles
    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TFrame", background=BG_WHITE)
        style.configure("TLabel", background=BG_WHITE, font=("Segoe UI", 10), foreground=TEXT_DARK)
        style.configure("Header.TLabel", font=("Helvetica", 22, "bold"), foreground=BRAND_BLUE)
        style.configure("SubHeader.TLabel", font=("Segoe UI", 9), foreground=TEXT_LIGHT)
        style.configure("Footer.TLabel", font=("Segoe UI", 9), foreground=TEXT_LIGHT)
        style.configure("TLabelframe", background=BG_WHITE)
        style.configure("TLabelframe.Label", background=BG_WHITE, foreground=BRAND_BLUE, font=("Segoe UI", 11, "bold"))
        
        style.configure("Primary.TButton",
                        background=BRAND_BLUE, foreground="white",
                        font=("Segoe UI", 10, "bold"), padding=8, borderwidth=0)
        style.map("Primary.TButton", background=[("active", "#004494")])
        
        style.configure("Secondary.TButton",
                        background=TEXT_LIGHT, foreground="white",
                        font=("Segoe UI", 10, "bold"), padding=6, borderwidth=0)
        style.map("Secondary.TButton", background=[("active", "#4B5563")])

        style.configure("Treeview",
                        background=BG_WHITE, fieldbackground=BG_WHITE,
                        foreground=TEXT_DARK, rowheight=30, font=("Segoe UI", 10))
        style.configure("Treeview.Heading",
                        background="#e1e1e1", foreground=BRAND_BLUE,
                        font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[('selected', BRAND_BLUE)], foreground=[('selected', "white")])
        
        style.configure("TNotebook", background=BG_WHITE, borderwidth=0)
        style.configure("TNotebook.Tab", padding=[15, 5], font=("Segoe UI", 10, "bold"), background="#e1e1e1")
        style.map("TNotebook.Tab", background=[("selected", BRAND_BLUE)], foreground=[("selected", "white")])

    # ------------------------------------------------------------------ header
    def _create_header(self):
        hdr = ttk.Frame(self.root)
        hdr.pack(fill="x", padx=40, pady=(20, 5))
        hdr.columnconfigure(1, weight=1)

        try:
            logo_path = resource_path("Nagarkot Logo.png")
            if os.path.exists(logo_path):
                img = Image.open(logo_path)
                h = 35
                w = int((h / float(img.size[1])) * float(img.size[0]))
                img = img.resize((w, h), Image.Resampling.LANCZOS)
                self.logo_img = ImageTk.PhotoImage(img)
                ttk.Label(hdr, image=self.logo_img).grid(row=0, column=0, rowspan=2, padx=(0, 30))
        except Exception:
            pass

        ttk.Label(hdr, text="Duty Exemption Updater", style="Header.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(hdr, text="Upload Excel to calculate and sync exempted duty to Shakti", style="SubHeader.TLabel").grid(row=1, column=1, sticky="w")

        btn_manage = ttk.Button(hdr, text="Manage Duty Rates", style="Secondary.TButton", command=self.open_duty_rates)
        btn_manage.grid(row=0, column=2, rowspan=2, sticky="e")

    # ------------------------------------------------------------------ footer
    def _create_footer(self):
        f = ttk.Frame(self.root)
        f.pack(fill="x", side="bottom", padx=40, pady=10)
        ttk.Label(f, text="© Nagarkot Forwarders Pvt Ltd", style="Footer.TLabel").pack(side="left")
        ttk.Label(f, text=APP_VERSION, style="Footer.TLabel").pack(side="right")

    # ------------------------------------------------------------------ body
    def _create_body(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=40, pady=10)

        main_tab = ttk.Frame(self.notebook)
        self.notebook.add(main_tab, text=" Upload & Sync ")

        body = ttk.Frame(main_tab)
        body.pack(fill="both", expand=True, padx=10, pady=10)

        top = ttk.LabelFrame(body, text=" Upload Master Data Excel ", padding=15)
        top.pack(fill="x", pady=(0, 10))
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Excel File:").grid(row=0, column=0, sticky="w", pady=5, padx=5)
        self.filepath_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.filepath_var, state="readonly").grid(row=0, column=1, sticky="ew", pady=5, padx=5)
        ttk.Button(top, text="Browse", command=self.upload_file).grid(row=0, column=2, padx=5)

        btn_frame = ttk.Frame(top)
        btn_frame.grid(row=1, column=0, columnspan=3, pady=10)
        
        self.lbl_status = ttk.Label(btn_frame, text="Please upload a file.", font=("Segoe UI", 11, "italic"), foreground=TEXT_LIGHT)
        self.lbl_status.pack(side="left", padx=5)
        
        self.btn_sync = ttk.Button(btn_frame, text="SYNC TO SHAKTI", style="Primary.TButton", command=self.open_month_picker, state="disabled")
        self.btn_sync.pack(side="right", padx=5)

        preview = ttk.LabelFrame(body, text=" Preview (Right-click to copy)", padding=5)
        preview.pack(fill="both", expand=True, pady=(0, 5))

        columns = ("Job No.", "BE No.", "BE Date", "Exempted Rows", "Total Exempted Duty (INR)", "Status")
        self.tree = ttk.Treeview(preview, columns=columns, show="headings", height=15)

        for col in columns:
            if col in self.SORTABLE_COLUMNS:
                self.tree.heading(col, text=col, command=lambda c=col: self._sort_by_column(c))
            else:
                self.tree.heading(col, text=col)

        self.tree.column("Job No.", anchor="center", width=120)
        self.tree.column("BE No.", anchor="center", width=120)
        self.tree.column("BE Date", anchor="center", width=120)
        self.tree.column("Exempted Rows", anchor="center", width=110)
        self.tree.column("Total Exempted Duty (INR)", anchor="center", width=190)
        self.tree.column("Status", anchor="center", width=280)

        self.tree.tag_configure("error", foreground=ACCENT_RED)
        self.tree.tag_configure("success", foreground="#15803d")
        self.tree.tag_configure("syncing", foreground=BRAND_BLUE)
        self.tree.tag_configure("even", background="#f8f9fa")

        self.tree.bind("<Button-3>", self.show_context_menu)

        sb = ttk.Scrollbar(preview, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        
    def open_duty_rates(self, missing_cths: List[int] = None):
        pwd = simpledialog.askstring("Security Check", "Enter Duty Rates Key:", show="*")
        if pwd != "NAGARKOT123":
            messagebox.showerror("Access Denied", "Incorrect key.")
            return
        DutyRatesDialog(self.root, missing_cths=missing_cths)

    # ---------------------------------------------------------- sorting
    def _sort_by_column(self, col: str):
        ascending = not self._sort_state.get(col, False)
        self._sort_state[col] = ascending
        key_fn = self.SORTABLE_COLUMNS[col]

        data = self.preview_data if self.preview_data else self.all_preview_data
        try:
            data.sort(key=lambda r: (key_fn(r) is None or key_fn(r) == "", key_fn(r)), reverse=not ascending)
        except TypeError:
            data.sort(key=lambda r: str(key_fn(r)), reverse=not ascending)

        arrow = " ▲" if ascending else " ▼"
        for c in self.SORTABLE_COLUMNS:
            label = c + (arrow if c == col else "")
            self.tree.heading(c, text=label, command=lambda cc=c: self._sort_by_column(cc))

        self._repopulate_tree(data)

    # ---------------------------------------------------------- tree helpers
    def _populate_tree(self, data: List[Dict[str, Any]]):
        self._repopulate_tree(data)

    def _repopulate_tree(self, data: List[Dict[str, Any]]):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.tree_items = {}

        for idx, row in enumerate(data):
            row.setdefault("Status", "Pending")
            be_no = row["BE No"]
            tag = self._tag_for_status(row["Status"])
            tags = (tag,) if tag else ()
            if idx % 2 == 0 and not tag:
                tags = ("even",)
            elif idx % 2 == 0 and tag:
                tags = (tag, "even")

            iid = self.tree.insert("", tk.END, values=(
                row["Job No"],
                be_no,
                row["BE Date"],
                row["Row Count"],
                f"₹{row['Total Exempted Duty']:,.2f}",
                row["Status"]
            ), tags=tags)
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
        menu.add_command(label=f"Copy Job No: {job_no}", command=lambda: self.copy_to_clipboard(job_no))
        menu.add_command(label=f"Copy BE No: {be_no}", command=lambda: self.copy_to_clipboard(be_no))
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

        self.filepath_var.set(filepath)
        self.lbl_status.config(text=f"Processing: {os.path.basename(filepath)}...", foreground=BRAND_BLUE)
        self.root.update()

        try:
            result, sheet_name, applied_rates = process_duty_exemption(filepath)
            self.all_preview_data = result
            self.applied_rates = applied_rates
            self.preview_data = []
            self.input_file_path = filepath
            self.sheet_name_used = sheet_name
            self._sort_state = {}

            for col in self.SORTABLE_COLUMNS:
                self.tree.heading(col, text=col, command=lambda c=col: self._sort_by_column(c))

            self._populate_tree(self.all_preview_data)

            if self.all_preview_data:
                self.lbl_status.config(text=f"Found {len(self.all_preview_data)} BE records for exemption.", foreground=TEXT_DARK)
                self.btn_sync.config(state="normal")
            else:
                self.lbl_status.config(text="No duty exempted records found in the file.", foreground=ACCENT_RED)
                self.btn_sync.config(state="disabled")

        except MissingCTHError as e:
            msg = (f"Found missing duty rates for the following CTH(s):\n\n"
                   f"{', '.join(map(str, e.missing_cths))}\n\n"
                   f"Please add their duty rates, then upload the file again.")
            messagebox.showwarning("Missing Duty Rates", msg)
            self.lbl_status.config(text="Missing CTH Duty Rates. Please update and try again.", foreground=ACCENT_RED)
            self.btn_sync.config(state="disabled")
            self.open_duty_rates(missing_cths=e.missing_cths)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to process file:\n{str(e)}")
            self.lbl_status.config(text="Error processing file.", foreground=ACCENT_RED)
            self.btn_sync.config(state="disabled")

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
            return

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

        for row in self.preview_data:
            row["Status"] = "Pending"

        self._sort_state = {}
        for col in self.SORTABLE_COLUMNS:
            self.tree.heading(col, text=col, command=lambda c=col: self._sort_by_column(c))
        self._populate_tree(self.preview_data)

        rates_text = "\n".join([f"CTH {c}: {r*100:.1f}%" for c, r in self.applied_rates.items()])
        if not rates_text:
            rates_text = "None applied"

        month_label = "All Months" if dialog.selected == "ALL" else f"{calendar.month_name[dialog.selected[1]]} {dialog.selected[0]}"
        proceed = messagebox.askyesno("Confirm Sync", f"Ready to sync {len(self.preview_data)} records for {month_label}.\n\n"
                                                      f"Applied Duty Rates:\n{rates_text}\n\nProceed?")
        if not proceed:
            return

        self._start_sync()

    # ---------------------------------------------------------- sync
    def _start_sync(self):
        self.btn_sync.config(state="disabled")
        threading.Thread(target=self._sync_thread, daemon=True).start()

    def _sync_thread(self):
        self.root.after(0, lambda: self.lbl_status.config(text="Initializing API connection...", foreground=BRAND_BLUE))

        try:
            if not self.api:
                self.api = ShaktiCreatorAPI()
        except Exception as e:
            self.root.after(0, lambda e=e: messagebox.showerror("API Error", f"Failed to initialize Zoho API:\n{str(e)}"))
            self.root.after(0, self._sync_finished)
            return

        success_count = 0
        error_logs = []
        total = len(self.preview_data)

        for row in self.preview_data:
            be_no = row["BE No"]
            exempted_duty = row["Total Exempted Duty"]

            self.root.after(0, lambda b=be_no: self.update_row_status(b, "Syncing...", "syncing"))

            record_id, find_status, existing_duty = self.api.get_record_by_be(be_no)
            if not record_id:
                reason = "Duplicate BE No found in Shakti" if find_status == "DUPLICATE_RECORD" else find_status
                status_msg = f"Not Updated ({reason})"
                error_logs.append(f"BE: {be_no} - {reason}")
                self.root.after(0, lambda b=be_no, s=status_msg: self.update_row_status(b, s, "error"))
                continue

            if existing_duty is not None:
                status_msg = f"Skipped (Already has value: ₹{existing_duty:,.2f})"
                self.root.after(0, lambda b=be_no, s=status_msg: self.update_row_status(b, s, "error"))
                error_logs.append(f"BE: {be_no} - Already has Duty_exempted = {existing_duty:.2f}")
                continue

            ok, upd_status = self.api.update_duty_exempted(record_id, exempted_duty)
            if ok:
                success_count += 1
                self.root.after(0, lambda b=be_no: self.update_row_status(b, "Updated", "success"))
            else:
                status_msg = f"Not Updated ({upd_status})"
                error_logs.append(f"BE: {be_no} - {upd_status}")
                self.root.after(0, lambda b=be_no, s=status_msg: self.update_row_status(b, s, "error"))

        self.root.after(0, lambda: self._show_summary(success_count, total, error_logs))

    def update_row_status(self, be_no: str, status: str, tag: str = ""):
        for row in self.preview_data:
            if row["BE No"] == be_no:
                row["Status"] = status
                break
        iid = self.tree_items.get(be_no)
        if iid and self.tree.exists(iid):
            self.tree.set(iid, "Status", status)
            
            # Need to get current tags to keep 'even' tag if present
            current_tags = self.tree.item(iid, "tags")
            new_tags = [tag] if tag else []
            if "even" in current_tags:
                new_tags.append("even")
                
            self.tree.item(iid, tags=tuple(new_tags))
            self.tree.see(iid)

    def _show_summary(self, success_count: int, total: int, error_logs: List[str]):
        msg = f"Sync Complete!\nSuccessfully updated: {success_count} / {total}\n"
        if error_logs:
            msg += "\nErrors:\n" + "\n".join(error_logs[:10])
            if len(error_logs) > 10:
                msg += f"\n...and {len(error_logs) - 10} more errors."
            messagebox.showwarning("Sync Summary (with Errors)", msg)
            self.lbl_status.config(text=f"Sync finished with errors. ({success_count}/{total} updated)", foreground=ACCENT_RED)
        else:
            messagebox.showinfo("Sync Summary", msg)
            self.lbl_status.config(text=f"Sync complete. All {total} records updated successfully.", foreground="#15803d")
        self._sync_finished()

    def _sync_finished(self):
        self.btn_sync.config(state="normal")


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
