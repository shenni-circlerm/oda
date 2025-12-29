from flask import Blueprint, redirect, url_for, request, flash, render_template, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
import random
import string
from project.models import User, Restaurant
from extensions import db
from .email import send_email

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and user.is_active and user.password and check_password_hash(user.password, password):
            login_user(user)
            print(f"DEBUG: User '{user.email}' logged in with role: '{user.role}'")
            if user.role == 'kitchen':
                session['current_view'] = 'kitchen'
                return redirect(url_for('admin.kitchen_orders'))
            elif user.role == 'staff':
                session['current_view'] = 'store_front'
                return redirect(url_for('admin.storefront_tables'))
            session['current_view'] = 'online_store'
            return redirect(url_for('admin.design_branding'))
        elif user and not user.is_active:
            flash('Account not activated. Please check your email for an invitation link.')
            return redirect(url_for('admin.landing'))
        
        flash('Please check your login details and try again.')
        return redirect(url_for('admin.landing'))
    return redirect(url_for('admin.landing'))
    
@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('mfa_verified_this_session', None)
    return redirect(url_for('admin.landing'))

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
        current_user.password_version += 1
        db.session.commit()
        flash('Password updated successfully.')
        if current_user.role == 'kitchen':
            return redirect(url_for('admin.kitchen_orders'))
        elif current_user.role == 'staff':
            return redirect(url_for('admin.storefront_tables'))
        return redirect(url_for('admin.design_branding'))
        
    return render_template('change_password.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    # If a logged-in user visits a registration or invitation link, log them out first.
    if current_user.is_authenticated:
        logout_user()
        flash('You have been logged out to complete this action.', 'info')
        return redirect(request.url) # Redirect to the same URL to get a clean, logged-out state

    if request.method == 'GET':
        token = request.args.get('token')
        if token:
            user = User.verify_token(token, salt='staff-invitation', expires_sec=604800)
            if not user:
                flash('This invitation has been revoked or expired.')
                return redirect(url_for('admin.landing'))
            
            if user.password:
                flash('You have already registered. Logging you in...')
                login_user(user)
                if user.role == 'kitchen':
                    return redirect(url_for('admin.kitchen_orders'))
                elif user.role == 'staff':
                    return redirect(url_for('admin.storefront_tables'))
                session['current_view'] = 'online_store'
                return redirect(url_for('admin.design_branding'))
            
            return render_template('welcome.html', email=user.email)

    if request.method == 'POST':
        token = request.form.get('token')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if token:
            user = User.verify_token(token, salt='staff-invitation', expires_sec=604800)
            if not user:
                flash('This invitation has been revoked or expired.')
                return redirect(url_for('admin.landing'))
            
            user.password = generate_password_hash(password)
            user.is_active = True
            db.session.add(user)
            db.session.commit()
            
            login_user(user)
            
            if user.role == 'kitchen':
                return redirect(url_for('admin.kitchen_orders'))
            elif user.role == 'staff':
                return redirect(url_for('admin.storefront_tables'))
            session['current_view'] = 'online_store'
            return redirect(url_for('admin.design_branding'))

        restaurant_name = request.form.get('restaurant_name')
        
        if User.query.filter_by(email=email).first():
            flash("Email already registered.")
            return redirect(url_for('auth.register'))

        new_restaurant = Restaurant(
            name=restaurant_name,
            slug=restaurant_name.lower().replace(" ", "-")
        )
        db.session.add(new_restaurant)
        db.session.flush()

        hashed_pw = generate_password_hash(password)
        new_admin = User(
            email=email,
            password=hashed_pw,
            role='admin',
            restaurant_id=new_restaurant.id,
            is_active=True
        )
        
        db.session.add(new_admin)
        db.session.commit()
        
        login_user(new_admin)
        
        session['current_view'] = 'online_store'
        flash("Account created! You can now log in.")
        return redirect(url_for('admin.design_branding'))

    return render_template('register.html')

@auth_bp.route('/accept-invitation/<token>', methods=['GET', 'POST'])
def accept_invitation(token):
    # If a logged-in user visits an invitation link, log them out first.
    if current_user.is_authenticated:
        logout_user()
        flash('You have been logged out to accept the invitation.', 'info')
        return redirect(url_for('auth.accept_invitation', token=token))

    user = User.verify_token(token, salt='staff-invitation', expires_sec=604800) # 7 days
    if not user:
        flash('The invitation link is invalid or has expired.')
        return redirect(url_for('admin.landing'))

    if request.method == 'POST':
        password = request.form.get('password')
        user.password = generate_password_hash(password)
        user.is_active = True
        db.session.commit()
        flash('Your account has been activated! You can now log in.')
        return redirect(url_for('auth.login'))

    return render_template('accept_invitation.html', token=token, user=user)

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        if user:
            user.password_version += 1
            db.session.commit()
            token = user.get_token(salt='password-reset')
            send_email(
                user.email,
                'Reset Your Password',
                'email/reset_password',
                user=user,
                token=token
            )
            flash('A password reset link has been sent to your email.')
            return redirect(url_for('admin.landing'))
        else:
            flash('Email address not found.')
    return render_template('forgot_password.html')

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.verify_token(token, salt='password-reset')
    if not user:
        flash('The password reset link is invalid or has expired.')
        return redirect(url_for('admin.landing'))

    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html', token=token, user=user)

        user.password = generate_password_hash(password)
        user.password_version += 1
        db.session.commit()
        flash('Your password has been updated! You can now log in.')
        return redirect(url_for('admin.landing'))

    return render_template('reset_password.html', token=token, user=user)

@auth_bp.route('/verify-mfa', methods=['GET', 'POST'])
def verify_mfa():
    if 'mfa_code' not in session:
        return redirect(url_for('admin.landing'))

    # Check for timeout (5 minutes)
    mfa_timestamp = session.get('mfa_timestamp', 0)
    if (datetime.utcnow().timestamp() - mfa_timestamp) > 300:
        session.pop('mfa_code', None)
        session.pop('mfa_timestamp', None)
        flash("Your verification code has expired. Please log in again.", "warning")
        return redirect(url_for('admin.landing'))

    if request.method == 'POST':
        submitted_code = request.form.get('mfa_code')
        if submitted_code == session.get('mfa_code'):
            if current_user.is_authenticated and current_user.is_superadmin:
                session['mfa_verified_this_session'] = True
                session.pop('mfa_code', None)
                session.pop('mfa_timestamp', None)
                
                flash("Successfully verified. Welcome!", "success")
                return redirect(url_for('sysadmin.dashboard'))
        else:
            flash("Invalid verification code.", "danger")
    
    return render_template('sysadmin_mfa_verify.html')