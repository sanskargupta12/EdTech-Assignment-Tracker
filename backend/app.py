from flask import Flask, request, jsonify, g
from flask_cors import CORS
import sqlite3
import jwt
import datetime
from functools import wraps

# Constants
SECRET_KEY = "your_super_secret_key" # In a real app, use environment variables!
DATABASE = 'database.db'

app = Flask(__name__)
CORS(app) # Enable CORS for frontend communication

# Database helper functions
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row # Return rows as dictionaries
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                email TEXT UNIQUE,
                role TEXT NOT NULL CHECK(role IN ('teacher', 'student'))
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                due_date TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                teacher_id INTEGER NOT NULL,
                FOREIGN KEY (teacher_id) REFERENCES users(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assignment_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                submission_text TEXT,
                submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
                file_path TEXT,
                FOREIGN KEY (assignment_id) REFERENCES assignments(id),
                FOREIGN KEY (student_id) REFERENCES users(id)
            )
        ''')
        db.commit()

# --- Authentication Decorator ---
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]

        if not token:
            return jsonify({"message": "Token is missing!"}), 401

        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            g.current_user = data['user_id']
            g.current_role = data['role']
        except jwt.ExpiredSignatureError:
            return jsonify({"message": "Token has expired!"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"message": "Token is invalid!"}), 401

        return f(*args, **kwargs)
    return decorated

def role_required(required_role):
    def decorator(f):
        @wraps(f)
        @token_required
        def decorated_function(*args, **kwargs):
            if g.current_role != required_role:
                return jsonify({"message": f"Access denied. {required_role} role required."}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- API Endpoints ---

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password') # In a real app, hash this password!
    email = data.get('email')
    role = data.get('role')

    if not all([username, password, email, role]):
        return jsonify({"message": "Missing required fields"}), 400

    if role not in ['teacher', 'student']:
        return jsonify({"message": "Invalid role specified"}), 400

    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password_hash, email, role) VALUES (?, ?, ?, ?)",
                       (username, password, email, role)) # Store hashed password
        db.commit()
        user_id = cursor.lastrowid
        token = jwt.encode({
            'user_id': user_id,
            'role': role,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, SECRET_KEY, algorithm="HS256")
        return jsonify({"message": "User created successfully", "user_id": user_id, "token": token}), 201
    except sqlite3.IntegrityError:
        return jsonify({"message": "Username or email already exists"}), 409
    except Exception as e:
        return jsonify({"message": str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password') # In a real app, verify hashed password

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, username, password_hash, role FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()

    if user and user['password_hash'] == password: # In real app, check password hash
        token = jwt.encode({
            'user_id': user['id'],
            'role': user['role'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, SECRET_KEY, algorithm="HS256")
        return jsonify({
            "message": "Login successful",
            "user_id": user['id'],
            "role": user['role'],
            "token": token
        }), 200
    return jsonify({"message": "Invalid credentials"}), 401

# --- Teacher Endpoints ---

@app.route('/api/assignments', methods=['POST'])
@role_required('teacher')
def create_assignment():
    data = request.get_json()
    title = data.get('title')
    description = data.get('description')
    due_date = data.get('due_date') # YYYY-MM-DD format
    teacher_id = g.current_user # Get teacher_id from authenticated user

    if not all([title, due_date]):
        return jsonify({"message": "Title and due date are required"}), 400

    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("INSERT INTO assignments (title, description, due_date, teacher_id) VALUES (?, ?, ?, ?)",
                       (title, description, due_date, teacher_id))
        db.commit()
        return jsonify({"message": "Assignment created successfully", "assignment_id": cursor.lastrowid}), 201
    except Exception as e:
        return jsonify({"message": str(e)}), 500

@app.route('/api/assignments/<int:assignment_id>/submissions', methods=['GET'])
@role_required('teacher')
def view_submissions(assignment_id):
    db = get_db()
    cursor = db.cursor()
    # Ensure the teacher owns this assignment
    cursor.execute("SELECT teacher_id FROM assignments WHERE id = ?", (assignment_id,))
    assignment = cursor.fetchone()
    if not assignment or assignment['teacher_id'] != g.current_user:
        return jsonify({"message": "Assignment not found or you don't have permission to view submissions for this assignment"}), 403

    cursor.execute("""
        SELECT s.id AS submission_id, s.submission_text, s.submitted_at, s.file_path,
               u.id AS student_id, u.username AS student_username
        FROM submissions s
        JOIN users u ON s.student_id = u.id
        WHERE s.assignment_id = ?
    """, (assignment_id,))
    submissions = cursor.fetchall()
    return jsonify([dict(s) for s in submissions]), 200

@app.route('/api/teacher/assignments', methods=['GET'])
@role_required('teacher')
def get_teacher_assignments():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, title, description, due_date, created_at FROM assignments WHERE teacher_id = ?", (g.current_user,))
    assignments = cursor.fetchall()
    return jsonify([dict(a) for a in assignments]), 200

# --- Student Endpoints ---

@app.route('/api/assignments/<int:assignment_id>/submit', methods=['POST'])
@role_required('student')
def submit_assignment(assignment_id):
    data = request.get_json()
    submission_text = data.get('submission_text')
    # file_path handling for bonus part:
    # file_path = request.files.get('file') # If using multipart/form-data
    # For simplicity, assuming file_path comes in JSON for now, or handle actual file upload separately.
    file_path = data.get('file_path') # Placeholder for file path

    student_id = g.current_user

    # Check if assignment exists
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id FROM assignments WHERE id = ?", (assignment_id,))
    if not cursor.fetchone():
        return jsonify({"message": "Assignment not found"}), 404

    # Check if student already submitted (optional, based on requirements)
    cursor.execute("SELECT id FROM submissions WHERE assignment_id = ? AND student_id = ?", (assignment_id, student_id))
    if cursor.fetchone():
        return jsonify({"message": "You have already submitted for this assignment."}), 409

    try:
        cursor.execute("INSERT INTO submissions (assignment_id, student_id, submission_text, file_path) VALUES (?, ?, ?, ?)",
                       (assignment_id, student_id, submission_text, file_path))
        db.commit()
        return jsonify({"message": "Assignment submitted successfully", "submission_id": cursor.lastrowid}), 201
    except Exception as e:
        return jsonify({"message": str(e)}), 500

@app.route('/api/student/assignments', methods=['GET'])
@role_required('student')
def get_student_assignments():
    db = get_db()
    cursor = db.cursor()
    # Get all assignments
    cursor.execute("SELECT a.id, a.title, a.description, a.due_date, u.username as teacher_name FROM assignments a JOIN users u ON a.teacher_id = u.id")
    all_assignments = cursor.fetchall()

    # Get student's submissions to mark status
    cursor.execute("SELECT assignment_id FROM submissions WHERE student_id = ?", (g.current_user,))
    submitted_assignment_ids = {row['assignment_id'] for row in cursor.fetchall()}

    result = []
    for assign in all_assignments:
        assignment_dict = dict(assign)
        assignment_dict['status'] = 'submitted' if assignment_dict['id'] in submitted_assignment_ids else 'pending'
        result.append(assignment_dict)

    return jsonify(result), 200

@app.route('/api/student/submissions', methods=['GET'])
@role_required('student')
def get_student_submissions():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT s.id AS submission_id, s.submission_text, s.submitted_at, s.file_path,
               a.title AS assignment_title
        FROM submissions s
        JOIN assignments a ON s.assignment_id = a.id
        WHERE s.student_id = ?
    """, (g.current_user,))
    submissions = cursor.fetchall()
    return jsonify([dict(s) for s in submissions]), 200

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True, port=5000)