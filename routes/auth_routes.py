from flask import Blueprint, redirect, url_for, request, flash, render_template
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from project.models import User
from extensions import db

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('admin.staff_dashboard'))
        
        flash('Please check your login details and try again.')
        return redirect(url_for('customer.landing'))
    return redirect(url_for('customer.landing'))

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('customer.landing'))

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        
        if not check_password_hash(current_user.password, current_password):
            flash('Incorrect current password.')
            return redirect(url_for('auth.change_password'))
            
        current_user.password = generate_password_hash(new_password)
        db.session.commit()
        flash('Password updated successfully.')
        return redirect(url_for('admin.staff_dashboard'))
        
    return render_template('change_password.html')