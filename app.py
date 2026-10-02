
from flask import Flask, render_template, request, jsonify, url_for, session, redirect, make_response
from flask_mail import Mail, Message
import mysql.connector
from datetime import datetime, timedelta
from flask_cors import CORS
import qrcode
import os
import base64
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ---------------------------------------------------------
# SECURE FLASK SECRET KEY
# ---------------------------------------------------------

SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY is missing. Please add it to your .env file."
    )

app.secret_key = SECRET_KEY

app.permanent_session_lifetime = timedelta(minutes=5)
CORS(app)


# ---------------------------------------------------------
# FLASK-MAIL CONFIGURATION
# ---------------------------------------------------------

SENDER_EMAIL = 'murithirodgers928@gmail.com'

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = SENDER_EMAIL

MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")

if not MAIL_PASSWORD:
    raise RuntimeError(
        "MAIL_PASSWORD is missing. Please add it to your .env file."
    )

app.config['MAIL_PASSWORD'] = MAIL_PASSWORD

app.config['MAIL_DEFAULT_SENDER'] = (
    'SEKU Smart Gate System',
    SENDER_EMAIL
)

mail = Mail(app)


BASE_DIR = os.path.abspath(os.path.dirname(__file__))


QR_FOLDER = os.path.join(
    BASE_DIR,
    'static',
    'qrcodes'
)


PASSPORT_FOLDER = os.path.join(
    BASE_DIR,
    'static',
    'passports'
)


for folder in [QR_FOLDER, PASSPORT_FOLDER]:

    if not os.path.exists(folder):
        os.makedirs(folder)


# ---------------------------------------------------------
# NO-CACHE HEADERS
# ---------------------------------------------------------

@app.after_request
def add_header(response):

    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response


# ---------------------------------------------------------
# SESSION TIMEOUT
# ---------------------------------------------------------

@app.before_request
def refresh_session():

    exempt_routes = [
        'login',
        'static',
        'portal',
        'scanner',
        'verify',
        'check_session',
        'dashboard_stats',
        'audit_search',
        'toggle_theme'
    ]

    if request.endpoint in exempt_routes:
        return

    if session.get('logged_in'):

        last_activity = session.get('last_activity')
        now = datetime.now()

        if last_activity:

            try:

                last_activity_dt = datetime.strptime(
                    last_activity,
                    "%Y-%m-%d %H:%M:%S"
                )

                if now - last_activity_dt > timedelta(minutes=5):

                    session.clear()

                    return redirect(
                        url_for('login')
                    )

            except Exception:
                pass

        session.permanent = True

        session['last_activity'] = now.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    else:

        if request.endpoint != 'login':

            return redirect(
                url_for('login')
            )


# ---------------------------------------------------------
# DATABASE CONNECTION
# ---------------------------------------------------------

def get_db_connection():

    return mysql.connector.connect(

        host="localhost",

        user="root",

        password="",

        database="smart_gate",

        charset='utf8mb4',

        collation='utf8mb4_general_ci',

        connect_timeout=5,

        autocommit=True
    )


# ---------------------------------------------------------
# HOME / PORTAL
# ---------------------------------------------------------

@app.route('/')
def portal():

    return render_template(
        'index.html'
    )


# ---------------------------------------------------------
# SCANNER
# ---------------------------------------------------------

@app.route('/scanner')
def scanner():

    return render_template(
        'scanner.html'
    )


# ---------------------------------------------------------
# ADMIN LOGIN
# ---------------------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        username = request.form.get('username')

        password = request.form.get('password')

        db = None

        try:

            db = get_db_connection()

            cursor = db.cursor(
                dictionary=True
            )

            cursor.execute(
                """
                SELECT *
                FROM admins
                WHERE username = %s
                AND password = %s
                """,
                (
                    username,
                    password
                )
            )

            admin = cursor.fetchone()

            if admin:

                session.clear()

                session.permanent = True

                session['logged_in'] = True

                session['last_activity'] = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                return redirect(
                    url_for('admin')
                )

            else:

                return render_template(
                    'login.html',
                    error="Invalid Username or Password"
                )

        except mysql.connector.Error as err:

            return render_template(
                'login.html',
                error=f"Database Error: {err}"
            )

        finally:

            if db and db.is_connected():
                db.close()

    return render_template(
        'login.html'
    )


# ---------------------------------------------------------
# LOGOUT
# ---------------------------------------------------------

@app.route('/logout')
def logout():

    session.clear()

    return redirect(
        url_for('login')
    )


# ---------------------------------------------------------
# ADMIN DASHBOARD
# ---------------------------------------------------------

@app.route('/admin')
def admin():

    db = None

    try:

        db = get_db_connection()

        cursor = db.cursor(
            dictionary=True
        )

        cursor.execute(
            """
            SELECT COUNT(*) AS total_students
            FROM students
            """
        )

        total_students = cursor.fetchone()[
            'total_students'
        ]

        cursor.execute(
            """
            SELECT COUNT(*) AS today_entries
            FROM entry_logs
            WHERE DATE(entry_time) = CURDATE()
            """
        )

        today_entries = cursor.fetchone()[
            'today_entries'
        ]

        cursor.execute(
            """
            SELECT
                s.full_name,
                s.reg_number,
                e.entry_time

            FROM entry_logs e

            JOIN students s
            ON e.student_id = s.id

            WHERE DATE(e.entry_time) = CURDATE()

            ORDER BY e.entry_time DESC

            LIMIT 50
            """
        )

        recent_logs = cursor.fetchall()

        for log in recent_logs:

            log['formatted_time'] = (
                log['entry_time'].strftime(
                    "%H:%M:%S"
                )
            )

        return render_template(
            "admin.html",

            total_students=total_students,

            today_entries=today_entries,

            recent_logs=recent_logs
        )

    except Exception as e:

        return f"Dashboard Error: {e}"

    finally:

        if db and db.is_connected():
            db.close()


# ---------------------------------------------------------
# DASHBOARD STATISTICS API
# ---------------------------------------------------------

@app.route('/api/dashboard_stats')
def dashboard_stats():

    db = None

    try:

        db = get_db_connection()

        cursor = db.cursor(
            dictionary=True
        )

        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM students
            """
        )

        total = cursor.fetchone()['total']

        cursor.execute(
            """
            SELECT COUNT(*) AS today
            FROM entry_logs
            WHERE DATE(entry_time) = CURDATE()
            """
        )

        today = cursor.fetchone()['today']

        cursor.execute(
            """
            SELECT
                s.full_name,
                s.reg_number,
                e.entry_time

            FROM entry_logs e

            JOIN students s
            ON e.student_id = s.id

            WHERE DATE(e.entry_time) = CURDATE()

            ORDER BY e.entry_time DESC

            LIMIT 15
            """
        )

        logs = cursor.fetchall()

        for l in logs:

            l['formatted_time'] = (
                l['entry_time'].strftime(
                    "%H:%M:%S"
                )
            )

            l['entry_time'] = str(
                l['entry_time']
            )

        return jsonify({

            "total_students": total,

            "today_entries": today,

            "recent_logs": logs

        })

    finally:

        if db:
            db.close()


# ---------------------------------------------------------
# AUDIT SEARCH
# ---------------------------------------------------------

@app.route('/audit_search', methods=['POST'])
def audit_search():

    data = request.json

    reg_num = data.get(
        'reg_number'
    )

    search_date = data.get(
        'date'
    )

    db = None

    try:

        db = get_db_connection()

        cursor = db.cursor(
            dictionary=True
        )

        if search_date:

            query = """
                SELECT
                    s.full_name,
                    s.reg_number,
                    e.entry_time

                FROM entry_logs e

                JOIN students s
                ON e.student_id = s.id

                WHERE s.reg_number = %s

                AND DATE(e.entry_time) = %s

                ORDER BY e.entry_time DESC
            """

            cursor.execute(
                query,
                (
                    reg_num,
                    search_date
                )
            )

        else:

            query = """
                SELECT
                    s.full_name,
                    s.reg_number,
                    e.entry_time

                FROM entry_logs e

                JOIN students s
                ON e.student_id = s.id

                WHERE s.reg_number = %s

                AND MONTH(e.entry_time)
                    = MONTH(CURRENT_DATE())

                AND YEAR(e.entry_time)
                    = YEAR(CURRENT_DATE())

                ORDER BY e.entry_time DESC
            """

            cursor.execute(
                query,
                (
                    reg_num,
                )
            )

        results = cursor.fetchall()

        for r in results:

            r['formatted_time'] = (
                r['entry_time'].strftime(
                    "%H:%M:%S"
                )
            )

            r['formatted_date'] = (
                r['entry_time'].strftime(
                    "%Y-%m-%d"
                )
            )

            r['entry_time'] = str(
                r['entry_time']
            )

        return jsonify({

            "status": "success",

            "logs": results,

            "mode":
                "date"
                if search_date
                else "month"

        })

    except Exception as e:

        return jsonify({

            "status": "error",

            "message": str(e)

        })

    finally:

        if db:
            db.close()


# ---------------------------------------------------------
# STUDENT REGISTRATION
# ---------------------------------------------------------

@app.route(
    '/register_student',
    methods=['POST']
)
def register_student():

    data = request.json

    name = data.get(
        'name'
    )

    reg_num = data.get(
        'reg_number'
    )

    student_email = data.get(
        'email'
    )

    course = data.get(
        'course'
    )

    photo_data = data.get(
        'photo'
    )


    # Make registration number safe for filenames

    file_safe_name = "".join(
        x for x in reg_num
        if x.isalnum()
    )


    # -----------------------------------------------------
    # SAVE PASSPORT PHOTO
    # -----------------------------------------------------

    if photo_data and ',' in photo_data:

        try:

            header, encoded = photo_data.split(
                ',',
                1
            )

            image_bytes = base64.b64decode(
                encoded
            )

            photo_path = os.path.join(
                PASSPORT_FOLDER,
                f"{file_safe_name}.jpg"
            )

            with open(
                photo_path,
                'wb'
            ) as f:

                f.write(
                    image_bytes
                )

        except Exception as img_err:

            print(
                f"Photo save warning: {img_err}"
            )


    db = None

    try:

        # -------------------------------------------------
        # SAVE STUDENT IN DATABASE
        # -------------------------------------------------

        db = get_db_connection()

        cursor = db.cursor()

        cursor.execute(

            """
            INSERT INTO students
            (
                full_name,
                reg_number,
                email,
                course
            )

            VALUES
            (
                %s,
                %s,
                %s,
                %s
            )
            """,

            (
                name,
                reg_num,
                student_email,
                course
            )
        )


        # -------------------------------------------------
        # GENERATE QR CODE
        # -------------------------------------------------

        qr_filename = (
            f"{file_safe_name}.png"
        )

        qr_path = os.path.join(
            QR_FOLDER,
            qr_filename
        )

        qrcode.make(
            reg_num
        ).save(
            qr_path
        )


        # -------------------------------------------------
        # EMAIL
        # -------------------------------------------------

        email_sent = False

        if student_email:

            try:

                recipient_email = (
                    student_email.strip()
                )

                msg = Message(

                    subject=
                    "SEKU Smart Gate - Registration Confirmation",

                    recipients=[
                        recipient_email
                    ]
                )


                # Plain text email

                msg.body = f"""
Dear {name},

Thank you for registering with the SEKU Smart Gate System.

Your student registration has been successfully completed.

Registration Number: {reg_num}
Course: {course}

Your personal SEKU Smart Gate QR Code is attached to this email.

Please keep your QR code safe and do not share it with another person.

You will be required to present it at designated university gate checkpoints
for verification and access.

Thank you for your cooperation in supporting a secure, efficient and
technology-driven campus environment.

Regards,

SEKU Smart Gate System
South Eastern Kenya University
Smart Security • Faster Verification • Safer Campus
"""


                # HTML email

                msg.html = f"""
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<title>
SEKU Smart Gate Registration
</title>

</head>


<body style="
margin:0;
padding:0;
background-color:#f4f7f5;
font-family:Arial, Helvetica, sans-serif;
">


<div style="
max-width:650px;
margin:30px auto;
background:#ffffff;
border-radius:12px;
overflow:hidden;
box-shadow:0 4px 15px rgba(0,0,0,0.10);
">


<!-- HEADER -->

<div style="
background:#0b6b3a;
color:white;
padding:28px;
text-align:center;
">

<h1 style="
margin:0;
font-size:26px;
">

SEKU SMART GATE

</h1>


<p style="
margin:8px 0 0;
font-size:15px;
">

Student Registration Confirmation

</p>

</div>


<!-- CONTENT -->

<div style="
padding:30px;
color:#333333;
">


<h2 style="
color:#0b6b3a;
margin-top:0;
">

Registration Successful

</h2>


<p>

Dear <strong>{name}</strong>,

</p>


<p>

Thank you for registering with the
<strong>SEKU Smart Gate System</strong>.

Your student registration has been successfully completed.

</p>


<!-- STUDENT DETAILS -->

<div style="
background:#f3f8f5;
border-left:5px solid #0b6b3a;
padding:18px;
margin:22px 0;
">


<p style="margin:6px 0;">

<strong>
Registration Number:
</strong>

{reg_num}

</p>


<p style="margin:6px 0;">

<strong>
Course:
</strong>

{course}

</p>


<p style="margin:6px 0;">

<strong>
Email:
</strong>

{student_email}

</p>


</div>


<p>

Your personal
<strong>SEKU Smart Gate QR Code</strong>
is provided below.

A copy has also been attached to this
email for your convenience.

</p>


<!-- QR CODE -->

<div style="
text-align:center;
margin:30px 0;
padding:20px;
background:#fafafa;
border:1px solid #dddddd;
border-radius:10px;
">


<h3 style="
color:#0b6b3a;
margin-top:0;
">

Your Smart Gate QR Code

</h3>


<img

src="cid:student_qr_code"

alt="SEKU Smart Gate QR Code"

width="220"

height="220"

style="
display:block;
margin:15px auto;
"

/>


<p style="
font-size:13px;
color:#666666;
margin-bottom:0;
">

Please keep this QR code safe.

</p>


</div>


<!-- SECURITY NOTICE -->

<div style="
background:#fff8e6;
border:1px solid #f0d98c;
padding:16px;
border-radius:8px;
margin:20px 0;
">


<strong>
Security Notice
</strong>


<p style="margin-bottom:0;">

This QR code is intended for your personal use.

Please do not share it with another person.

Present it at the designated university gate
checkpoint when requested.

</p>


</div>


<p>

Thank you for your cooperation in supporting a
<strong>
secure, efficient and technology-driven
campus environment.
</strong>

</p>


<p style="margin-top:30px;">

Regards,

<br>

<strong>
SEKU Smart Gate System
</strong>

<br>

South Eastern Kenya University

</p>


</div>


<!-- FOOTER -->

<div style="
background:#f1f1f1;
text-align:center;
padding:18px;
color:#777777;
font-size:12px;
">

Smart Security • Faster Verification • Safer Campus

</div>


</div>


</body>

</html>
"""


                # -------------------------------------------------
                # ATTACH QR CODE
                # -------------------------------------------------

                with open(
                    qr_path,
                    'rb'
                ) as qr_file:

                    msg.attach(

                        filename=
                        f"{file_safe_name}_SEKU_Smart_Gate_QR.png",

                        content_type=
                        "image/png",

                        data=
                        qr_file.read(),

                        disposition=
                        "inline",

                        headers={
                            "Content-ID":
                            "<student_qr_code>"
                        }
                    )


                # SEND EMAIL

                mail.send(
                    msg
                )

                email_sent = True

                print(
                    f"Registration email sent successfully to {recipient_email}"
                )


            except Exception as mail_err:

                print(
                    f"Mail dispatch error details: {mail_err}"
                )


        return jsonify({

            "status":
            "success",

            "email_sent":
            email_sent,

            "qr_code":
            url_for(
                'static',
                filename=
                f'qrcodes/{qr_filename}'
            )

        })


    except Exception as e:

        return jsonify({

            "status":
            "error",

            "message":
            str(e)

        })

    finally:

        if db and db.is_connected():

            db.close()


# ---------------------------------------------------------
# VERIFY QR CODE
# ---------------------------------------------------------

@app.route(
    '/verify',
    methods=['POST']
)
def verify():

    data = request.json or {}

    reg_num = data.get(
        'reg_number'
    )

    db = None

    try:

        db = get_db_connection()

        cursor = db.cursor(
            dictionary=True
        )


        # -------------------------------------------------
        # FIND STUDENT
        # -------------------------------------------------

        cursor.execute(

            """
            SELECT
                id,
                full_name,
                reg_number,
                course

            FROM students

            WHERE reg_number = %s
            """,

            (
                reg_num,
            )
        )


        student = cursor.fetchone()


        # -------------------------------------------------
        # STUDENT FOUND
        # -------------------------------------------------

        if student:

            # Record entry

            cursor.execute(

                """
                INSERT INTO entry_logs
                (student_id)

                VALUES
                (%s)
                """,

                (
                    student['id'],
                )
            )


            # -------------------------------------------------
            # FIND PASSPORT
            # -------------------------------------------------

            # Use exactly the same filename format
            # used during registration.

            file_safe_name = "".join(

                x for x in student['reg_number']

                if x.isalnum()
            )


            passport_filename = (
                f"{file_safe_name}.jpg"
            )


            passport_path = os.path.join(

                PASSPORT_FOLDER,

                passport_filename
            )


            if os.path.exists(
                passport_path
            ):

                passport_url = url_for(

                    'static',

                    filename=
                    f'passports/{passport_filename}'
                )

            else:

                passport_url = ""


            # -------------------------------------------------
            # RETURN STUDENT INFORMATION
            # -------------------------------------------------

            return jsonify({

                "status":
                "success",

                "name":
                student['full_name'],

                "reg_number":
                student['reg_number'],

                "course":
                student['course'],

                "school":
                "School of Science and Computing",

                "passport":
                passport_url

            })


        # -------------------------------------------------
        # STUDENT NOT FOUND
        # -------------------------------------------------

        return jsonify({

            "status":
            "error",

            "message":
            "Access Denied"

        })


    except Exception as e:

        return jsonify({

            "status":
            "error",

            "message":
            str(e)

        })


    finally:

        if db and db.is_connected():

            db.close()


# ---------------------------------------------------------
# THEME
# ---------------------------------------------------------

@app.route(
    '/toggle_theme',
    methods=['POST']
)
def toggle_theme():

    theme = request.json.get(
        'theme',
        'light'
    )

    session['theme'] = theme

    return jsonify({

        "status":
        "success"

    })


# ---------------------------------------------------------
# RUN APPLICATION
# ---------------------------------------------------------

if __name__ == "__main__":

    app.run(

        host='0.0.0.0',

        port=5000,

        debug=True

    )

