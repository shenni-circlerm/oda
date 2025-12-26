from functools import wraps
from flask import Blueprint, abort, request, redirect, url_for, render_template, flash, current_app, send_file
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
import os
from io import BytesIO
from sqlalchemy.orm.attributes import flag_modified

from project.models import User, Restaurant, Order, MenuItem, Table, Category
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
            return redirect(url_for('admin.register_restaurant'))

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
        return redirect(url_for('admin.manage_users'))

    new_user = User(
        email=email,
        password=generate_password_hash("temporary123"),
        role=role,
        restaurant_id=current_user.restaurant_id
    )
    db.session.add(new_user)
    db.session.commit()
    flash(f"New {role} added successfully!")
    return redirect(url_for('admin.manage_users'))

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
    
    file = request.files.get('image')
    if file and file.filename != '':
        new_item.image_data = file.read()
        new_item.image_mimetype = file.mimetype

    db.session.add(new_item)
    db.session.commit()
    flash("Item added successfully!")
    return redirect(url_for('admin.manage_menu'))

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
            item.image_data = file.read()
            item.image_mimetype = file.mimetype

        db.session.commit()
        flash("Menu item updated!")
        return redirect(url_for('admin.manage_menu'))

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

@admin_bp.route('/menu/image/<int:item_id>')
def serve_menu_image(item_id):
    item = MenuItem.query.get_or_404(item_id)
    if item.image_data:
        return send_file(
            BytesIO(item.image_data),
            mimetype=item.image_mimetype or 'image/jpeg'
        )
    return redirect(url_for('static', filename='img/placeholder.png'))

@admin_bp.route('/restaurant/image/<int:restaurant_id>/<string:image_type>')
def serve_restaurant_image(restaurant_id, image_type):
    restaurant = Restaurant.query.get_or_404(restaurant_id)
    data = None
    mimetype = None
    
    if image_type == 'logo':
        data = restaurant.logo_data
        mimetype = restaurant.logo_mimetype
    elif image_type == 'banner':
        data = restaurant.banner_data
        mimetype = restaurant.banner_mimetype
        
    if data:
        return send_file(BytesIO(data), mimetype=mimetype)
    return redirect(url_for('static', filename='img/placeholder.png'))

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

@admin_bp.route('/admin/categories', methods=['GET', 'POST'])
@login_required
def categories():
    if request.method == 'POST':
        name = request.form.get('name')
        if name:
            new_category = Category(name=name, restaurant_id=current_user.restaurant_id)
            db.session.add(new_category)
            db.session.commit()
            flash('Category added successfully.')
        return redirect(url_for('admin.categories'))
        
    categories = Category.query.filter_by(restaurant_id=current_user.restaurant_id).all()
    return render_template('categories.html', categories=categories)

@admin_bp.route('/admin/categories/edit/<int:category_id>', methods=['POST'])
@login_required
def edit_category(category_id):
    category = Category.query.filter_by(id=category_id, restaurant_id=current_user.restaurant_id).first_or_404()
    name = request.form.get('name')
    if name:
        category.name = name
        db.session.commit()
        flash('Category updated.')
    return redirect(url_for('admin.categories'))

@admin_bp.route('/admin/categories/delete/<int:category_id>', methods=['POST'])
@login_required
def delete_category(category_id):
    category = Category.query.filter_by(id=category_id, restaurant_id=current_user.restaurant_id).first_or_404()
    # Optional: Check if items exist before deleting, or set them to null
    # For now, we'll just delete the category. Items will have category_id set to NULL automatically if not cascaded, 
    # or we should handle it. SQLAlchemy default is usually SET NULL or RESTRICT depending on config.
    db.session.delete(category)
    db.session.commit()
    flash('Category deleted.')
    return redirect(url_for('admin.categories'))

@admin_bp.route('/admin/availability')
@login_required
def availability():
    return render_template('base.html', content="Manage Availability - Coming Soon")

@admin_bp.route('/admin/branding', methods=['GET', 'POST'])
@login_required
def branding():
    restaurant = db.session.get(Restaurant, current_user.restaurant_id)
    
    if request.method == 'POST':
        restaurant.name = request.form.get('name')
        restaurant.tagline = request.form.get('tagline')
        restaurant.brand_color = request.form.get('brand_color')
        
        logo = request.files.get('logo')
        if logo and logo.filename != '':
            restaurant.logo_data = logo.read()
            restaurant.logo_mimetype = logo.mimetype
            
        banner = request.files.get('banner')
        if banner and banner.filename != '':
            restaurant.banner_data = banner.read()
            restaurant.banner_mimetype = banner.mimetype
            
        db.session.commit()
        flash('Branding updated successfully.')
        return redirect(url_for('admin.branding'))
        
    return render_template('branding.html', restaurant=restaurant)

@admin_bp.route('/admin/menu-design', methods=['GET', 'POST'])
@login_required
def menu_design():
    restaurant = db.session.get(Restaurant, current_user.restaurant_id)
    
    # Default config structure
    default_config = {
        'welcome': {
            'label': 'Welcome', 'enabled': True,
            'elements': [
                {'key': 'restaurant_name', 'label': 'Restaurant Name', 'type': 'checkbox', 'value': True},
                {'key': 'table_number', 'label': 'Table Number', 'type': 'checkbox', 'value': True},
                {'key': 'start_label', 'label': 'Start Button Text', 'type': 'text', 'value': 'Start Ordering'}
            ]
        },
        'menu': {
            'label': 'Menu', 'enabled': True,
            'elements': [
                {'key': 'categories', 'label': 'Show Categories', 'type': 'checkbox', 'value': True},
                {'key': 'items', 'label': 'Show Items', 'type': 'checkbox', 'value': True},
                {'key': 'add_cart_label', 'label': 'Add to Cart Text', 'type': 'text', 'value': 'Add'}
            ]
        },
        'cart': {
            'label': 'Cart / Review', 'enabled': True,
            'elements': [
                {'key': 'show_qty', 'label': 'Show Quantity Controls', 'type': 'checkbox', 'value': True},
                {'key': 'allow_remove', 'label': 'Allow Remove Item', 'type': 'checkbox', 'value': True},
                {'key': 'total_label', 'label': 'Total Label', 'type': 'text', 'value': 'Total'}
            ]
        },
        'checkout': {
            'label': 'Checkout', 'enabled': True,
            'elements': [
                {'key': 'confirm_table', 'label': 'Confirm Table Number', 'type': 'checkbox', 'value': True},
                {'key': 'allow_notes', 'label': 'Allow Notes', 'type': 'checkbox', 'value': True},
                {'key': 'place_order_label', 'label': 'Place Order Text', 'type': 'text', 'value': 'Place Order'}
            ]
        },
        'thank_you': {
            'label': 'Thank You', 'enabled': True,
            'elements': [
                {'key': 'message', 'label': 'Confirmation Message', 'type': 'text', 'value': 'Order Placed Successfully!'}
            ]
        },
        'status': {
            'label': 'Order Status', 'enabled': True,
            'elements': [
                {'key': 'live_status', 'label': 'Show Live Status', 'type': 'checkbox', 'value': True},
                {'key': 'order_number', 'label': 'Show Order Number', 'type': 'checkbox', 'value': True}
            ]
        }
    }
    
    # Merge existing config with defaults to ensure all keys exist
    current_config = restaurant.pages_config or {}
    config = default_config.copy()
    
    # Deep merge for values
    for page_key, page_data in config.items():
        if page_key in current_config:
            page_data['enabled'] = current_config[page_key].get('enabled', True)
            saved_elements = {e['key']: e['value'] for e in current_config[page_key].get('elements', [])}
            for element in page_data['elements']:
                if element['key'] in saved_elements:
                    element['value'] = saved_elements[element['key']]

    if request.method == 'POST':
        for page_key, page_data in config.items():
            page_data['enabled'] = request.form.get(f'{page_key}_enabled') == 'on'
            for element in page_data['elements']:
                form_key = f"{page_key}_{element['key']}"
                if element['type'] == 'checkbox':
                    element['value'] = request.form.get(form_key) == 'on'
                else:
                    element['value'] = request.form.get(form_key)
        
        restaurant.pages_config = config
        flag_modified(restaurant, "pages_config")
        db.session.commit()
        flash("Store design updated.")
        return redirect(url_for('admin.menu_design'))

    return render_template('menu_design.html', config=config)

@admin_bp.route('/admin/qr-design', methods=['GET', 'POST'])
@login_required
def qr_design():
    restaurant = db.session.get(Restaurant, current_user.restaurant_id)
    
    default_config = {
        'color': '000000',
        'bgcolor': 'FFFFFF'
    }
    
    current_config = restaurant.qr_config or {}
    config = {**default_config, **current_config}
    
    if request.method == 'POST':
        config['color'] = request.form.get('color', '#000000').lstrip('#')
        config['bgcolor'] = request.form.get('bgcolor', '#FFFFFF').lstrip('#')
        restaurant.qr_config = config
        flag_modified(restaurant, "qr_config")
        db.session.commit()
        flash("QR Design updated.")
        return redirect(url_for('admin.qr_design'))
        
    return render_template('qr_design.html', config=config)

@admin_bp.route('/admin/qr-codes', methods=['GET', 'POST'])
@login_required
def qr_codes():
    restaurant = db.session.get(Restaurant, current_user.restaurant_id)
    
    if request.method == 'POST':
        number = request.form.get('number')
        if number:
            existing = Table.query.filter_by(restaurant_id=current_user.restaurant_id, number=number).first()
            if existing:
                flash('Table number already exists.')
            else:
                new_table = Table(number=number, restaurant_id=current_user.restaurant_id)
                db.session.add(new_table)
                db.session.commit()
                flash('Table added.')
        return redirect(url_for('admin.qr_codes'))

    tables = Table.query.filter_by(restaurant_id=current_user.restaurant_id).all()
    # Sort numerically if possible, otherwise alphabetically
    tables.sort(key=lambda x: int(x.number) if x.number.isdigit() else x.number)
    
    return render_template('qr_codes.html', tables=tables, restaurant=restaurant)

@admin_bp.route('/admin/qr-codes/delete/<int:table_id>', methods=['POST'])
@login_required
def delete_table(table_id):
    table = Table.query.filter_by(id=table_id, restaurant_id=current_user.restaurant_id).first_or_404()
    db.session.delete(table)
    db.session.commit()
    flash('Table deleted.')
    return redirect(url_for('admin.qr_codes'))