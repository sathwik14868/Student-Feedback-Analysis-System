
import os
import pandas as pd

from io import BytesIO
from functools import wraps
from dotenv import load_dotenv

from flask import (
    Flask, render_template, request,
    send_file, redirect, url_for, session
)

from werkzeug.security import (
    check_password_hash,
    generate_password_hash
)

from analysis import analyze_feedback
from database import get_connection


# LOAD ENVIRONMENT VARIABLES
load_dotenv()


# FLASK CONFIGURATION
app = Flask(__name__)

app.secret_key = os.getenv("FLASK_SECRET_KEY")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")


# ADMIN LOGIN PROTECTION
def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not session.get('admin_logged_in'):
            return redirect(url_for('login'))

        return function(*args, **kwargs)

    return wrapper


# HOME PAGE
@app.route('/')
def home():
    return render_template('index.html')


# STUDENT REGISTRATION
@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        full_name = request.form.get('full_name', '').strip()
        roll_number = request.form.get('roll_number', '').strip().upper()
        email = request.form.get('email', '').strip().lower()
        branch = request.form.get('branch', '').strip()
        password = request.form.get('password', '')

        if not full_name or not roll_number or not email or not branch or len(password) < 8:
            return render_template(
                'register.html',
                error="Please enter all details. Password must be at least 8 characters."
            )

        password_hash = generate_password_hash(password)

        conn = get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO students
                (full_name, roll_number, email, branch, password_hash)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (full_name, roll_number, email, branch, password_hash)
            )

            conn.commit()

            return render_template(
                'register.html',
                success="Registration successful! You can now log in."
            )

        except Exception as e:
            conn.rollback()

            if getattr(e, 'errno', None) == 1062:
                return render_template(
                    'register.html',
                    error="This email or roll number is already registered."
                )

            print("Registration error:", e)

            return render_template(
                'register.html',
                error="Registration failed. Please try again."
            )

        finally:
            cursor.close()
            conn.close()

    return render_template('register.html')


# STUDENT LOGIN
@app.route('/student-login', methods=['GET', 'POST'])
def student_login():

    if request.method == 'POST':

        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            cursor.execute(
                "SELECT * FROM students WHERE email = %s",
                (email,)
            )

            student = cursor.fetchone()

            if student and check_password_hash(
                student['password_hash'], password
            ):
                session['student_logged_in'] = True
                session['student_id'] = student['student_id']

                return redirect(url_for('feedback'))

            return render_template(
                'student_login.html',
                error="Invalid email or password"
            )

        finally:
            cursor.close()
            conn.close()

    return render_template('student_login.html')


# STUDENT LOGOUT
@app.route('/student-logout')
def student_logout():

    session.pop('student_logged_in', None)
    session.pop('student_id', None)

    return redirect(url_for('home'))


# FEEDBACK FORM AND SUBMISSION
@app.route('/feedback', methods=['GET', 'POST'])
def feedback():

    if not session.get('student_logged_in'):
        return redirect(url_for('student_login'))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':

        course_id = request.form.get('course_id')
        comment = request.form.get('comment', '').strip()

        cursor.execute(
            "SELECT question_id FROM feedback_questions ORDER BY question_id"
        )

        questions = cursor.fetchall()

        ratings = []

        for question in questions:

            rating = request.form.get(
                f"rating_{question['question_id']}"
            )

            if not rating or not rating.isdigit() or int(rating) not in range(1, 6):

                cursor.close()
                conn.close()

                return "Please select a rating from 1 to 5 for every question."

            ratings.append((question['question_id'], int(rating)))

        try:

            cursor.execute(
                """
                INSERT INTO feedback_submissions
                (course_id, comment_optional, student_id)
                VALUES (%s, %s, %s)
                """,
                (
                    course_id,
                    comment or None,
                    session['student_id']
                )
            )

            submission_id = cursor.lastrowid

            for question_id, rating in ratings:

                cursor.execute(
                    """
                    INSERT INTO feedback
                    (course_id, question_id, rating, submission_id)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (course_id, question_id, rating, submission_id)
                )

            conn.commit()

            return render_template('success.html')

        except Exception as e:

            conn.rollback()
            print("Feedback error:", e)
            return "Error saving feedback. Please try again."

        finally:

            cursor.close()
            conn.close()

    cursor.execute("SELECT * FROM courses")
    courses = cursor.fetchall()

    cursor.execute(
        "SELECT * FROM feedback_questions ORDER BY question_id"
    )

    questions = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'feedback.html',
        courses=courses,
        questions=questions
    )


# ADMIN LOGIN
@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        username = request.form.get('username')
        password = request.form.get('password')

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:

            session['admin_logged_in'] = True

            return redirect(url_for('dashboard'))

        return render_template(
            'login.html',
            error="Invalid username or password"
        )

    return render_template('login.html')


# ADMIN LOGOUT
@app.route('/logout')
def logout():

    session.pop('admin_logged_in', None)

    return redirect(url_for('login'))


# ADMIN DASHBOARD
@app.route('/dashboard')
@admin_required
def dashboard():

    result = analyze_feedback()

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:

        # 1. Total registered students
        cursor.execute("""
            SELECT COUNT(*) AS total_students
            FROM students
        """)

        total_students = cursor.fetchone()['total_students']

        # 2. All students sorted by branch and roll number
        cursor.execute("""
            SELECT
                student_id,
                full_name,
                roll_number,
                email,
                branch
            FROM students
            ORDER BY branch ASC, roll_number ASC
        """)

        all_students = cursor.fetchall()

        # 3. Student-wise feedback summary
        cursor.execute("""
            SELECT
                st.student_id,
                st.full_name,
                st.roll_number,
                st.branch,
                COUNT(DISTINCT fs.submission_id) AS total_submissions,
                COUNT(f.feedback_id) AS total_ratings,
                ROUND(AVG(f.rating), 2) AS average_rating
            FROM students st
            LEFT JOIN feedback_submissions fs
                ON st.student_id = fs.student_id
            LEFT JOIN feedback f
                ON fs.submission_id = f.submission_id
            GROUP BY
                st.student_id,
                st.full_name,
                st.roll_number,
                st.branch
            ORDER BY
                st.branch ASC,
                st.roll_number ASC
        """)

        student_summary = cursor.fetchall()

        # 4. Branch-wise count of every star rating
        cursor.execute("""
            SELECT
                st.branch,
                SUM(CASE WHEN f.rating = 1 THEN 1 ELSE 0 END) AS one_star,
                SUM(CASE WHEN f.rating = 2 THEN 1 ELSE 0 END) AS two_star,
                SUM(CASE WHEN f.rating = 3 THEN 1 ELSE 0 END) AS three_star,
                SUM(CASE WHEN f.rating = 4 THEN 1 ELSE 0 END) AS four_star,
                SUM(CASE WHEN f.rating = 5 THEN 1 ELSE 0 END) AS five_star
            FROM students st
            LEFT JOIN feedback_submissions fs
                ON st.student_id = fs.student_id
            LEFT JOIN feedback f
                ON fs.submission_id = f.submission_id
            GROUP BY st.branch
            ORDER BY st.branch ASC
        """)

        branch_analysis = cursor.fetchall()

        # 5. All student feedback details
        cursor.execute("""
            SELECT
                st.full_name,
                st.roll_number,
                st.branch,
                st.email,
                c.course_name,
                q.question_text,
                f.rating,
                fs.submitted_at
            FROM feedback f
            JOIN feedback_submissions fs
                ON f.submission_id = fs.submission_id
            JOIN students st
                ON fs.student_id = st.student_id
            JOIN courses c
                ON fs.course_id = c.course_id
            JOIN feedback_questions q
                ON f.question_id = q.question_id
            ORDER BY
                st.branch ASC,
                st.roll_number ASC,
                fs.submitted_at DESC
        """)

        all_feedback = cursor.fetchall()

    finally:
        cursor.close()
        conn.close()

    return render_template(
        'dashboard.html',
        result=result,
        total_students=total_students,
        all_students=all_students,
        student_summary=student_summary,
        branch_analysis=branch_analysis,
        all_feedback=all_feedback
    )


# INDIVIDUAL STUDENT DETAILS
@app.route('/student/<int:student_id>')
@admin_required
def student_details(student_id):

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:

        # Get student information
        cursor.execute("""
            SELECT
                student_id,
                full_name,
                roll_number,
                branch,
                email
            FROM students
            WHERE student_id = %s
        """, (student_id,))

        student = cursor.fetchone()

        if not student:
            return "Student not found", 404

        # Get all feedback submitted by this student
        cursor.execute("""
            SELECT
                c.course_name,
                q.question_text,
                f.rating,
                fs.comment_optional,
                fs.submitted_at,
                fs.submission_id
            FROM feedback_submissions fs
            JOIN feedback f
                ON fs.submission_id = f.submission_id
            JOIN courses c
                ON fs.course_id = c.course_id
            JOIN feedback_questions q
                ON f.question_id = q.question_id
            WHERE fs.student_id = %s
            ORDER BY fs.submitted_at DESC, fs.submission_id DESC
        """, (student_id,))

        feedback_details = cursor.fetchall()

        # Calculate student statistics
        cursor.execute("""
            SELECT
                COUNT(DISTINCT fs.submission_id) AS total_submissions,
                COUNT(f.feedback_id) AS total_ratings,
                ROUND(AVG(f.rating), 2) AS average_rating
            FROM feedback_submissions fs
            LEFT JOIN feedback f
                ON fs.submission_id = f.submission_id
            WHERE fs.student_id = %s
        """, (student_id,))

        statistics = cursor.fetchone()

    finally:
        cursor.close()
        conn.close()

    return render_template(
        'student_details.html',
        student=student,
        feedback_details=feedback_details,
        statistics=statistics
    )


# EXPORT FEEDBACK REPORT AS CSV
@app.route('/export')
@admin_required
def export_report():

    conn = get_connection()

    query = """
        SELECT
            c.course_name,
            q.question_text,
            ROUND(AVG(f.rating), 2) AS average_rating,
            COUNT(f.rating) AS total_ratings
        FROM feedback f
        JOIN courses c
            ON f.course_id = c.course_id
        JOIN feedback_questions q
            ON f.question_id = q.question_id
        GROUP BY c.course_name, q.question_id, q.question_text
        ORDER BY c.course_name, q.question_id
    """

    try:
        df = pd.read_sql(query, conn)

    finally:
        conn.close()

    output = BytesIO()

    output.write(
        df.to_csv(index=False).encode('utf-8')
    )

    output.seek(0)

    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name='student_feedback_report.csv'
    )


# RUN FLASK APPLICATION
if __name__ == '__main__':

    app.run(debug=True)
