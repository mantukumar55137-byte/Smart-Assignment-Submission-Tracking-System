import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
import os
import sys
import shutil
import csv
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
import re
import calendar

# Ensure current working directory is the script directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR and os.path.exists(BASE_DIR):
    os.chdir(BASE_DIR)

# Optional chart/PDF support
try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

try:
    from PIL import Image, ImageTk, ImageOps, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


# ============================================================
# CONFIGURATION
# ============================================================

DB_NAME = "assignment_system.db"
UPLOAD_DIR = "uploads"
EXPORT_DIR = "exports"
PROFILE_PIC_DIR = "profile_pics"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)
os.makedirs(PROFILE_PIC_DIR, exist_ok=True)

APP_TITLE = "Smart Assignment Submission & Tracking System"

# Modern light/dark colors
LIGHT = {
    "bg": "#F4F7FB",
    "sidebar": "#172033",
    "sidebar2": "#202C44",
    "card": "#FFFFFF",
    "text": "#182230",
    "muted": "#6B7280",
    "accent": "#2563EB",
    "accent2": "#1D4ED8",
    "success": "#16A34A",
    "warning": "#D97706",
    "danger": "#DC2626",
    "border": "#DDE3EC",
    "input": "#FFFFFF",
}

DARK = {
    "bg": "#111827",
    "sidebar": "#0B1220",
    "sidebar2": "#172033",
    "card": "#1F2937",
    "text": "#F3F4F6",
    "muted": "#9CA3AF",
    "accent": "#60A5FA",
    "accent2": "#3B82F6",
    "success": "#4ADE80",
    "warning": "#FBBF24",
    "danger": "#F87171",
    "border": "#374151",
    "input": "#111827",
}


# ============================================================
# DATABASE
# ============================================================

def get_db():
    con = sqlite3.connect(DB_NAME)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def hash_password(password):
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, 120000
    )
    return "PBKDF2$" + salt.hex() + "$" + key.hex()


def verify_password(password, stored):
    if not stored:
        return False

    # New secure format
    if stored.startswith("PBKDF2$"):
        try:
            _, salt_hex, key_hex = stored.split("$")
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(key_hex)
            actual = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), salt, 120000
            )
            return hmac.compare_digest(actual, expected)
        except Exception:
            return False

    # Backward compatibility with old plain-text passwords
    return hmac.compare_digest(password, stored)


def validate_password(password):
    """Require at least 6 characters, uppercase, lowercase, digit and symbol."""
    if len(password) < 6:
        return False, "Password must be at least 6 characters long."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one capital letter (A-Z)."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one small letter (a-z)."
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit (0-9)."
    if not re.search(r"[^A-Za-z0-9]", password):
        return False, "Password must contain at least one special symbol (e.g. @, #, $)."
    return True, ""


def init_db():
    con = get_db()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student',
            approval_status TEXT NOT NULL DEFAULT 'approved',
            student_id TEXT UNIQUE,
            profile_pic TEXT,
            teacher_subject TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            subject TEXT NOT NULL,
            description TEXT,
            deadline TEXT NOT NULL,
            max_marks INTEGER DEFAULT 100,
            teacher_id INTEGER,
            FOREIGN KEY (teacher_id) REFERENCES users(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            submission_time TEXT NOT NULL,
            status TEXT DEFAULT 'Submitted',
            marks REAL,
            feedback TEXT,
            version INTEGER DEFAULT 1,
            FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            details TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    """)

    con.commit()

    cur.execute("""CREATE TABLE IF NOT EXISTS resubmission_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, assignment_id INTEGER NOT NULL, student_id INTEGER NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', requested_at TEXT NOT NULL, reviewed_at TEXT, FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE, FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, title TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL, is_read INTEGER DEFAULT 0, FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS rubric_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        submission_id INTEGER NOT NULL,
        criterion TEXT NOT NULL,
        score REAL NOT NULL,
        max_score REAL NOT NULL DEFAULT 25,
        feedback TEXT,
        UNIQUE(submission_id, criterion),
        FOREIGN KEY (submission_id) REFERENCES submissions(id) ON DELETE CASCADE
    )""")
    con.commit()

    # Safe migrations for older databases
    migrate_columns(
        con,
        "users",
        {
            "name": "TEXT",
            "email": "TEXT",
            "password": "TEXT",
            "role": "TEXT DEFAULT 'student'",
            "approval_status": "TEXT DEFAULT 'approved'",
            "student_id": "TEXT",
            "profile_pic": "TEXT",
            "teacher_subject": "TEXT",
        },
    )
    migrate_columns(
        con,
        "assignments",
        {
            "title": "TEXT",
            "subject": "TEXT",
            "description": "TEXT",
            "deadline": "TEXT",
            "max_marks": "INTEGER DEFAULT 100",
            "teacher_id": "INTEGER",
        },
    )
    migrate_columns(
        con,
        "submissions",
        {
            "assignment_id": "INTEGER",
            "student_id": "INTEGER",
            "file_name": "TEXT",
            "submission_time": "TEXT",
            "status": "TEXT DEFAULT 'Submitted'",
            "marks": "REAL",
            "feedback": "TEXT",
            "version": "INTEGER DEFAULT 1",
        },
    )

    # Create default users only when missing.
    create_demo_user(con, "Student User", "student@gmail.com", "Student@123", "student")
    create_demo_user(con, "Teacher User", "teacher@gmail.com", "Teacher@123", "teacher")
    create_demo_user(con, "Administrator", "admin@gmail.com", "Admin@123", "admin")

    # Teacher and admin accounts are trusted system accounts.
    cur.execute("""
        UPDATE users
        SET approval_status='approved'
        WHERE role IN ('teacher', 'admin')
    """)
    cur.execute("UPDATE users SET teacher_subject='Python' WHERE email='teacher@gmail.com' AND (teacher_subject IS NULL OR trim(teacher_subject)='')")

    # Demo assignments if there are none
    count = cur.execute("SELECT COUNT(*) AS c FROM assignments").fetchone()["c"]
    if count == 0:
        teacher = cur.execute(
            "SELECT id FROM users WHERE email=?",
            ("teacher@gmail.com",)
        ).fetchone()
        teacher_id = teacher["id"] if teacher else None

        cur.execute("""
            INSERT INTO assignments
            (title, subject, description, deadline, max_marks, teacher_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "Python Tkinter GUI",
            "Python",
            "Create a Tkinter GUI application using widgets and geometry managers.",
            "2026-10-15 23:59",
            30,
            teacher_id,
        ))

        cur.execute("""
            INSERT INTO assignments
            (title, subject, description, deadline, max_marks, teacher_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "Database Design",
            "DBMS",
            "Prepare a database design with tables, keys and relationships.",
            "2026-10-20 23:59",
            30,
            teacher_id,
        ))

    # Database-level protection against duplicate emails.
    # SQLite treats this as a final safety layer even if two
    # registration requests happen at nearly the same time.
    try:
        con.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique
            ON users(email COLLATE NOCASE)
        """)
        con.commit()
    except sqlite3.IntegrityError:
        # If an old database already contains duplicate emails,
        # the application-level registration check still prevents
        # new duplicates. The existing data can be cleaned manually.
        pass

    try:
        con.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_student_id_unique
            ON users(student_id COLLATE NOCASE)
            WHERE student_id IS NOT NULL
        """)
        con.commit()
    except sqlite3.IntegrityError:
        pass

    con.close()


def migrate_columns(con, table, columns):
    existing = {
        row["name"]
        for row in con.execute(f"PRAGMA table_info({table})").fetchall()
    }
    for name, definition in columns.items():
        if name not in existing:
            try:
                con.execute(
                    f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
                )
            except sqlite3.OperationalError:
                pass
    con.commit()


def create_demo_user(con, name, email, password, role):
    row = con.execute(
        "SELECT id FROM users WHERE email=?", (email,)
    ).fetchone()

    if row is None:
        con.execute(
            "INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",
            (name, email, hash_password(password), role),
        )
    else:
        # Keep existing custom accounts untouched. For the built-in demo accounts,
        # upgrade the old 1234 password to the new strong demo password.
        stored = con.execute(
            "SELECT password FROM users WHERE email=?", (email,)
        ).fetchone()["password"]
        if verify_password("1234", stored) or stored == password:
            con.execute(
                "UPDATE users SET password=? WHERE email=?",
                (hash_password(password), email),
            )


def log_activity(user_id, action, details=""):
    try:
        con = get_db()
        con.execute("""
            INSERT INTO activity_log(user_id, action, details, timestamp)
            VALUES (?, ?, ?, ?)
        """, (
            user_id,
            action,
            details,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ))
        con.commit()
        con.close()
    except Exception:
        pass


# ============================================================
# GENERAL HELPERS
# ============================================================

def parse_deadline(value):
    return datetime.strptime(value, "%Y-%m-%d %H:%M")


def safe_filename(name):
    bad = '<>:"/\\|?*'
    for ch in bad:
        name = name.replace(ch, "_")
    return name


def open_file(path):
    if not os.path.exists(path):
        messagebox.showerror("File Not Found", "The selected file no longer exists.")
        return

    try:
        if os.name == "nt":
            os.startfile(os.path.abspath(path))
        elif os.uname().sysname == "Darwin":
            os.system(f'open "{os.path.abspath(path)}"')
        else:
            os.system(f'xdg-open "{os.path.abspath(path)}"')
    except Exception as e:
        messagebox.showerror("Open File", f"Could not open file.\n{e}")


def copy_submission_file_to(destination_dir, row):
    source = os.path.join(UPLOAD_DIR, row["file_name"])
    if not os.path.exists(source):
        raise FileNotFoundError("Original submission file is missing.")
    os.makedirs(destination_dir, exist_ok=True)
    destination = os.path.join(destination_dir, os.path.basename(row["file_name"]))
    shutil.copy2(source, destination)
    return destination


def get_latest_submission(assignment_id, student_id):
    con = get_db()
    row = con.execute("""
        SELECT *
        FROM submissions
        WHERE assignment_id=? AND student_id=?
        ORDER BY version DESC, id DESC
        LIMIT 1
    """, (assignment_id, student_id)).fetchone()
    con.close()
    return row


def calculate_status(deadline, submitted_time):
    try:
        return "Submitted" if submitted_time <= deadline else "Late"
    except Exception:
        return "Submitted"


# ============================================================
# MAIN APPLICATION
# ============================================================

def create_notification(user_id, title, message):
    try:
        con=get_db(); con.execute("INSERT INTO notifications(user_id,title,message,created_at) VALUES(?,?,?,?)",(user_id,title,message,datetime.now().strftime("%Y-%m-%d %H:%M:%S"))); con.commit(); con.close()
    except Exception: pass

def unread_notification_count(user_id):
    con=get_db(); n=con.execute("SELECT COUNT(*) c FROM notifications WHERE user_id=? AND is_read=0",(user_id,)).fetchone()["c"]; con.close(); return n

class AssignmentApp(tk.Tk):
    def __init__(self):
        super().__init__()

        init_db()

        self.title(APP_TITLE)
        self.geometry("1280x760")
        self.minsize(1050, 680)

        self.current_user = None
        self.current_page = None
        self.dark_mode = False
        self.colors = LIGHT

        self.configure(bg=self.colors["bg"])
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.show_login()

    # --------------------------------------------------------
    # Styling
    # --------------------------------------------------------

    def setup_styles(self):
        c = self.colors
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "Treeview",
            background=c["card"],
            foreground=c["text"],
            fieldbackground=c["card"],
            rowheight=34,
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Treeview.Heading",
            background=c["sidebar2"],
            foreground="white",
            font=("Segoe UI", 10, "bold"),
            padding=8,
        )
        style.map(
            "Treeview",
            background=[("selected", c["accent"])],
            foreground=[("selected", "white")],
        )

        style.configure(
            "TCombobox",
            fieldbackground=c["input"],
            background=c["input"],
            foreground=c["text"],
        )

        style.configure(
            "TEntry",
            fieldbackground=c["input"],
            foreground=c["text"],
        )

        style.configure(
            "TNotebook",
            background=c["bg"],
            borderwidth=0,
        )
        style.configure(
            "TNotebook.Tab",
            padding=[14, 8],
            font=("Segoe UI", 10),
        )

    def clear_window(self):
        for widget in self.winfo_children():
            widget.destroy()

    def button(self, parent, text, command, kind="primary", width=None):
        c = self.colors
        colors = {
            "primary": (c["accent"], "white"),
            "success": (c["success"], "white"),
            "danger": (c["danger"], "white"),
            "warning": (c["warning"], "white"),
            "dark": (c["sidebar2"], "white"),
            "light": (c["card"], c["text"]),
        }
        bg, fg = colors.get(kind, colors["primary"])

        b = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=c["accent2"],
            activeforeground="white",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 10, "bold"),
            padx=14,
            pady=8,
        )
        if width:
            b.config(width=width)
        return b

    def label(self, parent, text, size=10, bold=False, color=None):
        return tk.Label(
            parent,
            text=text,
            bg=self.colors["card"],
            fg=color or self.colors["text"],
            font=("Segoe UI", size, "bold" if bold else "normal"),
        )

    def card(self, parent, padx=20, pady=20):
        frame = tk.Frame(
            parent,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        frame.pack_propagate(False)
        frame.grid_propagate(False)
        return frame

    # --------------------------------------------------------
    # Login / Registration
    # --------------------------------------------------------

    def show_login(self):
        self.clear_window()
        self.setup_styles()
        self.configure(bg=self.colors["bg"])

        root = tk.Frame(self, bg=self.colors["bg"])
        root.pack(fill="both", expand=True)

        left = tk.Frame(root, bg=self.colors["sidebar"], width=500)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        tk.Label(
            left,
            text="ASSIGNMENT\nTRACKER",
            bg=self.colors["sidebar"],
            fg="white",
            font=("Segoe UI", 30, "bold"),
            justify="left",
        ).pack(anchor="w", padx=55, pady=(130, 15))

        tk.Label(
            left,
            text="A professional desktop solution for\n"
                 "assignment submission, tracking,\n"
                 "evaluation and academic reports.",
            bg=self.colors["sidebar"],
            fg="#B8C2D4",
            font=("Segoe UI", 13),
            justify="left",
        ).pack(anchor="w", padx=55)

        tk.Label(
            left,
            text="Student  •  Teacher  •  Admin",
            bg=self.colors["sidebar"],
            fg="#60A5FA",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=55, pady=35)

        right = tk.Frame(root, bg=self.colors["card"])
        right.pack(side="right", fill="both", expand=True)

        form = tk.Frame(right, bg=self.colors["card"], width=470)
        form.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            form,
            text="Welcome back",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 26, "bold"),
        ).pack(anchor="w")

        tk.Label(
            form,
            text="Sign in to continue to your dashboard",
            bg=self.colors["card"],
            fg=self.colors["muted"],
            font=("Segoe UI", 11),
        ).pack(anchor="w", pady=(4, 28))

        tk.Label(
            form, text="Email", bg=self.colors["card"],
            fg=self.colors["text"], font=("Segoe UI", 10, "bold")
        ).pack(anchor="w")

        email_var = tk.StringVar()
        email_entry = ttk.Entry(form, textvariable=email_var, width=48)
        email_entry.pack(fill="x", ipady=8, pady=(5, 18))

        tk.Label(
            form, text="Password", bg=self.colors["card"],
            fg=self.colors["text"], font=("Segoe UI", 10, "bold")
        ).pack(anchor="w")

        pass_var = tk.StringVar()
        pass_entry = ttk.Entry(form, textvariable=pass_var, show="•", width=48)
        pass_entry.pack(fill="x", ipady=8, pady=(5, 10))

        def toggle_password():
            pass_entry.config(show="" if pass_entry.cget("show") else "•")

        show_var = tk.BooleanVar()
        tk.Checkbutton(
            form,
            text="Show password",
            variable=show_var,
            command=toggle_password,
            bg=self.colors["card"],
            fg=self.colors["muted"],
            activebackground=self.colors["card"],
            activeforeground=self.colors["text"],
            selectcolor=self.colors["card"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(0, 20))

        def login():
            email = email_var.get().strip().lower()
            password = pass_var.get()

            if not email or not password:
                messagebox.showwarning("Login", "Please enter email and password.")
                return

            con = get_db()
            user = con.execute(
                "SELECT * FROM users WHERE lower(email)=?",
                (email,)
            ).fetchone()

            if user and verify_password(password, user["password"]):

                # Students must be approved by an administrator first.
                if user["role"] == "student":
                    approval = (
                        user["approval_status"]
                        if "approval_status" in user.keys()
                        else "approved"
                    )

                    if approval == "pending":
                        con.close()
                        messagebox.showwarning(
                            "Account Pending Approval",
                            "Your registration request has been sent to the administrator.\n\n"
                            "Please wait until an admin approves your account."
                        )
                        return

                    if approval == "rejected":
                        con.close()
                        messagebox.showerror(
                            "Registration Rejected",
                            "Your registration request was rejected by the administrator.\n\n"
                            "Please contact the administrator."
                        )
                        return

            if user and verify_password(password, user["password"]):
                # Upgrade legacy password storage after successful login
                if not user["password"].startswith("PBKDF2$"):
                    con.execute(
                        "UPDATE users SET password=? WHERE id=?",
                        (hash_password(password), user["id"]),
                    )
                    con.commit()

                self.current_user = dict(user)
                con.close()

                log_activity(
                    self.current_user["id"],
                    "Login",
                    "User logged into the system"
                )
                self.show_dashboard()
            else:
                con.close()
                messagebox.showerror(
                    "Login Failed",
                    "Invalid email or password."
                )

        self.button(form, "SIGN IN", login, "primary").pack(fill="x", pady=5)
        tk.Button(form, text="Forgot password?", command=self.show_forgot_password, bg=self.colors["card"], fg=self.colors["accent"], relief="flat", cursor="hand2").pack(anchor="e", pady=(4, 0))

        lower = tk.Frame(form, bg=self.colors["card"])
        lower.pack(fill="x", pady=18)

        tk.Label(
            lower,
            text="New student or teacher?",
            bg=self.colors["card"],
            fg=self.colors["muted"],
            font=("Segoe UI", 10),
        ).pack(side="left")

        reg_btn = tk.Button(
            lower,
            text="Create account",
            command=self.show_registration,
            bg=self.colors["card"],
            fg=self.colors["accent"],
            activebackground=self.colors["card"],
            activeforeground=self.colors["accent2"],
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 10, "bold"),
        )
        reg_btn.pack(side="left", padx=5)

        email_entry.focus_set()
        self.bind("<Return>", lambda e: login())

    def show_forgot_password(self):
        """Local recovery flow. No email service/OTP is configured."""
        win = tk.Toplevel(self)
        win.title("Recover Password")
        win.geometry("460x430")
        win.transient(self)
        box = tk.Frame(win, padx=22, pady=20, bg=self.colors["card"])
        box.pack(fill="both", expand=True)
        tk.Label(box, text="Recover Password", bg=self.colors["card"], fg=self.colors["text"], font=("Segoe UI", 17, "bold")).pack(anchor="w", pady=(0, 8))
        tk.Label(box, text="Enter your registered email and Student ID. For teacher accounts, enter the registered subject instead. This local demo does not send email OTPs.", bg=self.colors["card"], fg=self.colors["muted"], wraplength=400, justify="left").pack(anchor="w", pady=(0, 12))
        email = tk.StringVar(); identity = tk.StringVar(); newpw = tk.StringVar(); confirm = tk.StringVar()
        for label, var, show in [("Registered email", email, None), ("Student ID / Teacher subject", identity, None), ("New password", newpw, "*"), ("Confirm new password", confirm, "*")]:
            tk.Label(box, text=label, bg=self.colors["card"], fg=self.colors["text"]).pack(anchor="w", pady=(6, 2))
            ttk.Entry(box, textvariable=var, show=show).pack(fill="x", ipady=5)
        def recover():
            em = email.get().strip().lower(); ident = identity.get().strip()
            if not all([em, ident, newpw.get(), confirm.get()]):
                messagebox.showwarning("Recovery", "Fill in all fields.", parent=win); return
            if newpw.get() != confirm.get():
                messagebox.showerror("Recovery", "Passwords do not match.", parent=win); return
            ok, msg = validate_password(newpw.get())
            if not ok:
                messagebox.showwarning("Weak password", msg, parent=win); return
            con = get_db()
            user = con.execute("SELECT * FROM users WHERE lower(email)=?", (em,)).fetchone()
            valid = bool(user and ((user["role"] == "student" and (user["student_id"] or "").strip().lower() == ident.lower()) or (user["role"] == "teacher" and (user["teacher_subject"] or "").strip().lower() == ident.lower())))
            if not valid:
                con.close(); messagebox.showerror("Recovery", "The supplied account details could not be verified.", parent=win); return
            con.execute("UPDATE users SET password=? WHERE id=?", (hash_password(newpw.get()), user["id"]))
            con.commit(); con.close(); log_activity(user["id"], "Password Recovery", "Password reset through local identity check")
            messagebox.showinfo("Recovery", "Password updated. You can now sign in.", parent=win); win.destroy()
        self.button(box, "RESET PASSWORD", recover, "primary").pack(fill="x", pady=18)

    def show_registration(self):
        self.clear_window()
        self.setup_styles()

        outer = tk.Frame(self, bg=self.colors["bg"])
        outer.pack(fill="both", expand=True)

        box = tk.Frame(
            outer, bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1, width=560, height=650
        )
        box.place(relx=0.5, rely=0.5, anchor="center")
        box.pack_propagate(False)

        tk.Label(box, text="Create Account", bg=self.colors["card"],
                 fg=self.colors["text"], font=("Segoe UI", 24, "bold")).pack(
                     anchor="w", padx=40, pady=(28, 4))
        tk.Label(box, text="Register as a Student or Teacher. Admin approval is required.",
                 bg=self.colors["card"], fg=self.colors["muted"],
                 font=("Segoe UI", 10)).pack(anchor="w", padx=40, pady=(0, 15))

        vars_ = {k: tk.StringVar() for k in ("student_id","name","email","password","confirm")}
        role_var = tk.StringVar(value="student")
        teacher_subject_var = tk.StringVar(value="Python")

        role_row = tk.Frame(box, bg=self.colors["card"])
        role_row.pack(fill="x", padx=40, pady=(0, 8))
        tk.Label(role_row, text="Register As", bg=self.colors["card"], fg=self.colors["text"],
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        ttk.Radiobutton(role_row, text="Student", variable=role_var, value="student",
                        command=lambda: update_role()).pack(side="left", padx=15)
        ttk.Radiobutton(role_row, text="Teacher", variable=role_var, value="teacher",
                        command=lambda: update_role()).pack(side="left")

        student_id_label = tk.Label(box, text="Student ID / Enrollment Number", bg=self.colors["card"],
                                    fg=self.colors["text"], font=("Segoe UI", 10, "bold"))
        student_id_label.pack(anchor="w", padx=40, pady=(6, 4))
        student_id_entry = ttk.Entry(box, textvariable=vars_["student_id"])
        student_id_entry.pack(fill="x", padx=40, ipady=6)

        teacher_subject_label = tk.Label(box, text="Teacher Subject / Specialization", bg=self.colors["card"], fg=self.colors["text"], font=("Segoe UI", 10, "bold"))
        teacher_subject_combo = ttk.Combobox(box, textvariable=teacher_subject_var, values=["Python", "Java", "C", "C++", "Web Programming", "DBMS", "Computer Networks", "Operating Systems", "Mathematics", "Other"], state="readonly")

        for key, title in [("name","Full Name"),("email","Email"),("password","Password"),("confirm","Confirm Password")]:
            tk.Label(box, text=title, bg=self.colors["card"], fg=self.colors["text"],
                     font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=40, pady=(7, 3))
            e=ttk.Entry(box, textvariable=vars_[key], show="•" if key in ("password","confirm") else None)
            e.pack(fill="x", padx=40, ipady=6)

        tk.Label(box, text="Password: min 6 chars + capital + small letter + digit + symbol",
                 bg=self.colors["card"], fg=self.colors["muted"], font=("Segoe UI", 8)).pack(anchor="w", padx=40, pady=(4, 5))

        def update_role():
            is_student = role_var.get() == "student"
            student_id_label.config(text="Student ID / Enrollment Number" if is_student else "Student ID / Enrollment Number (not required for teacher)")
            student_id_entry.config(state="normal" if is_student else "disabled")
            if not is_student:
                vars_["student_id"].set("")
                teacher_subject_label.pack(anchor="w", padx=40, pady=(6, 4), before=next(w for w in box.winfo_children() if isinstance(w, tk.Label) and w.cget("text") == "Full Name"))
                teacher_subject_combo.pack(fill="x", padx=40, ipady=5, before=next(w for w in box.winfo_children() if isinstance(w, tk.Label) and w.cget("text") == "Full Name"))
            else:
                teacher_subject_label.pack_forget()
                teacher_subject_combo.pack_forget()

        def register():
            role=role_var.get()
            student_id=vars_["student_id"].get().strip().upper()
            name=vars_["name"].get().strip()
            email=vars_["email"].get().strip().lower()
            password=vars_["password"].get()
            confirm=vars_["confirm"].get()

            if not all([name,email,password,confirm]) or (role=="student" and not student_id):
                messagebox.showwarning("Registration", "Please fill all required fields.")
                return
            if role=="student" and (len(student_id)<3 or not all(ch.isalnum() or ch in "-_" for ch in student_id)):
                messagebox.showwarning("Registration", "Enter a valid Student ID / Enrollment Number.")
                return
            if "@" not in email or "." not in email:
                messagebox.showwarning("Registration", "Enter a valid email.")
                return
            ok,msg=validate_password(password)
            if not ok:
                messagebox.showwarning("Weak Password", msg)
                return
            if password != confirm:
                messagebox.showerror("Registration", "Passwords do not match.")
                return

            con=get_db()
            try:
                if role=="student":
                    existing=con.execute("SELECT id,name,email FROM users WHERE upper(trim(student_id))=upper(trim(?))",(student_id,)).fetchone()
                    if existing:
                        raise ValueError("This Student ID / Enrollment Number is already registered.")
                existing=con.execute("SELECT id FROM users WHERE lower(trim(email))=lower(trim(?))",(email,)).fetchone()
                if existing:
                    raise ValueError("This email is already registered.")
                con.execute("INSERT INTO users(student_id,name,email,password,role,approval_status,teacher_subject) VALUES(?,?,?,?,?,?,?)",
                             (student_id or None,name,email,hash_password(password),role,"pending",teacher_subject_var.get() if role == "teacher" else None))
                con.commit()
                messagebox.showinfo("Registration Submitted",
                    f"{role.title()} registration submitted successfully.\n\nAn administrator must approve your account before login.")
                self.show_login()
            except ValueError as e:
                con.close(); messagebox.showerror("Registration", str(e)); return
            except sqlite3.IntegrityError:
                con.rollback(); con.close(); messagebox.showerror("Registration", "Email or Student ID already exists."); return
            con.close()

        self.button(box,"CREATE ACCOUNT",register,"primary").pack(fill="x",padx=40,pady=13)
        self.button(box,"BACK TO LOGIN",self.show_login,"light").pack(fill="x",padx=40)
        update_role()

    def show_dashboard(self):
        self.clear_window()
        self.setup_styles()

        shell = tk.Frame(self, bg=self.colors["bg"])
        shell.pack(fill="both", expand=True)

        sidebar = tk.Frame(
            shell,
            bg=self.colors["sidebar"],
            width=235,
        )
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        content = tk.Frame(shell, bg=self.colors["bg"])
        content.pack(side="right", fill="both", expand=True)

        self.content_frame = content

        tk.Label(
            sidebar,
            text="ASSIGNMENT\nTRACKER",
            bg=self.colors["sidebar"],
            fg="white",
            font=("Segoe UI", 17, "bold"),
            justify="left",
        ).pack(anchor="w", padx=24, pady=(25, 28))

        user_name = self.current_user["name"]
        role = self.current_user["role"].upper()

        profile = tk.Frame(sidebar, bg=self.colors["sidebar2"])
        profile.pack(fill="x", padx=12, pady=(0, 20))

        tk.Label(
            profile,
            text=user_name,
            bg=self.colors["sidebar2"],
            fg="white",
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(12, 2))

        tk.Label(
            profile, text=role, bg=self.colors["sidebar2"], fg="#93C5FD",
            font=("Segoe UI", 9, "bold"), anchor="w"
        ).pack(fill="x", padx=12, pady=(0, 4))
        pic_path = self.current_user.get("profile_pic")
        if pic_path and os.path.exists(pic_path) and PIL_AVAILABLE:
            try:
                im = Image.open(pic_path).convert("RGB")
                # Crop to a consistent square so wide/tall photos never appear tiny.
                im = ImageOps.fit(im, (52, 52), method=Image.Resampling.LANCZOS, centering=(0.5, 0.35))
                self.sidebar_profile_image = ImageTk.PhotoImage(im)
                photo_frame = tk.Frame(profile, bg=self.colors["sidebar2"])
                photo_frame.pack(anchor="w", padx=12, pady=(0, 10))
                tk.Label(photo_frame, image=self.sidebar_profile_image, bg=self.colors["sidebar2"],
                         bd=0, highlightthickness=1, highlightbackground=self.colors["border"]).pack()
            except Exception:
                pass

        menu = [
            ("Dashboard", self.show_home),
            ("Assignments", self.show_assignments_page),
            (f"Notifications ({unread_notification_count(self.current_user['id'])})", self.show_notifications),
            ("Profile", self.show_profile),
            ("Change Password", self.show_change_password),
        ]

        if role == "STUDENT":
            menu.insert(2, ("My Submissions", self.show_student_history))
            menu.insert(3, ("My Performance", self.show_student_performance))

        elif role == "TEACHER":
            menu.insert(2, ("Create Assignment", self.show_create_assignment))
            menu.insert(3, ("Manage Assignments", self.show_manage_assignments))
            menu.insert(4, ("Submissions", self.show_teacher_submissions))
            menu.insert(5, ("Performance", self.show_teacher_performance))
            menu.insert(6, ("Student Approvals", self.show_teacher_approvals))

        elif role == "ADMIN":
            menu.insert(2, ("Users & Approvals", self.show_admin_users))
            menu.insert(3, ("System Statistics", self.show_admin_statistics))
            menu.insert(4, ("Activity Log", self.show_activity_log))

        for title, command in menu:
            b = tk.Button(
                sidebar,
                text="  " + title,
                command=command,
                anchor="w",
                bg=self.colors["sidebar"],
                fg="#D9E2F1",
                activebackground=self.colors["sidebar2"],
                activeforeground="white",
                relief="flat",
                bd=0,
                cursor="hand2",
                font=("Segoe UI", 10),
                padx=12,
                pady=10,
            )
            b.pack(fill="x", padx=8, pady=1)

        bottom = tk.Frame(sidebar, bg=self.colors["sidebar"])
        bottom.pack(side="bottom", fill="x", padx=8, pady=15)

        self.button(
            bottom, "☾  Dark Mode", self.toggle_theme, "dark"
        ).pack(fill="x", pady=3)

        # Keep Logout at the bottom of the sidebar, below Dark Mode.
        self.button(
            bottom, "↪  Logout", self.logout, "danger"
        ).pack(fill="x", pady=3)

        self.show_home()

    def logout(self):
        """Confirm logout, record it, clear the session, and show login."""
        if not self.current_user:
            self.show_login()
            return

        confirm = messagebox.askyesno(
            "Confirm Logout",
            "Are you sure you want to logout?",
            parent=self,
        )
        if not confirm:
            return

        log_activity(
            self.current_user["id"],
            "Logout",
            "User logged out"
        )
        self.current_user = None
        self.current_page = None
        self.show_login()

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.colors = DARK if self.dark_mode else LIGHT
        self.show_dashboard()

    def page_header(self, title, subtitle=""):
        for w in self.content_frame.winfo_children():
            w.destroy()

        top = tk.Frame(self.content_frame, bg=self.colors["bg"])
        top.pack(fill="x", padx=28, pady=(24, 15))

        tk.Label(
            top,
            text=title,
            bg=self.colors["bg"],
            fg=self.colors["text"],
            font=("Segoe UI", 24, "bold"),
        ).pack(anchor="w")

        if subtitle:
            tk.Label(
                top,
                text=subtitle,
                bg=self.colors["bg"],
                fg=self.colors["muted"],
                font=("Segoe UI", 10),
            ).pack(anchor="w", pady=(3, 0))

    # --------------------------------------------------------
    # Home Dashboard
    # --------------------------------------------------------

    def show_home(self):
        self.page_header(
            "Dashboard",
            f"Welcome, {self.current_user['name']}. Here is your academic activity overview."
        )

        body = tk.Frame(self.content_frame, bg=self.colors["bg"])
        body.pack(fill="both", expand=True, padx=28, pady=5)

        role = self.current_user["role"]

        if role == "student":
            self.student_home(body)
        elif role == "teacher":
            self.teacher_home(body)
        else:
            self.admin_home(body)

    def stat_card(self, parent, title, value, icon=""):
        # Give the card enough vertical space for icon, value and title.
        card = tk.Frame(
            parent,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
            height=135,
        )
        card.pack(side="left", fill="both", expand=True, padx=6)
        card.pack_propagate(False)

        tk.Label(
            card,
            text=icon,
            bg=self.colors["card"],
            fg=self.colors["accent"],
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w", padx=16, pady=(12, 0))

        tk.Label(
            card,
            text=str(value),
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 23, "bold"),
        ).pack(anchor="w", padx=16)

        tk.Label(
            card,
            text=title,
            bg=self.colors["card"],
            fg=self.colors["muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=16)

    def student_home(self, parent):
        con = get_db()

        assignments = con.execute(
            "SELECT * FROM assignments ORDER BY deadline"
        ).fetchall()

        total = len(assignments)
        submitted = 0
        reviewed = 0
        late = 0

        for a in assignments:
            sub = get_latest_submission(a["id"], self.current_user["id"])
            if sub:
                submitted += 1
                if sub["status"] == "Late":
                    late += 1
                if sub["marks"] is not None:
                    reviewed += 1

        con.close()

        stats = tk.Frame(parent, bg=self.colors["bg"])
        stats.pack(fill="x")

        self.stat_card(stats, "Total Assignments", total, "▣")
        self.stat_card(stats, "Submitted", submitted, "✓")
        self.stat_card(stats, "Reviewed", reviewed, "★")
        self.stat_card(stats, "Late", late, "!")

        lower = tk.Frame(parent, bg=self.colors["bg"])
        lower.pack(fill="both", expand=True, pady=18)

        upcoming = tk.Frame(
            lower,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        upcoming.pack(side="left", fill="both", expand=True, padx=(0, 8))

        tk.Label(
            upcoming,
            text="Upcoming Deadlines",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", padx=18, pady=15)

        tree = ttk.Treeview(
            upcoming,
            columns=("title", "subject", "deadline", "status"),
            show="headings",
            height=10,
        )
        for col, heading, width in [
            ("title", "Assignment", 220),
            ("subject", "Subject", 120),
            ("deadline", "Deadline", 150),
            ("status", "Status", 100),
        ]:
            tree.heading(col, text=heading)
            tree.column(col, width=width)

        tree.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        now = datetime.now()
        for a in assignments[:15]:
            try:
                deadline = parse_deadline(a["deadline"])
                if deadline < now:
                    continue
            except Exception:
                pass

            sub = get_latest_submission(a["id"], self.current_user["id"])
            status = sub["status"] if sub else "Pending"

            tree.insert(
                "",
                "end",
                values=(
                    a["title"],
                    a["subject"],
                    a["deadline"],
                    status,
                ),
            )

        notice = tk.Frame(
            lower,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
            width=300,
        )
        notice.pack(side="right", fill="y", padx=(8, 0))
        notice.pack_propagate(False)

        tk.Label(
            notice,
            text="Smart Reminder",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", padx=18, pady=(18, 8))

        upcoming_count = 0
        for a in assignments:
            try:
                d = parse_deadline(a["deadline"])
                if 0 <= (d - now).total_seconds() <= 3 * 86400:
                    sub = get_latest_submission(a["id"], self.current_user["id"])
                    if not sub:
                        upcoming_count += 1
            except Exception:
                pass

        message = (
            f"You have {upcoming_count} assignment(s) "
            f"due within the next 3 days."
            if upcoming_count else
            "No urgent pending deadline was detected."
        )

        tk.Label(
            notice,
            text=message,
            bg=self.colors["card"],
            fg=self.colors["muted"],
            wraplength=250,
            justify="left",
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=18, pady=8)

        self.button(
            notice,
            "View All Assignments",
            self.show_assignments_page,
            "primary",
        ).pack(fill="x", padx=18, pady=20)

    def teacher_home(self, parent):
        con = get_db()
        aid_rows = con.execute(
            "SELECT COUNT(*) AS c FROM assignments WHERE teacher_id=?",
            (self.current_user["id"],)
        ).fetchone()["c"]

        sub_count = con.execute("""
            SELECT COUNT(*) AS c
            FROM submissions s
            JOIN assignments a ON a.id=s.assignment_id
            WHERE a.teacher_id=?
        """, (self.current_user["id"],)).fetchone()["c"]

        reviewed = con.execute("""
            SELECT COUNT(*) AS c
            FROM submissions s
            JOIN assignments a ON a.id=s.assignment_id
            WHERE a.teacher_id=? AND s.marks IS NOT NULL
        """, (self.current_user["id"],)).fetchone()["c"]

        students = con.execute(
            "SELECT COUNT(*) AS c FROM users WHERE role='student'"
        ).fetchone()["c"]
        con.close()

        stats = tk.Frame(parent, bg=self.colors["bg"])
        stats.pack(fill="x")

        self.stat_card(stats, "My Assignments", aid_rows, "▣")
        self.stat_card(stats, "Submissions", sub_count, "↓")
        self.stat_card(stats, "Reviewed", reviewed, "★")
        self.stat_card(stats, "Students", students, "♙")

        lower = tk.Frame(parent, bg=self.colors["bg"])
        lower.pack(fill="both", expand=True, pady=18)

        info = tk.Frame(
            lower,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        info.pack(fill="both", expand=True)

        tk.Label(
            info,
            text="Teacher Workspace",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=25, pady=(25, 5))

        tk.Label(
            info,
            text="Create assignments, track student submissions, review work, "
                 "enter marks and feedback, and generate performance reports.",
            bg=self.colors["card"],
            fg=self.colors["muted"],
            font=("Segoe UI", 11),
            wraplength=700,
            justify="left",
        ).pack(anchor="w", padx=25, pady=5)

        actions = tk.Frame(info, bg=self.colors["card"])
        actions.pack(anchor="w", padx=25, pady=25)

        self.button(
            actions, "Create Assignment",
            self.show_create_assignment, "primary"
        ).pack(side="left", padx=(0, 10))

        self.button(
            actions, "Review Submissions",
            self.show_teacher_submissions, "success"
        ).pack(side="left", padx=(0, 10))

        # Logout button shown directly in the Teacher Dashboard workspace.
        self.button(
            actions, "↪ Logout",
            self.logout, "danger"
        ).pack(side="left")

    def admin_home(self, parent):
        con = get_db()

        users = con.execute(
            "SELECT COUNT(*) AS c FROM users"
        ).fetchone()["c"]
        assignments = con.execute(
            "SELECT COUNT(*) AS c FROM assignments"
        ).fetchone()["c"]
        submissions = con.execute(
            "SELECT COUNT(*) AS c FROM submissions"
        ).fetchone()["c"]
        logs = con.execute(
            "SELECT COUNT(*) AS c FROM activity_log"
        ).fetchone()["c"]
        pending = con.execute(
            "SELECT COUNT(*) AS c FROM users "
            "WHERE role IN ('student','teacher') AND approval_status='pending'"
        ).fetchone()["c"]
        con.close()

        stats = tk.Frame(parent, bg=self.colors["bg"])
        stats.pack(fill="x")

        self.stat_card(stats, "Users", users, "♙")
        self.stat_card(stats, "Assignments", assignments, "▣")
        self.stat_card(stats, "Submissions", submissions, "↓")
        self.stat_card(stats, "Activity Events", logs, "◷")
        self.stat_card(stats, "Pending Requests", pending, "⏳")

        info = tk.Frame(
            parent,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        info.pack(fill="both", expand=True, pady=18)

        tk.Label(
            info,
            text="Administration Center",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=25, pady=(25, 8))

        tk.Label(
            info,
            text="Manage users, monitor system statistics and inspect the audit log.",
            bg=self.colors["card"],
            fg=self.colors["muted"],
            font=("Segoe UI", 11),
        ).pack(anchor="w", padx=25)

    # --------------------------------------------------------
    # Assignment List + Search
    # --------------------------------------------------------

    def show_assignments_page(self):
        self.page_header(
            "Assignments",
            "Search assignments, check deadlines and manage submissions."
        )

        wrapper = tk.Frame(self.content_frame, bg=self.colors["bg"])
        wrapper.pack(fill="both", expand=True, padx=28, pady=5)

        filters = tk.Frame(
            wrapper,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        filters.pack(fill="x", pady=(0, 10))

        search_var = tk.StringVar()
        subject_var = tk.StringVar(value="All")
        status_var = tk.StringVar(value="All")

        tk.Label(
            filters, text="Search",
            bg=self.colors["card"], fg=self.colors["text"],
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(15, 5), pady=12)

        search = ttk.Entry(filters, textvariable=search_var, width=28)
        search.pack(side="left", ipady=5)

        tk.Label(
            filters, text="Subject",
            bg=self.colors["card"], fg=self.colors["text"],
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(20, 5))

        subject_combo = ttk.Combobox(
            filters,
            textvariable=subject_var,
            state="readonly",
            width=16,
        )
        subject_combo.pack(side="left")

        tk.Label(
            filters, text="Status",
            bg=self.colors["card"], fg=self.colors["text"],
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(20, 5))

        status_combo = ttk.Combobox(
            filters,
            textvariable=status_var,
            values=["All", "Pending", "Submitted", "Late", "Reviewed"],
            state="readonly",
            width=13,
        )
        status_combo.pack(side="left")

        tree_frame = tk.Frame(
            wrapper,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        tree_frame.pack(fill="both", expand=True)

        columns = (
            "id", "title", "subject", "deadline",
            "status", "marks", "max_marks", "remaining"
        )
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings")

        headings = {
            "id": "ID",
            "title": "Assignment",
            "subject": "Subject",
            "deadline": "Deadline",
            "status": "Status",
            "marks": "Marks",
            "max_marks": "Max",
            "remaining": "Time Left",
        }
        widths = {
            "id": 50, "title": 230, "subject": 110,
            "deadline": 145, "status": 95, "marks": 70,
            "max_marks": 60, "remaining": 150
        }

        for col in columns:
            tree.heading(col, text=headings[col])
            tree.column(col, width=widths[col], anchor="center")

        tree.pack(fill="both", expand=True, side="left", padx=8, pady=8)

        scrollbar = ttk.Scrollbar(
            tree_frame, orient="vertical", command=tree.yview
        )
        scrollbar.pack(side="right", fill="y", pady=8)
        tree.configure(yscrollcommand=scrollbar.set)

        con = get_db()
        if self.current_user["role"] == "teacher":
            rows = con.execute("""
                SELECT * FROM assignments
                WHERE teacher_id=?
                ORDER BY deadline
            """, (self.current_user["id"],)).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM assignments ORDER BY deadline"
            ).fetchall()
        con.close()

        subjects = ["All"] + sorted({r["subject"] for r in rows})
        subject_combo["values"] = subjects

        row_map = {}

        def refresh():
            for item in tree.get_children():
                tree.delete(item)
            row_map.clear()

            search_text = search_var.get().strip().lower()
            selected_subject = subject_var.get()
            selected_status = status_var.get()

            for a in rows:
                if search_text and search_text not in (
                    a["title"] + " " +
                    a["subject"] + " " +
                    (a["description"] or "")
                ).lower():
                    continue

                if selected_subject != "All" and a["subject"] != selected_subject:
                    continue

                status = "Pending"
                marks = ""

                if self.current_user["role"] == "student":
                    sub = get_latest_submission(
                        a["id"], self.current_user["id"]
                    )
                    if sub:
                        status = sub["status"]
                        marks = "" if sub["marks"] is None else str(sub["marks"])
                        if sub["marks"] is not None:
                            status = "Reviewed"
                elif self.current_user["role"] == "teacher":
                    con2 = get_db()
                    count = con2.execute("""
                        SELECT COUNT(*) AS c
                        FROM submissions
                        WHERE assignment_id=?
                    """, (a["id"],)).fetchone()["c"]
                    con2.close()
                    status = f"{count} submissions"

                if selected_status != "All" and selected_status not in status:
                    continue

                remaining = self.time_remaining(a["deadline"])

                iid = tree.insert(
                    "",
                    "end",
                    values=(
                        a["id"],
                        a["title"],
                        a["subject"],
                        a["deadline"],
                        status,
                        marks,
                        a["max_marks"],
                        remaining,
                    ),
                )
                row_map[iid] = a

        refresh()

        search_var.trace_add("write", lambda *args: refresh())
        subject_var.trace_add("write", lambda *args: refresh())
        status_var.trace_add("write", lambda *args: refresh())

        actions = tk.Frame(wrapper, bg=self.colors["bg"])
        actions.pack(fill="x", pady=10)

        def details():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("Assignment", "Select an assignment.")
                return
            self.show_assignment_details(row_map[selected[0]])

        self.button(
            actions, "View Details", details, "primary"
        ).pack(side="left")

        if self.current_user["role"] == "student":
            def submit():
                selected = tree.selection()
                if not selected:
                    messagebox.showwarning(
                        "Submission", "Select an assignment."
                    )
                    return
                self.submit_assignment(row_map[selected[0]])

            self.button(
                actions, "Submit / Replace", submit, "success"
            ).pack(side="left", padx=8)

    def time_remaining(self, deadline_text):
        try:
            deadline = parse_deadline(deadline_text)
            diff = deadline - datetime.now()

            if diff.total_seconds() <= 0:
                return "Deadline passed"

            days = diff.days
            hours = diff.seconds // 3600
            minutes = (diff.seconds % 3600) // 60

            if days > 0:
                return f"{days}d {hours}h {minutes}m"
            return f"{hours}h {minutes}m"
        except Exception:
            return "-"

    def show_assignment_details(self, assignment):
        win = tk.Toplevel(self)
        win.title("Assignment Details")
        win.geometry("620x550")
        win.configure(bg=self.colors["bg"])
        win.transient(self)
        win.grab_set()

        box = tk.Frame(
            win,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        box.pack(fill="both", expand=True, padx=25, pady=25)

        tk.Label(
            box,
            text=assignment["title"],
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w", padx=25, pady=(25, 5))

        info = (
            f"Subject: {assignment['subject']}\n"
            f"Deadline: {assignment['deadline']}\n"
            f"Maximum Marks: {assignment['max_marks']}\n"
            f"Time Remaining: {self.time_remaining(assignment['deadline'])}"
        )

        tk.Label(
            box,
            text=info,
            bg=self.colors["card"],
            fg=self.colors["muted"],
            justify="left",
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=25, pady=10)

        tk.Label(
            box,
            text="Description",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=25, pady=(15, 5))

        desc = tk.Text(
            box,
            height=9,
            wrap="word",
            bg=self.colors["input"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief="flat",
            font=("Segoe UI", 10),
        )
        desc.pack(fill="both", expand=True, padx=25, pady=5)
        desc.insert("1.0", assignment["description"] or "No description provided.")
        desc.config(state="disabled")

        if self.current_user["role"] == "student":
            self.button(
                box,
                "Submit / Replace Assignment",
                lambda: [win.destroy(), self.submit_assignment(assignment)],
                "success",
            ).pack(fill="x", padx=25, pady=20)

    # --------------------------------------------------------
    # Student Submission
    # --------------------------------------------------------

    def submit_assignment(self, assignment):
        path = filedialog.askopenfilename(
            title="Select Assignment File",
            filetypes=[
                ("Documents", "*.pdf *.docx *.txt *.py *.doc"),
                ("All Files", "*.*"),
            ],
        )
        if not path:
            return

        latest = get_latest_submission(
            assignment["id"], self.current_user["id"]
        )

        if latest:
            con_check = get_db()
            req = con_check.execute("SELECT status FROM resubmission_requests WHERE assignment_id=? AND student_id=? ORDER BY id DESC LIMIT 1", (assignment["id"], self.current_user["id"])).fetchone()
            con_check.close()
            if not req or req["status"] != "approved":
                messagebox.showwarning("Teacher approval required", "A submission already exists. Request teacher approval before uploading/replacing any version, whether or not it has been reviewed.")
                return
            version = latest["version"] + 1
            if not messagebox.askyesno("Resubmit", f"Teacher approval found. Upload version {version}?"):
                return
        else:
            version = 1
            if datetime.now() > parse_deadline(assignment["deadline"]):
                req_con = get_db()
                late_req = req_con.execute("SELECT status FROM resubmission_requests WHERE assignment_id=? AND student_id=? ORDER BY id DESC LIMIT 1", (assignment["id"], self.current_user["id"])).fetchone()
                req_con.close()
                if late_req and late_req["status"] == "approved":
                    pass  # Teacher approved this first late submission.
                else:
                    if late_req and late_req["status"] == "pending":
                        messagebox.showinfo("Request pending", "Your late-submission request is waiting for teacher approval.")
                        return
                    messagebox.showwarning("Deadline passed", "The deadline has passed. You must request teacher approval before submitting this assignment.")
                    reason_win = tk.Toplevel(self)
                    reason_win.title("Request Late Submission")
                    reason_win.geometry("500x330")
                    reason_box = tk.Frame(reason_win, padx=18, pady=18, bg=self.colors["card"])
                    reason_box.pack(fill="both", expand=True)
                    tk.Label(reason_box, text="Explain why you need late submission approval:", bg=self.colors["card"], fg=self.colors["text"], wraplength=440, justify="left").pack(anchor="w", pady=(0, 8))
                    reason_text = tk.Text(reason_box, height=7, wrap="word")
                    reason_text.pack(fill="both", expand=True)
                    def send_late_request():
                        why = reason_text.get("1.0", "end").strip()
                        if len(why) < 5:
                            messagebox.showwarning("Request", "Please enter a reason of at least 5 characters.", parent=reason_win); return
                        con_req = get_db()
                        existing_req = con_req.execute("SELECT status FROM resubmission_requests WHERE assignment_id=? AND student_id=? ORDER BY id DESC LIMIT 1", (assignment["id"], self.current_user["id"])).fetchone()
                        if existing_req and existing_req["status"] == "pending":
                            con_req.close(); messagebox.showinfo("Request", "A request is already pending for this assignment.", parent=reason_win); return
                        con_req.execute("INSERT INTO resubmission_requests(assignment_id,student_id,reason,requested_at) VALUES(?,?,?,?)", (assignment["id"], self.current_user["id"], why, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                        con_req.commit(); con_req.close()
                        if assignment["teacher_id"]:
                            create_notification(assignment["teacher_id"], "Late Submission Request", f"{self.current_user['name']} requested permission to submit {assignment['title']} late.")
                        log_activity(self.current_user["id"], "Late Submission Request", assignment["title"])
                        reason_win.destroy(); messagebox.showinfo("Request sent", "Your request was sent. Upload is available after the teacher approves it.")
                    self.button(reason_box, "SEND APPROVAL REQUEST", send_late_request, "primary").pack(fill="x", pady=(10, 0))
                    return

        ext = os.path.splitext(path)[1]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_name = safe_filename(
            f"student_{self.current_user['id']}_"
            f"assignment_{assignment['id']}_"
            f"v{version}_{timestamp}{ext}"
        )
        destination = os.path.join(UPLOAD_DIR, new_name)

        try:
            shutil.copy2(path, destination)
        except Exception as e:
            messagebox.showerror(
                "Upload Error", f"Could not save the file.\n{e}"
            )
            return

        submission_time = datetime.now()
        deadline = parse_deadline(assignment["deadline"])
        status = calculate_status(deadline, submission_time)

        con = get_db()

        # New versions are fresh reviews. Previous marks/feedback are not copied.
        con.execute("""
            INSERT INTO submissions
            (assignment_id, student_id, file_name, submission_time,
             status, marks, feedback, version)
            VALUES (?, ?, ?, ?, ?, NULL, NULL, ?)
        """, (
            assignment["id"],
            self.current_user["id"],
            new_name,
            submission_time.strftime("%Y-%m-%d %H:%M:%S"),
            status,
            version,
        ))

        con.execute("UPDATE resubmission_requests SET status='used', reviewed_at=? WHERE assignment_id=? AND student_id=? AND status='approved'",(datetime.now().strftime("%Y-%m-%d %H:%M:%S"),assignment["id"],self.current_user["id"]))
        teacher_row=con.execute("SELECT teacher_id FROM assignments WHERE id=?",(assignment["id"],)).fetchone(); con.commit(); con.close()
        if teacher_row and teacher_row["teacher_id"]: create_notification(teacher_row["teacher_id"],"New Submission",f"{self.current_user['name']} submitted {assignment['title']} (Version {version}).")

        log_activity(
            self.current_user["id"],
            "Submit Assignment",
            f"{assignment['title']} - Version {version} - {status}"
        )

        messagebox.showinfo(
            "Submission Successful",
            f"Assignment submitted successfully as Version {version}.\n"
            f"Status: {status}"
        )

        self.show_assignments_page()

    def show_student_history(self):
        self.page_header(
            "My Submissions",
            "View version history, files, marks and teacher feedback."
        )

        wrapper = tk.Frame(self.content_frame, bg=self.colors["bg"])
        wrapper.pack(fill="both", expand=True, padx=28, pady=5)

        top = tk.Frame(wrapper, bg=self.colors["bg"])
        top.pack(fill="x", pady=(0, 10))

        selected_var = tk.StringVar(value="All Assignments")

        con = get_db()
        assignments = con.execute(
            "SELECT * FROM assignments ORDER BY deadline"
        ).fetchall()
        con.close()

        values = ["All Assignments"] + [a["title"] for a in assignments]

        ttk.Combobox(
            top,
            textvariable=selected_var,
            values=values,
            state="readonly",
            width=35,
        ).pack(side="left")

        tree_frame = tk.Frame(
            wrapper,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        tree_frame.pack(fill="both", expand=True)

        columns = (
            "id", "assignment", "version", "file",
            "time", "status", "marks", "feedback"
        )
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings")

        heads = {
            "id": "ID",
            "assignment": "Assignment",
            "version": "Version",
            "file": "File",
            "time": "Submitted",
            "status": "Status",
            "marks": "Marks",
            "feedback": "Feedback",
        }

        widths = {
            "id": 50, "assignment": 200, "version": 75,
            "file": 250, "time": 150, "status": 90,
            "marks": 80, "feedback": 250,
        }

        for col in columns:
            tree.heading(col, text=heads[col])
            tree.column(col, width=widths[col])

        tree.pack(fill="both", expand=True, padx=8, pady=8)

        row_map = {}

        def refresh():
            for i in tree.get_children():
                tree.delete(i)
            row_map.clear()

            selected = selected_var.get()

            con2 = get_db()
            rows = con2.execute("""
                SELECT s.*, a.title AS assignment_title
                FROM submissions s
                JOIN assignments a ON a.id=s.assignment_id
                WHERE s.student_id=?
                ORDER BY s.assignment_id, s.version DESC
            """, (self.current_user["id"],)).fetchall()
            con2.close()

            for r in rows:
                if selected != "All Assignments" and r["assignment_title"] != selected:
                    continue

                iid = tree.insert(
                    "",
                    "end",
                    values=(
                        r["id"],
                        r["assignment_title"],
                        r["version"],
                        r["file_name"],
                        r["submission_time"],
                        r["status"],
                        "" if r["marks"] is None else r["marks"],
                        r["feedback"] or "",
                    )
                )
                row_map[iid] = r

        refresh()
        selected_var.trace_add("write", lambda *args: refresh())

        actions = tk.Frame(wrapper, bg=self.colors["bg"])
        actions.pack(fill="x", pady=10)

        def open_selected():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("File", "Select a submission.")
                return
            r = row_map[sel[0]]
            open_file(os.path.join(UPLOAD_DIR, r["file_name"]))

        def download_selected():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Download", "Select a submission.")
                return
            r = row_map[sel[0]]
            destination = filedialog.asksaveasfilename(
                initialfile=r["file_name"],
                title="Save Submission As",
            )
            if destination:
                try:
                    shutil.copy2(
                        os.path.join(UPLOAD_DIR, r["file_name"]),
                        destination
                    )
                    messagebox.showinfo(
                        "Download",
                        "Submission copied successfully."
                    )
                except Exception as e:
                    messagebox.showerror("Download", str(e))

        def delete_all_versions():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Delete", "Select a submission.")
                return

            messagebox.showwarning("Deletion disabled", "Students cannot delete or replace submitted work. Contact your teacher and request permission if a correction is needed.")

        self.button(
            actions, "Open File", open_selected, "primary"
        ).pack(side="left")
        self.button(
            actions, "Download", download_selected, "success"
        ).pack(side="left", padx=8)
        self.button(
            actions, "Delete All Versions", delete_all_versions, "danger"
        ).pack(side="left")

        def request_resubmission():
            sel=tree.selection()
            if not sel: messagebox.showwarning("Resubmission","Select a reviewed submission."); return
            r=row_map[sel[0]]
            con=get_db(); req=con.execute("SELECT status FROM resubmission_requests WHERE assignment_id=? AND student_id=? ORDER BY id DESC LIMIT 1",(r["assignment_id"],self.current_user["id"])).fetchone(); con.close()
            if req and req["status"] in ("pending","approved"): messagebox.showinfo("Resubmission",f"Request is already {req['status']}."); return
            win=tk.Toplevel(self); win.title("Request Resubmission"); win.geometry("520x350"); win.configure(bg=self.colors["bg"])
            box=tk.Frame(win,bg=self.colors["card"]); box.pack(fill="both",expand=True,padx=20,pady=20)
            tk.Label(box,text="Reason for resubmission",bg=self.colors["card"],fg=self.colors["text"],font=("Segoe UI",12,"bold")).pack(anchor="w",padx=20,pady=(20,8))
            reason=tk.Text(box,height=8,wrap="word",bg=self.colors["input"],fg=self.colors["text"],insertbackground=self.colors["text"],relief="flat"); reason.pack(fill="both",expand=True,padx=20)
            def send():
                why=reason.get("1.0","end").strip()
                if len(why)<5: messagebox.showwarning("Resubmission","Enter a reason."); return
                con=get_db(); con.execute("INSERT INTO resubmission_requests(assignment_id,student_id,reason,requested_at) VALUES(?,?,?,?)",(r["assignment_id"],self.current_user["id"],why,datetime.now().strftime("%Y-%m-%d %H:%M:%S"))); teacher=con.execute("SELECT teacher_id FROM assignments WHERE id=?",(r["assignment_id"],)).fetchone(); con.commit(); con.close()
                if teacher and teacher["teacher_id"]: create_notification(teacher["teacher_id"],"Resubmission Request",f"{self.current_user['name']} requested resubmission for {r['assignment_title']}.")
                log_activity(self.current_user["id"],"Request Resubmission",r["assignment_title"]); win.destroy(); messagebox.showinfo("Request Sent","Request sent to teacher.")
            self.button(box,"SEND REQUEST",send,"primary").pack(fill="x",padx=20,pady=18)
        self.button(actions,"Request Resubmission",request_resubmission,"warning").pack(side="left",padx=8)

    # --------------------------------------------------------
    # Student Performance
    # --------------------------------------------------------

    def show_notifications(self):
        self.page_header("Notifications", "Deadline alerts, resubmission requests, review updates and system messages.")
        wrapper = tk.Frame(self.content_frame, bg=self.colors["bg"])
        wrapper.pack(fill="both", expand=True, padx=28, pady=5)

        # Reconcile pending requests into the teacher's notification inbox.
        if self.current_user.get("role", "").upper() == "TEACHER":
            con = get_db()
            pending = con.execute("""
                SELECT r.id, r.student_id, r.assignment_id, r.requested_at,
                       u.name AS student_name, a.title AS assignment_title
                FROM resubmission_requests r
                JOIN users u ON u.id = r.student_id
                JOIN assignments a ON a.id = r.assignment_id
                WHERE a.teacher_id = ? AND r.status = 'pending'
                ORDER BY r.id DESC
            """, (self.current_user["id"],)).fetchall()
            for request in pending:
                message = f"{request['student_name']} requested resubmission for {request['assignment_title']}."
                exists = con.execute("""
                    SELECT id FROM notifications
                    WHERE user_id = ? AND title = 'Resubmission Request' AND message = ?
                """, (self.current_user["id"], message)).fetchone()
                if not exists:
                    con.execute("""
                        INSERT INTO notifications(user_id, title, message, created_at, is_read)
                        VALUES(?, 'Resubmission Request', ?, ?, 0)
                    """, (self.current_user["id"], message, request["requested_at"]))
            con.commit()
            con.close()

        # Show all notifications for the logged-in user and mark them read once opened.
        con = get_db()
        rows = con.execute(
            "SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 100",
            (self.current_user["id"],)
        ).fetchall()
        con.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (self.current_user["id"],))
        con.commit()
        con.close()

        if self.current_user.get("role", "").upper() == "TEACHER":
            con = get_db()
            pending_count = con.execute("""
                SELECT COUNT(*) AS total FROM resubmission_requests r
                JOIN assignments a ON a.id = r.assignment_id
                WHERE a.teacher_id = ? AND r.status = 'pending'
            """, (self.current_user["id"],)).fetchone()["total"]
            con.close()
            action_bar = tk.Frame(wrapper, bg=self.colors["bg"])
            action_bar.pack(fill="x", pady=(0, 10))
            self.button(
                action_bar,
                f"Review Pending Resubmission Requests ({pending_count})",
                self.show_resubmission_requests,
                "warning"
            ).pack(side="left")

        # Quick approval/deletion panel: handle pending registrations directly here.
        role = self.current_user.get("role", "").lower()
        if role in ("admin", "teacher"):
            con = get_db()
            if role == "admin":
                pending_users = con.execute("SELECT id,name,email,role,approval_status FROM users WHERE role IN ('student','teacher') AND approval_status='pending' ORDER BY id").fetchall()
            else:
                pending_users = con.execute("SELECT id,name,email,role,approval_status FROM users WHERE role='student' AND approval_status='pending' ORDER BY id").fetchall()
            con.close()
            tk.Label(wrapper, text=f"Pending Registration Requests ({len(pending_users)})", bg=self.colors["bg"], fg=self.colors["text"], font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 6))
            pframe = tk.Frame(wrapper, bg=self.colors["card"])
            pframe.pack(fill="x", pady=(0, 12))
            pending_tree = ttk.Treeview(pframe, columns=("name", "email", "role"), show="headings", height=4)
            for c,h,w in [("name","Name",190),("email","Email",260),("role","Role",100)]:
                pending_tree.heading(c,text=h); pending_tree.column(c,width=w)
            pending_tree.pack(fill="x", padx=6, pady=6)
            pending_map = {}
            for u in pending_users:
                iid = pending_tree.insert("","end",values=(u["name"],u["email"],u["role"].title()))
                pending_map[iid] = u
            def quick_approve():
                sel = pending_tree.selection()
                if not sel:
                    messagebox.showwarning("Approval", "Select a pending registration first."); return
                u = pending_map[sel[0]]
                con = get_db(); con.execute("UPDATE users SET approval_status='approved' WHERE id=? AND approval_status='pending'", (u["id"],)); con.commit(); con.close()
                create_notification(u["id"], "Registration Approved", f"Your {u['role']} account has been approved. You can now login.")
                log_activity(self.current_user["id"], "Approve Registration", f"{u['role']} {u['name']} ({u['email']})")
                messagebox.showinfo("Approved", f"{u['name']} has been approved."); self.show_notifications()
            def quick_delete():
                sel = pending_tree.selection()
                if not sel:
                    messagebox.showwarning("Delete", "Select a pending registration first."); return
                u = pending_map[sel[0]]
                if not messagebox.askyesno("Delete Registration", f"Permanently delete pending account for {u['name']}?"): return
                con = get_db(); con.execute("DELETE FROM users WHERE id=? AND approval_status='pending'", (u["id"],)); con.commit(); con.close()
                log_activity(self.current_user["id"], "Delete Pending Registration", f"{u['role']} {u['name']} ({u['email']})")
                messagebox.showinfo("Deleted", "Pending registration deleted."); self.show_notifications()
            quick_actions = tk.Frame(wrapper, bg=self.colors["bg"]); quick_actions.pack(fill="x", pady=(0,10))
            self.button(quick_actions, "Approve Selected", quick_approve, "success").pack(side="left")
            self.button(quick_actions, "Delete Selected", quick_delete, "danger").pack(side="left", padx=8)

        frame = tk.Frame(wrapper, bg=self.colors["card"])
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=("title", "message", "time"), show="headings")
        for col, head, width in [("title", "Notification", 190), ("message", "Message", 560), ("time", "Time", 170)]:
            tree.heading(col, text=head)
            tree.column(col, width=width)
        tree.pack(fill="both", expand=True, padx=8, pady=8)
        for r in rows:
            tree.insert("", "end", values=(r["title"], r["message"], r["created_at"]))

    def show_student_performance(self):
        self.page_header(
            "My Performance",
            "Grade summary and visual performance analysis."
        )

        wrapper = tk.Frame(self.content_frame, bg=self.colors["bg"])
        wrapper.pack(fill="both", expand=True, padx=28, pady=5)

        con = get_db()
        rows = con.execute("""
            SELECT s.*, a.title, a.subject, a.max_marks
            FROM submissions s
            JOIN assignments a ON a.id=s.assignment_id
            WHERE s.student_id=? AND s.marks IS NOT NULL
            AND s.version = (
                SELECT MAX(s2.version)
                FROM submissions s2
                WHERE s2.assignment_id=s.assignment_id
                AND s2.student_id=s.student_id
            )
            ORDER BY a.subject, a.title
        """, (self.current_user["id"],)).fetchall()
        con.close()

        total_marks = sum(float(r["marks"]) for r in rows)
        total_max = sum(float(r["max_marks"]) for r in rows)

        percentage = (total_marks / total_max * 100) if total_max else 0

        stats = tk.Frame(wrapper, bg=self.colors["bg"])
        stats.pack(fill="x")

        self.stat_card(stats, "Assignments Reviewed", len(rows), "★")
        self.stat_card(stats, "Marks Obtained", f"{total_marks:g}", "✓")
        self.stat_card(stats, "Maximum Marks", f"{total_max:g}", "▣")
        self.stat_card(stats, "Percentage", f"{percentage:.2f}%", "%")

        table = tk.Frame(
            wrapper,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        table.pack(fill="both", expand=True, pady=18)

        tree = ttk.Treeview(
            table,
            columns=("title", "subject", "marks", "max", "percent"),
            show="headings",
        )

        for col, head, width in [
            ("title", "Assignment", 300),
            ("subject", "Subject", 150),
            ("marks", "Marks", 100),
            ("max", "Max", 100),
            ("percent", "Percentage", 120),
        ]:
            tree.heading(col, text=head)
            tree.column(col, width=width)

        tree.pack(fill="both", expand=True, padx=8, pady=8)

        for r in rows:
            pct = float(r["marks"]) / float(r["max_marks"]) * 100
            tree.insert(
                "",
                "end",
                values=(
                    r["title"],
                    r["subject"],
                    r["marks"],
                    r["max_marks"],
                    f"{pct:.2f}%",
                )
            )

        actions = tk.Frame(wrapper, bg=self.colors["bg"])
        actions.pack(fill="x")

        self.button(
            actions,
            "Show Performance Chart",
            lambda: self.show_student_chart(rows),
            "primary"
        ).pack(side="left")

        self.button(
            actions,
            "Export CSV",
            lambda: self.export_student_report(rows, "csv"),
            "success"
        ).pack(side="left", padx=8)

        self.button(
            actions,
            "Export PDF",
            lambda: self.export_student_report(rows, "pdf"),
            "warning"
        ).pack(side="left")

    def show_student_chart(self, rows):
        if not MATPLOTLIB_AVAILABLE:
            messagebox.showerror(
                "Chart",
                "Matplotlib is not installed.\nRun: pip install matplotlib"
            )
            return

        if not rows:
            messagebox.showinfo("Chart", "No reviewed assignments available.")
            return

        titles = [r["title"][:18] for r in rows]
        percentages = [
            float(r["marks"]) / float(r["max_marks"]) * 100
            for r in rows
        ]

        plt.figure(figsize=(10, 5))
        plt.bar(titles, percentages)
        plt.ylabel("Percentage")
        plt.xlabel("Assignments")
        plt.title("Student Performance")
        plt.xticks(rotation=30, ha="right")
        plt.ylim(0, 100)
        plt.tight_layout()
        plt.show()

    def export_student_report(self, rows, kind):
        if kind == "csv":
            path = filedialog.asksaveasfilename(
                initialdir=EXPORT_DIR,
                defaultextension=".csv",
                filetypes=[("CSV", "*.csv")],
                initialfile="student_performance.csv",
            )
            if not path:
                return

            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Assignment", "Subject", "Marks", "Maximum Marks", "Percentage"
                ])
                for r in rows:
                    pct = float(r["marks"]) / float(r["max_marks"]) * 100
                    writer.writerow([
                        r["title"], r["subject"],
                        r["marks"], r["max_marks"], f"{pct:.2f}%"
                    ])

            messagebox.showinfo("Export", "CSV report exported successfully.")
            return

        if not REPORTLAB_AVAILABLE:
            messagebox.showerror(
                "PDF Export",
                "ReportLab is not installed.\nRun: pip install reportlab"
            )
            return

        path = filedialog.asksaveasfilename(
            initialdir=EXPORT_DIR,
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile="student_performance.pdf",
        )
        if not path:
            return

        c = canvas.Canvas(path, pagesize=A4)
        width, height = A4

        y = height - 55
        c.setFont("Helvetica-Bold", 17)
        c.drawString(45, y, "Student Performance Report")
        y -= 25

        c.setFont("Helvetica", 10)
        c.drawString(45, y, f"Student: {self.current_user['name']}")
        y -= 25

        for r in rows:
            pct = float(r["marks"]) / float(r["max_marks"]) * 100
            line = (
                f"{r['title']} | {r['subject']} | "
                f"{r['marks']}/{r['max_marks']} | {pct:.2f}%"
            )
            c.drawString(45, y, line[:105])
            y -= 18

            if y < 55:
                c.showPage()
                y = height - 55
                c.setFont("Helvetica", 10)

        c.save()
        messagebox.showinfo("Export", "PDF report exported successfully.")

    # --------------------------------------------------------
    # Teacher: Create / Manage
    # --------------------------------------------------------

    def choose_deadline(self, variable, parent=None):
        """Open a small built-in calendar/time picker and put the result in variable."""
        parent = parent or self
        now = datetime.now()

        # Try to start from the value already present.
        try:
            selected = parse_deadline(variable.get().strip())
            year, month, day = selected.year, selected.month, selected.day
            hour, minute = selected.hour, selected.minute
        except Exception:
            year, month, day = now.year, now.month, now.day
            minute = ((now.minute + 4) // 5) * 5
            hour = now.hour
            if minute >= 60:
                minute = 0
                hour = (hour + 1) % 24

        win = tk.Toplevel(parent)
        win.title("Choose Deadline")
        win.geometry("390x475")
        win.resizable(False, False)
        win.configure(bg=self.colors["card"])
        win.transient(parent)
        win.grab_set()

        state = {"year": year, "month": month, "day": day}

        header = tk.Frame(win, bg=self.colors["sidebar2"])
        header.pack(fill="x")

        month_label = tk.Label(
            header, bg=self.colors["sidebar2"], fg="white",
            font=("Segoe UI", 12, "bold")
        )
        month_label.pack(side="left", padx=15, pady=12)

        body = tk.Frame(win, bg=self.colors["card"])
        body.pack(fill="both", expand=True, padx=15, pady=10)

        weekdays = tk.Frame(body, bg=self.colors["card"])
        weekdays.pack(fill="x")
        for i, name in enumerate(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")):
            tk.Label(
                weekdays, text=name, width=4,
                bg=self.colors["card"], fg=self.colors["muted"],
                font=("Segoe UI", 9, "bold")
            ).grid(row=0, column=i, pady=4)

        days_frame = tk.Frame(body, bg=self.colors["card"])
        days_frame.pack(fill="x")

        def render_calendar():
            for w in days_frame.winfo_children():
                w.destroy()
            month_label.config(text=f"{calendar.month_name[state['month']]} {state['year']}")
            weeks = calendar.monthcalendar(state["year"], state["month"])
            for r, week in enumerate(weeks):
                for c, day_num in enumerate(week):
                    if day_num == 0:
                        tk.Label(days_frame, text="", width=4, height=2,
                                 bg=self.colors["card"]).grid(row=r, column=c)
                        continue
                    selected_day = day_num == state["day"]
                    b = tk.Button(
                        days_frame, text=str(day_num), width=4, height=2,
                        relief="flat", bd=0, cursor="hand2",
                        bg=self.colors["accent"] if selected_day else self.colors["card"],
                        fg="white" if selected_day else self.colors["text"],
                        activebackground=self.colors["accent2"],
                        activeforeground="white",
                        command=lambda d=day_num: select_day(d),
                    )
                    b.grid(row=r, column=c, padx=1, pady=1)

        def previous_month():
            state["month"] -= 1
            if state["month"] == 0:
                state["month"] = 12
                state["year"] -= 1
            state["day"] = min(
                state["day"],
                calendar.monthrange(state["year"], state["month"])[1]
            )
            render_calendar()

        def next_month():
            state["month"] += 1
            if state["month"] == 13:
                state["month"] = 1
                state["year"] += 1
            state["day"] = min(
                state["day"],
                calendar.monthrange(state["year"], state["month"])[1]
            )
            render_calendar()

        nav = tk.Frame(header, bg=self.colors["sidebar2"])
        nav.pack(side="right", padx=8)
        tk.Button(nav, text="‹", command=previous_month, width=3,
                  bg=self.colors["sidebar2"], fg="white", relief="flat",
                  font=("Segoe UI", 12, "bold")).pack(side="left")
        tk.Button(nav, text="›", command=next_month, width=3,
                  bg=self.colors["sidebar2"], fg="white", relief="flat",
                  font=("Segoe UI", 12, "bold")).pack(side="left")

        def select_day(day_num):
            state["day"] = day_num
            render_calendar()

        render_calendar()

        time_box = tk.Frame(win, bg=self.colors["card"])
        time_box.pack(fill="x", padx=20, pady=(4, 8))

        tk.Label(time_box, text="Time", bg=self.colors["card"],
                 fg=self.colors["text"], font=("Segoe UI", 10, "bold")).pack(anchor="w")

        time_row = tk.Frame(time_box, bg=self.colors["card"])
        time_row.pack(anchor="w", pady=5)

        hour_var = tk.StringVar(value=f"{hour:02d}")
        minute_var = tk.StringVar(value=f"{minute:02d}")

        ttk.Combobox(time_row, textvariable=hour_var, width=5, state="readonly",
                     values=[f"{h:02d}" for h in range(24)]).pack(side="left")
        tk.Label(time_row, text=":", bg=self.colors["card"], fg=self.colors["text"],
                 font=("Segoe UI", 11, "bold")).pack(side="left", padx=4)
        ttk.Combobox(time_row, textvariable=minute_var, width=5, state="readonly",
                     values=[f"{m:02d}" for m in range(0, 60, 5)]).pack(side="left")

        tk.Label(
            win, text="Select a date and time for the assignment deadline.",
            bg=self.colors["card"], fg=self.colors["muted"],
            font=("Segoe UI", 9)
        ).pack(pady=(0, 8))

        def apply():
            try:
                h = int(hour_var.get())
                m = int(minute_var.get())
                value = datetime(
                    state["year"], state["month"], state["day"], h, m
                )
                if value <= datetime.now():
                    if not messagebox.askyesno(
                        "Past Deadline",
                        "The selected deadline is in the past. Use it anyway?",
                        parent=win,
                    ):
                        return
                variable.set(value.strftime("%Y-%m-%d %H:%M"))
                win.destroy()
            except Exception:
                messagebox.showerror("Deadline", "Please select a valid date and time.", parent=win)

        actions = tk.Frame(win, bg=self.colors["card"])
        actions.pack(fill="x", padx=20, pady=(0, 18))
        self.button(actions, "SET DEADLINE", apply, "success").pack(side="left", fill="x", expand=True)
        self.button(actions, "CANCEL", win.destroy, "light").pack(side="left", fill="x", expand=True, padx=(8, 0))

    def deadline_picker_row(self, parent, variable, label_text="Deadline"):
        """Create a deadline entry with a calendar button."""
        tk.Label(
            parent, text=label_text, bg=self.colors["card"],
            fg=self.colors["text"], font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", pady=(5, 4))

        row = tk.Frame(parent, bg=self.colors["card"])
        row.pack(fill="x", pady=(0, 10))
        entry = ttk.Entry(row, textvariable=variable)
        entry.pack(side="left", fill="x", expand=True, ipady=7)
        self.button(
            row, "📅 Choose from Calendar",
            lambda: self.choose_deadline(variable, row), "primary"
        ).pack(side="left", padx=(8, 0))
        return entry

    def show_create_assignment(self):
        self.current_page = "create_assignment"
        self.page_header(
            "Create Assignment",
            "Add a new assignment with subject, description and deadline."
        )

        wrapper = tk.Frame(self.content_frame, bg=self.colors["bg"])
        wrapper.pack(fill="both", expand=True, padx=28, pady=5)

        box = tk.Frame(
            wrapper,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        box.pack(fill="both", expand=True)

        form = tk.Frame(box, bg=self.colors["card"])
        form.pack(fill="both", expand=True, padx=35, pady=25)

        teacher_subject = (self.current_user.get("teacher_subject") or "").strip()
        vars_ = {
            "title": tk.StringVar(),
            "subject": tk.StringVar(value=teacher_subject),
            "deadline": tk.StringVar(),
            "max_marks": tk.StringVar(value="30"),
        }

        for key, text in [
            ("title", "Assignment Title"),
            ("subject", "Subject"),
        ]:
            tk.Label(
                form, text=text, bg=self.colors["card"],
                fg=self.colors["text"], font=("Segoe UI", 10, "bold")
            ).pack(anchor="w", pady=(5, 4))

            if key == "subject" and self.current_user["role"] == "teacher":
                if teacher_subject:
                    ttk.Entry(form, textvariable=vars_[key], state="readonly").pack(fill="x", ipady=7, pady=(0, 10))
                else:
                    ttk.Combobox(form, textvariable=vars_[key], values=["Python", "Java", "C", "C++", "Web Programming", "DBMS", "Computer Networks", "Operating Systems", "Mathematics", "Other"], state="readonly").pack(fill="x", ipady=7, pady=(0, 10))
            else:
                ttk.Entry(form, textvariable=vars_[key]).pack(fill="x", ipady=7, pady=(0, 10))

        self.deadline_picker_row(form, vars_["deadline"], "Deadline")

        tk.Label(
            form, text="Maximum Marks", bg=self.colors["card"],
            fg=self.colors["text"], font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", pady=(5, 4))
        ttk.Entry(form, textvariable=vars_["max_marks"]).pack(
            fill="x", ipady=7, pady=(0, 10)
        )

        tk.Label(
            form, text="Description", bg=self.colors["card"],
            fg=self.colors["text"], font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", pady=(5, 4))

        desc = tk.Text(
            form,
            height=8,
            wrap="word",
            bg=self.colors["input"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief="flat",
        )
        desc.pack(fill="both", expand=True, pady=(0, 15))

        def create():
            title = vars_["title"].get().strip()
            subject = vars_["subject"].get().strip()
            deadline = vars_["deadline"].get().strip()
            max_marks = vars_["max_marks"].get().strip()
            description = desc.get("1.0", "end").strip()

            if self.current_user["role"] == "teacher" and teacher_subject and subject.strip().lower() != teacher_subject.lower():
                messagebox.showerror("Subject restriction", f"You can only create {teacher_subject} assignments.")
                return
            if not title or not subject or not deadline:
                messagebox.showwarning(
                    "Create Assignment",
                    "Title, subject and deadline are required."
                )
                return

            try:
                parse_deadline(deadline)
                max_marks_int = int(max_marks)
                if max_marks_int <= 0:
                    raise ValueError
            except Exception:
                messagebox.showerror(
                    "Create Assignment",
                    "Use a valid deadline and positive maximum marks."
                )
                return

            con = get_db()
            con.execute("""
                INSERT INTO assignments
                (title, subject, description, deadline, max_marks, teacher_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                title, subject, description, deadline,
                max_marks_int, self.current_user["id"]
            ))
            con.commit()
            con.close()

            log_activity(
                self.current_user["id"],
                "Create Assignment",
                title
            )

            messagebox.showinfo(
                "Success",
                "Assignment created successfully."
            )
            self.show_manage_assignments()

        self.button(form, "CREATE ASSIGNMENT", create, "primary").pack(
            fill="x"
        )

    def show_manage_assignments(self):
        self.current_page = "manage_assignments"
        self.page_header(
            "Manage Assignments",
            "Edit or delete assignments created by you."
        )

        wrapper = tk.Frame(self.content_frame, bg=self.colors["bg"])
        wrapper.pack(fill="both", expand=True, padx=28, pady=5)

        tree_frame = tk.Frame(
            wrapper,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        tree_frame.pack(fill="both", expand=True)

        tree = ttk.Treeview(
            tree_frame,
            columns=("id", "title", "subject", "deadline", "max"),
            show="headings",
        )

        for col, head, width in [
            ("id", "ID", 60),
            ("title", "Title", 300),
            ("subject", "Subject", 160),
            ("deadline", "Deadline", 180),
            ("max", "Max Marks", 100),
        ]:
            tree.heading(col, text=head)
            tree.column(col, width=width)

        tree.pack(fill="both", expand=True, padx=8, pady=8)

        con = get_db()
        rows = con.execute("""
            SELECT * FROM assignments
            WHERE teacher_id=? AND (?='' OR lower(trim(subject))=lower(trim(?)))
            ORDER BY deadline
        """, (self.current_user["id"], self.current_user.get("teacher_subject") or "", self.current_user.get("teacher_subject") or "")).fetchall()
        con.close()

        row_map = {}

        for r in rows:
            iid = tree.insert(
                "",
                "end",
                values=(
                    r["id"], r["title"], r["subject"],
                    r["deadline"], r["max_marks"]
                )
            )
            row_map[iid] = r

        actions = tk.Frame(wrapper, bg=self.colors["bg"])
        actions.pack(fill="x", pady=10)

        def get_selected():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning(
                    "Assignment", "Select an assignment."
                )
                return None
            return row_map[sel[0]]

        self.button(
            actions,
            "Edit",
            lambda: self.edit_assignment(get_selected()),
            "primary"
        ).pack(side="left")

        def delete():
            a = get_selected()
            if not a:
                return

            if not messagebox.askyesno(
                "Delete Assignment",
                "Delete this assignment and all related submissions/files?"
            ):
                return

            con2 = get_db()
            subs = con2.execute(
                "SELECT file_name FROM submissions WHERE assignment_id=?",
                (a["id"],)
            ).fetchall()

            for s in subs:
                p = os.path.join(UPLOAD_DIR, s["file_name"])
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

            con2.execute(
                "DELETE FROM submissions WHERE assignment_id=?",
                (a["id"],)
            )
            con2.execute(
                "DELETE FROM assignments WHERE id=? AND teacher_id=?",
                (a["id"], self.current_user["id"])
            )
            con2.commit()
            con2.close()

            log_activity(
                self.current_user["id"],
                "Delete Assignment",
                a["title"]
            )

            messagebox.showinfo(
                "Delete",
                "Assignment deleted successfully."
            )
            self.show_manage_assignments()

        self.button(
            actions, "Delete", delete, "danger"
        ).pack(side="left", padx=8)

    def edit_assignment(self, assignment):
        if not assignment:
            return

        win = tk.Toplevel(self)
        win.title("Edit Assignment")
        win.geometry("600x650")
        win.configure(bg=self.colors["bg"])
        win.transient(self)
        win.grab_set()

        box = tk.Frame(
            win,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        box.pack(fill="both", expand=True, padx=25, pady=25)

        vars_ = {
            "title": tk.StringVar(value=assignment["title"]),
            "subject": tk.StringVar(value=assignment["subject"]),
            "deadline": tk.StringVar(value=assignment["deadline"]),
            "max": tk.StringVar(value=str(assignment["max_marks"])),
        }

        for key, text in [
            ("title", "Title"),
            ("subject", "Subject"),
        ]:
            tk.Label(
                box, text=text, bg=self.colors["card"],
                fg=self.colors["text"], font=("Segoe UI", 10, "bold")
            ).pack(anchor="w", padx=25, pady=(15, 4))

            if key == "subject" and self.current_user.get("teacher_subject"):
                ttk.Entry(box, textvariable=vars_[key], state="readonly").pack(fill="x", padx=25, ipady=7)
            else:
                ttk.Entry(box, textvariable=vars_[key]).pack(fill="x", padx=25, ipady=7)

        # Calendar-based deadline picker
        deadline_row = tk.Frame(box, bg=self.colors["card"])
        deadline_row.pack(fill="x", padx=25)
        tk.Label(
            deadline_row, text="Deadline", bg=self.colors["card"],
            fg=self.colors["text"], font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", pady=(15, 4))
        deadline_controls = tk.Frame(deadline_row, bg=self.colors["card"])
        deadline_controls.pack(fill="x")
        ttk.Entry(deadline_controls, textvariable=vars_["deadline"]).pack(
            side="left", fill="x", expand=True, ipady=7
        )
        self.button(
            deadline_controls, "📅 Calendar",
            lambda: self.choose_deadline(vars_["deadline"], win), "primary"
        ).pack(side="left", padx=(8, 0))

        tk.Label(
            box, text="Maximum Marks", bg=self.colors["card"],
            fg=self.colors["text"], font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", padx=25, pady=(15, 4))
        ttk.Entry(box, textvariable=vars_["max"]).pack(
            fill="x", padx=25, ipady=7
        )

        tk.Label(
            box, text="Description", bg=self.colors["card"],
            fg=self.colors["text"], font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", padx=25, pady=(15, 4))

        desc = tk.Text(
            box,
            height=9,
            wrap="word",
            bg=self.colors["input"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief="flat",
        )
        desc.pack(fill="both", expand=True, padx=25)
        desc.insert("1.0", assignment["description"] or "")

        def save():
            special = (self.current_user.get("teacher_subject") or "").strip()
            if special and vars_["subject"].get().strip().lower() != special.lower():
                messagebox.showerror("Subject restriction", f"You can only manage {special} assignments.")
                return
            try:
                parse_deadline(vars_["deadline"].get().strip())
                max_marks = int(vars_["max"].get().strip())
                if max_marks <= 0:
                    raise ValueError
            except Exception:
                messagebox.showerror(
                    "Edit Assignment",
                    "Invalid deadline or maximum marks."
                )
                return

            con = get_db()
            con.execute("""
                UPDATE assignments
                SET title=?, subject=?, description=?, deadline=?, max_marks=?
                WHERE id=? AND teacher_id=?
            """, (
                vars_["title"].get().strip(),
                vars_["subject"].get().strip(),
                desc.get("1.0", "end").strip(),
                vars_["deadline"].get().strip(),
                max_marks,
                assignment["id"],
                self.current_user["id"],
            ))
            con.commit()
            con.close()

            log_activity(
                self.current_user["id"],
                "Edit Assignment",
                assignment["title"]
            )

            win.destroy()
            self.show_manage_assignments()

        self.button(box, "SAVE CHANGES", save, "success").pack(
            fill="x", padx=25, pady=20
        )

    # --------------------------------------------------------
    # Teacher: Submissions / Review
    # --------------------------------------------------------

    def show_teacher_submissions(self):
        self.page_header(
            "Student Submissions",
            "Review files, enter marks, edit feedback and manage submissions."
        )

        wrapper = tk.Frame(self.content_frame, bg=self.colors["bg"])
        wrapper.pack(fill="both", expand=True, padx=28, pady=5)

        filters = tk.Frame(
            wrapper,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        filters.pack(fill="x", pady=(0, 10))

        search_var = tk.StringVar()

        tk.Label(
            filters,
            text="Search student / assignment",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(15, 6), pady=12)

        ttk.Entry(
            filters,
            textvariable=search_var,
            width=35,
        ).pack(side="left", ipady=5)

        tree_frame = tk.Frame(
            wrapper,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        tree_frame.pack(fill="both", expand=True)

        columns = (
            "id", "student", "assignment", "version",
            "submitted", "status", "marks", "feedback", "file"
        )
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings")

        heads = {
            "id": "ID", "student": "Student",
            "assignment": "Assignment", "version": "Ver.",
            "submitted": "Submitted", "status": "Status",
            "marks": "Marks", "feedback": "Feedback",
            "file": "File",
        }

        widths = {
            "id": 50, "student": 150, "assignment": 220,
            "version": 55, "submitted": 150, "status": 90,
            "marks": 70, "feedback": 220, "file": 240
        }

        for col in columns:
            tree.heading(col, text=heads[col])
            tree.column(col, width=widths[col])

        tree.pack(fill="both", expand=True, padx=8, pady=8)

        row_map = {}

        def refresh():
            for item in tree.get_children():
                tree.delete(item)
            row_map.clear()

            con = get_db()
            rows = con.execute("""
                SELECT s.*, u.name AS student_name,
                       a.title AS assignment_title
                FROM submissions s
                JOIN users u ON u.id=s.student_id
                JOIN assignments a ON a.id=s.assignment_id
                WHERE a.teacher_id=? AND (?='' OR lower(trim(a.subject))=lower(trim(?)))
                ORDER BY s.submission_time DESC
            """, (self.current_user["id"], self.current_user.get("teacher_subject") or "", self.current_user.get("teacher_subject") or "")).fetchall()
            con.close()

            q = search_var.get().strip().lower()

            for r in rows:
                combined = (
                    f"{r['student_name']} {r['assignment_title']} "
                    f"{r['file_name']} {r['feedback'] or ''}"
                ).lower()

                if q and q not in combined:
                    continue

                iid = tree.insert(
                    "",
                    "end",
                    values=(
                        r["id"],
                        r["student_name"],
                        r["assignment_title"],
                        r["version"],
                        r["submission_time"],
                        "Reviewed" if r["marks"] is not None else r["status"],
                        "" if r["marks"] is None else r["marks"],
                        r["feedback"] or "",
                        r["file_name"],
                    )
                )
                row_map[iid] = r

        refresh()
        search_var.trace_add("write", lambda *args: refresh())

        actions = tk.Frame(wrapper, bg=self.colors["bg"])
        actions.pack(fill="x", pady=10)

        def selected():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning(
                    "Submission", "Select a submission."
                )
                return None
            return row_map[sel[0]]

        def open_file_selected():
            r = selected()
            if r:
                open_file(os.path.join(UPLOAD_DIR, r["file_name"]))

        def download_file_selected():
            r = selected()
            if not r:
                return

            destination = filedialog.asksaveasfilename(
                initialfile=r["file_name"],
                title="Download Submission",
            )
            if destination:
                try:
                    shutil.copy2(
                        os.path.join(UPLOAD_DIR, r["file_name"]),
                        destination
                    )
                    messagebox.showinfo(
                        "Download",
                        "File downloaded successfully."
                    )
                except Exception as e:
                    messagebox.showerror("Download", str(e))

        self.button(
            actions, "Open File", open_file_selected, "primary"
        ).pack(side="left")

        self.button(
            actions, "Download", download_file_selected, "success"
        ).pack(side="left", padx=8)

        self.button(
            actions,
            "Review / Edit",
            lambda: self.review_submission(selected(), refresh),
            "warning",
        ).pack(side="left")

        def delete_submission():
            r = selected()
            if not r:
                return

            if r["marks"] is not None:
                messagebox.showwarning("Deletion blocked", "Reviewed submissions are retained for audit history and cannot be deleted here.")
                return
            check = get_db()
            owner = check.execute("SELECT a.teacher_id, a.subject FROM assignments a WHERE a.id=?", (r["assignment_id"],)).fetchone()
            check.close()
            subject = (self.current_user.get("teacher_subject") or "").strip()
            if not owner or owner["teacher_id"] != self.current_user["id"] or (subject and owner["subject"].strip().lower() != subject.lower()):
                messagebox.showerror("Permission denied", "You cannot delete submissions outside your own subject assignments.")
                return
            if not messagebox.askyesno("Delete Submission", "Delete this unreviewed submission record and its file? This cannot be undone."):
                return

            p = os.path.join(UPLOAD_DIR, r["file_name"])
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

            con2 = get_db()
            con2.execute(
                "DELETE FROM submissions WHERE id=?",
                (r["id"],)
            )
            con2.commit()
            con2.close()

            log_activity(
                self.current_user["id"],
                "Delete Submission",
                f"Submission ID {r['id']}"
            )

            refresh()

        self.button(
            actions, "Delete", delete_submission, "danger"
        ).pack(side="left", padx=8)
        self.button(actions,"Resubmission Requests",self.show_resubmission_requests,"warning").pack(side="left",padx=8)

    def show_resubmission_requests(self):
        win=tk.Toplevel(self); win.title("Resubmission Requests"); win.geometry("900x500"); win.configure(bg=self.colors["bg"])
        wrapper=tk.Frame(win,bg=self.colors["bg"]); wrapper.pack(fill="both",expand=True,padx=18,pady=18)
        tree=ttk.Treeview(wrapper,columns=("student","assignment","reason","status","time"),show="headings")
        for col,head,width in [("student","Student",150),("assignment","Assignment",190),("reason","Reason",330),("status","Status",100),("time","Requested",160)]: tree.heading(col,text=head); tree.column(col,width=width)
        tree.pack(fill="both",expand=True); row_map={}
        def refresh():
            for i in tree.get_children(): tree.delete(i)
            row_map.clear(); con=get_db(); rows=con.execute("SELECT r.*,u.name student_name,a.title assignment_title FROM resubmission_requests r JOIN users u ON u.id=r.student_id JOIN assignments a ON a.id=r.assignment_id WHERE a.teacher_id=? AND (?='' OR lower(trim(a.subject))=lower(trim(?))) ORDER BY r.id DESC",(self.current_user["id"], self.current_user.get("teacher_subject") or "", self.current_user.get("teacher_subject") or "")).fetchall(); con.close()
            for r in rows: row_map[tree.insert("","end",values=(r["student_name"],r["assignment_title"],r["reason"],r["status"],r["requested_at"]))]=r
        refresh(); actions=tk.Frame(wrapper,bg=self.colors["bg"]); actions.pack(fill="x",pady=10)
        def decide(status):
            sel=tree.selection()
            if not sel: messagebox.showwarning("Request","Select a request."); return
            r=row_map[sel[0]]
            if r["status"]!="pending": messagebox.showinfo("Request","This request is already processed."); return
            con=get_db(); con.execute("UPDATE resubmission_requests SET status=?,reviewed_at=? WHERE id=?",(status,datetime.now().strftime("%Y-%m-%d %H:%M:%S"),r["id"])); con.commit(); con.close()
            create_notification(r["student_id"],"Resubmission "+status.title(),f"Your resubmission request for {r['assignment_title']} was {status}."); log_activity(self.current_user["id"],"Resubmission Request",f"{r['assignment_title']} - {status}"); refresh()
        self.button(actions,"Approve",lambda:decide("approved"),"success").pack(side="left"); self.button(actions,"Reject",lambda:decide("rejected"),"danger").pack(side="left",padx=8); self.button(actions,"Close",win.destroy,"light").pack(side="right")

    def review_submission(self, submission, refresh_callback):
        if not submission:
            return
        if self.current_user and self.current_user.get("role") == "teacher":
            check = get_db()
            allowed = check.execute("SELECT a.teacher_id, a.subject FROM assignments a WHERE a.id=?", (submission["assignment_id"],)).fetchone()
            check.close()
            special = (self.current_user.get("teacher_subject") or "").strip()
            if not allowed or allowed["teacher_id"] != self.current_user["id"] or (special and allowed["subject"].strip().lower() != special.lower()):
                messagebox.showerror("Permission denied", "You can only review assignments assigned to you and within your subject.")
                return

        con = get_db()
        assignment = con.execute(
            "SELECT * FROM assignments WHERE id=?",
            (submission["assignment_id"],)
        ).fetchone()
        con.close()

        win = tk.Toplevel(self)
        win.title("Review Submission")
        win.geometry("760x700")
        win.minsize(680, 620)
        win.configure(bg=self.colors["bg"])
        win.transient(self)
        win.grab_set()

        box = tk.Frame(win, bg=self.colors["card"], highlightbackground=self.colors["border"], highlightthickness=1)
        box.pack(fill="both", expand=True, padx=18, pady=18)

        tk.Label(box, text=f"Review: {submission['assignment_title']}", bg=self.colors["card"], fg=self.colors["text"], font=("Segoe UI", 17, "bold")).pack(anchor="w", padx=20, pady=(18, 4))
        tk.Label(box, text=f"Student: {submission['student_name']}   |   Version: {submission['version']}\nMaximum Marks: {assignment['max_marks']}", bg=self.colors["card"], fg=self.colors["muted"], justify="left", font=("Segoe UI", 10)).pack(anchor="w", padx=20, pady=5)

        # Fixed practical evaluation split requested for this project.
        # Worksheet = 8, Viva = 10, Implementation = 12 (total = 30).
        max_marks = float(assignment["max_marks"] or 0)
        rubric_maxima = {
            "Worksheet Marks": 8.0,
            "Viva Marks": 10.0,
            "Implementation Marks": 12.0,
        }
        grading_total_max = sum(rubric_maxima.values())
        rubric_names = list(rubric_maxima.keys())
        con_r = get_db()
        saved_rubrics = con_r.execute("SELECT criterion, score, feedback FROM rubric_scores WHERE submission_id=?", (submission["id"],)).fetchall()
        con_r.close()
        saved_map = {x["criterion"]: x for x in saved_rubrics}

        rubric_frame = tk.LabelFrame(box, text="Evaluation (Worksheet /8, Viva /10, Implementation /12; Total /30)", bg=self.colors["card"], fg=self.colors["text"], padx=10, pady=8)
        rubric_frame.pack(fill="x", padx=20, pady=(12, 8))
        rubric_vars = {}
        rubric_feedback_vars = {}
        tk.Label(rubric_frame, text="Section", bg=self.colors["card"], fg=self.colors["text"], font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", padx=5, pady=4)
        tk.Label(rubric_frame, text="Marks", bg=self.colors["card"], fg=self.colors["text"], font=("Segoe UI", 9, "bold")).grid(row=0, column=1, sticky="w", padx=5, pady=4)
        tk.Label(rubric_frame, text="Feedback (optional)", bg=self.colors["card"], fg=self.colors["text"], font=("Segoe UI", 9, "bold")).grid(row=0, column=2, sticky="w", padx=5, pady=4)

        for idx, criterion in enumerate(rubric_names, start=1):
            tk.Label(rubric_frame, text=criterion, bg=self.colors["card"], fg=self.colors["text"]).grid(row=idx, column=0, sticky="w", padx=5, pady=5)
            saved = saved_map.get(criterion)
            score_var = tk.StringVar(value=str(saved["score"] if saved else "0"))
            rubric_vars[criterion] = score_var
            ttk.Entry(rubric_frame, textvariable=score_var, width=10).grid(row=idx, column=1, sticky="ew", padx=5, pady=5)
            fb_var = tk.StringVar(value=(saved["feedback"] or "") if saved else "")
            rubric_feedback_vars[criterion] = fb_var
            ttk.Entry(rubric_frame, textvariable=fb_var).grid(row=idx, column=2, sticky="ew", padx=5, pady=5)
        rubric_frame.columnconfigure(2, weight=1)

        total_var = tk.StringVar(value="Total: 0")
        tk.Label(box, textvariable=total_var, bg=self.colors["card"], fg=self.colors["text"], font=("Segoe UI", 12, "bold")).pack(anchor="e", padx=22, pady=(0, 6))

        def update_total(*_):
            total = 0.0
            for var in rubric_vars.values():
                try:
                    total += float(var.get().strip() or 0)
                except ValueError:
                    pass
            total_var.set(f"Total: {total:g} / {max_marks:g}")
        for var in rubric_vars.values():
            var.trace_add("write", update_total)
        update_total()

        tk.Label(box, text="Overall Feedback", bg=self.colors["card"], fg=self.colors["text"], font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=20, pady=(8, 4))
        feedback = tk.Text(box, height=4, wrap="word", bg=self.colors["input"], fg=self.colors["text"], insertbackground=self.colors["text"], relief="flat")
        feedback.pack(fill="both", expand=True, padx=20, pady=(0, 8))
        feedback.insert("1.0", submission["feedback"] or "")

        def save():
            rubric_values = []
            for criterion in rubric_names:
                try:
                    score = float(rubric_vars[criterion].get().strip())
                    criterion_max = rubric_maxima[criterion]
                    if score < 0 or score > criterion_max:
                        raise ValueError
                except (ValueError, TypeError):
                    messagebox.showerror("Invalid Marks", f"{criterion} must be between 0 and {rubric_maxima[criterion]:g}.", parent=win)
                    return
                rubric_values.append((criterion, score, rubric_feedback_vars[criterion].get().strip()))

            marks = round(sum(item[1] for item in rubric_values), 2)
            if marks > grading_total_max:
                messagebox.showerror("Invalid Total", f"Total marks cannot exceed {grading_total_max:g}.", parent=win)
                return
            feedback_text = feedback.get("1.0", "end").strip()
            con2 = get_db()
            con2.execute("UPDATE submissions SET marks=?, feedback=?, status='Reviewed' WHERE id=?", (marks, feedback_text or None, submission["id"]))
            for criterion, score, criterion_feedback in rubric_values:
                con2.execute("""INSERT INTO rubric_scores(submission_id, criterion, score, max_score, feedback) VALUES(?,?,?,?,?)
                    ON CONFLICT(submission_id, criterion) DO UPDATE SET score=excluded.score, max_score=excluded.max_score, feedback=excluded.feedback""",
                    (submission["id"], criterion, score, rubric_maxima[criterion], criterion_feedback or None))
            con2.commit()
            student_id = submission["student_id"]
            con2.close()
            create_notification(student_id, "Assignment Reviewed", f"Your submission for {submission['assignment_title']} has been reviewed. Marks: {marks:g}/{max_marks:g}.")
            log_activity(self.current_user["id"], "Review Submission", f"Submission ID {submission['id']}; marks {marks:g}/{max_marks:g}")
            win.destroy()
            refresh_callback()
            messagebox.showinfo("Saved", f"Review submitted successfully. Total: {marks:g}/{max_marks:g}.")

        actions = tk.Frame(box, bg=self.colors["card"])
        actions.pack(fill="x", padx=20, pady=(0, 16))
        self.button(actions, "SUBMIT REVIEW", save, "success").pack(side="right", padx=(8, 0))
        self.button(actions, "CANCEL", win.destroy, "light").pack(side="right")

    # --------------------------------------------------------
    # Teacher Performance
    # --------------------------------------------------------

    def show_teacher_performance(self):
        self.page_header(
            "Class Performance",
            "Analyze reviewed submissions across your assignments."
        )

        wrapper = tk.Frame(self.content_frame, bg=self.colors["bg"])
        wrapper.pack(fill="both", expand=True, padx=28, pady=5)

        con = get_db()
        rows = con.execute("""
            SELECT a.title, a.subject, a.max_marks,
                   s.marks, u.name AS student_name
            FROM submissions s
            JOIN assignments a ON a.id=s.assignment_id
            JOIN users u ON u.id=s.student_id
            WHERE a.teacher_id=? AND s.marks IS NOT NULL
            AND s.version = (
                SELECT MAX(s2.version)
                FROM submissions s2
                WHERE s2.assignment_id=s.assignment_id
                AND s2.student_id=s.student_id
            )
            ORDER BY a.title, u.name
        """, (self.current_user["id"],)).fetchall()
        con.close()

        total = len(rows)
        average = (
            sum(float(r["marks"]) / float(r["max_marks"]) * 100 for r in rows)
            / total
            if total else 0
        )

        stats = tk.Frame(wrapper, bg=self.colors["bg"])
        stats.pack(fill="x")

        self.stat_card(stats, "Reviewed Submissions", total, "★")
        self.stat_card(stats, "Average Percentage", f"{average:.2f}%", "%")
        self.stat_card(
            stats,
            "Highest %",
            f"{max([float(r['marks'])/float(r['max_marks'])*100 for r in rows], default=0):.2f}%",
            "↑"
        )
        self.stat_card(
            stats,
            "Lowest %",
            f"{min([float(r['marks'])/float(r['max_marks'])*100 for r in rows], default=0):.2f}%",
            "↓"
        )

        table = tk.Frame(
            wrapper,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        table.pack(fill="both", expand=True, pady=18)

        tree = ttk.Treeview(
            table,
            columns=("student", "assignment", "subject", "marks", "max", "percent"),
            show="headings",
        )

        for col, head, width in [
            ("student", "Student", 180),
            ("assignment", "Assignment", 260),
            ("subject", "Subject", 130),
            ("marks", "Marks", 80),
            ("max", "Max", 80),
            ("percent", "Percentage", 100),
        ]:
            tree.heading(col, text=head)
            tree.column(col, width=width)

        tree.pack(fill="both", expand=True, padx=8, pady=8)

        for r in rows:
            pct = float(r["marks"]) / float(r["max_marks"]) * 100
            tree.insert(
                "",
                "end",
                values=(
                    r["student_name"],
                    r["title"],
                    r["subject"],
                    r["marks"],
                    r["max_marks"],
                    f"{pct:.2f}%",
                )
            )

        actions = tk.Frame(wrapper, bg=self.colors["bg"])
        actions.pack(fill="x")

        self.button(
            actions,
            "Export Class CSV",
            lambda: self.export_teacher_report(rows, "csv"),
            "success",
        ).pack(side="left")

        self.button(
            actions,
            "Export Class PDF",
            lambda: self.export_teacher_report(rows, "pdf"),
            "warning",
        ).pack(side="left", padx=8)

        self.button(
            actions,
            "Performance Chart",
            lambda: self.show_teacher_chart(rows),
            "primary",
        ).pack(side="left")

    def show_teacher_chart(self, rows):
        if not MATPLOTLIB_AVAILABLE:
            messagebox.showerror(
                "Chart",
                "Matplotlib is not installed.\nRun: pip install matplotlib"
            )
            return

        if not rows:
            messagebox.showinfo("Chart", "No reviewed submissions available.")
            return

        # Average by assignment
        data = {}
        for r in rows:
            pct = float(r["marks"]) / float(r["max_marks"]) * 100
            data.setdefault(r["title"], []).append(pct)

        labels = list(data.keys())
        values = [sum(v) / len(v) for v in data.values()]

        plt.figure(figsize=(10, 5))
        plt.bar([x[:18] for x in labels], values)
        plt.ylabel("Average Percentage")
        plt.title("Assignment-wise Class Performance")
        plt.xticks(rotation=30, ha="right")
        plt.ylim(0, 100)
        plt.tight_layout()
        plt.show()

    def export_teacher_report(self, rows, kind):
        if kind == "csv":
            path = filedialog.asksaveasfilename(
                initialdir=EXPORT_DIR,
                defaultextension=".csv",
                filetypes=[("CSV", "*.csv")],
                initialfile="class_performance.csv",
            )
            if not path:
                return

            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Student", "Assignment", "Subject",
                    "Marks", "Maximum Marks", "Percentage"
                ])
                for r in rows:
                    pct = float(r["marks"]) / float(r["max_marks"]) * 100
                    writer.writerow([
                        r["student_name"], r["title"], r["subject"],
                        r["marks"], r["max_marks"], f"{pct:.2f}%"
                    ])

            messagebox.showinfo("Export", "Class CSV exported successfully.")
            return

        if not REPORTLAB_AVAILABLE:
            messagebox.showerror(
                "PDF Export",
                "ReportLab is not installed.\nRun: pip install reportlab"
            )
            return

        path = filedialog.asksaveasfilename(
            initialdir=EXPORT_DIR,
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile="class_performance.pdf",
        )
        if not path:
            return

        c = canvas.Canvas(path, pagesize=A4)
        width, height = A4
        y = height - 55

        c.setFont("Helvetica-Bold", 17)
        c.drawString(45, y, "Class Performance Report")
        y -= 25
        c.setFont("Helvetica", 10)
        c.drawString(45, y, f"Teacher: {self.current_user['name']}")
        y -= 25

        for r in rows:
            pct = float(r["marks"]) / float(r["max_marks"]) * 100
            line = (
                f"{r['student_name']} | {r['title']} | "
                f"{r['marks']}/{r['max_marks']} | {pct:.2f}%"
            )
            c.drawString(45, y, line[:105])
            y -= 18

            if y < 55:
                c.showPage()
                y = height - 55
                c.setFont("Helvetica", 10)

        c.save()
        messagebox.showinfo("Export", "Class PDF exported successfully.")

    # --------------------------------------------------------
    # Profile / Password
    # --------------------------------------------------------

    def show_profile(self):
        self.page_header("My Profile", "Update your name and profile picture.")
        wrapper=tk.Frame(self.content_frame,bg=self.colors["bg"]); wrapper.pack(fill="both",expand=True,padx=28,pady=5)
        box=tk.Frame(wrapper,bg=self.colors["card"],highlightbackground=self.colors["border"],highlightthickness=1)
        box.pack(anchor="nw",fill="x",padx=10,pady=10)

        name_var=tk.StringVar(value=self.current_user["name"])
        pic_var=tk.StringVar(value=self.current_user.get("profile_pic") or "")
        photo_section = tk.Frame(box, bg=self.colors["card"])
        photo_section.pack(anchor="w", padx=30, pady=(24, 8))
        image_holder = tk.Label(
            photo_section, text="No Photo", bg=self.colors["sidebar2"], fg="white",
            font=("Segoe UI", 10, "bold"), width=16, height=8,
            bd=0, highlightthickness=1, highlightbackground=self.colors["border"]
        )
        image_holder.pack(anchor="w")
        tk.Label(photo_section, text="Profile picture (square preview)", bg=self.colors["card"],
                 fg=self.colors["muted"], font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 0))
        self.profile_preview_image = None

        def load_preview(path):
            if not path or not os.path.exists(path):
                image_holder.config(image="", text="No Photo", width=16, height=8)
                self.profile_preview_image = None
                return
            if not PIL_AVAILABLE:
                image_holder.config(image="", text="Install Pillow to preview photos", width=28, height=3)
                return
            try:
                with Image.open(path) as source:
                    im = ImageOps.fit(source.convert("RGB"), (144, 144),
                                      method=Image.Resampling.LANCZOS, centering=(0.5, 0.35))
                photo = ImageTk.PhotoImage(im)
                self.profile_preview_image = photo
                image_holder.config(image=photo, text="", width=144, height=144)
            except Exception:
                image_holder.config(image="", text="Unable to preview photo", width=22, height=3)

        current_pic=pic_var.get()
        if current_pic:
            load_preview(current_pic)

        tk.Label(box,text="Full Name",bg=self.colors["card"],fg=self.colors["text"],font=("Segoe UI",10,"bold")).pack(anchor="w",padx=30,pady=(10,5))
        ttk.Entry(box,textvariable=name_var).pack(fill="x",padx=30,ipady=7)
        tk.Label(box,text=f"Email: {self.current_user['email']}",bg=self.colors["card"],fg=self.colors["muted"],font=("Segoe UI",10)).pack(anchor="w",padx=30,pady=(15,5))
        tk.Label(box,text=f"Role: {self.current_user['role'].upper()}",bg=self.colors["card"],fg=self.colors["muted"],font=("Segoe UI",10)).pack(anchor="w",padx=30,pady=(0,15))

        def choose_photo():
            path=filedialog.askopenfilename(title="Choose Profile Picture",filetypes=[("Image Files","*.png *.jpg *.jpeg *.gif"),("All Files","*.*")])
            if not path: return
            ext=os.path.splitext(path)[1].lower()
            if ext not in (".png",".jpg",".jpeg",".gif"):
                messagebox.showwarning("Profile Picture","Please select PNG, JPG, JPEG or GIF."); return
            dest=os.path.join(PROFILE_PIC_DIR,f"user_{self.current_user['id']}{ext}")
            try:
                shutil.copy2(path,dest); pic_var.set(dest); load_preview(dest)
            except Exception as e:
                messagebox.showerror("Profile Picture",f"Could not save picture.\n{e}")

        def remove_photo():
            old=pic_var.get()
            if old and os.path.exists(old):
                try: os.remove(old)
                except Exception: pass
            pic_var.set(""); load_preview("")

        row=tk.Frame(box,bg=self.colors["card"]); row.pack(fill="x",padx=30,pady=(0,20))
        self.button(row,"Choose Profile Picture",choose_photo,"primary").pack(side="left")
        self.button(row,"Remove Picture",remove_photo,"warning").pack(side="left",padx=10)

        def save():
            name=name_var.get().strip()
            if not name: messagebox.showwarning("Profile","Name cannot be empty."); return
            con=get_db(); con.execute("UPDATE users SET name=?,profile_pic=? WHERE id=?",(name,pic_var.get() or None,self.current_user["id"])); con.commit(); con.close()
            self.current_user["name"]=name; self.current_user["profile_pic"]=pic_var.get() or None
            log_activity(self.current_user["id"],"Update Profile","Name/profile picture updated")
            messagebox.showinfo("Profile","Profile updated successfully."); self.show_profile()

        self.button(box,"SAVE PROFILE",save,"success").pack(fill="x",padx=30,pady=(0,25))

    def show_change_password(self):
        self.page_header(
            "Change Password",
            "Update your account password securely."
        )

        box = tk.Frame(
            self.content_frame,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        box.pack(fill="x", padx=42, pady=(10, 20))

        old = tk.StringVar()
        new = tk.StringVar()
        confirm = tk.StringVar()

        for title, var in [
            ("Current Password", old),
            ("New Password", new),
            ("Confirm New Password", confirm),
        ]:
            tk.Label(
                box,
                text=title,
                bg=self.colors["card"],
                fg=self.colors["text"],
                font=("Segoe UI", 10, "bold"),
            ).pack(anchor="w", padx=30, pady=(25, 5))

            ttk.Entry(
                box, textvariable=var, show="*"
            ).pack(fill="x", padx=30, ipady=7)

        def save():
            old_password = old.get()
            new_password = new.get()
            confirm_password = confirm.get()

            if not old_password or not new_password or not confirm_password:
                messagebox.showwarning(
                    "Password", "Please fill in all password fields."
                )
                return

            con = get_db()
            user = con.execute(
                "SELECT password FROM users WHERE id=?",
                (self.current_user["id"],)
            ).fetchone()

            if not user or not verify_password(old_password, user["password"]):
                con.close()
                messagebox.showerror(
                    "Password", "Current password is incorrect."
                )
                return

            ok, msg = validate_password(new_password)
            if not ok:
                con.close()
                messagebox.showwarning("Weak Password", msg)
                return

            if new_password == old_password:
                con.close()
                messagebox.showwarning(
                    "Password", "New password must be different from the current password."
                )
                return

            if new_password != confirm_password:
                con.close()
                messagebox.showerror(
                    "Password", "New passwords do not match."
                )
                return

            con.execute(
                "UPDATE users SET password=? WHERE id=?",
                (hash_password(new_password), self.current_user["id"])
            )
            con.commit()
            con.close()

            log_activity(
                self.current_user["id"],
                "Change Password",
                "Password changed"
            )

            messagebox.showinfo(
                "Password",
                "Password changed successfully."
            )

            old.set("")
            new.set("")
            confirm.set("")

        tk.Label(
            box, text="Password must be 6+ characters and include capital, small letter, digit and symbol.",
            bg=self.colors["card"], fg=self.colors["muted"], font=("Segoe UI", 8)
        ).pack(anchor="w", padx=30, pady=(10, 0))

        self.button(
            box, "CHANGE PASSWORD", save, "primary"
        ).pack(fill="x", padx=30, pady=25)

    # --------------------------------------------------------
    # Teacher: Student Approvals
    # --------------------------------------------------------

    def show_teacher_approvals(self):
        self.page_header("Student Approvals", "Approve or reject pending student registrations.")
        wrapper=tk.Frame(self.content_frame,bg=self.colors["bg"]); wrapper.pack(fill="both",expand=True,padx=28,pady=5)
        frame=tk.Frame(wrapper,bg=self.colors["card"],highlightbackground=self.colors["border"],highlightthickness=1); frame.pack(fill="both",expand=True)
        tree=ttk.Treeview(frame,columns=("id","student_id","name","email","status"),show="headings")
        for c,h,w in [("id","ID",50),("student_id","Student ID",140),("name","Name",190),("email","Email",250),("status","Status",120)]: tree.heading(c,text=h); tree.column(c,width=w)
        tree.pack(fill="both",expand=True,padx=8,pady=8)
        row_map={}
        def refresh():
            for x in tree.get_children(): tree.delete(x)
            row_map.clear(); con=get_db()
            rows=con.execute("SELECT id,student_id,name,email,approval_status FROM users WHERE role='student' AND approval_status='pending' ORDER BY id").fetchall(); con.close()
            for r in rows:
                iid=tree.insert("","end",values=(r["id"],r["student_id"] or "-",r["name"],r["email"],r["approval_status"])); row_map[iid]=r
        refresh()
        actions=tk.Frame(wrapper,bg=self.colors["bg"]); actions.pack(fill="x",pady=10)
        def approve():
            sel=tree.selection()
            if not sel: messagebox.showwarning("Approval","Select a student."); return
            u=row_map[sel[0]]; con=get_db(); con.execute("UPDATE users SET approval_status='approved' WHERE id=?",(u["id"],)); con.commit(); con.close()
            create_notification(u["id"],"Registration Approved","A teacher approved your student account. You can now login.")
            log_activity(self.current_user["id"],"Approve Student",f"{u['name']} ({u['email']})")
            messagebox.showinfo("Approved",f"{u['name']} can now login."); refresh()
        def reject():
            sel=tree.selection()
            if not sel: messagebox.showwarning("Approval","Select a student."); return
            u=row_map[sel[0]]
            if not messagebox.askyesno("Reject",f"Reject {u['name']}'s registration?"): return
            con=get_db(); con.execute("UPDATE users SET approval_status='rejected' WHERE id=?",(u["id"],)); con.commit(); con.close()
            create_notification(u["id"],"Registration Rejected","Your student registration request was rejected by a teacher.")
            log_activity(self.current_user["id"],"Reject Student",f"{u['name']} ({u['email']})")
            refresh()
        self.button(actions,"Approve Student",approve,"success").pack(side="left")
        self.button(actions,"Reject Student",reject,"warning").pack(side="left",padx=8)

    # --------------------------------------------------------
    # Admin: Users
    # --------------------------------------------------------

    def show_admin_users(self):
        self.page_header(
            "Manage Users",
            "Add, edit, delete and reset user accounts."
        )

        wrapper = tk.Frame(self.content_frame, bg=self.colors["bg"])
        wrapper.pack(fill="both", expand=True, padx=28, pady=5)

        tree_frame = tk.Frame(
            wrapper,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        tree_frame.pack(fill="both", expand=True)

        tree = ttk.Treeview(
            tree_frame,
            columns=("id", "student_id", "name", "email", "role", "approval"),
            show="headings",
        )

        for col, head, width in [
            ("id", "ID", 50),
            ("student_id", "Student ID", 130),
            ("name", "Name", 190),
            ("email", "Email", 240),
            ("role", "Role", 100),
            ("approval", "Approval Status", 130),
        ]:
            tree.heading(col, text=head)
            tree.column(col, width=width)

        tree.pack(fill="both", expand=True, padx=8, pady=8)

        row_map = {}

        def refresh():
            for i in tree.get_children():
                tree.delete(i)
            row_map.clear()

            con = get_db()
            rows = con.execute(
                "SELECT id,student_id,name,email,role,approval_status FROM users ORDER BY id"
            ).fetchall()
            con.close()

            for r in rows:
                iid = tree.insert(
                    "",
                    "end",
                    values=(r["id"], r["student_id"] or "-", r["name"], r["email"], r["role"], r["approval_status"])
                )
                row_map[iid] = r

        refresh()

        actions = tk.Frame(wrapper, bg=self.colors["bg"])
        actions.pack(fill="x", pady=10)

        self.button(
            actions,
            "Add User",
            lambda: self.admin_user_form(None, refresh),
            "primary",
        ).pack(side="left")

        def edit():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Users", "Select a user.")
                return
            self.admin_user_form(row_map[sel[0]], refresh)

        self.button(
            actions, "Edit User", edit, "success"
        ).pack(side="left", padx=8)

        def approve_user():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Approval", "Select a student or teacher.")
                return

            user = row_map[sel[0]]

            if user["role"] not in ("student", "teacher"):
                messagebox.showwarning("Approval", "Only student and teacher registrations require approval.")
                return

            if user["approval_status"] == "approved":
                messagebox.showinfo("Approval", f"This {user['role']} is already approved.")
                return

            con = get_db()
            con.execute(
                "UPDATE users SET approval_status='approved' WHERE id=?",
                (user["id"],)
            )
            con.commit()
            con.close()
            create_notification(user["id"],"Registration Approved","Your account has been approved. You can now login.")

            log_activity(
                self.current_user["id"],
                "Approve User",
                f"{user['name']} ({user['email']})"
            )

            messagebox.showinfo(
                "User Approved",
                f"{user['name']} can now login."
            )
            refresh()

        def reject_user():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Approval", "Select a student or teacher.")
                return

            user = row_map[sel[0]]

            if user["role"] not in ("student", "teacher"):
                messagebox.showwarning("Approval", "Only student and teacher registrations can be rejected.")
                return

            if not messagebox.askyesno(
                "Reject Registration",
                f"Reject {user['role']} registration request for {user['name']}?"
            ):
                return

            con = get_db()
            con.execute(
                "UPDATE users SET approval_status='rejected' WHERE id=?",
                (user["id"],)
            )
            con.commit()
            con.close()
            create_notification(user["id"],"Registration Rejected","Your registration request was rejected by the administrator.")

            log_activity(
                self.current_user["id"],
                "Reject User",
                f"{user['name']} ({user['email']})"
            )

            messagebox.showinfo(
                "Registration Rejected",
                "The registration request was rejected."
            )
            refresh()

        self.button(
            actions, "Approve Selected User", approve_user, "success"
        ).pack(side="left", padx=8)

        self.button(
            actions, "Reject Selected User", reject_user, "warning"
        ).pack(side="left")

        def reset():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Users", "Select a user.")
                return

            user = row_map[sel[0]]
            if not messagebox.askyesno(
                "Reset Password",
                f"Reset password for {user['email']} to temporary password Temp@1234?"
            ):
                return

            con = get_db()
            con.execute(
                "UPDATE users SET password=? WHERE id=?",
                (hash_password("Temp@1234"), user["id"])
            )
            con.commit()
            con.close()

            log_activity(
                self.current_user["id"],
                "Reset Password",
                user["email"]
            )

            messagebox.showinfo(
                "Reset Password",
                "Password reset successfully.\n\nTemporary password: Temp@1234\nPlease change it after login."
            )

        self.button(
            actions, "Reset Password", reset, "warning"
        ).pack(side="left")

        def delete():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Users", "Select a user.")
                return

            user = row_map[sel[0]]

            if user["id"] == self.current_user["id"]:
                messagebox.showwarning(
                    "Users",
                    "You cannot delete your currently logged-in account."
                )
                return

            if not messagebox.askyesno(
                "Delete User",
                f"Delete {user['name']} and related submissions?"
            ):
                return

            con = get_db()
            subs = con.execute(
                "SELECT file_name FROM submissions WHERE student_id=?",
                (user["id"],)
            ).fetchall()

            for s in subs:
                p = os.path.join(UPLOAD_DIR, s["file_name"])
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

            con.execute("DELETE FROM users WHERE id=?", (user["id"],))
            con.commit()
            con.close()

            log_activity(
                self.current_user["id"],
                "Delete User",
                user["email"]
            )

            refresh()

        self.button(
            actions, "Delete User", delete, "danger"
        ).pack(side="left", padx=8)

        def student_report():
            sel=tree.selection()
            if not sel: messagebox.showwarning("Report","Select a student."); return
            user=row_map[sel[0]]
            if user["role"]!="student": messagebox.showwarning("Report","Select a student account."); return
            self.export_user_report(user)
        self.button(actions,"Student Report",student_report,"primary").pack(side="left",padx=8)

    def export_user_report(self,user):
        if not REPORTLAB_AVAILABLE: messagebox.showerror("PDF Report","Install ReportLab: pip install reportlab"); return
        con=get_db(); rows=con.execute("SELECT a.title,a.subject,a.max_marks,s.marks,s.status,s.feedback FROM submissions s JOIN assignments a ON a.id=s.assignment_id WHERE s.student_id=? AND s.id IN (SELECT MAX(s2.id) FROM submissions s2 WHERE s2.student_id=? GROUP BY s2.assignment_id) ORDER BY a.deadline",(user["id"],user["id"])).fetchall(); con.close()
        path=filedialog.asksaveasfilename(initialdir=EXPORT_DIR,defaultextension=".pdf",filetypes=[("PDF","*.pdf")],initialfile=safe_filename(f"{user['name']}_assignment_report.pdf"));
        if not path:return
        c=canvas.Canvas(path,pagesize=A4); w,h=A4; y=h-50; c.setFont("Helvetica-Bold",17); c.drawString(45,y,"Student Assignment Report"); y-=25; c.setFont("Helvetica",10); c.drawString(45,y,f"Student: {user['name']}"); y-=16; c.drawString(45,y,f"Student ID: {user['student_id'] or '-'}"); y-=25
        total=count=0
        for r in rows:
            pct=(float(r["marks"])/float(r["max_marks"])*100) if r["marks"] is not None and r["max_marks"] else None
            if pct is not None: total+=pct; count+=1
            c.drawString(45,y,f"{r['title']} | {r['subject']} | {r['marks'] if r['marks'] is not None else '-'} / {r['max_marks']} | {r['status']}"[:105]); y-=16
            if pct is not None: c.drawString(60,y,f"{pct:.2f}% | Feedback: {(r['feedback'] or '-')[:70]}"); y-=18
            if y<55: c.showPage(); y=h-50; c.setFont("Helvetica",10)
        c.setFont("Helvetica-Bold",11); c.drawString(45,y,f"Average Performance: {(total/count if count else 0):.2f}%"); c.save(); log_activity(self.current_user["id"],"Generate Student Report",user["email"]); messagebox.showinfo("Report","Student PDF report generated successfully.")

    def backup_database(self):
        path=filedialog.asksaveasfilename(initialdir=EXPORT_DIR,defaultextension=".db",filetypes=[("SQLite Database","*.db")],initialfile=f"assignment_system_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db");
        if not path:return
        try:
            src=sqlite3.connect(DB_NAME); dst=sqlite3.connect(path); src.backup(dst); dst.close(); src.close(); log_activity(self.current_user["id"],"Database Backup",path); messagebox.showinfo("Backup","Database backup created successfully.")
        except Exception as e: messagebox.showerror("Backup Error",str(e))

    def restore_database(self):
        path=filedialog.askopenfilename(filetypes=[("SQLite Database","*.db")]);
        if not path:return
        if os.path.abspath(path)==os.path.abspath(DB_NAME): messagebox.showwarning("Restore","Select a backup database."); return
        try:
            test=sqlite3.connect(path); ok=test.execute("PRAGMA integrity_check").fetchone()[0]; test.close()
            if ok!="ok": raise ValueError("Database integrity check failed.")
            if not messagebox.askyesno("Restore Database","This will replace the current database. Continue?"):return
            shutil.copy2(DB_NAME,DB_NAME+".before_restore.bak"); shutil.copy2(path,DB_NAME); messagebox.showinfo("Restore","Database restored. Restart the application to load it."); self.destroy()
        except Exception as e: messagebox.showerror("Restore Error",str(e))

    def admin_user_form(self, user, refresh_callback):
        win = tk.Toplevel(self)
        win.title("Add User" if user is None else "Edit User")
        win.geometry("560x520")
        win.configure(bg=self.colors["bg"])
        win.transient(self)
        win.grab_set()

        box = tk.Frame(
            win,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        box.pack(fill="both", expand=True, padx=25, pady=25)

        student_id_var = tk.StringVar(value=(user["student_id"] or "") if user else "")
        name_var = tk.StringVar(value=user["name"] if user else "")
        email_var = tk.StringVar(value=user["email"] if user else "")
        password_var = tk.StringVar()
        role_var = tk.StringVar(value=user["role"] if user else "student")

        for text, var in [
            ("Student ID / Enrollment Number", student_id_var),
            ("Name", name_var),
            ("Email", email_var),
        ]:
            tk.Label(
                box, text=text, bg=self.colors["card"],
                fg=self.colors["text"], font=("Segoe UI", 10, "bold")
            ).pack(anchor="w", padx=25, pady=(18, 4))
            ttk.Entry(box, textvariable=var).pack(
                fill="x", padx=25, ipady=7
            )

        tk.Label(
            box, text="Password" + (" (leave blank to keep current)" if user else ""),
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", padx=25, pady=(18, 4))

        ttk.Entry(
            box, textvariable=password_var, show="•"
        ).pack(fill="x", padx=25, ipady=7)

        tk.Label(
            box, text="Role",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", padx=25, pady=(18, 4))

        ttk.Combobox(
            box,
            textvariable=role_var,
            values=["student", "teacher", "admin"],
            state="readonly",
        ).pack(fill="x", padx=25)

        def save():
            student_id = student_id_var.get().strip().upper()
            name = name_var.get().strip()
            email = email_var.get().strip().lower()
            password = password_var.get()
            role = role_var.get()

            if not name or not email:
                messagebox.showwarning(
                    "User", "Name and email are required."
                )
                return

            if role == "student" and not student_id:
                messagebox.showwarning(
                    "User",
                    "Student ID / Enrollment Number is required for students."
                )
                return

            if student_id and not all(
                ch.isalnum() or ch in "-_" for ch in student_id
            ):
                messagebox.showwarning(
                    "User",
                    "Student ID can contain only letters, numbers, '-' and '_'."
                )
                return

            con = get_db()

            try:
                if user is None:
                    ok, msg = validate_password(password)
                    if not ok:
                        raise ValueError(msg)

                    con.execute("""
                        INSERT INTO users(name,email,password,role)
                        VALUES(?,?,?,?)
                    """, (
                        name, email, hash_password(password), role
                    ))
                    action = "Create User"
                else:
                    if password:
                        ok, msg = validate_password(password)
                        if not ok:
                            raise ValueError(msg)
                        con.execute("""
                            UPDATE users
                            SET name=?, email=?, role=?, password=?
                            WHERE id=?
                        """, (
                            name, email, role,
                            hash_password(password),
                            user["id"],
                        ))
                    else:
                        con.execute("""
                            UPDATE users
                            SET name=?, email=?, role=?
                            WHERE id=?
                        """, (
                            name, email, role, user["id"]
                        ))
                    action = "Edit User"

                con.commit()
                con.close()

                log_activity(
                    self.current_user["id"],
                    action,
                    email
                )

                win.destroy()
                refresh_callback()

            except sqlite3.IntegrityError:
                con.close()
                messagebox.showerror(
                    "User",
                    "Email already exists."
                )
            except ValueError as e:
                con.close()
                messagebox.showwarning("User", str(e))

        self.button(
            box, "SAVE USER", save, "success"
        ).pack(fill="x", padx=25, pady=25)

    # --------------------------------------------------------
    # Admin: Statistics
    # --------------------------------------------------------

    def show_admin_statistics(self):
        self.page_header(
            "System Statistics",
            "Overall usage, submissions and academic activity."
        )

        wrapper = tk.Frame(self.content_frame, bg=self.colors["bg"])
        wrapper.pack(fill="both", expand=True, padx=28, pady=5)

        tools=tk.Frame(wrapper,bg=self.colors["bg"]); tools.pack(fill="x",pady=(0,12))
        self.button(tools,"Backup Database",self.backup_database,"success").pack(side="left")
        self.button(tools,"Restore Database",self.restore_database,"warning").pack(side="left",padx=8)

        con = get_db()

        values = {
            "Users": con.execute(
                "SELECT COUNT(*) AS c FROM users"
            ).fetchone()["c"],
            "Students": con.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role='student'"
            ).fetchone()["c"],
            "Teachers": con.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role='teacher'"
            ).fetchone()["c"],
            "Admins": con.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role='admin'"
            ).fetchone()["c"],
            "Assignments": con.execute(
                "SELECT COUNT(*) AS c FROM assignments"
            ).fetchone()["c"],
            "Submissions": con.execute(
                "SELECT COUNT(*) AS c FROM submissions"
            ).fetchone()["c"],
            "Reviewed": con.execute(
                "SELECT COUNT(*) AS c FROM submissions WHERE marks IS NOT NULL"
            ).fetchone()["c"],
            "Late": con.execute(
                "SELECT COUNT(*) AS c FROM submissions WHERE status='Late'"
            ).fetchone()["c"],
            "Pending Registrations": con.execute(
                "SELECT COUNT(*) AS c FROM users "
                "WHERE role IN ('student','teacher') AND approval_status='pending'"
            ).fetchone()["c"],
        }

        con.close()

        top = tk.Frame(wrapper, bg=self.colors["bg"])
        top.pack(fill="x")

        for title, value in values.items():
            self.stat_card(top, title, value, "•")

        report = tk.Frame(
            wrapper,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        report.pack(fill="both", expand=True, pady=20)

        tk.Label(
            report,
            text="System Overview",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=25, pady=(25, 8))

        for title, value in values.items():
            row = tk.Frame(report, bg=self.colors["card"])
            row.pack(fill="x", padx=25, pady=5)

            tk.Label(
                row, text=title,
                bg=self.colors["card"],
                fg=self.colors["muted"],
                font=("Segoe UI", 10),
            ).pack(side="left")

            tk.Label(
                row, text=str(value),
                bg=self.colors["card"],
                fg=self.colors["text"],
                font=("Segoe UI", 10, "bold"),
            ).pack(side="right")

    # --------------------------------------------------------
    # Activity Log
    # --------------------------------------------------------

    def show_activity_log(self):
        self.page_header(
            "Activity Log",
            "Audit trail of important actions performed in the system."
        )

        wrapper = tk.Frame(self.content_frame, bg=self.colors["bg"])
        wrapper.pack(fill="both", expand=True, padx=28, pady=5)

        tree_frame = tk.Frame(
            wrapper,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
        )
        tree_frame.pack(fill="both", expand=True)

        tree = ttk.Treeview(
            tree_frame,
            columns=("id", "user", "action", "details", "time"),
            show="headings",
        )

        for col, head, width in [
            ("id", "ID", 60),
            ("user", "User", 180),
            ("action", "Action", 180),
            ("details", "Details", 430),
            ("time", "Timestamp", 170),
        ]:
            tree.heading(col, text=head)
            tree.column(col, width=width)

        tree.pack(fill="both", expand=True, padx=8, pady=8)

        con = get_db()
        rows = con.execute("""
            SELECT l.*, COALESCE(u.name, 'System') AS user_name
            FROM activity_log l
            LEFT JOIN users u ON u.id=l.user_id
            ORDER BY l.id DESC
            LIMIT 500
        """).fetchall()
        con.close()

        for r in rows:
            tree.insert(
                "",
                "end",
                values=(
                    r["id"],
                    r["user_name"],
                    r["action"],
                    r["details"] or "",
                    r["timestamp"],
                )
            )

    # --------------------------------------------------------
    # Start / periodic deadline refresh
    # --------------------------------------------------------

    def run_periodic_refresh(self):
        try:
            if self.current_user and self.current_user["role"] == "student":
                con=get_db(); rows=con.execute("SELECT * FROM assignments").fetchall()
                for a in rows:
                    try:
                        diff=(parse_deadline(a["deadline"])-datetime.now()).total_seconds(); sub=get_latest_submission(a["id"],self.current_user["id"])
                        if not sub and 0 < diff <= 86400:
                            exists=con.execute("SELECT id FROM notifications WHERE user_id=? AND title='Deadline Alert' AND message LIKE ? AND created_at>=?",(self.current_user["id"],f"%{a['title']}%",(datetime.now()-timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S"))).fetchone()
                            if not exists: create_notification(self.current_user["id"],"Deadline Alert",f"{a['title']} is due within 24 hours.")
                    except Exception: pass
                con.close()
        except Exception: pass
        self.after(60000,self.run_periodic_refresh)


# ============================================================
# PATCH PAGE TRACKING
# ============================================================

_original_show_assignments = AssignmentApp.show_assignments_page


def tracked_show_assignments(self):
    self.current_page = "assignments"
    _original_show_assignments(self)


AssignmentApp.show_assignments_page = tracked_show_assignments


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    app = AssignmentApp()
    app.after(60000, app.run_periodic_refresh)
    app.mainloop()
