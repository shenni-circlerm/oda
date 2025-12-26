from functools import wraps
from flask import Blueprint, abort, request, redirect, url_for, render_template, flash, current_app, send_file, session
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
import os
from io import BytesIO
from sqlalchemy.orm.attributes import flag_modified

from project.models import User, Restaurant, Order, MenuItem, Table, Category, OrderItem
from extensions import db, socketio

admin_bp = Blueprint('admin', __name__)

# UPLOAD_FOLDER is now accessed via current_app.config['UPLOAD_FOLDER']

@admin_bp.before_request
def restrict_bp_access():
    if not current_user.is_authenticated:
        return redirect(url_for('customer.landing'))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            abort(403) # Forbidden
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/admin/dashboard')
@login_required
def staff_dashboard():
    active_orders = Order.query.filter_by(
        restaurant_id=current_user.restaurant_id
    ).filter(Order.status.in_(['pending', 'preparing'])).all()
    return render_template('kitchen_dashboard.html', orders=active_orders)

@admin_bp.route('/admin/users')
@login_required
@admin_required
def manage_users():
    staff = User.query.filter_by(restaurant_id=current_user.restaurant_id).all()
    return render_template('office_staff.html', staff=staff)

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
    
    selected_item = None
    item_id = request.args.get('item_id')
    if item_id:
        selected_item = next((i for i in items if str(i.id) == str(item_id)), None)
    return render_template('menu_items.html', items=items, restaurant=restaurant, selected_item=selected_item)

@admin_bp.route('/admin/menu/add', methods=['POST'])
@login_required
def add_menu_item():
    if request.form.get('quick_add'):
        count = MenuItem.query.filter_by(restaurant_id=current_user.restaurant_id).count()
        new_item = MenuItem(
            name="New Item",
            sku=f"ITEM-{count + 1:03d}",
            price=0.0,
            restaurant_id=current_user.restaurant_id,
            is_available=False
        )
        db.session.add(new_item)
        db.session.commit()
        return redirect(url_for('admin.manage_menu', item_id=new_item.id))

    name = request.form.get('name')
    sku = request.form.get('sku')
    price = request.form.get('price')
    description = request.form.get('description')
    
    new_item = MenuItem(
        name=name,
        sku=sku,
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
        item.sku = request.form.get('sku')
        item.price = float(request.form.get('price'))
        item.description = request.form.get('description')
        item.is_available = 'is_available' in request.form
        
        file = request.files.get('image')
        if file and file.filename != '':
            item.image_data = file.read()
            item.image_mimetype = file.mimetype

        db.session.commit()
        flash("Menu item updated!")
        return redirect(url_for('admin.manage_menu', item_id=item.id))

    return redirect(url_for('admin.manage_menu', item_id=item_id))

@admin_bp.route('/admin/menu/delete/<int:item_id>', methods=['POST'])
@login_required
@admin_required
def delete_menu_item(item_id):
    item = MenuItem.query.filter_by(id=item_id, restaurant_id=current_user.restaurant_id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    flash("Menu item deleted.")
    return redirect(url_for('admin.manage_menu'))

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
    tables = Table.query.filter_by(restaurant_id=current_user.restaurant_id).all()
    tables.sort(key=lambda x: int(x.number) if x.number.isdigit() else x.number)
    
    active_orders = Order.query.filter_by(restaurant_id=current_user.restaurant_id).filter(Order.status.in_(['pending', 'preparing', 'ready'])).all()
    
    table_status = {}
    for order in active_orders:
        table_status[order.table_id] = order.status
        
    return render_template('kitchen_tables.html', tables=tables, table_status=table_status)

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
    return render_template('menu_categories.html', categories=categories)

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
    categories = Category.query.filter_by(restaurant_id=current_user.restaurant_id).all()
    uncategorized_items = MenuItem.query.filter_by(restaurant_id=current_user.restaurant_id, category_id=None).all()
    return render_template('menu_availability.html', categories=categories, uncategorized_items=uncategorized_items)

@admin_bp.route('/admin/availability/toggle/<int:item_id>', methods=['POST'])
@login_required
def toggle_availability(item_id):
    item = MenuItem.query.filter_by(id=item_id, restaurant_id=current_user.restaurant_id).first_or_404()
    item.is_available = not item.is_available
    db.session.commit()
    return {"success": True, "new_status": item.is_available}, 200

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
        
    return render_template('design_branding.html', restaurant=restaurant)

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

    return render_template('design_pages.html', config=config)

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
        
    return render_template('design_qr.html', config=config)

@admin_bp.route('/admin/storefront/tables', methods=['GET', 'POST'])
@login_required
def storefront_tables():
    restaurant = db.session.get(Restaurant, current_user.restaurant_id)
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create':
            number = request.form.get('number')
            floor = request.form.get('floor')
            seating = request.form.get('seating_capacity')
            notes = request.form.get('notes')
            
            if number:
                existing = Table.query.filter_by(restaurant_id=current_user.restaurant_id, number=number).first()
                if existing:
                    flash('Table number already exists.')
                else:
                    new_table = Table(
                        number=number, 
                        restaurant_id=current_user.restaurant_id,
                        floor=floor,
                        seating_capacity=int(seating) if seating else None,
                        notes=notes
                    )
                    
                    # Handle Reservation
                    res_name = request.form.get('res_name')
                    if res_name:
                        new_table.reservation_info = {
                            'name': res_name,
                            'date': request.form.get('res_date'),
                            'start': request.form.get('res_start'),
                            'end': request.form.get('res_end')
                        }
                        
                    db.session.add(new_table)
                    db.session.commit()
                    flash('Table added.')
            return redirect(url_for('admin.storefront_tables'))
            
        elif action == 'auto_create':
            tables = Table.query.filter_by(restaurant_id=current_user.restaurant_id).all()
            existing_numbers = [int(t.number) for t in tables if t.number.isdigit()]
            next_num = 1
            if existing_numbers:
                next_num = max(existing_numbers) + 1
            
            # Ensure uniqueness
            while Table.query.filter_by(restaurant_id=current_user.restaurant_id, number=str(next_num)).first():
                next_num += 1
                
            new_table = Table(number=str(next_num), restaurant_id=current_user.restaurant_id)
            db.session.add(new_table)
            db.session.commit()
            flash(f'Table {next_num} created.')
            return redirect(url_for('admin.storefront_tables', table_id=new_table.id))
            
        elif action == 'update':
            table_id = request.form.get('table_id')
            new_number = request.form.get('number')
            
            table = Table.query.filter_by(id=table_id, restaurant_id=current_user.restaurant_id).first()
            if table and new_number:
                table.number = new_number
                table.floor = request.form.get('floor')
                seating = request.form.get('seating_capacity')
                table.seating_capacity = int(seating) if seating else None
                table.status = request.form.get('status')
                table.notes = request.form.get('notes')
                
                # Handle Reservation Update
                res_name = request.form.get('res_name')
                if res_name:
                    table.reservation_info = {
                        'name': res_name,
                        'date': request.form.get('res_date'),
                        'start': request.form.get('res_start'),
                        'end': request.form.get('res_end')
                    }
                else:
                    table.reservation_info = {} # Clear reservation if name is empty

                db.session.commit()
                flash('Table updated.')
            return redirect(url_for('admin.storefront_tables', table_id=table_id))

    tables = Table.query.filter_by(restaurant_id=current_user.restaurant_id).all()
    # Sort numerically if possible, otherwise alphabetically
    tables.sort(key=lambda x: int(x.number) if x.number.isdigit() else x.number)

    # Fetch active orders for status display
    active_orders = Order.query.filter_by(restaurant_id=current_user.restaurant_id).filter(
        Order.status.in_(['pending', 'preparing', 'ready', 'served', 'paid'])
    ).all()
    
    table_data = {}
    for table in tables:
        # Find active order for this table
        order = next((o for o in active_orders if o.table_id == table.id), None)
        
        state = {
            'items_count': 0,
            'total': 0.0,
            'payment_status': '',
            'order_id': None
        }
        
        # Priority 1: Manual override for maintenance
        if table.status == 'maintenance':
            state['status'] = 'Not Available'
            state['color'] = 'dark'
        # Priority 2: Active Order exists
        elif order:
            state['order_id'] = order.id
            state['items_count'] = len(order.items)
            state['total'] = sum(item.menu_item.price for item in order.items)
            
            if order.status == 'paid':
                state['status'] = 'Paid'
                state['color'] = 'primary' # Blue
                state['payment_status'] = 'PAID'
            elif order.status == 'completed':
                state['status'] = 'Ready to clear'
                state['color'] = 'light' # White/Grey
                state['payment_status'] = 'PAID'
            else:
                state['status'] = 'Ordered'
                state['color'] = 'warning' # Yellow
                state['payment_status'] = 'UNPAID'
        # Priority 3: Manual override for occupied
        elif table.status == 'occupied':
            state['status'] = 'Occupied'
            state['color'] = 'secondary'
        # Priority 4: Reservation exists
        elif table.reservation_info and table.reservation_info.get('name'):
            state['status'] = 'Booked'
            state['color'] = 'info'
        # Priority 5: Default is available
        else:
            state['status'] = 'Available'
            state['color'] = 'success' # Green
        
        table_data[table.id] = state
    
    selected_table = None
    selected_id = request.args.get('table_id')
    if selected_id:
        selected_table = Table.query.filter_by(id=selected_id, restaurant_id=current_user.restaurant_id).first()
    
    # Default to first table if none selected and tables exist
    if not selected_table and tables:
        selected_table = tables[0]
    
    return render_template('storefront_tables.html', tables=tables, restaurant=restaurant, selected_table=selected_table, table_data=table_data)

@admin_bp.route('/admin/storefront/tables/delete/<int:table_id>', methods=['POST'])
@login_required
def delete_table(table_id):
    table = Table.query.filter_by(id=table_id, restaurant_id=current_user.restaurant_id).first_or_404()
    
    # Determine next table to highlight
    all_tables = Table.query.filter_by(restaurant_id=current_user.restaurant_id).all()
    all_tables.sort(key=lambda x: int(x.number) if x.number.isdigit() else x.number)
    
    next_id = None
    try:
        current_idx = next(i for i, t in enumerate(all_tables) if t.id == table_id)
        if current_idx + 1 < len(all_tables):
            next_id = all_tables[current_idx + 1].id
        elif len(all_tables) > 1:
            next_id = all_tables[0].id
    except StopIteration:
        pass

    # Store table data for Undo
    session['last_deleted_table'] = {
        'number': table.number,
        'restaurant_id': table.restaurant_id,
        'floor': table.floor,
        'seating_capacity': table.seating_capacity,
        'notes': table.notes,
        'reservation_info': table.reservation_info,
        'qr_identifier': table.qr_identifier
    }

    db.session.delete(table)
    db.session.commit()
    
    undo_url = url_for('admin.undo_delete_table')
    flash(f"Table {table.number} deleted. <a href='{undo_url}' class='fw-bold text-decoration-underline'>Undo</a>")
    
    if next_id:
        return redirect(url_for('admin.storefront_tables', table_id=next_id))
    return redirect(url_for('admin.storefront_tables'))

@admin_bp.route('/admin/storefront/tables/undo', methods=['GET'])
@login_required
def undo_delete_table():
    data = session.get('last_deleted_table')
    if data:
        # Check if table number is still available (simple check)
        existing = Table.query.filter_by(restaurant_id=current_user.restaurant_id, number=data['number']).first()
        if existing:
            flash(f"Cannot undo: Table {data['number']} already exists.")
            return redirect(url_for('admin.storefront_tables'))

        # Restore table
        table = Table(
            number=data['number'],
            restaurant_id=data['restaurant_id'],
            floor=data['floor'],
            seating_capacity=data['seating_capacity'],
            notes=data['notes'],
            reservation_info=data['reservation_info'],
            qr_identifier=data['qr_identifier']
        )
        db.session.add(table)
        db.session.commit()
        
        # Clear session data
        session.pop('last_deleted_table', None)
        
        flash(f"Table {table.number} restored.")
        return redirect(url_for('admin.storefront_tables', table_id=table.id))
    
    flash("Nothing to undo.")
    return redirect(url_for('admin.storefront_tables'))

@admin_bp.route('/admin/storefront/tables/<int:table_id>/status', methods=['POST'])
@login_required
def set_table_status(table_id):
    table = Table.query.filter_by(id=table_id, restaurant_id=current_user.restaurant_id).first_or_404()
    new_status = request.form.get('status')
    
    valid_statuses = ['available', 'occupied', 'maintenance']
    if new_status in valid_statuses:
        table.status = new_status
        db.session.commit()
    else:
        flash("Invalid status.", "danger")
        
    return redirect(url_for('admin.storefront_tables', table_id=table.id))

@admin_bp.route('/admin/storefront/orders', methods=['GET', 'POST'])
@login_required
def storefront_orders():
    restaurant = db.session.get(Restaurant, current_user.restaurant_id)
    
    if request.method == 'POST':
        action = request.form.get('action')
        order_id = request.form.get('order_id')
        
        if action == 'add_item':
            menu_item_id = request.form.get('menu_item_id')
            if order_id and menu_item_id:
                # Check if item already exists in order
                existing_item = OrderItem.query.filter_by(order_id=order_id, menu_item_id=menu_item_id).first()
                if existing_item:
                    existing_item.quantity += 1
                    flash('Item quantity updated.')
                else:
                    order = Order.query.filter_by(id=order_id, restaurant_id=restaurant.id).first()
                    if order:
                        new_item = OrderItem(order_id=order.id, menu_item_id=menu_item_id, quantity=1)
                        db.session.add(new_item)
                        flash('Item added to order.')
                db.session.commit()
        
        elif action == 'remove_item':
            item_id = request.form.get('item_id')
            if item_id:
                item = OrderItem.query.join(Order).filter(OrderItem.id == item_id, Order.restaurant_id == restaurant.id).first()
                if item:
                    db.session.delete(item)
                    db.session.commit()
                    flash('Item removed.')
        
        elif action == 'create_order':
            table_id = request.form.get('table_id')
            if table_id:
                existing_order = Order.query.filter_by(
                    table_id=table_id, 
                    restaurant_id=restaurant.id
                ).filter(
                    Order.status.in_(['pending', 'preparing', 'ready', 'served', 'paid'])
                ).first()

                if existing_order:
                    flash('Table already has an active order.')
                    return redirect(url_for('admin.storefront_orders', order_id=existing_order.id))

                new_order = Order(
                    table_id=table_id,
                    restaurant_id=restaurant.id,
                    status='pending'
                )
                db.session.add(new_order)
                db.session.commit()
                flash('New order created. You can now add items.')
                return redirect(url_for('admin.storefront_orders', order_id=new_order.id))
        
        elif action == 'move_table':
            new_table_id = request.form.get('new_table_id')
            if order_id and new_table_id:
                # Verify target table is empty (double check)
                target_has_order = Order.query.filter_by(
                    table_id=new_table_id, 
                    restaurant_id=restaurant.id
                ).filter(Order.status.in_(['pending', 'preparing', 'ready', 'served'])).first()
                
                if target_has_order:
                    flash('Target table is occupied. Please use "Merge" if you wish to combine bills.', 'warning')
                else:
                    order = Order.query.get(order_id)
                    order.table_id = new_table_id
                    db.session.commit()
                    flash(f'Order moved to Table {order.table.number}.')

        elif action == 'merge_orders':
            target_order_id = request.form.get('target_order_id')
            if order_id and target_order_id:
                source_order = Order.query.get(order_id)
                target_order = Order.query.get(target_order_id)
                
                if source_order and target_order:
                    # Move items from source to target
                    for item in source_order.items:
                        # Check if same item exists in target to merge quantities
                        existing_item = OrderItem.query.filter_by(order_id=target_order.id, menu_item_id=item.menu_item_id).first()
                        if existing_item:
                            existing_item.quantity += item.quantity
                            db.session.delete(item)
                        else:
                            item.order_id = target_order.id
                    
                    source_order.status = 'cancelled' # Effectively closes the source order
                    db.session.commit()
                    flash(f'Order #{source_order.id} merged into Order #{target_order.id}.')
                    return redirect(url_for('admin.storefront_orders', order_id=target_order.id))
        
        return redirect(url_for('admin.storefront_orders', order_id=order_id))

    orders = Order.query.filter_by(restaurant_id=restaurant.id).filter(
        Order.status.in_(['pending', 'preparing', 'ready', 'served', 'paid'])
    ).order_by(Order.created_at.desc()).all()
    
    menu_items = MenuItem.query.filter_by(restaurant_id=restaurant.id, is_available=True).all()
    
    # --- DEBUG PRINTS START ---
    print("\n--- Debugging Available Tables for New Order ---")
    all_restaurant_tables = Table.query.filter_by(restaurant_id=restaurant.id).all()
    print(f"Total tables for restaurant: {len(all_restaurant_tables)}")
    for t in all_restaurant_tables:
        print(f"  - Table ID: {t.id}, Number: {t.number}, Status: '{t.status}'")

    active_table_ids = [o.table_id for o in orders]
    print(f"Active table IDs from orders: {active_table_ids}")
    
    available_tables = Table.query.filter(
        Table.restaurant_id == restaurant.id,
        Table.id.notin_(active_table_ids), # Exclude tables with active orders
        Table.status != 'maintenance'      # Exclude tables under maintenance
    ).all()
    print(f"Final 'available_tables' count after filtering: {len(available_tables)}")
    print("------------------------------------------------\n")
    # --- DEBUG PRINTS END ---
    
    selected_order = None
    selected_id = request.args.get('order_id')
    if selected_id:
        selected_order = next((o for o in orders if str(o.id) == str(selected_id)), None)
    
    if not selected_order and orders:
        selected_order = orders[0]

    return render_template('storefront_orders.html', orders=orders, selected_order=selected_order, menu_items=menu_items, available_tables=available_tables)