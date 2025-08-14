import sqlite3
import os
import csv
import json
from datetime import datetime
import pandas as pd
from fpdf import FPDF
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

BASE_DIR = os.path.dirname(os.path.dirname(__file__))  # project_root/utils -> project_root
DB_PATH = os.path.join(BASE_DIR, "db", "restaurant.db")
DATA_DIR = os.path.join(BASE_DIR, "data")
MENU_CSV = os.path.join(DATA_DIR, "menu.csv")
SAMPLE_BILLS_JSON = os.path.join(DATA_DIR, "sample_bills.json")
SALES_CSV = os.path.join(DATA_DIR, "sales_report.csv")

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

def _connect():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def initialize_database():
    conn = _connect()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS menu (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_name TEXT NOT NULL,
        category TEXT,
        price REAL,
        gst INTEGER DEFAULT 5,
        image TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_type TEXT,        -- Dine-In or Takeaway
        table_id INTEGER,       -- if dine-in
        payment_mode TEXT,
        subtotal REAL,
        gst_amount REAL,
        discount_amount REAL,
        total_amount REAL,
        order_date TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        item_id INTEGER,
        quantity INTEGER,
        FOREIGN KEY(order_id) REFERENCES orders(id),
        FOREIGN KEY(item_id) REFERENCES menu(id)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tables (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        capacity INTEGER DEFAULT 2,
        status TEXT DEFAULT 'available',    -- available / occupied / cleaning
        current_order_id INTEGER
    );
    """)

    conn.commit()
    conn.close()

def populate_menu_from_csv(csv_path=MENU_CSV):
    if not os.path.exists(csv_path):
        return False, f"{csv_path} not found"
    conn = _connect()
    cur = conn.cursor()
    # If menu has items, skip to avoid duplicates
    cur.execute("SELECT COUNT(*) FROM menu")
    if cur.fetchone()[0] > 0:
        conn.close()
        return False, "Menu already populated. Skipping import."
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # image value optional: if CSV has an image column, use it, else try data/images/{slug}.jpg
            image = row.get("image") or os.path.join(DATA_DIR, "images", slugify(row["item_name"]) + ".jpg")
            cur.execute("INSERT INTO menu (item_name, category, price, gst, image) VALUES (?, ?, ?, ?, ?)",
                        (row["item_name"].strip(), row["category"].strip(), float(row["price"]), int(row.get("gst", 5)), image))
    conn.commit()
    conn.close()
    return True, "Menu imported."

def slugify(name):
    return "".join(c if c.isalnum() else "_" for c in name.strip()).lower()

# menu CRUD / read
def load_menu_df():
    conn = _connect()
    df = pd.read_sql_query("SELECT * FROM menu ORDER BY category, item_name", conn)
    conn.close()
    return df

def add_menu_item(name, category, price, gst=5, image=None):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("INSERT INTO menu (item_name, category, price, gst, image) VALUES (?, ?, ?, ?, ?)",
                (name, category, float(price), int(gst), image))
    conn.commit()
    last = cur.lastrowid
    conn.close()
    return last

def delete_menu_item(item_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM menu WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()

def update_menu_item(item_id, name, category, price, gst, image):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE menu
        SET item_name = ?, category = ?, price = ?, gst = ?, image = ?
        WHERE id = ?
    """, (name, category, price, gst, image, item_id))
    conn.commit()
    conn.close()


def get_menu_item_by_id(id_):
    conn = sqlite3.connect("your_database_path.db")
    conn.row_factory = sqlite3.Row  # So you can access columns by name
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM menu WHERE id=?", (id_,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    else:
        return None
    
# tables
def get_tables_df():
    conn = _connect()
    df = pd.read_sql_query("SELECT * FROM tables ORDER BY id", conn)
    conn.close()
    return df

def add_table(name, capacity=2):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("INSERT INTO tables (name, capacity) VALUES (?, ?)", (name, int(capacity)))
    conn.commit()
    last = cur.lastrowid
    conn.close()
    return last

def update_table_status(table_id, status, current_order_id=None):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("UPDATE tables SET status=?, current_order_id=? WHERE id=?", (status, current_order_id, int(table_id)))
    conn.commit()
    conn.close()

# orders
def save_order(order_type, payment_mode, subtotal, gst_amount, discount_amount, total, items, table_id=None):
    """
    items: list of dicts {item_id, name, price, quantity}
    returns order_id
    """
    conn = _connect()
    cur = conn.cursor()
    order_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""INSERT INTO orders
                   (order_type, table_id, payment_mode, subtotal, gst_amount, discount_amount, total_amount, order_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (order_type, table_id, payment_mode, subtotal, gst_amount, discount_amount, total, order_date))
    order_id = cur.lastrowid
    for it in items:
        cur.execute("INSERT INTO order_items (order_id, item_id, quantity) VALUES (?, ?, ?)",
                    (order_id, int(it["item_id"]), int(it["quantity"])))
    conn.commit()
    conn.close()

    # append to JSON file
    bill_record = {
        "order_id": order_id,
        "order_type": order_type,
        "table_id": table_id,
        "payment_mode": payment_mode,
        "subtotal": subtotal,
        "gst": gst_amount,
        "discount": discount_amount,
        "total": total,
        "order_date": order_date,
        "items": items
    }
    _append_json_line(SAMPLE_BILLS_JSON, bill_record)

    # append to sales csv
    _append_sales_csv(order_id, order_date, items)

    return order_id

def _append_json_line(path, record):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

def _append_sales_csv(order_id, order_date, items):
    os.makedirs(os.path.dirname(SALES_CSV), exist_ok=True)
    header = not os.path.exists(SALES_CSV)
    rows = []
    for it in items:
        rows.append({
            "order_id": order_id,
            "order_date": order_date,
            "item_name": it.get("name"),
            "quantity": it.get("quantity"),
            "price": it.get("price"),
            "line_total": float(it.get("price")) * int(it.get("quantity"))
        })
    df = pd.DataFrame(rows)
    df.to_csv(SALES_CSV, mode="a", header=header, index=False, encoding="utf-8")

# fetch order details
def fetch_order_details(order_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT id, order_type, table_id, payment_mode, subtotal, gst_amount, discount_amount, total_amount, order_date FROM orders WHERE id=?", (int(order_id),))
    order = cur.fetchone()
    cur.execute("""SELECT oi.quantity, m.item_name, m.price, m.gst
                   FROM order_items oi JOIN menu m ON oi.item_id = m.id
                   WHERE oi.order_id = ?""", (int(order_id),))
    items = cur.fetchall()
    conn.close()
    return order, items

# reporting helpers
def get_sales_dataframe(start_date=None, end_date=None):
    conn = _connect()
    query = """
    SELECT o.id as order_id, o.order_date, o.order_type, o.payment_mode,
           m.item_name, m.category, m.price, oi.quantity, (oi.quantity * m.price) as line_total
    FROM orders o
    JOIN order_items oi ON o.id = oi.order_id
    JOIN menu m ON oi.item_id = m.id
    """
    params = []
    if start_date and end_date:
        query += " WHERE o.order_date BETWEEN ? AND ?"
        params = [start_date + " 00:00:00", end_date + " 23:59:59"]
    query += " ORDER BY o.order_date DESC"
    df = pd.read_sql_query(query, _connect(), params=params)
    if not df.empty:
        df["order_date"] = pd.to_datetime(df["order_date"])
    return df

def most_sold_items_df(df, top_n=10):
    if df.empty:
        return pd.DataFrame(columns=["item_name", "quantity"])
    ms = df.groupby("item_name")["quantity"].sum().reset_index().sort_values(by="quantity", ascending=False)
    return ms.head(top_n)

# export helpers: bill -> csv/json/pdf and report -> pdf
def bill_to_csv_string(order_id):
    order, items = fetch_order_details(order_id)
    if not order:
        return None
    rows = []
    for qty, name, price, gst in items:
        rows.append({"item_name": name, "quantity": qty, "price": price, "line_total": qty * price})
    df = pd.DataFrame(rows)
    df.loc[len(df.index)] = ["", "", "Total", order[7]]
    return df.to_csv(index=False)

def bill_to_json_str(order_id):
    order, items = fetch_order_details(order_id)
    if not order:
        return None
    order_obj = {
        "order_id": order[0],
        "order_type": order[1],
        "table_id": order[2],
        "payment_mode": order[3],
        "total_amount": order[7],
        "order_date": order[8],
        "items": []
    }
    for qty, name, price, gst in items:
        order_obj["items"].append({"item_name": name, "quantity": qty, "price": price, "line_total": qty * price})
    return json.dumps(order_obj, ensure_ascii=False, indent=4)

def bill_to_pdf_bytes(order_id):
    order, items = fetch_order_details(order_id)
    if not order:
        return None
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "Restaurant Bill", ln=True, align="C")
    pdf.ln(4)
    pdf.set_font("Arial", size=11)
    pdf.cell(0, 8, f"Order ID: {order[0]}  |  Type: {order[1]}  |  Table: {order[2]}", ln=True)
    pdf.cell(0, 8, f"Date: {order[8]}", ln=True)
    pdf.ln(4)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(80, 8, "Item", border=1)
    pdf.cell(30, 8, "Price", border=1, align="R")
    pdf.cell(20, 8, "Qty", border=1, align="R")
    pdf.cell(30, 8, "Total", border=1, align="R")
    pdf.ln()
    pdf.set_font("Arial", size=11)
    subtotal = 0.0
    for qty, name, price, gst in items:
        line_total = qty * price
        subtotal += line_total
        pdf.cell(80, 8, str(name), border=1)
        pdf.cell(30, 8, f"{price:.2f}", border=1, align="R")
        pdf.cell(20, 8, str(qty), border=1, align="R")
        pdf.cell(30, 8, f"{line_total:.2f}", border=1, align="R")
        pdf.ln()
    gst_amount = subtotal * 0.05
    total = subtotal + gst_amount
    pdf.ln(6)
    pdf.cell(130, 8, "", ln=False)
    pdf.cell(30, 8, "Subtotal:", align="R")
    pdf.cell(30, 8, f"{subtotal:.2f}", align="R", ln=True)
    pdf.cell(130, 8, "", ln=False)
    pdf.cell(30, 8, "GST (5%):", align="R")
    pdf.cell(30, 8, f"{gst_amount:.2f}", align="R", ln=True)
    pdf.cell(130, 8, "", ln=False)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(30, 8, "Total:", align="R")
    pdf.cell(30, 8, f"{total:.2f}", align="R", ln=True)
    return pdf.output(dest="S").encode("latin-1")

def report_df_to_pdf_bytes(df, title="Report"):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    x = 40
    y = height - 40
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, y, title)
    y -= 25
    c.setFont("Helvetica", 10)
    line_h = 14
    for i, row in df.iterrows():
        line = " | ".join([f"{col}: {row[col]}" for col in df.columns])
        c.drawString(x, y, str(line)[:200])
        y -= line_h
        if y < 60:
            c.showPage()
            y = height - 40
    c.save()
    buf.seek(0)
    return buf.read()
