from functools import wraps
from flask import Blueprint, abort, request, redirect, url_for, render_template, flash, current_app
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
import os

from project.models import User, Restaurant, Order, MenuItem, Table
from extensions import db, socketio

admin_bp = Blueprint('admin', __name__)

# UPLOAD_FOLDER is now accessed via current_app.config['UPLOAD_FOLDER']

@admin_bp.before_request
def restrict_bp_access():
    if not current_user.is_authenticated and request.endpoint != 'admin.register_restaurant':
        return redirect(url_for('customer.landing'))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            abort(403) # Forbidden
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/register', methods=['GET', 'POST'])
def register_restaurant():
    if request.method == 'POST':
        restaurant_name = request.form.get('restaurant_name')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(email=email).first():
            flash("Email already registered.")
            return redirect(url_for('register_restaurant'))

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
            restaurant_id=new_restaurant.id
        )
        
        db.session.add(new_admin)
        db.session.commit()
        
        flash("Account created! You can now log in.")
        return redirect(url_for('customer.landing'))

    return render_template('register.html')

@admin_bp.route('/admin/dashboard')
@login_required
def staff_dashboard():
    active_orders = Order.query.filter_by(
        restaurant_id=current_user.restaurant_id
    ).filter(Order.status.in_(['pending', 'preparing'])).all()
    return render_template('dashboard.html', orders=active_orders)

@admin_bp.route('/admin/users')
@login_required
@admin_required
def manage_users():
    staff = User.query.filter_by(restaurant_id=current_user.restaurant_id).all()
    return render_template('users.html', staff=staff)

@admin_bp.route('/admin/invite-staff', methods=['POST'])
@login_required
@admin_required
def invite_staff():
    email = request.form.get('email')
    role = request.form.get('role')
    
    if User.query.filter_by(email=email).first():
        flash("User already registered.")
        return redirect(url_for('manage_users'))

    new_user = User(
        email=email,
        password=generate_password_hash("temporary123"),
        role=role,
        restaurant_id=current_user.restaurant_id
    )
    db.session.add(new_user)
    db.session.commit()
    flash(f"New {role} added successfully!")
    return redirect(url_for('manage_users'))

@admin_bp.route('/admin/menu')
@login_required
def manage_menu():
    restaurant = db.session.get(Restaurant, current_user.restaurant_id)
    items = MenuItem.query.filter_by(restaurant_id=current_user.restaurant_id).all()
    return render_template('menu.html', items=items, restaurant=restaurant, table={'number': 'Admin'})

@admin_bp.route('/admin/menu/add', methods=['POST'])
@login_required
def add_menu_item():
    name = request.form.get('name')
    price = request.form.get('price')
    description = request.form.get('description')
    
    new_item = MenuItem(
        name=name,
        price=float(price),
        description=description,
        restaurant_id=current_user.restaurant_id
    )
    db.session.add(new_item)
    db.session.commit()
    flash("Item added successfully!")
    return redirect(url_for('manage_menu'))

@admin_bp.route('/admin/menu/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_menu_item(item_id):
    item = MenuItem.query.filter_by(id=item_id, restaurant_id=current_user.restaurant_id).first_or_404()

    if request.method == 'POST':
        item.name = request.form.get('name')
        item.price = float(request.form.get('price'))
        item.description = request.form.get('description')
        item.is_available = 'is_available' in request.form
        
        file = request.files.get('image')
        if file and file.filename != '':
            filename = secure_filename(f"{item.restaurant_id}_{item_id}_{file.filename}")
            file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            item.image_filename = filename

        db.session.commit()
        flash("Menu item updated!")
        return redirect(url_for('manage_menu'))

    return render_template('edit_item.html', item=item)

@admin_bp.route('/admin/order/<int:order_id>/update', methods=['POST'])
@login_required
def update_order_status(order_id):
    order = Order.query.filter_by(id=order_id, restaurant_id=current_user.restaurant_id).first_or_404()
    new_status = request.json.get('status')
    order.status = new_status
    db.session.commit()
    
    socketio.emit('status_change', {'order_id': order.id, 'new_status': new_status}, room=f"order_{order.id}")
    return {"message": "Updated"}, 200

@admin_bp.route('/admin/tables')
@login_required
def tables():
    return render_template('base.html', content="Tables View - Coming Soon")

@admin_bp.route('/admin/completed')
@login_required
def completed():
    return render_template('base.html', content="Completed Orders - Coming Soon")

@admin_bp.route('/admin/history')
@login_required
def history():
    return render_template('base.html', content="Order History - Coming Soon")

@admin_bp.route('/admin/payments')
@login_required
def payments():
    return render_template('base.html', content="Payments - Coming Soon")

@admin_bp.route('/admin/walkin')
@login_required
def walkin():
    return render_template('base.html', content="Walk-in Orders - Coming Soon")

@admin_bp.route('/admin/print-receipt')
@login_required
def print_receipt():
    return render_template('base.html', content="Print Receipt - Coming Soon")

@admin_bp.route('/admin/categories')
@login_required
def categories():
    return render_template('base.html', content="Manage Categories - Coming Soon")

@admin_bp.route('/admin/availability')
@login_required
def availability():
    return render_template('base.html', content="Manage Availability - Coming Soon")