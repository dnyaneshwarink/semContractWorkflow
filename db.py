import mysql.connector
import PyPDF2
from datetime import datetime, timedelta

#  DB CONFIG
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": ""   # change if needed
}

DB_NAME = "contract_system"


#  STEP 1: CREATE DATABASE
def create_database():
    conn = mysql.connector.connect(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"]
    )
    cursor = conn.cursor()

    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
    conn.commit()

    cursor.close()
    conn.close()


#  STEP 2: CONNECT TO DATABASE
def get_db_connection():
    return mysql.connector.connect(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_NAME
    )


#  STEP 3: CREATE TABLES
def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()

    #  USERS TABLE
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100),
        email VARCHAR(100) UNIQUE,
        password VARCHAR(255),
        role VARCHAR(50),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    #  CONTRACTS TABLE (UPDATED)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS contracts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        contract_id VARCHAR(50) UNIQUE,
        title VARCHAR(255),
        description TEXT,
        department VARCHAR(100),
        created_by INT,
        status VARCHAR(50),
        current_stage VARCHAR(50),
        expiry_date DATE,
        file_path VARCHAR(255),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        
        FOREIGN KEY (created_by) REFERENCES users(id)
        ON DELETE SET NULL
    )
    """)

    cursor.execute("""
CREATE TABLE IF NOT EXISTS approvals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    contract_id INT,
    reviewer_id INT,
    stage VARCHAR(50),
    status VARCHAR(50),
    comment TEXT,
    action_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (contract_id) REFERENCES contracts(id) ON DELETE CASCADE,
    FOREIGN KEY (reviewer_id) REFERENCES users(id) ON DELETE CASCADE
)
""")
    cursor.execute("""
CREATE TABLE IF NOT EXISTS notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    message TEXT,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
)
""")

    conn.commit()
    cursor.close()
    conn.close()


#  STEP 4: GENERATE CONTRACT ID (FIXED VERSION)
def generate_contract_id():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get last inserted contract
    cursor.execute("""
        SELECT contract_id FROM contracts 
        ORDER BY id DESC LIMIT 1
    """)
    result = cursor.fetchone()

    if result:
        last_id = int(result[0].split("-")[1])
        new_id = last_id + 1
    else:
        new_id = 1

    contract_id = f"CNT-{str(new_id).zfill(4)}"

    cursor.close()
    conn.close()

    return contract_id


#  STEP 5: INSERT TEST USERS
def insert_test_users():
    conn = get_db_connection()
    cursor = conn.cursor()

    users = [
        ("Admin User", "admin@gmail.com", "1234", "Admin"),
        ("Creator User", "creator@gmail.com", "1234", "Creator"),
        ("Legal User", "legal@gmail.com", "1234", "Legal"),
        ("Finance User", "finance@gmail.com", "1234", "Finance"),
        ("Procurement User", "proc@gmail.com", "1234", "Procurement"),
    ]

    for user in users:
        try:
            cursor.execute(
                "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
                user
            )
        except:
            pass  

    conn.commit()
    cursor.close()
    conn.close()


#  STEP 6: INITIALIZE DB
def init_db():
    create_database()
    create_tables()

def create_notification(user_id, message):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO notifications (user_id, message)
        VALUES (%s, %s)
    """, (user_id, message))

    conn.commit()
    cursor.close()
    conn.close()

from datetime import datetime, timedelta

def check_expiry_and_notify():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    today = datetime.today().date()

    cursor.execute("SELECT * FROM contracts")
    contracts = cursor.fetchall()

    for contract in contracts:

        if contract['expiry_date']:

            days_left = (contract['expiry_date'] - today).days

            # 🔔 Reminder alerts
            if days_left in [30, 7, 1]:
                create_notification(
                    contract['created_by'],
                    f"Contract {contract['contract_id']} expires in {days_left} day(s)"
                )

            # ❌ Expired
            if days_left < 0 and contract['status'] != "Expired":

                cursor.execute("""
                UPDATE contracts 
                SET status='Expired' 
                WHERE id=%s
                """, (contract['id'],))

                create_notification(
                    contract['created_by'],
                    f"Contract {contract['contract_id']} has expired"
                )

    conn.commit()
    cursor.close()
    conn.close()

# ================= DASHBOARD ANALYTICS =================

def get_dashboard_stats():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) as total FROM contracts")
    total = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) as pending FROM contracts WHERE status='Pending'")
    pending = cursor.fetchone()['pending']

    cursor.execute("SELECT COUNT(*) as approved FROM contracts WHERE status='Approved'")
    approved = cursor.fetchone()['approved']

    cursor.execute("SELECT COUNT(*) as rejected FROM contracts WHERE status='Rejected'")
    rejected = cursor.fetchone()['rejected']

    cursor.close()
    conn.close()

    return total, pending, approved, rejected


def get_expiry_analysis():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            COUNT(CASE WHEN expiry_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY) THEN 1 END) as week,
            COUNT(CASE WHEN expiry_date < CURDATE() THEN 1 END) as expired
        FROM contracts
    """)

    result = cursor.fetchone()

    cursor.close()
    conn.close()

    return result


# ================= CONTRACT INTELLIGENCE =================



def extract_text_from_pdf(path):
    try:
        reader = PyPDF2.PdfReader(path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except:
        return ""


def generate_summary(text):
    sentences = text.split(".")
    return ". ".join(sentences[:3])


def extract_keywords(text):
    words = text.lower().split()
    freq = {}

    for w in words:
        if len(w) > 5:
            freq[w] = freq.get(w, 0) + 1

    return sorted(freq, key=freq.get, reverse=True)[:5]


def detect_risk(text, expiry_date):
    risks = []

    if "penalty" in text.lower():
        risks.append("Penalty clause present")

    if not expiry_date:
        risks.append("Missing expiry date")

    if len(text) < 100:
        risks.append("Very short contract")

    return risks

def cleanup_old_contracts():
    conn = get_db_connection()
    cursor = conn.cursor()

    today = datetime.today().date()
    cutoff = today - timedelta(days=5)

    # 🔥 DELETE REJECTED (older than 5 days)
    cursor.execute("""
        DELETE FROM contracts
        WHERE status = 'Rejected'
        AND created_at < %s
    """, (cutoff,))

    # 🔥 DELETE EXPIRED (older than 5 days)
    cursor.execute("""
        DELETE FROM contracts
        WHERE status = 'Expired'
        AND created_at < %s
    """, (cutoff,))

    conn.commit()
    cursor.close()
    conn.close()

#  RUN FILE DIRECTLY
if __name__ == "__main__":
    print(" Setting up database...")
    init_db()
    insert_test_users()
    print(" Database, Tables & Users Ready!")