# analytics_web_app.py
from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS
import pyodbc
from datetime import datetime

app = Flask(__name__)
CORS(app)

# DB Connection
def get_db_cursor():
    try:
        conn = pyodbc.connect(
            "DRIVER={ODBC Driver 17 for SQL Server};"
            "SERVER=172.20.13.73;"
            "DATABASE=FredDB;"
            "UID=sa;"
            "PWD=sefam@21;"
        )
        return conn, conn.cursor()
    except Exception as e:
        print("❌ DB Error:", e)
        return None, None

# Utility
def format_hour_range(hour_24):
    start = hour_24 % 24
    end = (hour_24 + 1) % 24
    def to_ampm(h): return f"{h % 12 or 12}{'am' if h < 12 else 'pm'}"
    return f"{to_ampm(start)} to {to_ampm(end)}"

# Routes
@app.route("/")
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route("/top-items")
def top_items():
    start = request.args.get("start")
    end = request.args.get("end")
    branch = request.args.get("branch")

    where_clause = "WHERE GroupName = 'MAIN KITCHEN'"
    params = []

    # ✅ Only allow both dates or neither
    if (start and not end) or (end and not start):
        return jsonify({"error": "Please select both start and end dates or leave both empty."}), 400

    if start and end:
        where_clause += " AND VoucherDate BETWEEN ? AND ?"
        params.extend([start, end])

    if branch and branch != "All":
        where_clause += " AND BranchName = ?"
        params.append(branch)

    query = f"""
        SELECT TOP 10 ItemName, SUM(Qty) AS TotalQty
        FROM vwSaleDetail
        {where_clause}
        GROUP BY ItemName
        ORDER BY TotalQty DESC
    """

    conn, cursor = get_db_cursor()
    cursor.execute(query, *params)
    results = [{"ItemName": row[0], "TotalQty": int(row[1])} for row in cursor.fetchall()]
    conn.close()
    return jsonify(results)

@app.route("/avg-spending")
def avg_spending():
    conn, cursor = get_db_cursor()
    cursor.execute("""
        SELECT BranchName, TableName, ROUND(AVG(Amount), 2) AS AvgAmount
        FROM vwSaleDetail
        WHERE TableCode IS NOT NULL AND SaleType = 'D'
        GROUP BY BranchName, TableName
    """)
    results = [{"Branch": r[0], "Table": r[1], "AvgAmount": float(r[2])} for r in cursor.fetchall()]
    conn.close()
    return jsonify(results)

@app.route("/peak-times")
def peak_times():
    conn, cursor = get_db_cursor()
    cursor.execute("""
        SELECT DATEPART(HOUR, EntryTime) AS Hour, SUM(ISNULL(Amount, 0)) AS TotalAmount
        FROM vwSaleDetail WHERE EntryTime IS NOT NULL
        GROUP BY DATEPART(HOUR, EntryTime)
        ORDER BY TotalAmount DESC
    """)
    amt = cursor.fetchone()
    hour_amt = format_hour_range(int(amt[0])) if amt else None

    cursor.execute("""
        SELECT DATEPART(HOUR, EntryTime) AS Hour, COUNT(DISTINCT VoucherNo) AS OrderCount
        FROM vwSaleDetail WHERE EntryTime IS NOT NULL
        GROUP BY DATEPART(HOUR, EntryTime)
        ORDER BY OrderCount DESC
    """)
    ords = cursor.fetchone()
    hour_ord = format_hour_range(int(ords[0])) if ords else None

    conn.close()
    return jsonify({
        "peak_amount": {"hour": hour_amt, "amount": float(amt[1]) if amt else 0},
        "peak_orders": {"hour": hour_ord, "orders": int(ords[1]) if ords else 0}
    })

@app.route("/peak-by-date")
def peak_by_date():
    date = request.args.get("date")
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    conn, cursor = get_db_cursor()

    cursor.execute("""
        SELECT DATEPART(HOUR, EntryTime) AS Hour, SUM(ISNULL(Amount, 0)) AS TotalAmount
        FROM vwSaleDetail WHERE CAST(EntryTime AS DATE) = ?
        GROUP BY DATEPART(HOUR, EntryTime)
        ORDER BY TotalAmount DESC
    """, date)
    amt = cursor.fetchone()
    hour_amt = format_hour_range(int(amt[0])) if amt else None

    cursor.execute("""
        SELECT DATEPART(HOUR, EntryTime) AS Hour, COUNT(DISTINCT VoucherNo) AS OrderCount
        FROM vwSaleDetail WHERE CAST(EntryTime AS DATE) = ?
        GROUP BY DATEPART(HOUR, EntryTime)
        ORDER BY OrderCount DESC
    """, date)
    ords = cursor.fetchone()
    hour_ord = format_hour_range(int(ords[0])) if ords else None

    conn.close()
    return jsonify({
        "peak_amount": {"hour": hour_amt, "amount": float(amt[1]) if amt else 0},
        "peak_orders": {"hour": hour_ord, "orders": int(ords[1]) if ords else 0}
    })


@app.route("/peak-by-date-range")
def peak_by_date_range():
    start = request.args.get("start")
    end = request.args.get("end")
    branch = request.args.get("branch")

    try:
        datetime.strptime(start, "%Y-%m-%d")
        datetime.strptime(end, "%Y-%m-%d")
    except:
        return jsonify({"error": "Invalid date format"}), 400

    conn, cursor = get_db_cursor()

    query = """
        SELECT DATEPART(HOUR, EntryTime) AS Hour,
               SUM(ISNULL(Amount, 0)) AS TotalAmount,
               COUNT(DISTINCT VoucherNo) AS TotalOrders
        FROM vwSaleDetail
        WHERE CAST(EntryTime AS DATE) BETWEEN ? AND ?
    """

    params = [start, end]

    if branch and branch != "All":
        query += " AND BranchName = ?"
        params.append(branch)

    query += " GROUP BY DATEPART(HOUR, EntryTime) ORDER BY DATEPART(HOUR, EntryTime)"

    try:
        cursor.execute(query, *params)  # ✅ Fix here
        rows = cursor.fetchall()
    except Exception as e:
        print("❌ SQL Error:", e)
        return jsonify({"error": "Query failed"}), 500
    finally:
        conn.close()

    result = []
    for r in rows:
        hour = int(r[0])
        result.append({
            "HourRange": format_hour_range(hour),
            "TotalAmount": float(r[1]),
            "TotalOrders": int(r[2])
        })

    return jsonify(result)


@app.route("/table-spending")
def table_spending():
    start = request.args.get("start")
    end = request.args.get("end")
    branch = request.args.get("branch")

    if not start or not end:
        return jsonify({"error": "Start and end dates are required."}), 400

    try:
        datetime.strptime(start, "%Y-%m-%d")
        datetime.strptime(end, "%Y-%m-%d")
    except:
        return jsonify({"error": "Invalid date format"}), 400

    conn, cursor = get_db_cursor()

    base_query = """
        SELECT TableCode, TableName, 
               COUNT(DISTINCT VoucherNo) AS TotalOrders,
               SUM(Amount) AS TotalSpending,
               ROUND(SUM(Amount) * 1.0 / COUNT(DISTINCT VoucherNo), 0) AS AvgSpending
        FROM vwSaleDetail
        WHERE VoucherDate BETWEEN ? AND ?
          AND SaleType = 'D'
    """

    params = [start, end]

    if branch and branch != "All":
        base_query += " AND BranchName = ?"
        params.append(branch)

    base_query += " GROUP BY TableCode, TableName"

    cursor.execute(base_query, params)
    rows = cursor.fetchall()
    conn.close()

    results = [dict(zip(["TableCode", "TableName", "TotalOrders", "TotalSpending", "AvgSpending"], r)) for r in rows]
    for r in results:
        r["TotalSpending"] = float(r["TotalSpending"])
        r["AvgSpending"] = float(r["AvgSpending"])
    return jsonify(results)



HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>FredDB Sale Analytics</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
  <style>
    :root {
      --primary-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      --secondary-gradient: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
      --success-gradient: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
      --dark-bg: #1a1d29;
      --card-bg: #ffffff;
      --sidebar-bg: #2d3748;
      --text-primary: #2d3748;
      --text-secondary: #718096;
      --border-color: #e2e8f0;
      --shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
      --shadow-hover: 0 20px 40px rgba(0, 0, 0, 0.15);
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
      min-height: 100vh;
    }

    /* Header */
    .main-header {
      background: var(--primary-gradient);
      padding: 1rem 0;
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      z-index: 1030;
      box-shadow: var(--shadow);
    }

    .main-header h1 {
      color: white;
      font-weight: 700;
      font-size: 1.75rem;
      margin: 0;
      text-align: center;
    }

    .hamburger {
      display: none;
      background: none;
      border: none;
      color: white;
      font-size: 1.5rem;
      cursor: pointer;
      position: absolute;
      left: 1rem;
      top: 50%;
      transform: translateY(-50%);
    }

    /* Sidebar */
    .sidebar {
      background: var(--sidebar-bg);
      width: 280px;
      position: fixed;
      left: 0;
      top: 70px;
      bottom: 0;
      padding: 2rem 0;
      transition: transform 0.3s ease;
      z-index: 1020;
      overflow-y: auto;
    }

    .sidebar.collapsed {
      transform: translateX(-100%);
    }

    .sidebar-nav {
      list-style: none;
      padding: 0;
      margin: 0;
    }

    .sidebar-nav li {
      margin: 0.5rem 1rem;
    }

    .sidebar-nav a {
      display: flex;
      align-items: center;
      padding: 0.875rem 1rem;
      color: #cbd5e1;
      text-decoration: none;
      border-radius: 10px;
      transition: all 0.3s ease;
      font-weight: 500;
    }

    .sidebar-nav a:hover,
    .sidebar-nav a.active {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      transform: translateX(5px);
      box-shadow: 0 5px 15px rgba(102, 126, 234, 0.3);
    }

    .sidebar-nav a i {
      margin-right: 0.75rem;
      width: 20px;
      text-align: center;
    }

    /* Main Content */
    .main-content {
      margin-left: 280px;
      margin-top: 70px;
      padding: 2rem;
      transition: margin-left 0.3s ease;
      min-height: calc(100vh - 70px);
    }

    .main-content.expanded {
      margin-left: 0;
    }

    /* Cards */
    .analytics-card {
      background: var(--card-bg);
      border-radius: 16px;
      padding: 2rem;
      box-shadow: var(--shadow);
      border: 1px solid var(--border-color);
      transition: all 0.3s ease;
      margin-bottom: 2rem;
    }

    # .analytics-card:hover {
    #   box-shadow: var(--shadow-hover);
    #   transform: translateY(-2px);
    # }

    .section-title {
      font-size: 1.5rem;
      font-weight: 700;
      color: var(--text-primary);
      margin-bottom: 1.5rem;
      display: flex;
      align-items: center;
    }

    .section-title i {
      margin-right: 0.75rem;
      background: var(--primary-gradient);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }

    /* Form Controls */
    .form-control, .form-select {
      border: 2px solid var(--border-color);
      border-radius: 10px;
      padding: 0.75rem 1rem;
      font-size: 0.95rem;
      transition: all 0.3s ease;
    }

    .form-control:focus, .form-select:focus {
      border-color: #667eea;
      box-shadow: 0 0 0 0.2rem rgba(102, 126, 234, 0.25);
    }

    /* Buttons */
    .btn-gradient {
      background: var(--primary-gradient);
      border: none;
      color: white;
      padding: 0.75rem 1.5rem;
      border-radius: 10px;
      font-weight: 600;
      transition: all 0.3s ease;
      box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
    }

    .btn-gradient:hover {
      transform: translateY(-2px);
      box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4);
      color: white;
    }

    .btn-secondary-gradient {
      background: var(--secondary-gradient);
      border: none;
      color: white;
      padding: 0.75rem 1.5rem;
      border-radius: 10px;
      font-weight: 600;
      transition: all 0.3s ease;
      box-shadow: 0 4px 15px rgba(245, 87, 108, 0.3);
    }

    .btn-secondary-gradient:hover {
      transform: translateY(-2px);
      box-shadow: 0 8px 25px rgba(245, 87, 108, 0.4);
      color: white;
    }

    .btn-success-gradient {
      background: var(--success-gradient);
      border: none;
      color: white;
      padding: 0.75rem 1.5rem;
      border-radius: 10px;
      font-weight: 600;
      transition: all 0.3s ease;
      box-shadow: 0 4px 15px rgba(79, 172, 254, 0.3);
    }

    .btn-success-gradient:hover {
      transform: translateY(-2px);
      box-shadow: 0 8px 25px rgba(79, 172, 254, 0.4);
      color: white;
    }

    /* Search Bar */
    .search-container {
      position: relative;
      margin-bottom: 1.5rem;
    }

    .search-input {
      padding-left: 3rem;
    }

    .search-icon {
      position: absolute;
      left: 1rem;
      top: 50%;
      transform: translateY(-50%);
      color: var(--text-secondary);
    }

    /* Table */
    .table-container {
      background: white;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: var(--shadow);
    }

    .table {
      margin: 0;
    }

    .table thead th {
      background: var(--primary-gradient);
      color: white;
      font-weight: 600;
      border: none;
      padding: 1rem;
      text-align: center;
    }

    .table tbody td {
      padding: 0.875rem 1rem;
      border-color: var(--border-color);
      text-align: center;
      vertical-align: middle;
    }

    .table tbody tr:hover {
      background-color: #f8fafc;
    }

    /* Stats Cards */
    .stats-card {
      background: var(--card-bg);
      border-radius: 16px;
      padding: 1.5rem;
      text-align: center;
      box-shadow: var(--shadow);
      border: 1px solid var(--border-color);
      transition: all 0.3s ease;
    }

    .stats-card:hover {
      transform: translateY(-5px);
      box-shadow: var(--shadow-hover);
    }

    .stats-card .icon {
      font-size: 2.5rem;
      background: var(--primary-gradient);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      margin-bottom: 1rem;
    }

    .stats-card h3 {
      font-size: 2rem;
      font-weight: 700;
      color: var(--text-primary);
      margin-bottom: 0.5rem;
    }

    .stats-card p {
      color: var(--text-secondary);
      margin: 0;
      font-weight: 500;
    }

    /* Records Counter */
    .records-info {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 1rem;
      background: #f8fafc;
      border-top: 1px solid var(--border-color);
      font-size: 0.875rem;
      color: var(--text-secondary);
      font-weight: 500;
    }

    .no-data {
      text-align: center;
      padding: 3rem;
      color: var(--text-secondary);
    }

    .no-data i {
      font-size: 3rem;
      margin-bottom: 1rem;
      opacity: 0.5;
    }

    /* Responsive Design */
    @media (max-width: 11024px) {
      .sidebar {
        transform: translateX(-100%);
      }
      
      .sidebar.show {
        transform: translateX(0);
      }
      
      .main-content {
        margin-left: 0;
      }
      
      .hamburger {
        display: block;
      }
    }

    @media (max-width: 768px) {
      .main-header h1 {
        font-size: 1.25rem;
        margin-left: 3rem;
        text-align: left;
      }
      
      .main-content {
        padding: 1rem;
      }
      
      .analytics-card {
        padding: 1.5rem;
      }
      
      .section-title {
        font-size: 1.25rem;
      }
      
      .table-responsive {
        font-size: 0.875rem;
      }
    }

    @media (max-width: 576px) {
      .main-header h1 {
        font-size: 1.1rem;
      }
      
      .analytics-card {
        padding: 1rem;
      }
      
      .form-control, .form-select {
        padding: 0.625rem 0.875rem;
        font-size: 0.875rem;
      }
      
      .btn-gradient, .btn-secondary-gradient, .btn-success-gradient {
        padding: 0.625rem 1rem;
        font-size: 0.875rem;
      }
    }

    /* Loading Animation */
    .loading {
      display: flex;
      justify-content: center;
      align-items: center;
      padding: 3rem;
    }

    .spinner {
      width: 40px;
      height: 40px;
      border: 4px solid #f3f3f3;
      border-top: 4px solid #667eea;
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }

    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }

    /* Overlay for mobile sidebar */
    .sidebar-overlay {
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.5);
      z-index: 1010;
    }

    .sidebar-overlay.show {
      display: block;
    }
  </style>
</head>
<body>
  <!-- Header -->
  <header class="main-header">
    <button class="hamburger" onclick="toggleSidebar()">
      <i class="fas fa-bars"></i>
    </button>
    <h1><i class="fas fa-chart-line me-2"></i>FredDB Sale Analytics</h1>
  </header>

  <!-- Sidebar Overlay -->
  <div class="sidebar-overlay" id="sidebarOverlay" onclick="toggleSidebar()"></div>

  <!-- Sidebar -->
  <nav class="sidebar" id="sidebar">
    <ul class="sidebar-nav">
      <li>
        <a href="#" onclick="showSection('top-selling')" class="active">
          <i class="fas fa-trophy"></i>
          Top Selling Items
        </a>
      </li>
      <li>
        <a href="#" onclick="showSection('avg-spending')">
          <i class="fas fa-coins"></i>
          Average Spending
        </a>
      </li>
      <li>
        <a href="#" onclick="showSection('peak-time')">
          <i class="fas fa-clock"></i>
          Peak Times
        </a>
      </li>
      <li>
        <a href="#" onclick="showSection('peak-date')">
          <i class="fas fa-calendar-alt"></i>
          Peak by Date
        </a>
      </li>
      <li>
        <a href="#" onclick="showSection('table-spending')">
          <i class="fas fa-table"></i>
          Table Spending
        </a>
      </li>
    </ul>
  </nav>

  <!-- Main Content -->
  <main class="main-content" id="mainContent">
    
    <!-- Top Selling Items Section -->
    <section id="top-selling" class="section">
      <div class="analytics-card">
        <h2 class="section-title">
          <i class="fas fa-trophy"></i>
          Top Selling Items
        </h2>
        
        <div class="row g-3 mb-4">
          <div class="col-md-3">
            <label class="form-label fw-semibold">From Date</label>
            <input type="date" id="start" class="form-control">
          </div>
          <div class="col-md-3">
            <label class="form-label fw-semibold">To Date</label>
            <input type="date" id="end" class="form-control">
          </div>
          <div class="col-md-4">
            <label class="form-label fw-semibold">Branch</label>
            <select id="branch" class="form-select">
              <option>All</option>
              <option>FRED - THE RESTAURANT</option>
              <option>GAIJIN</option>
              <option>POLYMATH</option>
              <option>SOULFEST 2024</option>
              <option>THE OBSERVATORY</option>
            </select>
          </div>
          <div class="col-md-2 d-flex align-items-end">
            <button onclick="loadTopItems()" class="btn btn-gradient w-100">
              <i class="fas fa-search me-2"></i>Analyze
            </button>
          </div>
        </div>
        
        <div id="top-selling-output">
          <div class="no-data">
            <i class="fas fa-chart-bar"></i>
            <p>Please select filters and click "Analyze" to view results</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Average Spending Section -->
    <section id="avg-spending" class="section d-none">
      <div class="analytics-card">
        <h2 class="section-title">
          <i class="fas fa-coins"></i>
          Average Spending per Table for All Data
        </h2>
        <div id="avg-output">
          <div class="loading">
            <div class="spinner"></div>
          </div>
        </div>
      </div>
    </section>

    <!-- Peak Times Section -->
    <section id="peak-time" class="section d-none">
      <div class="analytics-card">
        <h2 class="section-title">
          <i class="fas fa-clock"></i>
          Peak Times (All Time)
        </h2>
        <div id="peak-output">
          <div class="loading">
            <div class="spinner"></div>
          </div>
        </div>
      </div>
    </section>

<!-- Peak by Date Section -->
<section id="peak-date" class="section d-none">
  <div class="analytics-card">
    <h2 class="section-title">
      <i class="fas fa-calendar-alt"></i>
      Peak Times by Date Range
    </h2>

    <div class="row g-3 mb-4">
      <div class="col-md-3">
        <label class="form-label fw-semibold">Start Date</label>
        <input type="date" id="pb-start" class="form-control">
      </div>
      <div class="col-md-3">
        <label class="form-label fw-semibold">End Date</label>
        <input type="date" id="pb-end" class="form-control">
      </div>
      <div class="col-md-3">
        <label class="form-label fw-semibold">Branch</label>
        <select id="pb-branch" class="form-select">
          <option value="All">All</option>
          <option>FRED - THE RESTAURANT</option>
          <option>GAIJIN</option>
          <option>POLYMATH</option>
          <option>SOULFEST 2024</option>
          <option>THE OBSERVATORY</option>
        </select>
      </div>
      <div class="col-md-3 d-flex align-items-end">
        <button onclick="loadPeakByDateRange()" class="btn btn-secondary-gradient w-100">
          <i class="fas fa-calendar-check me-2"></i>Analyze Range
        </button>
      </div>
      <div class="col-md-3 d-flex align-items-end mt-2">
        <button onclick="showPeakChartPopup()" class="btn btn-success-gradient w-100">
          <i class="fas fa-chart-bar me-2"></i>Show Chart
        </button>
      </div>
    </div>

    <div id="peak-date-output">
      <div class="no-data">
        <i class="fas fa-calendar"></i>
        <p>Choose date range and click "Analyze Range" to view results</p>
      </div>
    </div>
  </div>
</section>

<!-- 🔳 MODAL CHART POPUP -->
<div class="modal" id="peakChartModal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.6); z-index:1050; justify-content:center; align-items:center;">
  <div style="background:white; border-radius:12px; padding:20px; max-width:800px; width:90%; position:relative;">
    <button onclick="closePeakChartPopup()" style="position:absolute; top:10px; right:15px; background:none; border:none; font-size:1.5rem; cursor:pointer;">
      <i class="fas fa-times"></i>
    </button>
    <h5 class="mb-3">Peak Hours by Date Range</h5>
    <canvas id="peakChartCanvas" height="100"></canvas>
  </div>
</div>


   
    <!-- Table Spending Section -->
<section id="table-spending" class="section d-none">
  <div class="analytics-card">
    <h2 class="section-title">
      <i class="fas fa-table"></i>
      Table Spending Analysis
    </h2>

    <div class="row g-3 mb-4">
      <div class="col-md-3">
        <label class="form-label fw-semibold">Start Date</label>
        <input type="date" id="ts-start" class="form-control">
      </div>
      <div class="col-md-3">
        <label class="form-label fw-semibold">End Date</label>
        <input type="date" id="ts-end" class="form-control">
      </div>
      <div class="col-md-3">
        <label class="form-label fw-semibold">Branch</label>
        <select id="ts-branch" class="form-select">
          <option value="All">All</option>
          <option>FRED - THE RESTAURANT</option>
          <option>GAIJIN</option>
          <option>POLYMATH</option>
          <option>SOULFEST 2024</option>
          <option>THE OBSERVATORY</option>
        </select>
      </div>
      <div class="col-md-3 d-flex align-items-end">
        <button onclick="loadTableSpending()" class="btn btn-secondary-gradient w-100">
          <i class="fas fa-chart-line me-2"></i>Get Data
        </button>
      </div>
      <div class="col-md-3 d-flex align-items-end">
        <button onclick="renderSpendingChart()" class="btn btn-success-gradient w-100">
          <i class="fas fa-chart-bar me-2"></i>Show Chart
        </button>
      </div>
    </div>

    <div id="table-spending-output">
      <div class="no-data">
        <i class="fas fa-table"></i>
        <p>Select date range and click "Get Data" to view results</p>
      </div>
    </div>
  </div>

</section>

  <!-- 🔳 TABLE SPENDING CHART POPUP -->
<div class="modal" id="tableChartModal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.6); z-index:1050; justify-content:center; align-items:center;">
  <div style="background:white; border-radius:12px; padding:20px; max-width:800px; width:90%; position:relative;">
    <button onclick="closeTableChartPopup()" style="position:absolute; top:10px; right:15px; background:none; border:none; font-size:1.5rem; cursor:pointer;">
      <i class="fas fa-times"></i>
    </button>
    <h5 class="mb-3">Table Spending Chart</h5>
    <canvas id="tableSpendingChart" height="100"></canvas>
  </div>
</div>


  </main>

  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
  <script>
    let currentTableData = [];
    let filteredData = [];

    // Toggle sidebar for mobile
    function toggleSidebar() {
      const sidebar = document.getElementById('sidebar');
      const overlay = document.getElementById('sidebarOverlay');
      const mainContent = document.getElementById('mainContent');
      
      sidebar.classList.toggle('show');
      overlay.classList.toggle('show');
      
      if (window.innerWidth > 1024) {
        sidebar.classList.toggle('collapsed');
        mainContent.classList.toggle('expanded');
      }
    }

    // Show section
    function showSection(sectionId) {
      // Hide all sections
      document.querySelectorAll('.section').forEach(section => {
        section.classList.add('d-none');
      });
      
      // Show selected section
      document.getElementById(sectionId).classList.remove('d-none');
      
      // Update active nav item
      document.querySelectorAll('.sidebar-nav a').forEach(link => {
        link.classList.remove('active');
      });
      event.target.classList.add('active');
      
      // Close sidebar on mobile after selection
      if (window.innerWidth <= 11024) {
        toggleSidebar();
      }
      
      // Load data for specific sections
      if (sectionId === 'avg-spending') {
        loadAvgSpending();
      } else if (sectionId === 'peak-time') {
        loadPeakTimes();
      }
    }

    // Load top items
function loadTopItems() {
  const start = document.getElementById('start').value;
  const end = document.getElementById('end').value;
  const branch = document.getElementById('branch').value;
  const output = document.getElementById('top-selling-output');

  // 🛑 Enforce both or none logic
  if ((start && !end) || (!start && end)) {
    alert('⚠️ Please select both Start and End dates.');
    return;
  }

  // ✅ At least require both dates
  if (!start || !end) {
    alert('⚠️ Date range is required.');
    return;
  }

  output.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

  const url = `/top-items?start=${start}&end=${end}&branch=${encodeURIComponent(branch)}`;

  fetch(url)
    .then(response => response.json())
    .then(data => {
      currentTableData = data;
      filteredData = [...data];
      renderTable('top-selling-output', data, ['ItemName', 'TotalQty']);
    })
    .catch(error => {
      output.innerHTML = '<div class="no-data"><i class="fas fa-exclamation-triangle"></i><p>Error loading data</p></div>';
    });
}


    // Load average spending
    function loadAvgSpending() {
      const output = document.getElementById('avg-output');
      output.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
      
      fetch('/avg-spending')
        .then(response => response.json())
        .then(data => {
          currentTableData = data;
          filteredData = [...data];
          renderTable('avg-output', data, ['Branch', 'Table', 'AvgAmount']);
        })
        .catch(error => {
          output.innerHTML = '<div class="no-data"><i class="fas fa-exclamation-triangle"></i><p>Error loading data</p></div>';
        });
    }

    // Load peak times
    function loadPeakTimes() {
      const output = document.getElementById('peak-output');
      output.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
      
      fetch('/peak-times')
        .then(response => response.json())
        .then(data => {
          renderPeakStats(data, 'peak-output');
        })
        .catch(error => {
          output.innerHTML = '<div class="no-data"><i class="fas fa-exclamation-triangle"></i><p>Error loading data</p></div>';
        });
    }

    // Load peak by date
    function loadPeakDate() {
      const date = document.getElementById('peak-date-input').value;
      if (!date) {
        alert('Please select a date');
        return;
      }
      
      const output = document.getElementById('peak-date-output');
      output.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
      
      fetch(`/peak-by-date?date=${date}`)
        .then(response => response.json())
        .then(data => {
          renderPeakStats(data, 'peak-date-output');
        })
        .catch(error => {
          output.innerHTML = '<div class="no-data"><i class="fas fa-exclamation-triangle"></i><p>Error loading data</p></div>';
        });
    }

    // Load table spending
  function loadTableSpending() {
  const start = document.getElementById('ts-start').value;
  const end = document.getElementById('ts-end').value;
  const branch = document.getElementById('ts-branch').value;

  if (!start || !end) {
    alert('Please select start and end dates');
    return;
  }

  const output = document.getElementById('table-spending-output');
  output.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

  fetch(`/table-spending?start=${start}&end=${end}&branch=${encodeURIComponent(branch)}`)
    .then(response => response.json())
    .then(data => {
      currentTableData = data;
      filteredData = [...data];
      renderTable('table-spending-output', data, ['TableCode', 'TableName', 'TotalOrders', 'TotalSpending', 'AvgSpending']);
    })
    .catch(error => {
      output.innerHTML = '<div class="no-data"><i class="fas fa-exclamation-triangle"></i><p>Error loading data</p></div>';
    });
}


    // Render table with search functionality
    function renderTable(containerId, data, columns) {
      const container = document.getElementById(containerId);
      
      if (!data || data.length === 0) {
        container.innerHTML = '<div class="no-data"><i class="fas fa-inbox"></i><p>No data found</p></div>';
        return;
      }

      // Create search bar
      const searchId = `search-${containerId}`;
      const tableId = `table-${containerId}`;
      
      let html = `
        <div class="search-container">
          <i class="fas fa-search search-icon"></i>
          <input type="text" 
                 id="${searchId}" 
                 class="form-control search-input" 
                 placeholder="Search in results..." 
                 onkeyup="filterTable('${searchId}', '${tableId}', '${containerId}')">
        </div>
        <div class="table-container">
          <div class="table-responsive">
            <table class="table table-hover" id="${tableId}">
              <thead>
                <tr>
                  <th><i class="fas fa-hashtag me-1"></i>#</th>
      `;
      
      // Add column headers
      columns.forEach(col => {
        let icon = getColumnIcon(col);
        html += `<th><i class="${icon} me-1"></i>${formatColumnName(col)}</th>`;
      });
      html += '</tr></thead><tbody>';
      
      // Add data rows
      data.forEach((row, index) => {
        html += `<tr><td><span class="badge bg-primary">${index + 1}</span></td>`;
        columns.forEach(col => {
          let value = row[col];
          if (col.includes('Amount') || col.includes('Avg')) {
            value = `<span class="fw-bold text-success">Rs. ${Number(value).toLocaleString()}</span>`;
          } else if (col.includes('Date')) {
            value = `<span class="text-muted">${value}</span>`;
          } else if (col.includes('Qty')) {
            value = `<span class="badge bg-info">${value}</span>`;
          }
          html += `<td>${value}</td>`;
        });
        html += '</tr>';
      });
      
      html += '</tbody></table></div>';
      html += `<div class="records-info">
                 <span><i class="fas fa-info-circle me-1"></i>Showing <span id="showing-${containerId}">${data.length}</span> of <span id="total-${containerId}">${data.length}</span> records</span>
                 <span><i class="fas fa-database me-1"></i>Total Records: ${data.length}</span>
               </div>`;
      html += '</div>';
      
      container.innerHTML = html;
      
      // Store original data for filtering
      window[`originalData_${containerId}`] = data;
    }

    // Filter table based on search input
    function filterTable(searchId, tableId, containerId) {
      const searchInput = document.getElementById(searchId);
      const table = document.getElementById(tableId);
      const searchTerm = searchInput.value.toLowerCase();
      const tbody = table.getElementsByTagName('tbody')[0];
      const rows = tbody.getElementsByTagName('tr');
      
      let visibleCount = 0;
      
      for (let i = 0; i < rows.length; i++) {
        let row = rows[i];
        let text = row.textContent || row.innerText;
        
        if (text.toLowerCase().indexOf(searchTerm) > -1) {
          row.style.display = '';
          visibleCount++;
          // Update row number
          row.cells[0].innerHTML = `<span class="badge bg-primary">${visibleCount}</span>`;
        } else {
          row.style.display = 'none';
        }
      }
      
      // Update records info
      const showingElement = document.getElementById(`showing-${containerId}`);
      if (showingElement) {
        showingElement.textContent = visibleCount;
      }
    }

    // Render peak statistics
    function renderPeakStats(data, containerId) {
      const container = document.getElementById(containerId);
      
      const html = `
        <div class="row">
          <div class="col-md-6 mb-3">
            <div class="stats-card">
              <div class="icon">
                <i class="fas fa-money-bill-wave"></i>
              </div>
              <h3>Rs. ${Number(data.peak_amount.amount).toLocaleString()}</h3>
              <p>Peak Revenue Hour</p>
              <div class="mt-2">
                <span class="badge bg-success fs-6">${data.peak_amount.hour}</span>
              </div>
            </div>
          </div>
          <div class="col-md-6 mb-3">
            <div class="stats-card">
              <div class="icon">
                <i class="fas fa-shopping-cart"></i>
              </div>
              <h3>${data.peak_orders.orders}</h3>
              <p>Peak Orders Hour</p>
              <div class="mt-2">
                <span class="badge bg-info fs-6">${data.peak_orders.hour}</span>
              </div>
            </div>
          </div>
        </div>
      `;
      
      container.innerHTML = html;
    }

    // Get appropriate icon for column
    function getColumnIcon(columnName) {
      const icons = {
        'ItemName': 'fas fa-box',
        'TotalQty': 'fas fa-chart-bar',
        'Branch': 'fas fa-building',
        'Table': 'fas fa-chair',
        'AvgAmount': 'fas fa-calculator',
        'Date': 'fas fa-calendar',
        'Type': 'fas fa-tag',
        'TypeName': 'fas fa-tags',
        'Amount': 'fas fa-dollar-sign',
        'TableCode': 'fas fa-hashtag',
        'TotalOrders': 'fas fa-receipt',
        'TotalSpending': 'fas fa-wallet',
        'AvgSpending': 'fas fa-balance-scale'

      };
      return icons[columnName] || 'fas fa-circle';
    }

    // Format column name for display
    function formatColumnName(columnName) {
      const names = {
        'ItemName': 'Item Name',
        'TotalQty': 'Total Quantity',
        'AvgAmount': 'Average Amount',
        'TypeName': 'Sale Type'
      };
      return names[columnName] || columnName;
    }

    // Handle window resize
    window.addEventListener('resize', function() {
      const sidebar = document.getElementById('sidebar');
      const overlay = document.getElementById('sidebarOverlay');
      
      if (window.innerWidth > 1024) {
        sidebar.classList.remove('show');
        overlay.classList.remove('show');
      }
    });

    // Initialize page
    window.addEventListener('DOMContentLoaded', function() {
      // Set default dates
      const today = new Date();
      const oneWeekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
      
      document.getElementById('start').value = oneWeekAgo.toISOString().split('T')[0];
      document.getElementById('end').value = today.toISOString().split('T')[0];
      document.getElementById('peak-date-input').value = today.toISOString().split('T')[0];
      document.getElementById('ts-start').value = oneWeekAgo.toISOString().split('T')[0];
      document.getElementById('ts-end').value = today.toISOString().split('T')[0];
    });
window.addEventListener('DOMContentLoaded', () => {
  // Top Selling
  document.getElementById('start').value = '';
  document.getElementById('end').value = '';

  // Peak by Date
  document.getElementById('peak-date-input').value = '';

  // Table Spending
  document.getElementById('ts-start').value = '';
  document.getElementById('ts-end').value = '';
});
  let tableChart = null;
  function renderSpendingChart() {
  if (!filteredData || filteredData.length === 0) {
    alert('Please get data first before showing chart.');
    return;
  }

  // Show popup modal
  const modal = document.getElementById('tableChartModal');
  modal.style.display = 'flex';

  const ctx = document.getElementById('tableSpendingChart').getContext('2d');
  if (window.tableChart) window.tableChart.destroy();

  const labels = filteredData.map(row => row.TableName || row.TableCode);
  const spending = filteredData.map(row => row.TotalSpending);

  window.tableChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Total Spending (Rs.)',
        data: spending,
        backgroundColor: 'rgba(102, 126, 234, 0.6)',
        borderColor: 'rgba(102, 126, 234, 1)',
        borderWidth: 1
      }]
    },
    options: {
      responsive: true,
      plugins: {
        title: {
          display: true,
          text: 'Total Spending per Table',
          font: { size: 18 }
        },
        tooltip: {
          callbacks: {
            label: ctx => `Rs. ${Number(ctx.raw).toLocaleString()}`
          }
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            callback: value => `Rs. ${value}`
          },
          title: {
            display: true,
            text: 'Total Spending (Rs.)'
          }
        },
        x: {
          title: {
            display: true,
            text: 'Table'
          }
        }
      }
    }
  });
}
function closeTableChartPopup() {
  document.getElementById('tableChartModal').style.display = 'none';
}


  function loadPeakByDateRange() {
  const start = document.getElementById('pb-start').value;
  const end = document.getElementById('pb-end').value;
  const branch = document.getElementById('pb-branch').value;
  const output = document.getElementById('peak-date-output');

  if (!start || !end) {
    alert('Please select both Start and End dates.');
    return;
  }

  output.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

  fetch(`/peak-by-date-range?start=${start}&end=${end}&branch=${encodeURIComponent(branch)}`)
    .then(response => response.json())
    .then(data => {
      currentTableData = data;
      filteredData = [...data];
      renderTable('peak-date-output', data, ['HourRange', 'TotalAmount', 'TotalOrders']);
    })
    .catch(error => {
      output.innerHTML = '<div class="no-data"><i class="fas fa-exclamation-triangle"></i><p>Error loading data</p></div>';
    });
}

function showPeakChartPopup() {
  if (!filteredData || filteredData.length === 0) {
    alert('Please analyze data first.');
    return;
  }

  const modal = document.getElementById('peakChartModal');
  modal.style.display = 'flex';

  const ctx = document.getElementById('peakChartCanvas').getContext('2d');
  if (window.peakChart) window.peakChart.destroy();

  const labels = filteredData.map(r => r.HourRange);
  const amounts = filteredData.map(r => r.TotalAmount);

  window.peakChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Total Amount (Rs.)',
        data: amounts,
        backgroundColor: 'rgba(245, 87, 108, 0.6)',
        borderColor: 'rgba(245, 87, 108, 1)',
        borderWidth: 1
      }]
    },
    options: {
      responsive: true,
      plugins: {
        title: {
          display: true,
          text: 'Total Sale by Hour',
          font: { size: 18 }
        },
        tooltip: {
          callbacks: {
            label: ctx => `Rs. ${Number(ctx.raw).toLocaleString()}`
          }
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: { callback: val => `Rs. ${val}` },
          title: { display: true, text: 'Total Sale (Rs.)' }
        }
      }
    }
  });
}

function closePeakChartPopup() {
  document.getElementById('peakChartModal').style.display = 'none';
}

  

  </script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</body>
</html>
"""

# ------------- RUN APP -------------
if __name__ == "__main__":
    app.run(debug=True, port=5000)