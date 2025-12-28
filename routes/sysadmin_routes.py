from functools import wraps
from flask import Blueprint, abort, render_template, request, redirect, url_for, flash, current_app, session
from flask_login import login_required, current_user, login_user, logout_user
from datetime import datetime
import random
import string
from project.models import Restaurant, User, Order
from extensions import db
from .email import send_email

sysadmin_bp = Blueprint('sysadmin', __name__, url_prefix='/sysadmin')

def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_superadmin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

@sysadmin_bp.route('/')
@login_required
@superadmin_required
def dashboard():
    # Initiate MFA if not already verified in this session
    if not session.get('mfa_verified_this_session'):
        mfa_code = ''.join(random.choices(string.digits, k=6))
        session['mfa_code'] = mfa_code
        session['mfa_timestamp'] = datetime.utcnow().timestamp()
        
        send_email(
            current_user.email,
            'Your Two-Factor Authentication Code',
            'email/sysadmin_mfa_code',
            mfa_code=mfa_code
        )
        flash("For security, please verify your identity. A code has been sent to your email.", "info")
        return redirect(url_for('auth.verify_mfa'))

    # If MFA is verified, show the dashboard
    restaurants = Restaurant.query.all()
    total_users = User.query.count()
    total_orders = Order.query.count()
    return render_template('sysadmin_dashboard.html', 
                           restaurants=restaurants, 
                           total_users=total_users,
                           total_orders=total_orders)

@sysadmin_bp.route('/impersonate/<int:user_id>')
@login_required
@superadmin_required
def impersonate_user(user_id):
    """Logs in as another user, storing the original superadmin ID."""
    if 'original_user_id' in session:
        flash("You are already impersonating a user. Stop the current session first.", "warning")
        return redirect(url_for('sysadmin.dashboard'))

    user_to_impersonate = User.query.get_or_404(user_id)
    session['original_user_id'] = current_user.id
    
    logout_user()
    login_user(user_to_impersonate)
    
    flash(f"You are now impersonating {user_to_impersonate.email}. To stop, log out.", "info")
    return redirect(url_for('admin.landing'))

@sysadmin_bp.route('/impersonate/stop')
@login_required
def stop_impersonation():
    """Logs out the impersonated user and logs the original superadmin back in."""
    original_user_id = session.pop('original_user_id', None)
    if not original_user_id:
        return redirect(url_for('admin.landing'))

    superadmin = User.query.get(original_user_id)
    logout_user()
    login_user(superadmin)
    session['mfa_verified_this_session'] = True # Re-verify MFA for the superadmin after impersonation
    flash("Impersonation stopped. You are now logged in as the system administrator.", "info")
    return redirect(url_for('sysadmin.dashboard'))