from functools import wraps
from flask import Blueprint, abort, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from project.models import Restaurant, User, Order, GlobalAnnouncement
from extensions import db

super_admin_bp = Blueprint('super_admin', __name__)

def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_superadmin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

@super_admin_bp.route('/sysadmin')
@login_required
@superadmin_required
def sysadmin_dashboard():
    restaurants = Restaurant.query.all()
    total_users = User.query.count()
    total_orders = Order.query.count()
    return render_template('sysadmin/dashboard.html', 
                           restaurants=restaurants, 
                           total_users=total_users,
                           total_orders=total_orders)

@super_admin_bp.route('/sysadmin/restaurant/<int:res_id>/impersonate')
@login_required
@superadmin_required
def impersonate_restaurant(res_id):
    pass

@super_admin_bp.route('/sysadmin/announcements', methods=['GET', 'POST'])
@login_required
@superadmin_required
def manage_announcements():
    if request.method == 'POST':
        new_announcement = GlobalAnnouncement(
            title=request.form.get('title'),
            message=request.form.get('message'),
            level=request.form.get('level')
        )
        db.session.add(new_announcement)
        db.session.commit()
        flash("Announcement published to all restaurants!")
        return redirect(url_for('manage_announcements'))

    announcements = GlobalAnnouncement.query.order_by(GlobalAnnouncement.created_at.desc()).all()
    return render_template('sysadmin/announcements.html', announcements=announcements)