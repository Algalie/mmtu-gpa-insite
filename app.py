from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
import json
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-in-production')

# =============================================================================
# POSTGRESQL DATABASE CONFIGURATION - USING pg8000
# =============================================================================

# Get DATABASE_URL from environment (REQUIRED)
DATABASE_URL = os.environ.get('DATABASE_URL')

# ENFORCE PostgreSQL - No SQLite fallback
if not DATABASE_URL:
    print("❌ CRITICAL ERROR: DATABASE_URL environment variable is missing!")
    print("💡 On Render, make sure you have:")
    print("   - PostgreSQL database created")
    print("   - DATABASE_URL environment variable set")
    raise RuntimeError("DATABASE_URL environment variable is required for production")

# Convert to pg8000 format
if DATABASE_URL.startswith('postgresql://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+pg8000://', 1)
elif DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql+pg8000://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

print(f"🎯 Database configured: PostgreSQL with pg8000")
print(f"🔗 Connection: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else 'Connected'}")

# =============================================================================
# DATABASE MODELS
# =============================================================================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    department = db.Column(db.String(100), default='Computer Science')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)
    
    # Relationships
    saved_records = db.relationship('SavedRecord', backref='user', lazy=True, cascade='all, delete-orphan')
    final_gpa_records = db.relationship('FinalGPARecord', backref='user', lazy=True, cascade='all, delete-orphan')
    save_actions = db.relationship('SaveAction', backref='user', lazy=True, cascade='all, delete-orphan')
    feedback_responses = db.relationship('FeedbackResponse', backref='user', lazy=True, cascade='all, delete-orphan')

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

class FeedbackMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(50), default='thank_you')  # thank_you, feedback_request, etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

class FeedbackResponse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    feedback_message_id = db.Column(db.Integer, db.ForeignKey('feedback_message.id'), nullable=False)
    rating = db.Column(db.String(50))  # excellent, good, average, poor
    comments = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    feedback_message = db.relationship('FeedbackMessage', backref='responses')

def init_db():
    with app.app_context():
        try:
            # Verify we're using PostgreSQL
            if not DATABASE_URL or 'postgresql' not in DATABASE_URL:
                raise ValueError("Must use PostgreSQL database! Current: " + str(DATABASE_URL))
            
            # Create all tables
            db.create_all()
            
            # Check if we need to add the is_admin column
            try:
                # Try to query the is_admin column to see if it exists
                db.session.execute(text('SELECT is_admin FROM "user" LIMIT 1'))
            except Exception as e:
                if 'column "is_admin" does not exist' in str(e):
                    print("🔄 Adding is_admin column to user table...")
                    db.session.execute(text('ALTER TABLE "user" ADD COLUMN is_admin BOOLEAN DEFAULT FALSE'))
                    db.session.commit()
                    print("✅ Added is_admin column")
            
            # Check if we need to create the new tables
            try:
                # Try to query the new tables to see if they exist
                db.session.execute(text('SELECT 1 FROM feedback_message LIMIT 1'))
                db.session.execute(text('SELECT 1 FROM feedback_response LIMIT 1'))
            except Exception as e:
                if 'relation "feedback_message" does not exist' in str(e):
                    print("🔄 Creating new tables for admin functionality...")
                    # Create the new tables manually
                    db.session.execute(text('''
                        CREATE TABLE feedback_message (
                            id SERIAL PRIMARY KEY,
                            title VARCHAR(200) NOT NULL,
                            message TEXT NOT NULL,
                            message_type VARCHAR(50) DEFAULT 'thank_you',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            is_active BOOLEAN DEFAULT TRUE
                        )
                    '''))
                    db.session.execute(text('''
                        CREATE TABLE feedback_response (
                            id SERIAL PRIMARY KEY,
                            user_id INTEGER REFERENCES "user"(id),
                            feedback_message_id INTEGER REFERENCES feedback_message(id),
                            rating VARCHAR(50),
                            comments TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    '''))
                    db.session.commit()
                    print("✅ Created new tables for admin functionality")
            
            # Create admin user if not exists
            admin_user = User.query.filter_by(student_id='584870').first()
            if not admin_user:
                admin_password_hash = generate_password_hash('codex222')
                admin_user = User(
                    student_id='584870',
                    name='Kanja Kamara',
                    password_hash=admin_password_hash,
                    department='Computer Science',
                    is_admin=True
                )
                db.session.add(admin_user)
                db.session.commit()
                print("✅ Admin user created successfully!")
            else:
                # Ensure existing admin user has admin privileges
                if not admin_user.is_admin:
                    admin_user.is_admin = True
                    db.session.commit()
                    print("✅ Updated existing admin user privileges")
            
            print("✅ PostgreSQL database tables created/updated successfully!")
            print(f"🔗 Using database: {DATABASE_URL.split('@')[-1] if DATABASE_URL else 'Unknown'}")
            
        except Exception as e:
            print(f"❌ Error creating/updating database tables: {e}")
            import traceback
            traceback.print_exc()
            # Don't raise in production, just log
            if os.environ.get('FLASK_ENV') == 'development':
                raise

# Initialize database when app starts
with app.app_context():
    init_db()

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page', 'error')
            return redirect(url_for('welcome'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def admin_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page', 'error')
            return redirect(url_for('welcome'))
        
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            flash('Admin access required', 'error')
            return redirect(url_for('dashboard'))
        
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

def format_datetime(dt):
    if not dt:
        return 'Unknown'
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return dt[:16] if len(dt) >= 16 else dt
    if hasattr(dt, 'strftime'):
        return dt.strftime('%Y-%m-%d %H:%M')
    return str(dt)

# =============================================================================
# ROUTES
# =============================================================================

@app.route('/')
def welcome():
    return render_template('login.html')

@app.route('/health')
def health_check():
    try:
        # Test database connection
        db.session.execute(text('SELECT 1'))
        user_count = User.query.count()
        return jsonify({
            'status': 'healthy', 
            'database': 'postgresql_connected',
            'users_count': user_count,
            'timestamp': datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy', 
            'error': str(e),
            'database_url': DATABASE_URL[:50] + '...' if DATABASE_URL else 'missing'
        }), 500

@app.route('/login', methods=['POST'])
def login():
    student_id = request.form.get('student_id')
    password = request.form.get('password')
    
    user = User.query.filter_by(student_id=student_id).first()
    
    if user and check_password_hash(user.password_hash, password):
        session['user_id'] = user.id
        session['student_id'] = user.student_id
        session['student_name'] = user.name
        session['is_admin'] = user.is_admin
        
        if user.is_admin:
            flash('Admin login successful!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
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
        
        # Prevent using admin ID
        if student_id == '584870':
            flash('This student ID is reserved', 'error')
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
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
    
    user = User.query.get(session['user_id'])
    
    # Check for active feedback messages
    active_feedback = FeedbackMessage.query.filter_by(is_active=True).first()
    has_feedback = active_feedback is not None
    
    return render_template('dashboard.html', user=user, has_feedback=has_feedback)

@app.route('/set-modules', methods=['GET', 'POST'])
@login_required
def set_modules():
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
        
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
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
        
    num_modules = session.get('num_modules', 1)
    return render_template('modules_input.html', num_modules=num_modules)

@app.route('/calculate', methods=['POST'])
@login_required
def calculate():
    if session.get('is_admin'):
        return jsonify({'error': 'Admin access only'}), 403
        
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
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
        
    calculation = session.get('last_calculation')
    if not calculation:
        flash('No calculation found. Please calculate your GPA first.', 'error')
        return redirect(url_for('modules_input'))
    return render_template('result.html', calculation=calculation)

@app.route('/save-result', methods=['POST'])
@login_required
def save_result():
    if session.get('is_admin'):
        return jsonify({'error': 'Admin access only'}), 403
        
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
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
        
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
                'created_at': format_datetime(record.created_at)
            })
        
        return render_template('saved_records.html', records=records_list)
        
    except Exception as e:
        print(f"❌ Error in saved_records: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Error loading saved records. Please try again.', 'error')
        return redirect(url_for('dashboard'))

@app.route('/saved-records/<int:record_id>')
@login_required
def view_record(record_id):
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
        
    try:
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
            'created_at': format_datetime(record.created_at)
        }
        record_dict['modules'] = json.loads(record_dict['modules_json'])
        return render_template('view_record.html', record=record_dict)
    except Exception as e:
        print(f"Error in view_record: {e}")
        import traceback
        traceback.print_exc()
        flash('Error loading record', 'error')
        return redirect(url_for('saved_records'))

@app.route('/delete-record/<int:record_id>', methods=['POST'])
@login_required
def delete_record(record_id):
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
        
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
    if session.get('is_admin'):
        return redirect(url_for('admin_profile'))
        
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
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
        
    try:
        saved_records = SavedRecord.query.filter_by(user_id=session['user_id']).order_by(SavedRecord.created_at.desc()).all()
        
        # Format dates for template
        records_list = []
        for record in saved_records:
            records_list.append({
                'id': record.id,
                'title': record.title,
                'gpa': record.gpa,
                'created_at': format_datetime(record.created_at)
            })
        
        return render_template('final_calculation.html', saved_records=records_list)
    except Exception as e:
        print(f"❌ Error in final_calculation route: {str(e)}")
        flash('Error loading final calculation page', 'error')
        return redirect(url_for('dashboard'))

@app.route('/calculate-final-gpa', methods=['POST'])
@login_required
def calculate_final_gpa():
    if session.get('is_admin'):
        return jsonify({'error': 'Admin access only'}), 403
        
    try:
        data = request.get_json()
        print(f"🔍 Debug: Received data for final GPA: {data}")
        
        first_semester_id = data.get('first_semester_id')
        second_semester_id = data.get('second_semester_id')
        
        if not first_semester_id or not second_semester_id:
            return jsonify({'success': False, 'message': 'Both semesters are required'}), 400
        
        # Convert to integers
        first_semester_id = int(first_semester_id)
        second_semester_id = int(second_semester_id)
        
        if first_semester_id == second_semester_id:
            return jsonify({'success': False, 'message': 'Please select different semesters'}), 400
        
        # Get first semester GPA
        first_semester = SavedRecord.query.filter_by(id=first_semester_id, user_id=session['user_id']).first()
        
        # Get second semester GPA
        second_semester = SavedRecord.query.filter_by(id=second_semester_id, user_id=session['user_id']).first()
        
        if not first_semester:
            return jsonify({'success': False, 'message': 'First semester record not found'}), 400
        
        if not second_semester:
            return jsonify({'success': False, 'message': 'Second semester record not found'}), 400
        
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
        
    except Exception as e:
        print(f"❌ Error in calculate_final_gpa: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'An error occurred during calculation: {str(e)}'}), 500

@app.route('/save-final-gpa', methods=['POST'])
@login_required
def save_final_gpa():
    if session.get('is_admin'):
        return jsonify({'error': 'Admin access only'}), 403
        
    try:
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
        
    except Exception as e:
        print(f"❌ Error in save_final_gpa: {str(e)}")
        return jsonify({'success': False, 'message': f'Error saving final GPA: {str(e)}'}), 500

@app.route('/final-records')
@login_required
def final_records():
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
        
    try:
        records = FinalGPARecord.query.filter_by(user_id=session['user_id']).order_by(FinalGPARecord.created_at.desc()).all()
        
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
                'created_at': format_datetime(record.created_at)
            })
        
        return render_template('final_records.html', records=records_list)
    except Exception as e:
        print(f"❌ Error in final_records: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Error loading final records. Please try again.', 'error')
        return redirect(url_for('dashboard'))

@app.route('/delete-final-record/<int:record_id>', methods=['POST'])
@login_required
def delete_final_record(record_id):
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
        
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

# =============================================================================
# ADMIN ROUTES
# =============================================================================

@app.route('/admin')
@admin_required
def admin_dashboard():
    # Get statistics
    total_users = User.query.filter_by(is_admin=False).count()
    total_records = SavedRecord.query.count()
    total_final_records = FinalGPARecord.query.count()
    recent_users = User.query.filter_by(is_admin=False).order_by(User.created_at.desc()).limit(5).all()
    
    # Get feedback statistics
    feedback_responses = FeedbackResponse.query.count()
    rating_counts = {
        'excellent': FeedbackResponse.query.filter_by(rating='excellent').count(),
        'good': FeedbackResponse.query.filter_by(rating='good').count(),
        'average': FeedbackResponse.query.filter_by(rating='average').count(),
        'poor': FeedbackResponse.query.filter_by(rating='poor').count()
    }
    
    return render_template('admin/dashboard.html',
                         total_users=total_users,
                         total_records=total_records,
                         total_final_records=total_final_records,
                         recent_users=recent_users,
                         feedback_responses=feedback_responses,
                         rating_counts=rating_counts)

@app.route('/admin/users')
@admin_required
def admin_users():
    users = User.query.filter_by(is_admin=False).order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/delete-user/<int:user_id>', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    if user_id == session['user_id']:
        flash('Cannot delete your own account', 'error')
        return redirect(url_for('admin_users'))
    
    user = User.query.get(user_id)
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('admin_users'))
    
    # Log the delete action
    new_action = SaveAction(
        user_id=session['user_id'],
        action='admin_delete_user',
        details=f"Admin deleted user: {user.name} ({user.student_id})"
    )
    
    db.session.add(new_action)
    db.session.delete(user)
    db.session.commit()
    
    flash(f'User {user.name} deleted successfully', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/feedback')
@admin_required
def admin_feedback():
    # Get active feedback message
    active_message = FeedbackMessage.query.filter_by(is_active=True).first()
    
    # Get all feedback responses with user info
    responses = FeedbackResponse.query.order_by(FeedbackResponse.created_at.desc()).all()
    
    # Get all feedback messages
    messages = FeedbackMessage.query.order_by(FeedbackMessage.created_at.desc()).all()
    
    return render_template('admin/feedback.html',
                         active_message=active_message,
                         responses=responses,
                         messages=messages)

@app.route('/admin/send-feedback', methods=['POST'])
@admin_required
def admin_send_feedback():
    title = request.form.get('title')
    message = request.form.get('message')
    message_type = request.form.get('message_type', 'thank_you')
    
    if not title or not message:
        flash('Title and message are required', 'error')
        return redirect(url_for('admin_feedback'))
    
    # Deactivate any existing active message
    FeedbackMessage.query.update({'is_active': False})
    
    # Create new feedback message
    new_message = FeedbackMessage(
        title=title,
        message=message,
        message_type=message_type,
        is_active=True
    )
    
    db.session.add(new_message)
    
    # Log the action
    new_action = SaveAction(
        user_id=session['user_id'],
        action='send_feedback_message',
        details=f"Admin sent feedback message: {title}"
    )
    
    db.session.add(new_action)
    db.session.commit()
    
    flash('Feedback message sent to all users!', 'success')
    return redirect(url_for('admin_feedback'))

@app.route('/admin/end-feedback', methods=['POST'])
@admin_required
def admin_end_feedback():
    # Deactivate all active messages
    FeedbackMessage.query.update({'is_active': False})
    db.session.commit()
    
    flash('Feedback session ended', 'success')
    return redirect(url_for('admin_feedback'))

@app.route('/admin/delete-feedback-message/<int:message_id>', methods=['POST'])
@admin_required
def admin_delete_feedback_message(message_id):
    message = FeedbackMessage.query.get(message_id)
    if not message:
        flash('Message not found', 'error')
        return redirect(url_for('admin_feedback'))
    
    db.session.delete(message)
    db.session.commit()
    
    flash('Feedback message deleted', 'success')
    return redirect(url_for('admin_feedback'))

@app.route('/admin/profile')
@admin_required
def admin_profile():
    user = User.query.get(session['user_id'])
    return render_template('admin/profile.html', user=user)

# =============================================================================
# FEEDBACK ROUTES (FOR STUDENTS)
# =============================================================================

@app.route('/feedback')
@login_required
def feedback():
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
        
    # Get active feedback message
    active_message = FeedbackMessage.query.filter_by(is_active=True).first()
    
    if not active_message:
        flash('No active feedback request at the moment', 'info')
        return redirect(url_for('dashboard'))
    
    # Check if user already responded
    existing_response = FeedbackResponse.query.filter_by(
        user_id=session['user_id'],
        feedback_message_id=active_message.id
    ).first()
    
    if existing_response:
        flash('You have already submitted feedback for this message', 'info')
        return redirect(url_for('dashboard'))
    
    return render_template('feedback.html', message=active_message)

@app.route('/submit-feedback', methods=['POST'])
@login_required
def submit_feedback():
    if session.get('is_admin'):
        return jsonify({'error': 'Admin access only'}), 403
        
    rating = request.form.get('rating')
    comments = request.form.get('comments', '')
    message_id = request.form.get('message_id')
    
    if not rating or not message_id:
        flash('Please provide a rating', 'error')
        return redirect(url_for('feedback'))
    
    # Check if already responded
    existing_response = FeedbackResponse.query.filter_by(
        user_id=session['user_id'],
        feedback_message_id=message_id
    ).first()
    
    if existing_response:
        flash('You have already submitted feedback', 'error')
        return redirect(url_for('dashboard'))
    
    # Save feedback response
    new_response = FeedbackResponse(
        user_id=session['user_id'],
        feedback_message_id=message_id,
        rating=rating,
        comments=comments
    )
    
    db.session.add(new_response)
    db.session.commit()
    
    flash('Thank you for your feedback!', 'success')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)

