from flask import Blueprint, render_template, request, redirect, session, url_for
from db import (
    get_db_connection, generate_contract_id, create_notification,
    get_dashboard_stats, get_expiry_analysis,
    extract_text_from_pdf, generate_summary,
    extract_keywords, detect_risk
)
import os
from datetime import datetime



contract_bp = Blueprint('contract', __name__)

UPLOAD_FOLDER = "uploads"




# 🔹 HELPER FUNCTION
def normalize_role(value):
    return value.strip().lower()

# 🔷 DASHBOARD
@contract_bp.route('/dashboard')
def dashboard():

    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    total, pending, approved, rejected = get_dashboard_stats()
    expiry = get_expiry_analysis()

    total_safe = total if total > 0 else 1

    return render_template(
        'dashboard.html',
        name=session['name'],
        role=session['role'],
        total=total,
        pending=pending,
        approved=approved,
        rejected=rejected,
        pending_percent=(pending / total_safe) * 100,
        approved_percent=(approved / total_safe) * 100,
        rejected_percent=(rejected / total_safe) * 100,
        expiry_week=expiry['week'],
        expired=expiry['expired']
    )
# 🔹 CREATE CONTRACT
@contract_bp.route('/create_contract', methods=['GET', 'POST'])
def create_contract():

    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        department = request.form['department']
        expiry_date = request.form['expiry_date']
        action = request.form['action']

        file = request.files['file']
        file_path = None

        # 🔥 CONTRACT INTELLIGENCE (SAFE DEFAULTS)
        summary = ""
        keywords = ""
        risk_flags = ""

        # 🔥 FILE UPLOAD + INTELLIGENCE (SINGLE CLEAN BLOCK)
        if file and file.filename != "":
            
            if not file.filename.lower().endswith('.pdf'):
                return "❌ Only PDF files are allowed"

            os.makedirs(UPLOAD_FOLDER, exist_ok=True)

            save_path = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(save_path)

            file_path = f"uploads/{file.filename}".replace("\\", "/")

            # 🔥 INTELLIGENCE PROCESSING
            text = extract_text_from_pdf(save_path)

            summary = generate_summary(text)
            keywords = ", ".join(extract_keywords(text))
            risk_flags = ", ".join(detect_risk(text, expiry_date))

        contract_id = generate_contract_id()

        if action == "draft":
            status = "Draft"
            current_stage = "Creator"
        else:
            status = "Pending"
            current_stage = "Legal"

        # 🔥 PRIORITY LOGIC
        priority = 1

        if expiry_date:
            expiry = datetime.strptime(expiry_date, "%Y-%m-%d").date()
            today = datetime.today().date()
            days_left = (expiry - today).days

            if days_left <= 3:
                priority = 3
            elif days_left <= 7:
                priority = 2
            else:
                priority = 1

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
        INSERT INTO contracts 
        (contract_id, title, description, department, created_by, status, current_stage, expiry_date, file_path, priority, summary, keywords, risk_flags)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            contract_id,
            title,
            description,
            department,
            session['user_id'],
            status,
            current_stage,
            expiry_date,
            file_path,
            priority,
            summary,
            keywords,
            risk_flags
        ))

        conn.commit()

        # 🔔 NOTIFY LEGAL
        if status == "Pending":
            cursor.execute("SELECT id, role FROM users")
            users = cursor.fetchall()

            for user in users:
                if normalize_role(user['role']) == "legal":
                    create_notification(user['id'], "New contract submitted for approval")

        cursor.close()
        conn.close()

        # 🔁 (OPTIONAL: better UX)
        return redirect(url_for('contract.dashboard'))

    return render_template('create_contract.html')

# 🔹 VIEW CONTRACTS
@contract_bp.route('/contracts')
def view_contracts():

    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    role = session['role']

    # 🔹 ADMIN → sees all
    if role == "Admin":
        cursor.execute("""
            SELECT c.*,
            
            (SELECT comment FROM approvals 
             WHERE contract_id = c.id 
             ORDER BY created_at DESC LIMIT 1) AS last_comment,

            (SELECT stage FROM approvals 
             WHERE contract_id = c.id 
             ORDER BY created_at DESC LIMIT 1) AS last_stage

            FROM contracts c
            ORDER BY c.priority DESC, c.created_at DESC
        """)

    # 🔹 CREATOR → sees own contracts + feedback
    elif role == "Creator":
        cursor.execute("""
            SELECT c.*, 
            
            (SELECT comment FROM approvals 
             WHERE contract_id = c.id 
             ORDER BY created_at DESC LIMIT 1) AS last_comment,

            (SELECT stage FROM approvals 
             WHERE contract_id = c.id 
             ORDER BY created_at DESC LIMIT 1) AS last_stage

            FROM contracts c
            WHERE c.created_by=%s
            ORDER BY c.priority DESC, c.created_at DESC
        """, (session['user_id'],))

    # 🔹 OTHER ROLES (Legal, Finance, Procurement)
    else:
        cursor.execute("""
            SELECT c.*,
            
            (SELECT comment FROM approvals 
             WHERE contract_id = c.id 
             ORDER BY created_at DESC LIMIT 1) AS last_comment,

            (SELECT stage FROM approvals 
             WHERE contract_id = c.id 
             ORDER BY created_at DESC LIMIT 1) AS last_stage

            FROM contracts c
            WHERE c.current_stage=%s
            ORDER BY c.priority DESC, c.created_at DESC
        """, (role,))

    contracts = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('contracts.html', contracts=contracts)

# 🔹 REVIEW CONTRACT (FINAL FIXED)
@contract_bp.route('/review/<int:contract_id>', methods=['GET', 'POST'])
def review_contract(contract_id):

    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM contracts WHERE id=%s", (contract_id,))
    contract = cursor.fetchone()

    # 🔹 HANDLE POST (APPROVAL)
    if request.method == 'POST':
            # 🔒 ONLY BLOCK ACTION (NOT VIEW)
        if session['role'] not in ['Legal', 'Finance', 'Procurement']:
             return "❌ You are not allowed to take action"
        
        action = request.form['action']
        comment = request.form['comment']

        status = None
        next_stage = None

        current_stage = contract['current_stage'].strip().title()
        STAGES = ["Legal", "Finance", "Procurement"]

        if action == "approve":
            if current_stage not in STAGES:
                next_stage = "Completed"
                status = "Approved"
            else:
                index = STAGES.index(current_stage)
                if index + 1 < len(STAGES):
                    next_stage = STAGES[index + 1]
                    status = "Pending"
                else:
                    next_stage = "Completed"
                    status = "Approved"

        elif action == "reject":
            status = "Rejected"
            next_stage = current_stage

        elif action == "changes":
            status = "Changes Requested"
            next_stage = "Creator"

        # 🔹 UPDATE CONTRACT
        cursor.execute("""
        UPDATE contracts 
        SET status=%s, current_stage=%s 
        WHERE id=%s
        """, (status, next_stage, contract_id))

        # 🔹 INSERT APPROVAL
        cursor.execute("""
        INSERT INTO approvals 
        (contract_id, reviewer_id, stage, status, comment)
        VALUES (%s, %s, %s, %s, %s)
        """, (
            contract_id,
            session['user_id'],
            current_stage,
            status,
            comment
        ))

        conn.commit()

        # 🔔 NOTIFICATIONS
        if next_stage and status:

            if next_stage != "Completed" and status == "Pending":
                normalized_stage = normalize_role(next_stage)

                cursor.execute("SELECT id, role FROM users")
                users = cursor.fetchall()

                for user in users:
                    if normalize_role(user['role']) == normalized_stage:
                        create_notification(user['id'], "New contract awaiting your approval")

                create_notification(
                    contract['created_by'],
                    f"Your contract was approved by {current_stage}"
                )

            if next_stage == "Completed" and status == "Approved":
                create_notification(
                    contract['created_by'],
                    "Your contract has been fully approved and completed"
                )

            if status == "Rejected":
                create_notification(
                    contract['created_by'],
                    f"Your contract was rejected by {current_stage}"
                )

            if status == "Changes Requested":
                create_notification(
                    contract['created_by'],
                    f"Changes requested by {current_stage}"
                )

        cursor.close()
        conn.close()

        return redirect(url_for('contract.view_contracts'))

    # 🔹 GET REQUEST (SHOW PAGE + TIMELINE)
    cursor.execute("""
        SELECT * FROM approvals 
        WHERE contract_id=%s 
        ORDER BY created_at ASC
    """, (contract_id,))
    
    approvals = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('review_contract.html', contract=contract, approvals=approvals)


# 🔹 NOTIFICATIONS
@contract_bp.route('/notifications')
def view_notifications():

    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT * FROM notifications 
        WHERE user_id=%s 
        ORDER BY created_at DESC
    """, (session['user_id'],))

    notifications = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('notifications.html', notifications=notifications)