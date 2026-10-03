"""
College Event Management System
Python + Tkinter + SQLite

Default admin login -> username: admin   password: admin123
Students register themselves from the login screen.
"""

import csv
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime

DB_NAME = "college_events.db"


# ---------------- DATABASE ----------------
def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def setup_database():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    full_name TEXT,
                    department TEXT,
                    role TEXT NOT NULL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    event_date TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    coordinator TEXT,
                    total_seats INTEGER NOT NULL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS registrations(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    UNIQUE(event_id, username),
                    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE)""")
    cur.execute("INSERT OR IGNORE INTO users(username,password,full_name,department,role) "
                "VALUES('admin','admin123','Administrator','-','admin')")
    conn.commit()
    conn.close()


def check_login(username, password):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE username=? AND password=?", (username, password))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def register_student(username, password, full_name, department):
    conn = get_connection()
    try:
        conn.execute("INSERT INTO users(username,password,full_name,department,role) VALUES(?,?,?,?,'student')",
                     (username, password, full_name, department))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def add_event(name, event_date, venue, coordinator, seats):
    conn = get_connection()
    conn.execute("INSERT INTO events(name,event_date,venue,coordinator,total_seats) VALUES(?,?,?,?,?)",
                 (name, event_date, venue, coordinator, seats))
    conn.commit()
    conn.close()


def update_event(event_id, name, event_date, venue, coordinator, seats):
    conn = get_connection()
    conn.execute("UPDATE events SET name=?, event_date=?, venue=?, coordinator=?, total_seats=? WHERE id=?",
                 (name, event_date, venue, coordinator, seats, event_id))
    conn.commit()
    conn.close()


def delete_event(event_id):
    conn = get_connection()
    conn.execute("DELETE FROM events WHERE id=?", (event_id,))
    conn.commit()
    conn.close()


def get_events(upcoming_only=False):
    """Returns (id, name, date, venue, coordinator, total_seats, seats_filled)."""
    conn = get_connection()
    cur = conn.cursor()
    query = """SELECT e.id, e.name, e.event_date, e.venue, e.coordinator, e.total_seats,
                      COUNT(r.id)
               FROM events e LEFT JOIN registrations r ON e.id = r.event_id"""
    params = ()
    if upcoming_only:
        query += " WHERE e.event_date >= ?"
        params = (date.today().isoformat(),)
    query += " GROUP BY e.id ORDER BY e.event_date"
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return rows


def seats_filled(event_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM registrations WHERE event_id=?", (event_id,))
    n = cur.fetchone()[0]
    conn.close()
    return n


def register_for_event(event_id, username):
    """Returns 'ok', 'full', 'already' or 'missing'."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT total_seats FROM events WHERE id=?", (event_id,))
        row = cur.fetchone()
        if row is None:
            return "missing"
        cur.execute("SELECT 1 FROM registrations WHERE event_id=? AND username=?", (event_id, username))
        if cur.fetchone():
            return "already"
        cur.execute("SELECT COUNT(*) FROM registrations WHERE event_id=?", (event_id,))
        if cur.fetchone()[0] >= row[0]:
            return "full"
        cur.execute("INSERT INTO registrations(event_id, username) VALUES(?,?)", (event_id, username))
        conn.commit()
        return "ok"
    except sqlite3.IntegrityError:
        return "already"
    finally:
        conn.close()


def cancel_registration(event_id, username):
    conn = get_connection()
    conn.execute("DELETE FROM registrations WHERE event_id=? AND username=?", (event_id, username))
    conn.commit()
    conn.close()


def get_my_events(username):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""SELECT e.id, e.name, e.event_date, e.venue FROM events e
                   JOIN registrations r ON e.id = r.event_id
                   WHERE r.username=? ORDER BY e.event_date""", (username,))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_participants(event_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""SELECT u.username, u.full_name, u.department FROM registrations r
                   JOIN users u ON u.username = r.username
                   WHERE r.event_id=? ORDER BY u.full_name""", (event_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def export_participants(event_id, filename):
    rows = get_participants(event_id)
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Username", "Full Name", "Department"])
        writer.writerows(rows)
    return len(rows)


def validate_event(name, event_date, venue, seats_text):
    """Returns an error message, or None if the data is valid."""
    if name == "" or venue == "":
        return "Event name and venue are required"
    try:
        datetime.strptime(event_date, "%Y-%m-%d")
    except ValueError:
        return "Date must be in YYYY-MM-DD format"
    if not seats_text.isdigit() or int(seats_text) <= 0:
        return "Seats must be a positive number"
    return None


# ---------------- GUI ----------------
class EventApp:
    def __init__(self, root):
        self.root = root
        self.root.title("College Event Management System")
        self.root.geometry("900x560")
        self.username = None
        self.show_login()

    def clear(self):
        for w in self.root.winfo_children():
            w.destroy()

    def make_event_table(self, parent, height=12):
        cols = ("ID", "Event", "Date", "Venue", "Coordinator", "Seats", "Filled")
        widths = (40, 200, 100, 150, 140, 60, 60)
        table = ttk.Treeview(parent, columns=cols, show="headings", height=height)
        for c, w in zip(cols, widths):
            table.heading(c, text=c)
            table.column(c, width=w)
        table.pack(fill="both", expand=True, padx=10, pady=5)
        return table

    def fill_event_table(self, table, upcoming_only=False):
        for row in table.get_children():
            table.delete(row)
        for e in get_events(upcoming_only):
            table.insert("", tk.END, values=e)

    def selected_id(self, table):
        sel = table.selection()
        if not sel:
            messagebox.showinfo("Info", "Select an event first")
            return None
        return table.item(sel[0])["values"][0]

    # ---------- Login ----------
    def show_login(self):
        self.clear()
        tk.Label(self.root, text="College Event Management", font=("Arial", 20, "bold")).pack(pady=25)
        tk.Label(self.root, text="Username").pack()
        user_e = tk.Entry(self.root)
        user_e.pack()
        tk.Label(self.root, text="Password").pack()
        pass_e = tk.Entry(self.root, show="*")
        pass_e.pack()

        def login():
            role = check_login(user_e.get().strip(), pass_e.get().strip())
            if role is None:
                messagebox.showerror("Error", "Wrong username or password")
                return
            self.username = user_e.get().strip()
            self.show_admin() if role == "admin" else self.show_student()

        tk.Button(self.root, text="Login", width=15, command=login).pack(pady=8)
        tk.Button(self.root, text="New Student? Register", width=20, command=self.show_register).pack()

    def show_register(self):
        win = tk.Toplevel(self.root)
        win.title("Student Registration")
        fields = {}
        for label in ["Username", "Password", "Full Name", "Department"]:
            tk.Label(win, text=label).pack(padx=20)
            e = tk.Entry(win, show="*" if label == "Password" else "")
            e.pack(padx=20)
            fields[label] = e

        def save():
            v = {k: e.get().strip() for k, e in fields.items()}
            if "" in v.values():
                messagebox.showwarning("Warning", "Fill all fields", parent=win)
            elif register_student(v["Username"], v["Password"], v["Full Name"], v["Department"]):
                messagebox.showinfo("Done", "Registered! Now login.", parent=win)
                win.destroy()
            else:
                messagebox.showerror("Error", "Username already exists", parent=win)

        tk.Button(win, text="Register", command=save).pack(pady=10)

    # ---------- Admin ----------
    def show_admin(self):
        self.clear()
        tk.Label(self.root, text="Admin Panel - Manage Events", font=("Arial", 15, "bold")).pack(pady=8)

        form = tk.LabelFrame(self.root, text="Event Details", padx=8, pady=8)
        form.pack(fill="x", padx=10)
        labels = ["Event Name", "Date (YYYY-MM-DD)", "Venue", "Coordinator", "Total Seats"]
        entries = []
        for i, label in enumerate(labels):
            tk.Label(form, text=label).grid(row=0, column=i)
            e = tk.Entry(form, width=18)
            e.grid(row=1, column=i, padx=4)
            entries.append(e)

        table = self.make_event_table(self.root, height=10)

        def read_form():
            v = [e.get().strip() for e in entries]
            err = validate_event(v[0], v[1], v[2], v[4])
            if err:
                messagebox.showerror("Error", err)
                return None
            return v[0], v[1], v[2], v[3], int(v[4])

        def clear_form():
            for e in entries:
                e.delete(0, tk.END)

        def on_add():
            data = read_form()
            if data:
                add_event(*data)
                clear_form()
                self.fill_event_table(table)

        def on_select(event=None):
            sel = table.selection()
            if not sel:
                return
            vals = table.item(sel[0])["values"]
            clear_form()
            for e, v in zip(entries, [vals[1], vals[2], vals[3], vals[4], vals[5]]):
                e.insert(0, v)

        def on_update():
            event_id = self.selected_id(table)
            data = read_form()
            if event_id is None or data is None:
                return
            if data[4] < seats_filled(event_id):
                messagebox.showerror("Error", "Seats cannot be less than students already registered")
                return
            update_event(event_id, *data)
            self.fill_event_table(table)

        def on_delete():
            event_id = self.selected_id(table)
            if event_id and messagebox.askyesno("Delete", "Delete this event and its registrations?"):
                delete_event(event_id)
                clear_form()
                self.fill_event_table(table)

        def on_participants():
            event_id = self.selected_id(table)
            if event_id is None:
                return
            rows = get_participants(event_id)
            if not rows:
                messagebox.showinfo("Participants", "No students registered yet")
                return
            text = "\n".join(f"{r[1]} ({r[0]}) - {r[2]}" for r in rows)
            messagebox.showinfo("Participants", text)

        def on_export():
            event_id = self.selected_id(table)
            if event_id is None:
                return
            filename = f"participants_event_{event_id}.csv"
            n = export_participants(event_id, filename)
            messagebox.showinfo("Exported", f"{n} participants saved to {filename}")

        table.bind("<<TreeviewSelect>>", on_select)

        btns = tk.Frame(self.root)
        btns.pack(pady=6)
        for i, (text, cmd) in enumerate([("Add Event", on_add), ("Update", on_update), ("Delete", on_delete),
                                         ("Participants", on_participants), ("Export CSV", on_export),
                                         ("Logout", self.show_login)]):
            tk.Button(btns, text=text, width=12, command=cmd).grid(row=0, column=i, padx=4)

        self.fill_event_table(table)

    # ---------- Student ----------
    def show_student(self):
        self.clear()
        tk.Label(self.root, text=f"Welcome, {self.username}", font=("Arial", 15, "bold")).pack(pady=8)
        tk.Label(self.root, text="Upcoming Events").pack()
        table = self.make_event_table(self.root, height=10)

        def on_register():
            event_id = self.selected_id(table)
            if event_id is None:
                return
            result = register_for_event(event_id, self.username)
            msgs = {"ok": "Registered successfully!", "full": "Sorry, this event is full",
                    "already": "You are already registered", "missing": "Event not found"}
            messagebox.showinfo("Registration", msgs[result])
            self.fill_event_table(table, upcoming_only=True)

        def on_my_events():
            rows = get_my_events(self.username)
            if not rows:
                messagebox.showinfo("My Events", "You have not registered for any event")
                return
            text = "\n".join(f"[{r[0]}] {r[1]} - {r[2]} at {r[3]}" for r in rows)
            messagebox.showinfo("My Events", text)

        def on_cancel():
            event_id = self.selected_id(table)
            if event_id and messagebox.askyesno("Cancel", "Cancel your registration for this event?"):
                cancel_registration(event_id, self.username)
                self.fill_event_table(table, upcoming_only=True)

        btns = tk.Frame(self.root)
        btns.pack(pady=6)
        for i, (text, cmd) in enumerate([("Register", on_register), ("Cancel Registration", on_cancel),
                                         ("My Events", on_my_events), ("Logout", self.show_login)]):
            tk.Button(btns, text=text, width=16, command=cmd).grid(row=0, column=i, padx=4)

        self.fill_event_table(table, upcoming_only=True)


if __name__ == "__main__":
    setup_database()
    root = tk.Tk()
    EventApp(root)
    root.mainloop()
