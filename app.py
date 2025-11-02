from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
import json
import os
import traceback
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-in-production')

# PostgreSQL Configuration
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///gpa.db')
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Define Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    department = db.Column(db.String(100), default='Computer Science')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    saved_records = db.relationship('SavedRecord', backref='user', lazy=True, cascade='all, delete-orphan')
    final_gpa_records = db.relationship('FinalGPARecord', backref='user', lazy=True, cascade='all, delete-orphan')
    save_actions = db.relationship('SaveAction', backref='user', lazy=True, cascade='all, delete-orphan')

class SavedRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    semester = db.Column(db.String(100))
    modules_json = db.Column(db.Text, nullable=False)
    gpa = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class FinalGPARecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    first_semester_gpa = db.Column(db.Float, nullable=False)
    second_semester_gpa = db.Column(db.Float, nullable=False)
    final_gpa = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SaveAction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action = db.Column(db.String(100))
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def init_db():
    with app.app_context():
        try:
            db.create_all()
            print("✅ Database tables created successfully!")
        except Exception as e:
            print(f"❌ Error creating database tables: {e}")

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
    
    user = User.query.filter_by(student_id=student_id).first()
    
    if user and check_password_hash(user.password_hash, password):
        session['user_id'] = user.id
        session['student_id'] = user.student_id
        session['student_name'] = user.name
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
        
        if not all([name, student_id, department, password, confirm_password]):
            flash('Please fill in all required fields', 'error')
            return render_template('signup.html')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('signup.html')
        
        if not department.strip():
            flash('Please enter your department name', 'error')
            return render_template('signup.html')
        
        existing_user = User.query.filter_by(student_id=student_id).first()
        if existing_user:
            flash('Student ID already exists', 'error')
            return render_template('signup.html')
        
        password_hash = generate_password_hash(password)
        new_user = User(
            student_id=student_id,
            name=name,
            password_hash=password_hash,
            department=department.strip()
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('welcome'))
    
    return render_template('signup.html')

@app.route('/dashboard')
@login_required
def dashboard():
    user = User.query.get(session['user_id'])
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
    
    # Save the record
    new_record = SavedRecord(
        user_id=session['user_id'],
        title=title,
        semester=semester,
        modules_json=json.dumps(calculation['modules']),
        gpa=calculation['gpa'],
        status=calculation['status'],
        notes=notes
    )
    
    db.session.add(new_record)
    
    # Log the save action
    new_action = SaveAction(
        user_id=session['user_id'],
        action='save_record',
        details=f"Saved GPA record: {title} - GPA: {calculation['gpa']}"
    )
    
    db.session.add(new_action)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Result saved successfully!'})

@app.route('/saved-records')
@login_required
def saved_records():
    try:
        records = SavedRecord.query.filter_by(user_id=session['user_id']).order_by(SavedRecord.created_at.desc()).all()
        
        # Convert records to list of dictionaries for template
        records_list = []
        for record in records:
            records_list.append({
                'id': record.id,
                'title': record.title,
                'semester': record.semester,
                'gpa': record.gpa,
                'status': record.status,
                'notes': record.notes,
                'created_at': record.created_at
            })
        
        return render_template('saved_records.html', records=records_list)
    except Exception as e:
        print(f"Error in saved_records: {e}")
        flash('Error loading saved records', 'error')
        return redirect(url_for('dashboard'))

@app.route('/saved-records/<int:record_id>')
@login_required
def view_record(record_id):
    record = SavedRecord.query.filter_by(id=record_id, user_id=session['user_id']).first()
    
    if not record:
        flash('Record not found', 'error')
        return redirect(url_for('saved_records'))
    
    record_dict = {
        'id': record.id,
        'title': record.title,
        'semester': record.semester,
        'modules_json': record.modules_json,
        'gpa': record.gpa,
        'status': record.status,
        'notes': record.notes,
        'created_at': record.created_at
    }
    record_dict['modules'] = json.loads(record_dict['modules_json'])
    return render_template('view_record.html', record=record_dict)

@app.route('/delete-record/<int:record_id>', methods=['POST'])
@login_required
def delete_record(record_id):
    record = SavedRecord.query.filter_by(id=record_id, user_id=session['user_id']).first()
    
    if not record:
        flash('Record not found', 'error')
        return redirect(url_for('saved_records'))
    
    # Log the delete action
    new_action = SaveAction(
        user_id=session['user_id'],
        action='delete_record',
        details=f"Deleted GPA record: {record.title} - GPA: {record.gpa}"
    )
    
    db.session.add(new_action)
    db.session.delete(record)
    db.session.commit()
    
    flash('Record deleted successfully', 'success')
    return redirect(url_for('saved_records'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_profile':
            name = request.form.get('name')
            department = request.form.get('department')
            
            if not name.strip() or not department.strip():
                flash('Name and department are required', 'error')
            else:
                user.name = name
                user.department = department.strip()
                db.session.commit()
                session['student_name'] = name
                flash('Profile updated successfully', 'success')
            
        elif action == 'change_password':
            old_password = request.form.get('old_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            if not check_password_hash(user.password_hash, old_password):
                flash('Current password is incorrect', 'error')
            elif new_password != confirm_password:
                flash('New passwords do not match', 'error')
            else:
                user.password_hash = generate_password_hash(new_password)
                db.session.commit()
                flash('Password changed successfully', 'success')
    
    return render_template('profile.html', user=user)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('welcome'))

@app.route('/final-calculation')
@login_required
def final_calculation():
    saved_records = SavedRecord.query.filter_by(user_id=session['user_id']).order_by(SavedRecord.created_at.desc()).all()
    return render_template('final_calculation.html', saved_records=saved_records)

@app.route('/calculate-final-gpa', methods=['POST'])
@login_required
def calculate_final_gpa():
    data = request.get_json()
    first_semester_id = data.get('first_semester_id')
    second_semester_id = data.get('second_semester_id')
    
    # Get first semester GPA
    first_semester = SavedRecord.query.filter_by(id=first_semester_id, user_id=session['user_id']).first()
    
    # Get second semester GPA
    second_semester = SavedRecord.query.filter_by(id=second_semester_id, user_id=session['user_id']).first()
    
    if not first_semester or not second_semester:
        return jsonify({'success': False, 'message': 'One or both semester records not found'}), 400
    
    # Calculate final GPA
    first_gpa = first_semester.gpa
    second_gpa = second_semester.gpa
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
        'first_semester': {
            'id': first_semester.id,
            'title': first_semester.title,
            'gpa': first_semester.gpa
        },
        'second_semester': {
            'id': second_semester.id,
            'title': second_semester.title,
            'gpa': second_semester.gpa
        },
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
    
    # Save final GPA record
    new_final_record = FinalGPARecord(
        user_id=session['user_id'],
        title=title,
        first_semester_gpa=calculation['first_gpa'],
        second_semester_gpa=calculation['second_gpa'],
        final_gpa=calculation['final_gpa'],
        status=calculation['status'],
        notes=notes
    )
    
    db.session.add(new_final_record)
    
    # Log the save action
    new_action = SaveAction(
        user_id=session['user_id'],
        action='save_final_gpa',
        details=f"Saved Final GPA: {title} - GPA: {calculation['final_gpa']}"
    )
    
    db.session.add(new_action)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Final GPA saved successfully!'})

@app.route('/final-records')
@login_required
def final_records():
    try:
        records = FinalGPARecord.query.filter_by(user_id=session['user_id']).order_by(FinalGPARecord.created_at.desc()).all()
        
        # Convert records to list of dictionaries for template
        records_list = []
        for record in records:
            records_list.append({
                'id': record.id,
                'title': record.title,
                'first_semester_gpa': record.first_semester_gpa,
                'second_semester_gpa': record.second_semester_gpa,
                'final_gpa': record.final_gpa,
                'status': record.status,
                'notes': record.notes,
                'created_at': record.created_at
            })
        
        return render_template('final_records.html', records=records_list)
    except Exception as e:
        print(f"Error in final_records: {e}")
        flash('Error loading final records', 'error')
        return redirect(url_for('dashboard'))

@app.route('/delete-final-record/<int:record_id>', methods=['POST'])
@login_required
def delete_final_record(record_id):
    record = FinalGPARecord.query.filter_by(id=record_id, user_id=session['user_id']).first()
    
    if not record:
        flash('Record not found', 'error')
        return redirect(url_for('final_records'))
    
    # Log the delete action
    new_action = SaveAction(
        user_id=session['user_id'],
        action='delete_final_record',
        details=f"Deleted Final GPA record: {record.title} - GPA: {record.final_gpa}"
    )
    
    db.session.add(new_action)
    db.session.delete(record)
    db.session.commit()
    
    flash('Final record deleted successfully', 'success')
    return redirect(url_for('final_records'))

if __name__ == '__main__':
    app.run(debug=True)

