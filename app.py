from flask import Flask, render_template, request, redirect, session, send_file
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib.utils import ImageReader
import sqlite3
import os
import numpy as np
import pandas as pd 
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import pandas as pd
from flask import send_file

app = Flask(__name__)
app.secret_key = "secret123"

# ------------------ DATABASE SETUP ------------------

def init_db():
    conn = sqlite3.connect("users.db", timeout=10, check_same_thread=False)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            password TEXT,
            role TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product TEXT,
            cost_price REAL,
            selling_price REAL,
            stock INTEGER,
            category TEXT,
            date_added TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sales(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product TEXT,
            quantity INTEGER,
            total_amount REAL,
            date TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS expenses(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            amount REAL,
            category TEXT,
            date TEXT
        )
    """)

    conn.commit()
    conn.close()


# ------------------ DEMO PRODUCTS ------------------

def insert_demo_data():
    import sqlite3

    conn = sqlite3.connect("users.db", timeout=10, check_same_thread=False)
    cur = conn.cursor()

    # ------------------ INSERT USER ------------------
    cur.execute("SELECT COUNT(*) FROM users")
    user_count = cur.fetchone()[0]

    if user_count == 0:
        cur.execute("""
            INSERT INTO users (name, email, password, role)
            VALUES (?, ?, ?, ?)
        """, ("Admin", "admin@gmail.com", "admin123", "admin"))

    # ------------------ INSERT PRODUCTS ------------------
    cur.execute("SELECT COUNT(*) FROM products")
    count = cur.fetchone()[0]

    if count == 0:
        demo_products = [
            ("Laptop", 55000, 60000, 60, "Electronics", "2026-02-20"),
            ("Mouse", 400, 600, 85, "Accessories", "2026-02-20"),
            ("Monitor", 8000, 9500, 45, "Electronics", "2026-02-20"),
            ("Keyboard", 700, 1200, 15, "Accessories", "2026-02-20"),
            ("Printer", 12000, 15000, 10, "Office", "2026-02-20")
        ]

        cur.executemany("""
            INSERT INTO products
            (product, cost_price, selling_price, stock, category, date_added)
            VALUES (?, ?, ?, ?, ?, ?)
        """, demo_products)

    conn.commit()
    conn.close()
# ------------------ LOGIN ------------------

@app.route("/")
def login():
    return render_template("login.html")


@app.route("/login_check", methods=["POST"])
def login_check():
    email = request.form["email"]
    password = request.form["password"]

    conn = sqlite3.connect("users.db", timeout=10, check_same_thread=False)
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE email=? AND password=?", (email, password))
    user = cur.fetchone()
    conn.close()

    if user:
        session["user"] = user[1]
        return redirect("/dashboard")
    else:
        return "Invalid Login"


# ------------------ DASHBOARD ------------------

@app.route("/dashboard")
def dashboard():

    if "user" not in session:
        return redirect("/")

    conn = sqlite3.connect("users.db", timeout=10, check_same_thread=False)
    cur = conn.cursor()

    cur.execute("SELECT SUM(cost_price * stock) FROM products")
    inventory = cur.fetchone()[0] or 0

    cur.execute("SELECT SUM(selling_price * stock) FROM products")
    revenue = cur.fetchone()[0] or 0

    profit = revenue - inventory

    cur.execute("SELECT COUNT(*) FROM products WHERE stock < 20")
    low_stock = cur.fetchone()[0]

    # SALES TREND
    cur.execute("""
        SELECT date, SUM(total_amount) 
        FROM sales 
        GROUP BY date 
        ORDER BY date
    """)
    sales_data = cur.fetchall()
    sales_dates = [row[0] for row in sales_data]
    sales_values = [row[1] for row in sales_data]

    # PROFIT TREND (25% assumed margin)
    cur.execute("""
        SELECT date, SUM(total_amount) 
        FROM sales 
        GROUP BY date 
        ORDER BY date
    """)
    profit_data = cur.fetchall()
    profit_dates = [row[0] for row in profit_data]
    profit_values = [row[1] * 0.25 for row in profit_data]

        # EXPENSE BREAKDOWN
    cur.execute("""
        SELECT category, SUM(amount) 
        FROM expenses 
        GROUP BY category
    """)
    expense_data = cur.fetchall()
    expense_categories = [row[0] for row in expense_data]
    expense_values = [row[1] for row in expense_data]

    # TOTAL EXPENSE
    cur.execute("SELECT SUM(amount) FROM expenses")
    total_expense = cur.fetchone()[0] or 0

    conn.close()

    return render_template(
        "dashboard.html",
        name=session["user"],
        inventory=round(inventory, 2),
        revenue=round(revenue, 2),
        profit=round(profit, 2),
        total_expense=round(total_expense, 2),
        low_stock=low_stock,
        sales_dates=sales_dates,
        sales_values=sales_values,
        expense_categories=expense_categories,
        expense_values=expense_values,
        profit_dates=profit_dates,
        profit_values=profit_values
    )


# ------------------ SALES ------------------

@app.route("/sales", methods=["GET", "POST"])
def sales():

    conn = sqlite3.connect("users.db", timeout=10, check_same_thread=False)
    cur = conn.cursor()

    cur.execute("SELECT * FROM products")
    products = cur.fetchall()

    message = None

    if request.method == "POST":
        product = request.form["product"]
        quantity = int(request.form["quantity"])

        cur.execute("SELECT selling_price, stock FROM products WHERE product=?", (product,))
        data = cur.fetchone()

        selling_price = data[0]
        stock = data[1]

        if quantity > stock:
            message = "Not enough stock!"
        else:
            total_amount = selling_price * quantity
            new_stock = stock - quantity

            cur.execute("UPDATE products SET stock=? WHERE product=?", (new_stock, product))
            cur.execute("""
                INSERT INTO sales(product, quantity, total_amount, date)
                VALUES (?, ?, ?, DATE('now'))
            """, (product, quantity, total_amount))

            conn.commit()
            message = "Sale Recorded Successfully!"

    conn.close()
    return render_template("sales.html", products=products, message=message)


# ------------------ EXPENSES ------------------

@app.route("/expenses", methods=["GET", "POST"])
def expenses():

    conn = sqlite3.connect("users.db", timeout=10, check_same_thread=False)
    cur = conn.cursor()

    message = None

    if request.method == "POST":
        title = request.form["title"]
        amount = float(request.form["amount"])
        category = request.form["category"]

        cur.execute("""
            INSERT INTO expenses(title, amount, category, date)
            VALUES (?, ?, ?, DATE('now'))
        """, (title, amount, category))

        conn.commit()
        message = "Expense Added Successfully!"

    conn.close()
    return render_template("expenses.html", message=message)


# ------------------ INVENTORY ------------------

@app.route("/inventory")
def inventory():

    conn = sqlite3.connect("users.db", timeout=10, check_same_thread=False)
    cur = conn.cursor()

    cur.execute("SELECT * FROM products")
    products = cur.fetchall()

    conn.close()
    return render_template("inventory.html", products=products)


# ------------------ LOGOUT ------------------

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/predict", methods=["GET", "POST"])
def predict():

    if "user" not in session:
        return redirect("/")

    result = None
    graph_data = None
    pie_data = None

    if request.method == "POST":

        investment = float(request.form["investment"])
        sales = float(request.form["sales"])
        months = int(request.form["months"])

        profit = sales - investment
        margin = (profit / investment) * 100 if investment != 0 else 0

        result = {
            "investment": investment,
            "sales": sales,
            "profit": profit,
            "margin": round(margin, 2)
        }

        x = list(range(1, months + 1))
        y = [profit * (1 + 0.1*i) for i in range(months)]

        graph_data = {"x": x, "y": y}
        pie_data = {
            "investment": investment,
            "sales": sales,
            "profit": profit
        }

    return render_template(
        "predict.html",
        result=result,
        graph_data=graph_data,
        pie_data=pie_data
    )

@app.route("/upload", methods=["GET", "POST"])
def upload():

    if "user" not in session:
        return redirect("/")

    summary = None
    chart_data = None
    preview = None

    if request.method == "POST":
        file = request.files.get("file")

        if file and file.filename != "":

            if not os.path.exists("uploads"):
                os.makedirs("uploads")

            filepath = os.path.join("uploads", file.filename)
            file.save(filepath)

            df = pd.read_excel(filepath)

            # ---------------- PREVIEW ----------------
            preview = df.head().to_html(classes="table table-dark")

            # ---------------- AUTO ANALYSIS ----------------
            numeric_cols = df.select_dtypes(include=['int64','float64']).columns

            investment = df[numeric_cols[0]].sum() if len(numeric_cols) > 0 else 0
            sales = df[numeric_cols[1]].sum() if len(numeric_cols) > 1 else 0

            profit = sales - investment
            margin = (profit / investment * 100) if investment != 0 else 0

            summary = {
                "investment": round(investment,2),
                "sales": round(sales,2),
                "profit": round(profit,2),
                "margin": round(margin,2)
            }

            # ---------------- CHART DATA ----------------

            products = df[df.columns[0]].astype(str).tolist()[:10]

            stocks = []
            if len(numeric_cols) > 0:
                stocks = df[numeric_cols[0]].tolist()[:10]

            categories = df[df.columns[0]].astype(str).unique().tolist()[:5]

            category_values = []
            if len(numeric_cols) > 0:
                category_values = df.groupby(df.columns[0])[numeric_cols[0]].sum().tolist()[:5]

            chart_data = {
                "products": products,
                "stocks": stocks,
                "categories": categories,
                "category_values": category_values
            }

    return render_template(
        "upload.html",
        summary=summary,
        chart_data=chart_data,
        preview=preview
    )
@app.route("/forecast")
def forecast():

    if "user" not in session:
        return redirect("/")

    conn = sqlite3.connect("users.db", timeout=10, check_same_thread=False)
    cur = conn.cursor()

    cur.execute("""
        SELECT date, SUM(total_amount)
        FROM sales
        GROUP BY date
        ORDER BY date
    """)

    data = cur.fetchall()
    conn.close()

    if len(data) < 2:
        return "Not enough sales data for forecasting"

    dates = [row[0] for row in data]
    sales = [row[1] for row in data]

    # Convert to numeric index
    x = np.arange(len(sales))
    y = np.array(sales)

    # Simple Linear Regression (manual)
    slope, intercept = np.polyfit(x, y, 1)

    future_days = 7
    future_x = np.arange(len(sales), len(sales) + future_days)
    predictions = slope * future_x + intercept

    return render_template(
        "forecast.html",
        dates=dates,
        sales=sales,
        predictions=predictions.tolist()
    )

# ------------------ SIGNUP ------------------

@app.route("/signup")
def signup():
    return render_template("signup.html")


@app.route("/signup_submit", methods=["POST"])
def signup_submit():

    name = request.form["name"]
    email = request.form["email"]
    password = request.form["password"]

    conn = sqlite3.connect("users.db", timeout=10, check_same_thread=False)
    cur = conn.cursor()

    # Check if email already exists
    cur.execute("SELECT * FROM users WHERE email=?", (email,))
    existing_user = cur.fetchone()

    if existing_user:
        conn.close()
        return "Email already registered. Please login."

    cur.execute("""
        INSERT INTO users (name, email, password, role)
        VALUES (?, ?, ?, ?)
    """, (name, email, password, "user"))

    conn.commit()
    conn.close()

    return redirect("/")
@app.route("/admin")
def admin():

    if "user" not in session:
        return redirect("/")

    conn = sqlite3.connect("users.db", timeout=10, check_same_thread=False)
    cur = conn.cursor()

    # -------- SYSTEM STATS --------

    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM products")
    total_products = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM sales")
    total_sales = cur.fetchone()[0]

    cur.execute("SELECT SUM(amount) FROM expenses")
    total_expenses = cur.fetchone()[0] or 0


    # -------- USER GROWTH (demo for now) --------

    user_dates = ["Week1","Week2","Week3","Week4"]
    user_counts = [5, 8, 12, total_users]


    # -------- SYSTEM ACTIVITY --------

    activity_labels = ["Sales","Expenses","Products"]
    activity_values = [total_sales, total_expenses, total_products]


    # -------- RECENT SALES --------

    cur.execute("""
    SELECT product, quantity, total_amount, date
    FROM sales
    ORDER BY date DESC
    LIMIT 5
    """)

    recent_sales = cur.fetchall()


    # -------- LOW STOCK PRODUCTS --------

    cur.execute("""
    SELECT product, stock
    FROM products
    WHERE stock < 20
    """)

    low_stock_products = cur.fetchall()


    conn.close()

    return render_template(
        "admin.html",
        total_users=total_users,
        total_products=total_products,
        total_sales=total_sales,
        total_expenses=total_expenses,
        user_dates=user_dates,
        user_counts=user_counts,
        activity_labels=activity_labels,
        activity_values=activity_values,
        recent_sales=recent_sales,
        low_stock_products=low_stock_products
    )
@app.route("/download_report")
def download_report():

    if "user" not in session:
        return redirect("/")

    conn = sqlite3.connect("users.db", timeout=10, check_same_thread=False)
    cur = conn.cursor()

    # Fetch dashboard data
    cur.execute("SELECT SUM(cost_price * stock) FROM products")
    inventory = cur.fetchone()[0] or 0

    cur.execute("SELECT SUM(selling_price * stock) FROM products")
    revenue = cur.fetchone()[0] or 0

    profit = revenue - inventory

    cur.execute("SELECT SUM(amount) FROM expenses")
    expenses = cur.fetchone()[0] or 0


    # -------- SALES TREND CHART --------

    cur.execute("""
    SELECT date, SUM(total_amount)
    FROM sales
    GROUP BY date
    ORDER BY date
    """)

    sales_data = cur.fetchall()

    dates = [row[0] for row in sales_data]
    sales_values = [row[1] for row in sales_data]

    plt.figure()
    plt.plot(dates, sales_values, marker="o")
    plt.title("Sales Trend")
    plt.xlabel("Date")
    plt.ylabel("Sales")
    plt.xticks(rotation=45)

    sales_chart = "sales_chart.png"
    plt.tight_layout()
    plt.savefig(sales_chart)
    plt.close()


    # -------- EXPENSE PIE CHART --------

    cur.execute("""
    SELECT category, SUM(amount)
    FROM expenses
    GROUP BY category
    """)

    expense_data = cur.fetchall()

    labels = [row[0] for row in expense_data]
    values = [row[1] for row in expense_data]

    plt.figure()
    plt.pie(values, labels=labels, autopct="%1.1f%%")
    plt.title("Expense Distribution")

    expense_chart = "expense_chart.png"
    plt.savefig(expense_chart)
    plt.close()

    conn.close()


    # -------- GENERATE PDF REPORT --------

    file_path = "business_report.pdf"

    c = canvas.Canvas(file_path, pagesize=letter)

    c.setFont("Helvetica", 14)
    c.drawString(200, 750, "Business Analytics Report")

    c.setFont("Helvetica", 12)

    c.drawString(100, 700, f"Total Inventory Value: ₹ {inventory}")
    c.drawString(100, 670, f"Total Revenue: ₹ {revenue}")
    c.drawString(100, 640, f"Total Profit: ₹ {profit}")
    c.drawString(100, 610, f"Total Expenses: ₹ {expenses}")

    # Add charts to PDF
    c.drawImage(sales_chart, 100, 350, width=400, height=200)
    c.drawImage(expense_chart, 150, 120, width=300, height=200)

    c.save()

    return send_file(file_path, as_attachment=True)  
@app.route("/download_excel")
def download_excel():

    if "user" not in session:
        return redirect("/")

    conn = sqlite3.connect("users.db", timeout=10, check_same_thread=False)

    # Read tables into pandas
    products = pd.read_sql_query("SELECT * FROM products", conn)
    sales = pd.read_sql_query("SELECT * FROM sales", conn)
    expenses = pd.read_sql_query("SELECT * FROM expenses", conn)

    conn.close()

    file_path = "business_data.xlsx"

    with pd.ExcelWriter(file_path) as writer:
        products.to_excel(writer, sheet_name="Products", index=False)
        sales.to_excel(writer, sheet_name="Sales", index=False)
        expenses.to_excel(writer, sheet_name="Expenses", index=False)

    return send_file(file_path, as_attachment=True)
# ------------------ RUN APP ------------------
import os

if __name__ == "__main__":
    init_db()
    insert_demo_data()
    print(app.url_map)

    port = int(os.environ.get("PORT", 5000))

    app.run(host='0.0.0.0', port=port)