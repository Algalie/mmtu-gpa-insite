from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import sqlite3
import json
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
# Use environment variable in production. Keep fallback for local dev but change it before going live.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-in-production')
app.config['DATABASE'] = os.path.join(app.instance_path, 'gpa.db')

# Create instance folder if it doesn't exist
if not os.path.exists(app.instance_path):
    os.makedirs(app.instance_path)

def get_db_connection():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    
    # Create users table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            department TEXT DEFAULT 'Computer Science',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create saved_records table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS saved_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            semester TEXT,
            modules_json TEXT NOT NULL,
            gpa REAL NOT NULL,
            status TEXT NOT NULL,
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Create save_actions table for audit
    conn.execute('''
        CREATE TABLE IF NOT EXISTS save_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            details TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add this to your existing database tables
    conn.execute('''
        CREATE TABLE IF NOT EXISTS final_gpa_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            first_semester_gpa REAL NOT NULL,
            second_semester_gpa REAL NOT NULL,
            final_gpa REAL NOT NULL,
            status TEXT NOT NULL,
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')


    
    
    conn.commit()
    conn.close()

# Initialize database when app starts
with app.app_context():
    init_db()

# Helper function to check if user is logged in
def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page', 'error')
            return redirect(url_for('welcome'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# GPA calculation constants
GRADE_POINTS = {'A': 5.0, 'B': 4.0, 'C': 3.0, 'D': 2.0, 'E': 1.0, 'F': 0.0}
GRADE_ORDER = ['A', 'B', 'C', 'D', 'E', 'F']
CREDIT = 3

def apply_reference(grade, is_ref):
    if not is_ref:
        return grade
    idx = GRADE_ORDER.index(grade)
    new_idx = min(idx + 1, len(GRADE_ORDER) - 1)
    return GRADE_ORDER[new_idx]

# Routes
@app.route('/')
def welcome():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    student_id = request.form.get('student_id')
    password = request.form.get('password')
    
    conn = get_db_connection()
    user = conn.execute(
        'SELECT * FROM users WHERE student_id = ?', (student_id,)
    ).fetchone()
    conn.close()
    
    if user and check_password_hash(user['password_hash'], password):
        session['user_id'] = user['id']
        session['student_id'] = user['student_id']
        session['student_name'] = user['name']
        flash('Login successful!', 'success')
        return redirect(url_for('dashboard'))
    else:
        flash('Invalid student ID or password', 'error')
        return redirect(url_for('welcome'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        student_id = request.form.get('student_id')
        department = request.form.get('department')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate all required fields
        if not all([name, student_id, department, password, confirm_password]):
            flash('Please fill in all required fields', 'error')
            return render_template('signup.html')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('signup.html')
        
        # Validate department is not empty
        if not department.strip():
            flash('Please enter your department name', 'error')
            return render_template('signup.html')
        
        conn = get_db_connection()
        existing_user = conn.execute(
            'SELECT id FROM users WHERE student_id = ?', (student_id,)
        ).fetchone()
        
        if existing_user:
            flash('Student ID already exists', 'error')
            conn.close()
            return render_template('signup.html')
        
        password_hash = generate_password_hash(password)
        conn.execute(
            'INSERT INTO users (student_id, name, password_hash, department) VALUES (?, ?, ?, ?)',
            (student_id, name, password_hash, department.strip())
        )
        conn.commit()
        conn.close()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('welcome'))
    
    return render_template('signup.html')

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    user = conn.execute(
        'SELECT * FROM users WHERE id = ?', (session['user_id'],)
    ).fetchone()
    conn.close()
    return render_template('dashboard.html', user=user)

@app.route('/set-modules', methods=['GET', 'POST'])
@login_required
def set_modules():
    if request.method == 'POST':
        num_modules = int(request.form.get('num_modules', 1))
        if 1 <= num_modules <= 12:
            session['num_modules'] = num_modules
            return redirect(url_for('modules_input'))
        else:
            flash('Number of modules must be between 1 and 12', 'error')
    return render_template('set_modules.html')

@app.route('/modules-input')
@login_required
def modules_input():
    num_modules = session.get('num_modules', 1)
    return render_template('modules_input.html', num_modules=num_modules)

@app.route('/calculate', methods=['POST'])
@login_required
def calculate():
    data = request.get_json()
    modules = data.get('modules', [])
    
    # Block if any E or F selected
    for m in modules:
        if m['grade'] in ('E', 'F'):
            return jsonify({
                'blocked': True, 
                'reason': 'E_or_F_present',
                'message': 'Calculation disabled: E or F present. Please contact your faculty.'
            }), 400
    
    total_points = 0.0
    total_credits = 0
    details = []
    
    for m in modules:
        grade_before = m['grade']
        grade_after = apply_reference(grade_before, m.get('reference', False))
        points = GRADE_POINTS[grade_after]
        total_points += points * CREDIT
        total_credits += CREDIT
        
        details.append({
            'label': m.get('label'),
            'code': m.get('code', ''),
            'grade_before': grade_before,
            'grade_after': grade_after,
            'points': points,
            'reference': m.get('reference', False)
        })
    
    gpa = round(total_points / total_credits, 2) if total_credits else 0.0
    
    if gpa >= 4.0:
        status = "Excellent Pass"
    elif gpa >= 3.0:
        status = "Pass"
    elif gpa >= 2.7:
        status = "Fail"
    else:
        status = "Withdrew"
    
    session['last_calculation'] = {
        'gpa': gpa,
        'status': status,
        'modules': modules,
        'details': details
    }
    
    return jsonify({
        'blocked': False, 
        'gpa': gpa, 
        'status': status, 
        'details': details,
        'message': f"Your semester GPA is {gpa} --- {status}."
    })

@app.route('/result')
@login_required
def result():
    calculation = session.get('last_calculation')
    if not calculation:
        flash('No calculation found. Please calculate your GPA first.', 'error')
        return redirect(url_for('modules_input'))
    return render_template('result.html', calculation=calculation)

@app.route('/save-result', methods=['POST'])
@login_required
def save_result():
    calculation = session.get('last_calculation')
    if not calculation:
        return jsonify({'success': False, 'message': 'No calculation to save'}), 400
    
    title = request.form.get('title')
    semester = request.form.get('semester', '')
    notes = request.form.get('notes', '')
    
    if not title:
        return jsonify({'success': False, 'message': 'Title is required'}), 400
    
    conn = get_db_connection()
    
    # Save the record
    conn.execute(
        'INSERT INTO saved_records (user_id, title, semester, modules_json, gpa, status, notes) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (session['user_id'], title, semester, json.dumps(calculation['modules']), calculation['gpa'], calculation['status'], notes)
    )
    
    # Log the save action
    conn.execute(
        'INSERT INTO save_actions (user_id, action, details) VALUES (?, ?, ?)',
        (session['user_id'], 'save_record', f"Saved GPA record: {title} - GPA: {calculation['gpa']}")
    )
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Result saved successfully!'})

@app.route('/saved-records')
@login_required
def saved_records():
    conn = get_db_connection()
    records = conn.execute(
        'SELECT * FROM saved_records WHERE user_id = ? ORDER BY created_at DESC',
        (session['user_id'],)
    ).fetchall()
    conn.close()
    return render_template('saved_records.html', records=records)

@app.route('/saved-records/<int:record_id>')
@login_required
def view_record(record_id):
    conn = get_db_connection()
    record = conn.execute(
        'SELECT * FROM saved_records WHERE id = ? AND user_id = ?',
        (record_id, session['user_id'])
    ).fetchone()
    conn.close()
    
    if not record:
        flash('Record not found', 'error')
        return redirect(url_for('saved_records'))
    
    record_dict = dict(record)
    record_dict['modules'] = json.loads(record_dict['modules_json'])
    return render_template('view_record.html', record=record_dict)

@app.route('/delete-record/<int:record_id>', methods=['POST'])
@login_required
def delete_record(record_id):
    conn = get_db_connection()
    
    # Get record info before deleting
    record = conn.execute(
        'SELECT * FROM saved_records WHERE id = ? AND user_id = ?',
        (record_id, session['user_id'])
    ).fetchone()
    
    if not record:
        flash('Record not found', 'error')
        conn.close()
        return redirect(url_for('saved_records'))
    
    # Log the delete action
    conn.execute(
        'INSERT INTO save_actions (user_id, action, details) VALUES (?, ?, ?)',
        (session['user_id'], 'delete_record', f"Deleted GPA record: {record['title']} - GPA: {record['gpa']}")
    )
    
    # Delete the record
    conn.execute('DELETE FROM saved_records WHERE id = ?', (record_id,))
    conn.commit()
    conn.close()
    
    flash('Record deleted successfully', 'success')
    return redirect(url_for('saved_records'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    conn = get_db_connection()
    user = conn.execute(
        'SELECT * FROM users WHERE id = ?', (session['user_id'],)
    ).fetchone()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_profile':
            name = request.form.get('name')
            department = request.form.get('department')
            
            if not name.strip() or not department.strip():
                flash('Name and department are required', 'error')
            else:
                conn.execute(
                    'UPDATE users SET name = ?, department = ? WHERE id = ?',
                    (name, department.strip(), session['user_id'])
                )
                conn.commit()
                session['student_name'] = name
                flash('Profile updated successfully', 'success')
            
        elif action == 'change_password':
            old_password = request.form.get('old_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            if not check_password_hash(user['password_hash'], old_password):
                flash('Current password is incorrect', 'error')
            elif new_password != confirm_password:
                flash('New passwords do not match', 'error')
            else:
                new_password_hash = generate_password_hash(new_password)
                conn.execute(
                    'UPDATE users SET password_hash = ? WHERE id = ?',
                    (new_password_hash, session['user_id'])
                )
                conn.commit()
                flash('Password changed successfully', 'success')
    
    conn.close()
    return render_template('profile.html', user=user)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('welcome'))








@app.route('/final-calculation')
@login_required
def final_calculation():
    # Get saved records to populate semester selection
    conn = get_db_connection()
    saved_records = conn.execute(
        'SELECT * FROM saved_records WHERE user_id = ? ORDER BY created_at DESC',
        (session['user_id'],)
    ).fetchall()
    conn.close()
    return render_template('final_calculation.html', saved_records=saved_records)

@app.route('/calculate-final-gpa', methods=['POST'])
@login_required
def calculate_final_gpa():
    data = request.get_json()
    first_semester_id = data.get('first_semester_id')
    second_semester_id = data.get('second_semester_id')
    
    conn = get_db_connection()
    
    # Get first semester GPA
    first_semester = conn.execute(
        'SELECT * FROM saved_records WHERE id = ? AND user_id = ?',
        (first_semester_id, session['user_id'])
    ).fetchone()
    
    # Get second semester GPA
    second_semester = conn.execute(
        'SELECT * FROM saved_records WHERE id = ? AND user_id = ?',
        (second_semester_id, session['user_id'])
    ).fetchone()
    
    if not first_semester or not second_semester:
        conn.close()
        return jsonify({'success': False, 'message': 'One or both semester records not found'}), 400
    
    # Calculate final GPA
    first_gpa = first_semester['gpa']
    second_gpa = second_semester['gpa']
    final_gpa = round((first_gpa + second_gpa) / 2, 2)
    
    # Determine status
    if final_gpa >= 4.0:
        status = "Excellent Pass"
    elif final_gpa >= 3.0:
        status = "Pass"
    elif final_gpa >= 2.7:
        status = "Fail"
    else:
        status = "Withdrew"
    
    session['final_calculation'] = {
        'first_semester': dict(first_semester),
        'second_semester': dict(second_semester),
        'first_gpa': first_gpa,
        'second_gpa': second_gpa,
        'final_gpa': final_gpa,
        'status': status
    }
    
    conn.close()
    
    return jsonify({
        'success': True,
        'first_gpa': first_gpa,
        'second_gpa': second_gpa,
        'final_gpa': final_gpa,
        'status': status,
        'message': f'Final GPA: {final_gpa} - {status}'
    })

@app.route('/save-final-gpa', methods=['POST'])
@login_required
def save_final_gpa():
    calculation = session.get('final_calculation')
    if not calculation:
        return jsonify({'success': False, 'message': 'No calculation to save'}), 400
    
    title = request.form.get('title')
    notes = request.form.get('notes', '')
    
    if not title:
        return jsonify({'success': False, 'message': 'Title is required'}), 400
    
    conn = get_db_connection()
    
    # Save final GPA record
    conn.execute(
        'INSERT INTO final_gpa_records (user_id, title, first_semester_gpa, second_semester_gpa, final_gpa, status, notes) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (session['user_id'], title, calculation['first_gpa'], calculation['second_gpa'], calculation['final_gpa'], calculation['status'], notes)
    )
    
    # Log the save action
    conn.execute(
        'INSERT INTO save_actions (user_id, action, details) VALUES (?, ?, ?)',
        (session['user_id'], 'save_final_gpa', f"Saved Final GPA: {title} - GPA: {calculation['final_gpa']}")
    )
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Final GPA saved successfully!'})

@app.route('/final-records')
@login_required
def final_records():
    conn = get_db_connection()
    records = conn.execute(
        'SELECT * FROM final_gpa_records WHERE user_id = ? ORDER BY created_at DESC',
        (session['user_id'],)
    ).fetchall()
    conn.close()
    return render_template('final_records.html', records=records)


@app.route('/delete-final-record/<int:record_id>', methods=['POST'])
@login_required
def delete_final_record(record_id):
    conn = get_db_connection()
    
    # Get record info before deleting
    record = conn.execute(
        'SELECT * FROM final_gpa_records WHERE id = ? AND user_id = ?',
        (record_id, session['user_id'])
    ).fetchone()
    
    if not record:
        flash('Record not found', 'error')
        conn.close()
        return redirect(url_for('final_records'))
    
    # Log the delete action
    conn.execute(
        'INSERT INTO save_actions (user_id, action, details) VALUES (?, ?, ?)',
        (session['user_id'], 'delete_final_record', f"Deleted Final GPA record: {record['title']} - GPA: {record['final_gpa']}")
    )
    
    # Delete the record
    conn.execute('DELETE FROM final_gpa_records WHERE id = ?', (record_id,))
    conn.commit()
    conn.close()
    
    flash('Final record deleted successfully', 'success')
    return redirect(url_for('final_records'))

if __name__ == '__main__':
    app.run(debug=True)
    #port = int(os.environ.get('PORT', 5000))
    #app.run(host='0.0.0.0', port=port, debug=False)
