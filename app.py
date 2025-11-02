from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import os
import time
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import json

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

# Enhanced database configuration with better error handling
def get_db_connection():
    database_url = os.environ.get('DATABASE_URL')
    print(f"Database URL: {database_url}")
    
    if database_url:
        try:
            import psycopg2
            from urllib.parse import urlparse
            
            result = urlparse(database_url)
            print(f"Connecting to PostgreSQL: {result.hostname}:{result.port}, database: {result.path[1:]}")
            
            conn = psycopg2.connect(
                host=result.hostname,
                database=result.path[1:],
                user=result.username,
                password=result.password,
                port=result.port
            )
            print("✅ PostgreSQL connection successful!")
            return conn
        except ImportError as e:
            print(f"❌ psycopg2 import error: {e}")
        except Exception as e:
            print(f"❌ PostgreSQL connection error: {e}")
    
    # Fallback to SQLite
    try:
        import sqlite3
        instance_dir = 'instance'
        if not os.path.exists(instance_dir):
            os.makedirs(instance_dir, exist_ok=True)
        
        conn = sqlite3.connect('instance/gpa.db')
        conn.row_factory = sqlite3.Row
        print("✅ SQLite connection successful (fallback)")
        return conn
    except Exception as e:
        print(f"❌ SQLite connection error: {e}")
        raise Exception(f"No database connection available: {e}")

def execute_query(query, params=()):
    print(f"Executing query: {query} with params: {params}")
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        
        if query.strip().upper().startswith('SELECT'):
            result = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            result_dicts = []
            for row in result:
                if hasattr(row, '_asdict'):
                    result_dicts.append(dict(row._asdict()))
                else:
                    row_dict = {}
                    for i, col in enumerate(columns):
                        row_dict[col] = row[i] if i < len(row) else None
                    result_dicts.append(row_dict)
            conn.close()
            print(f"Query returned {len(result_dicts)} rows")
            return result_dicts
        else:
            conn.commit()
            if query.strip().upper().startswith('INSERT'):
                try:
                    cursor.execute("SELECT LASTVAL()")
                    last_id = cursor.fetchone()[0]
                except:
                    cursor.execute("SELECT last_insert_rowid()")
                    last_id = cursor.fetchone()[0]
                conn.close()
                print(f"Insert successful, ID: {last_id}")
                return last_id
            conn.close()
            print("Query executed successfully")
            return True
    except Exception as e:
        print(f"❌ Query error: {e}")
        conn.rollback()
        conn.close()
        raise e

def init_db():
    print("Initializing database...")
    try:
        # Users table
        execute_query('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                student_id VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                password_hash VARCHAR(200) NOT NULL,
                department VARCHAR(100) DEFAULT 'Computer Science',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Saved records table
        execute_query('''
            CREATE TABLE IF NOT EXISTS saved_records (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                title VARCHAR(200) NOT NULL,
                semester VARCHAR(100),
                modules_json TEXT NOT NULL,
                gpa REAL NOT NULL,
                status VARCHAR(50) NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Save actions table
        execute_query('''
            CREATE TABLE IF NOT EXISTS save_actions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                action VARCHAR(50),
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Final GPA records table
        execute_query('''
            CREATE TABLE IF NOT EXISTS final_gpa_records (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                title VARCHAR(200) NOT NULL,
                first_semester_gpa REAL NOT NULL,
                second_semester_gpa REAL NOT NULL,
                final_gpa REAL NOT NULL,
                status VARCHAR(50) NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        print("✅ Database initialized successfully!")
    except Exception as e:
        print(f"❌ Database initialization error: {e}")

# Initialize database when app starts
print("🚀 Starting MMTU GPA Insite...")
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
    print(f"Login attempt for student ID: {student_id}")
    
    try:
        users = execute_query('SELECT * FROM users WHERE student_id = %s', (student_id,))
        if users and check_password_hash(users[0]['password_hash'], password):
            user = users[0]
            session['user_id'] = user['id']
            session['student_id'] = user['student_id']
            session['student_name'] = user['name']
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid student ID or password', 'error')
            return redirect(url_for('welcome'))
    except Exception as e:
        print(f"❌ Login error: {e}")
        flash(f'Database error during login: {str(e)}', 'error')
        return redirect(url_for('welcome'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        student_id = request.form.get('student_id')
        department = request.form.get('department')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        print(f"Signup attempt: {name}, {student_id}, {department}")
        
        if not all([name, student_id, department, password, confirm_password]):
            flash('Please fill in all required fields', 'error')
            return render_template('signup.html')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('signup.html')
        
        if not department.strip():
            flash('Please enter your department name', 'error')
            return render_template('signup.html')
        
        try:
            existing_users = execute_query('SELECT id FROM users WHERE student_id = %s', (student_id,))
            if existing_users:
                flash('Student ID already exists', 'error')
                return render_template('signup.html')
            
            password_hash = generate_password_hash(password)
            user_id = execute_query(
                'INSERT INTO users (student_id, name, password_hash, department) VALUES (%s, %s, %s, %s)',
                (student_id, name, password_hash, department.strip())
            )
            
            print(f"✅ User registered successfully with ID: {user_id}")
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('welcome'))
        except Exception as e:
            print(f"❌ Registration error: {e}")
            flash(f'Database error during registration: {str(e)}', 'error')
            return render_template('signup.html')
    
    return render_template('signup.html')

@app.route('/dashboard')
@login_required
def dashboard():
    try:
        users = execute_query('SELECT * FROM users WHERE id = %s', (session['user_id'],))
        user = users[0] if users else None
        return render_template('dashboard.html', user=user)
    except Exception as e:
        flash('Error loading dashboard', 'error')
        return redirect(url_for('welcome'))

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
    try:
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
            'details': details,
            'message': f"Your semester GPA is {gpa} --- {status}."
        }
        
        return jsonify({
            'blocked': False, 
            'gpa': gpa, 
            'status': status, 
            'details': details,
            'message': f"Your semester GPA is {gpa} --- {status}."
        })
    
    except Exception as e:
        return jsonify({
            'blocked': True,
            'message': f'Calculation error: {str(e)}'
        }), 500

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
    
    try:
        execute_query(
            'INSERT INTO saved_records (user_id, title, semester, modules_json, gpa, status, notes) VALUES (%s, %s, %s, %s, %s, %s, %s)',
            (session['user_id'], title, semester, json.dumps(calculation['modules']), calculation['gpa'], calculation['status'], notes)
        )
        
        execute_query(
            'INSERT INTO save_actions (user_id, action, details) VALUES (%s, %s, %s)',
            (session['user_id'], 'save_record', f"Saved GPA record: {title} - GPA: {calculation['gpa']}")
        )
        
        return jsonify({'success': True, 'message': 'Result saved successfully!'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error saving result: {str(e)}'}), 500

@app.route('/saved-records')
@login_required
def saved_records():
    try:
        records = execute_query('SELECT * FROM saved_records WHERE user_id = %s ORDER BY created_at DESC', (session['user_id'],))
        return render_template('saved_records.html', records=records)
    except Exception as e:
        flash('Error loading saved records', 'error')
        return redirect(url_for('dashboard'))

@app.route('/saved-records/<int:record_id>')
@login_required
def view_record(record_id):
    try:
        records = execute_query('SELECT * FROM saved_records WHERE id = %s AND user_id = %s', (record_id, session['user_id']))
        if not records:
            flash('Record not found', 'error')
            return redirect(url_for('saved_records'))
        
        record = records[0]
        record['modules'] = json.loads(record['modules_json'])
        return render_template('view_record.html', record=record)
    except Exception as e:
        flash('Error loading record', 'error')
        return redirect(url_for('saved_records'))

@app.route('/delete-record/<int:record_id>', methods=['POST'])
@login_required
def delete_record(record_id):
    try:
        records = execute_query('SELECT * FROM saved_records WHERE id = %s AND user_id = %s', (record_id, session['user_id']))
        if not records:
            flash('Record not found', 'error')
            return redirect(url_for('saved_records'))
        
        record = records[0]
        execute_query(
            'INSERT INTO save_actions (user_id, action, details) VALUES (%s, %s, %s)',
            (session['user_id'], 'delete_record', f"Deleted GPA record: {record['title']} - GPA: {record['gpa']}")
        )
        
        execute_query('DELETE FROM saved_records WHERE id = %s', (record_id,))
        
        flash('Record deleted successfully', 'success')
        return redirect(url_for('saved_records'))
    except Exception as e:
        flash('Error deleting record', 'error')
        return redirect(url_for('saved_records'))

@app.route('/final-calculation')
@login_required
def final_calculation():
    try:
        saved_records = execute_query('SELECT * FROM saved_records WHERE user_id = %s ORDER BY created_at DESC', (session['user_id'],))
        return render_template('final_calculation.html', saved_records=saved_records)
    except Exception as e:
        flash('Error loading records for final calculation', 'error')
        return redirect(url_for('dashboard'))

@app.route('/calculate-final-gpa', methods=['POST'])
@login_required
def calculate_final_gpa():
    data = request.get_json()
    first_semester_id = data.get('first_semester_id')
    second_semester_id = data.get('second_semester_id')
    
    try:
        first_semester_records = execute_query('SELECT * FROM saved_records WHERE id = %s AND user_id = %s', (first_semester_id, session['user_id']))
        second_semester_records = execute_query('SELECT * FROM saved_records WHERE id = %s AND user_id = %s', (second_semester_id, session['user_id']))
        
        if not first_semester_records or not second_semester_records:
            return jsonify({'success': False, 'message': 'One or both semester records not found'}), 400
        
        first_semester = first_semester_records[0]
        second_semester = second_semester_records[0]
        
        first_gpa = first_semester['gpa']
        second_gpa = second_semester['gpa']
        final_gpa = round((first_gpa + second_gpa) / 2, 2)
        
        if final_gpa >= 4.0:
            status = "Excellent Pass"
        elif final_gpa >= 3.0:
            status = "Pass"
        elif final_gpa >= 2.7:
            status = "Fail"
        else:
            status = "Withdrew"
        
        session['final_calculation'] = {
            'first_semester': first_semester,
            'second_semester': second_semester,
            'first_gpa': first_gpa,
            'second_gpa': second_gpa,
            'final_gpa': final_gpa,
            'status': status
        }
        
        return jsonify({
            'success': True,
            'first_gpa': first_gpa,
            'second_gpa': second_gpa,
            'final_gpa': final_gpa,
            'status': status,
            'message': f'Final GPA: {final_gpa} - {status}'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error calculating final GPA: {str(e)}'}), 500

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
    
    try:
        execute_query(
            'INSERT INTO final_gpa_records (user_id, title, first_semester_gpa, second_semester_gpa, final_gpa, status, notes) VALUES (%s, %s, %s, %s, %s, %s, %s)',
            (session['user_id'], title, calculation['first_gpa'], calculation['second_gpa'], calculation['final_gpa'], calculation['status'], notes)
        )
        
        execute_query(
            'INSERT INTO save_actions (user_id, action, details) VALUES (%s, %s, %s)',
            (session['user_id'], 'save_final_gpa', f"Saved Final GPA: {title} - GPA: {calculation['final_gpa']}")
        )
        
        return jsonify({'success': True, 'message': 'Final GPA saved successfully!'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error saving final GPA: {str(e)}'}), 500

@app.route('/final-records')
@login_required
def final_records():
    try:
        records = execute_query('SELECT * FROM final_gpa_records WHERE user_id = %s ORDER BY created_at DESC', (session['user_id'],))
        return render_template('final_records.html', records=records)
    except Exception as e:
        flash('Error loading final records', 'error')
        return redirect(url_for('dashboard'))

@app.route('/delete-final-record/<int:record_id>', methods=['POST'])
@login_required
def delete_final_record(record_id):
    try:
        records = execute_query('SELECT * FROM final_gpa_records WHERE id = %s AND user_id = %s', (record_id, session['user_id']))
        if not records:
            flash('Record not found', 'error')
            return redirect(url_for('final_records'))
        
        record = records[0]
        execute_query(
            'INSERT INTO save_actions (user_id, action, details) VALUES (%s, %s, %s)',
            (session['user_id'], 'delete_final_record', f"Deleted Final GPA record: {record['title']} - GPA: {record['final_gpa']}")
        )
        
        execute_query('DELETE FROM final_gpa_records WHERE id = %s', (record_id,))
        
        flash('Final record deleted successfully', 'success')
        return redirect(url_for('final_records'))
    except Exception as e:
        flash('Error deleting final record', 'error')
        return redirect(url_for('final_records'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    try:
        users = execute_query('SELECT * FROM users WHERE id = %s', (session['user_id'],))
        user = users[0] if users else None
        
        if request.method == 'POST':
            action = request.form.get('action')
            
            if action == 'update_profile':
                name = request.form.get('name')
                department = request.form.get('department')
                
                if not name.strip() or not department.strip():
                    flash('Name and department are required', 'error')
                else:
                    execute_query(
                        'UPDATE users SET name = %s, department = %s WHERE id = %s',
                        (name, department.strip(), session['user_id'])
                    )
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
                    execute_query(
                        'UPDATE users SET password_hash = %s WHERE id = %s',
                        (new_password_hash, session['user_id'])
                    )
                    flash('Password changed successfully', 'success')
        
        return render_template('profile.html', user=user)
    except Exception as e:
        flash('Error loading profile', 'error')
        return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('welcome'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import os
import time
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import json

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

# Enhanced database configuration with better error handling
def get_db_connection():
    database_url = os.environ.get('DATABASE_URL')
    print(f"Database URL: {database_url}")
    
    if database_url:
        try:
            import psycopg2
            from urllib.parse import urlparse
            
            result = urlparse(database_url)
            print(f"Connecting to PostgreSQL: {result.hostname}:{result.port}, database: {result.path[1:]}")
            
            conn = psycopg2.connect(
                host=result.hostname,
                database=result.path[1:],
                user=result.username,
                password=result.password,
                port=result.port
            )
            print("✅ PostgreSQL connection successful!")
            return conn
        except ImportError as e:
            print(f"❌ psycopg2 import error: {e}")
        except Exception as e:
            print(f"❌ PostgreSQL connection error: {e}")
    
    # Fallback to SQLite
    try:
        import sqlite3
        instance_dir = 'instance'
        if not os.path.exists(instance_dir):
            os.makedirs(instance_dir, exist_ok=True)
        
        conn = sqlite3.connect('instance/gpa.db')
        conn.row_factory = sqlite3.Row
        print("✅ SQLite connection successful (fallback)")
        return conn
    except Exception as e:
        print(f"❌ SQLite connection error: {e}")
        raise Exception(f"No database connection available: {e}")

def execute_query(query, params=()):
    print(f"Executing query: {query} with params: {params}")
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        
        if query.strip().upper().startswith('SELECT'):
            result = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            result_dicts = []
            for row in result:
                if hasattr(row, '_asdict'):
                    result_dicts.append(dict(row._asdict()))
                else:
                    row_dict = {}
                    for i, col in enumerate(columns):
                        row_dict[col] = row[i] if i < len(row) else None
                    result_dicts.append(row_dict)
            conn.close()
            print(f"Query returned {len(result_dicts)} rows")
            return result_dicts
        else:
            conn.commit()
            if query.strip().upper().startswith('INSERT'):
                try:
                    cursor.execute("SELECT LASTVAL()")
                    last_id = cursor.fetchone()[0]
                except:
                    cursor.execute("SELECT last_insert_rowid()")
                    last_id = cursor.fetchone()[0]
                conn.close()
                print(f"Insert successful, ID: {last_id}")
                return last_id
            conn.close()
            print("Query executed successfully")
            return True
    except Exception as e:
        print(f"❌ Query error: {e}")
        conn.rollback()
        conn.close()
        raise e

def init_db():
    print("Initializing database...")
    try:
        # Users table
        execute_query('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                student_id VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                password_hash VARCHAR(200) NOT NULL,
                department VARCHAR(100) DEFAULT 'Computer Science',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Saved records table
        execute_query('''
            CREATE TABLE IF NOT EXISTS saved_records (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                title VARCHAR(200) NOT NULL,
                semester VARCHAR(100),
                modules_json TEXT NOT NULL,
                gpa REAL NOT NULL,
                status VARCHAR(50) NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Save actions table
        execute_query('''
            CREATE TABLE IF NOT EXISTS save_actions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                action VARCHAR(50),
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Final GPA records table
        execute_query('''
            CREATE TABLE IF NOT EXISTS final_gpa_records (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                title VARCHAR(200) NOT NULL,
                first_semester_gpa REAL NOT NULL,
                second_semester_gpa REAL NOT NULL,
                final_gpa REAL NOT NULL,
                status VARCHAR(50) NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        print("✅ Database initialized successfully!")
    except Exception as e:
        print(f"❌ Database initialization error: {e}")

# Initialize database when app starts
print("🚀 Starting MMTU GPA Insite...")
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
    print(f"Login attempt for student ID: {student_id}")
    
    try:
        users = execute_query('SELECT * FROM users WHERE student_id = %s', (student_id,))
        if users and check_password_hash(users[0]['password_hash'], password):
            user = users[0]
            session['user_id'] = user['id']
            session['student_id'] = user['student_id']
            session['student_name'] = user['name']
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid student ID or password', 'error')
            return redirect(url_for('welcome'))
    except Exception as e:
        print(f"❌ Login error: {e}")
        flash(f'Database error during login: {str(e)}', 'error')
        return redirect(url_for('welcome'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        student_id = request.form.get('student_id')
        department = request.form.get('department')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        print(f"Signup attempt: {name}, {student_id}, {department}")
        
        if not all([name, student_id, department, password, confirm_password]):
            flash('Please fill in all required fields', 'error')
            return render_template('signup.html')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('signup.html')
        
        if not department.strip():
            flash('Please enter your department name', 'error')
            return render_template('signup.html')
        
        try:
            existing_users = execute_query('SELECT id FROM users WHERE student_id = %s', (student_id,))
            if existing_users:
                flash('Student ID already exists', 'error')
                return render_template('signup.html')
            
            password_hash = generate_password_hash(password)
            user_id = execute_query(
                'INSERT INTO users (student_id, name, password_hash, department) VALUES (%s, %s, %s, %s)',
                (student_id, name, password_hash, department.strip())
            )
            
            print(f"✅ User registered successfully with ID: {user_id}")
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('welcome'))
        except Exception as e:
            print(f"❌ Registration error: {e}")
            flash(f'Database error during registration: {str(e)}', 'error')
            return render_template('signup.html')
    
    return render_template('signup.html')

@app.route('/dashboard')
@login_required
def dashboard():
    try:
        users = execute_query('SELECT * FROM users WHERE id = %s', (session['user_id'],))
        user = users[0] if users else None
        return render_template('dashboard.html', user=user)
    except Exception as e:
        flash('Error loading dashboard', 'error')
        return redirect(url_for('welcome'))

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
    try:
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
            'details': details,
            'message': f"Your semester GPA is {gpa} --- {status}."
        }
        
        return jsonify({
            'blocked': False, 
            'gpa': gpa, 
            'status': status, 
            'details': details,
            'message': f"Your semester GPA is {gpa} --- {status}."
        })
    
    except Exception as e:
        return jsonify({
            'blocked': True,
            'message': f'Calculation error: {str(e)}'
        }), 500

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
    
    try:
        execute_query(
            'INSERT INTO saved_records (user_id, title, semester, modules_json, gpa, status, notes) VALUES (%s, %s, %s, %s, %s, %s, %s)',
            (session['user_id'], title, semester, json.dumps(calculation['modules']), calculation['gpa'], calculation['status'], notes)
        )
        
        execute_query(
            'INSERT INTO save_actions (user_id, action, details) VALUES (%s, %s, %s)',
            (session['user_id'], 'save_record', f"Saved GPA record: {title} - GPA: {calculation['gpa']}")
        )
        
        return jsonify({'success': True, 'message': 'Result saved successfully!'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error saving result: {str(e)}'}), 500

@app.route('/saved-records')
@login_required
def saved_records():
    try:
        records = execute_query('SELECT * FROM saved_records WHERE user_id = %s ORDER BY created_at DESC', (session['user_id'],))
        return render_template('saved_records.html', records=records)
    except Exception as e:
        flash('Error loading saved records', 'error')
        return redirect(url_for('dashboard'))

@app.route('/saved-records/<int:record_id>')
@login_required
def view_record(record_id):
    try:
        records = execute_query('SELECT * FROM saved_records WHERE id = %s AND user_id = %s', (record_id, session['user_id']))
        if not records:
            flash('Record not found', 'error')
            return redirect(url_for('saved_records'))
        
        record = records[0]
        record['modules'] = json.loads(record['modules_json'])
        return render_template('view_record.html', record=record)
    except Exception as e:
        flash('Error loading record', 'error')
        return redirect(url_for('saved_records'))

@app.route('/delete-record/<int:record_id>', methods=['POST'])
@login_required
def delete_record(record_id):
    try:
        records = execute_query('SELECT * FROM saved_records WHERE id = %s AND user_id = %s', (record_id, session['user_id']))
        if not records:
            flash('Record not found', 'error')
            return redirect(url_for('saved_records'))
        
        record = records[0]
        execute_query(
            'INSERT INTO save_actions (user_id, action, details) VALUES (%s, %s, %s)',
            (session['user_id'], 'delete_record', f"Deleted GPA record: {record['title']} - GPA: {record['gpa']}")
        )
        
        execute_query('DELETE FROM saved_records WHERE id = %s', (record_id,))
        
        flash('Record deleted successfully', 'success')
        return redirect(url_for('saved_records'))
    except Exception as e:
        flash('Error deleting record', 'error')
        return redirect(url_for('saved_records'))

@app.route('/final-calculation')
@login_required
def final_calculation():
    try:
        saved_records = execute_query('SELECT * FROM saved_records WHERE user_id = %s ORDER BY created_at DESC', (session['user_id'],))
        return render_template('final_calculation.html', saved_records=saved_records)
    except Exception as e:
        flash('Error loading records for final calculation', 'error')
        return redirect(url_for('dashboard'))

@app.route('/calculate-final-gpa', methods=['POST'])
@login_required
def calculate_final_gpa():
    data = request.get_json()
    first_semester_id = data.get('first_semester_id')
    second_semester_id = data.get('second_semester_id')
    
    try:
        first_semester_records = execute_query('SELECT * FROM saved_records WHERE id = %s AND user_id = %s', (first_semester_id, session['user_id']))
        second_semester_records = execute_query('SELECT * FROM saved_records WHERE id = %s AND user_id = %s', (second_semester_id, session['user_id']))
        
        if not first_semester_records or not second_semester_records:
            return jsonify({'success': False, 'message': 'One or both semester records not found'}), 400
        
        first_semester = first_semester_records[0]
        second_semester = second_semester_records[0]
        
        first_gpa = first_semester['gpa']
        second_gpa = second_semester['gpa']
        final_gpa = round((first_gpa + second_gpa) / 2, 2)
        
        if final_gpa >= 4.0:
            status = "Excellent Pass"
        elif final_gpa >= 3.0:
            status = "Pass"
        elif final_gpa >= 2.7:
            status = "Fail"
        else:
            status = "Withdrew"
        
        session['final_calculation'] = {
            'first_semester': first_semester,
            'second_semester': second_semester,
            'first_gpa': first_gpa,
            'second_gpa': second_gpa,
            'final_gpa': final_gpa,
            'status': status
        }
        
        return jsonify({
            'success': True,
            'first_gpa': first_gpa,
            'second_gpa': second_gpa,
            'final_gpa': final_gpa,
            'status': status,
            'message': f'Final GPA: {final_gpa} - {status}'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error calculating final GPA: {str(e)}'}), 500

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
    
    try:
        execute_query(
            'INSERT INTO final_gpa_records (user_id, title, first_semester_gpa, second_semester_gpa, final_gpa, status, notes) VALUES (%s, %s, %s, %s, %s, %s, %s)',
            (session['user_id'], title, calculation['first_gpa'], calculation['second_gpa'], calculation['final_gpa'], calculation['status'], notes)
        )
        
        execute_query(
            'INSERT INTO save_actions (user_id, action, details) VALUES (%s, %s, %s)',
            (session['user_id'], 'save_final_gpa', f"Saved Final GPA: {title} - GPA: {calculation['final_gpa']}")
        )
        
        return jsonify({'success': True, 'message': 'Final GPA saved successfully!'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error saving final GPA: {str(e)}'}), 500

@app.route('/final-records')
@login_required
def final_records():
    try:
        records = execute_query('SELECT * FROM final_gpa_records WHERE user_id = %s ORDER BY created_at DESC', (session['user_id'],))
        return render_template('final_records.html', records=records)
    except Exception as e:
        flash('Error loading final records', 'error')
        return redirect(url_for('dashboard'))

@app.route('/delete-final-record/<int:record_id>', methods=['POST'])
@login_required
def delete_final_record(record_id):
    try:
        records = execute_query('SELECT * FROM final_gpa_records WHERE id = %s AND user_id = %s', (record_id, session['user_id']))
        if not records:
            flash('Record not found', 'error')
            return redirect(url_for('final_records'))
        
        record = records[0]
        execute_query(
            'INSERT INTO save_actions (user_id, action, details) VALUES (%s, %s, %s)',
            (session['user_id'], 'delete_final_record', f"Deleted Final GPA record: {record['title']} - GPA: {record['final_gpa']}")
        )
        
        execute_query('DELETE FROM final_gpa_records WHERE id = %s', (record_id,))
        
        flash('Final record deleted successfully', 'success')
        return redirect(url_for('final_records'))
    except Exception as e:
        flash('Error deleting final record', 'error')
        return redirect(url_for('final_records'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    try:
        users = execute_query('SELECT * FROM users WHERE id = %s', (session['user_id'],))
        user = users[0] if users else None
        
        if request.method == 'POST':
            action = request.form.get('action')
            
            if action == 'update_profile':
                name = request.form.get('name')
                department = request.form.get('department')
                
                if not name.strip() or not department.strip():
                    flash('Name and department are required', 'error')
                else:
                    execute_query(
                        'UPDATE users SET name = %s, department = %s WHERE id = %s',
                        (name, department.strip(), session['user_id'])
                    )
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
                    execute_query(
                        'UPDATE users SET password_hash = %s WHERE id = %s',
                        (new_password_hash, session['user_id'])
                    )
                    flash('Password changed successfully', 'success')
        
        return render_template('profile.html', user=user)
    except Exception as e:
        flash('Error loading profile', 'error')
        return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('welcome'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
