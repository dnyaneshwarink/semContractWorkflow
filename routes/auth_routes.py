from flask import Blueprint, render_template, request, redirect, session, url_for
from db import get_db_connection
from datetime import datetime, timedelta

auth_bp = Blueprint('auth', __name__)


# 🔹 LOGIN
@auth_bp.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM users WHERE email=%s AND password=%s",
            (email, password)
        )
        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if user:
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['name'] = user['name']

            return redirect(url_for('auth.dashboard'))

        return "❌ Invalid Email or Password"

    return render_template('login.html')


# 🔹 DASHBOARD (UNCHANGED)
@auth_bp.route('/dashboard')
def dashboard():

    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    role = session['role']
    user_id = session['user_id']

    # 🔥 DIFFERENT QUERY BASED ON ROLE

    if role == "Creator":

        # ✅ ONLY CREATOR'S CONTRACTS
        cursor.execute("SELECT COUNT(*) as total FROM contracts WHERE created_by=%s", (user_id,))
        total = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) as pending FROM contracts WHERE status='Pending' AND created_by=%s", (user_id,))
        pending = cursor.fetchone()['pending']

        cursor.execute("SELECT COUNT(*) as approved FROM contracts WHERE status='Approved' AND created_by=%s", (user_id,))
        approved = cursor.fetchone()['approved']

        cursor.execute("SELECT COUNT(*) as rejected FROM contracts WHERE status='Rejected' AND created_by=%s", (user_id,))
        rejected = cursor.fetchone()['rejected']

    else:
        # ✅ ADMIN / LEGAL / FINANCE → GLOBAL VIEW
        cursor.execute("SELECT COUNT(*) as total FROM contracts")
        total = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) as pending FROM contracts WHERE status='Pending'")
        pending = cursor.fetchone()['pending']

        cursor.execute("SELECT COUNT(*) as approved FROM contracts WHERE status='Approved'")
        approved = cursor.fetchone()['approved']

        cursor.execute("SELECT COUNT(*) as rejected FROM contracts WHERE status='Rejected'")
        rejected = cursor.fetchone()['rejected']

    # 🔹 USER ROLE DISTRIBUTION (ONLY ADMIN NEEDS THIS)
    cursor.execute("""
        SELECT role, COUNT(*) as count 
        FROM users 
        GROUP BY role
    """)
    user_roles = cursor.fetchall()

    # 🔹 EXPIRY LOGIC
    from datetime import datetime, timedelta
    today = datetime.today().date()
    next_week = today + timedelta(days=7)

    if role == "Creator":
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM contracts 
            WHERE expiry_date BETWEEN %s AND %s AND created_by=%s
        """, (today, next_week, user_id))
        expiry_week = cursor.fetchone()['count']

        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM contracts 
            WHERE expiry_date < %s AND created_by=%s
        """, (today, user_id))
        expired = cursor.fetchone()['count']
    else:
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM contracts 
            WHERE expiry_date BETWEEN %s AND %s
        """, (today, next_week))
        expiry_week = cursor.fetchone()['count']

        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM contracts 
            WHERE expiry_date < %s
        """, (today,))
        expired = cursor.fetchone()['count']

    # 🔹 REJECTION ANALYTICS (GLOBAL ONLY)
# 🔹 REJECTION ANALYTICS (ROLE BASED)

    if role == "Creator":

        cursor.execute("""
            SELECT a.stage, COUNT(*) as count
            FROM approvals a
            JOIN contracts c ON a.contract_id = c.id
            WHERE a.status = 'Rejected'
            AND c.created_by = %s
            GROUP BY a.stage
        """, (user_id,))

    else:

        cursor.execute("""
            SELECT stage, COUNT(*) as count
            FROM approvals
            WHERE status = 'Rejected'
            GROUP BY stage
        """)

    rejections = cursor.fetchall()

    # 🔹 PERCENTAGES
    pending_percent = (pending / total * 100) if total else 0
    approved_percent = (approved / total * 100) if total else 0
    rejected_percent = (rejected / total * 100) if total else 0

    cursor.close()
    conn.close()

    return render_template(
        'dashboard.html',
        name=session['name'],
        role=session['role'],
        total=total,
        pending=pending,
        approved=approved,
        rejected=rejected,
        pending_percent=pending_percent,
        approved_percent=approved_percent,
        rejected_percent=rejected_percent,
        user_roles=user_roles,
        expiry_week=expiry_week,
        expired=expired,
        rejections=rejections
    )

# 🔹 LOGOUT
@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))


# =====================================================
# 🔥 ADMIN FEATURES (NEW - SAFE ADDITION)
# =====================================================

# 🔹 MANAGE USERS
@auth_bp.route('/manage_users', methods=['GET', 'POST'])
def manage_users():

    if 'user_id' not in session or session['role'] != "Admin":
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # ADD USER
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']

        cursor.execute("""
            INSERT INTO users (name, email, password, role)
            VALUES (%s, %s, %s, %s)
        """, (name, email, password, role))

        conn.commit()

    # FETCH USERS
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('manage_users.html', users=users)


# 🔹 DELETE USER
@auth_bp.route('/delete_user/<int:user_id>')
def delete_user(user_id):

    if 'user_id' not in session or session['role'] != "Admin":
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
    conn.commit()

    cursor.close()
    conn.close()

    return redirect(url_for('auth.manage_users'))