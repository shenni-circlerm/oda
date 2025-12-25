from flask import Blueprint, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required
from werkzeug.security import check_password_hash
from project.models import User

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