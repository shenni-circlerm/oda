from functools import wraps
from flask import Blueprint, abort, request, redirect, url_for, render_template, flash, current_app, send_file, session, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
import os
from io import BytesIO
from datetime import datetime
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from project.models import User, Restaurant, Order, MenuItem, Table, Category, OrderItem, Menu, ModifierGroup, ModifierOption, Station
from extensions import db, socketio
from .email import send_email

admin_bp = Blueprint('admin', __name__)

# UPLOAD_FOLDER is now accessed via current_app.config['UPLOAD_FOLDER']

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            abort(403) # Forbidden
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/')
def landing():
    """Renders the main landing/login page for staff."""
    if current_user.is_authenticated:
        # Redirect to their dashboard if already logged in
        if current_user.role == 'kitchen':
            return redirect(url_for('admin.kitchen_orders'))
        elif current_user.role == 'staff':
            return redirect(url_for('admin.storefront_tables'))
        # Default for admin
        return redirect(url_for('admin.design_branding'))
    return render_template('landing.html')

@admin_bp.route('/kitchen/orders')
@login_required
def kitchen_orders():
    stations = Station.query.filter_by(restaurant_id=current_user.restaurant_id).order_by(Station.name).all()
    
    # Get all active order items that are not ready
    active_items = db.session.query(OrderItem).join(Order).filter(
        Order.restaurant_id == current_user.restaurant_id,
        Order.status.in_(['pending', 'preparing']),
        OrderItem.status != 'ready'
    ).order_by(OrderItem.created_at).all()

    # Group items by station
    station_items = {station.id: [] for station in stations}
    uncategorized_items = []

    for item in active_items:
        if item.menu_item.station_id:
            if item.menu_item.station_id in station_items:
                station_items[item.menu_item.station_id].append(item)
        else:
            uncategorized_items.append(item)

    return render_template('kitchen_orders.html', stations=stations, station_items=station_items, uncategorized_items=uncategorized_items, active_items=active_items)

@admin_bp.route('/office/users')
@login_required
@admin_required
def office_users():
    staff = User.query.filter_by(restaurant_id=current_user.restaurant_id).all()
    return render_template('office_staff.html', staff=staff)

@admin_bp.route('/office/invite-staff', methods=['POST'])
@login_required
@admin_required
def office_invite_staff():
    email = request.form.get('email')
    role = request.form.get('role')
    
    if User.query.filter_by(email=email).first():
        flash("User already registered.")
        return redirect(url_for('admin.office_users'))

    # Create inactive user without a password
    new_user = User(
        email=email,
        role=role,
        restaurant_id=current_user.restaurant_id,
        is_active=False
    )
    db.session.add(new_user)
    db.session.commit()

    # Send invitation email
    token = new_user.get_token(salt='staff-invitation', expires_sec=604800) # 7 days
    send_email(email, 'You are invited to join!', 'email/invite', user=new_user, token=token)

    flash(f"An invitation has been sent to {email}.")
    return redirect(url_for('admin.office_users'))

@admin_bp.route('/office/staff/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def office_delete_staff(user_id):
    user_to_delete = User.query.filter_by(id=user_id, restaurant_id=current_user.restaurant_id).first_or_404()

    # Prevent deleting oneself or the restaurant owner
    if user_to_delete.id == current_user.id:
        flash("You cannot delete yourself.", "danger")
        return redirect(url_for('admin.office_users'))

    # Store for undo
    session['last_deleted_staff'] = {
        'email': user_to_delete.email,
        'role': user_to_delete.role,
        'restaurant_id': user_to_delete.restaurant_id,
        'is_active': user_to_delete.is_active
    }

    db.session.delete(user_to_delete)
    db.session.commit()

    undo_url = url_for('admin.office_undo_delete_staff')
    flash(f"Staff member {user_to_delete.email} has been deleted. <a href='{undo_url}' class='fw-bold'>Undo</a>")
    return redirect(url_for('admin.office_users'))

@admin_bp.route('/office/staff/undo_delete', methods=['GET'])
@login_required
@admin_required
def office_undo_delete_staff():
    last_deleted = session.pop('last_deleted_staff', None)
    if last_deleted:
        restored_user = User(**last_deleted)
        db.session.add(restored_user)
        db.session.commit()
        flash(f"Staff member {last_deleted['email']} has been restored.")
    return redirect(url_for('admin.office_users'))

@admin_bp.route('/menu/menu')
@login_required
def menu_manage_menu():
    print(f"\n--- DEBUG: menu_manage_menu for user: {current_user.email} ---")
    restaurant = db.session.get(Restaurant, current_user.restaurant_id)
    print(f"DEBUG: Restaurant: {restaurant.name}")

    items = MenuItem.query.filter_by(restaurant_id=current_user.restaurant_id).all()
    print(f"DEBUG: Found {len(items)} total menu items.")
    for item in items:
        category_names = [c.name for c in item.categories]
        print(f"  - Item: '{item.name}' (ID: {item.id}), Available: {item.is_available}, Categories: {category_names}")

    categories = Category.query.filter_by(restaurant_id=current_user.restaurant_id).all()
    print(f"DEBUG: Found {len(categories)} total categories.")

    menus = Menu.query.filter_by(restaurant_id=current_user.restaurant_id).all()
    print(f"DEBUG: Found {len(menus)} total menus.")

    stations = Station.query.filter_by(restaurant_id=current_user.restaurant_id).all()
    print(f"DEBUG: Found {len(stations)} total stations.")
    
    selected_item = None
    item_id = request.args.get('item_id')
    print(f"DEBUG: Requested item_id from URL: {item_id}")
    if item_id:
        selected_item = next((i for i in items if str(i.id) == str(item_id)), None)
    
    if not selected_item and items:
        selected_item = items[0]

    print(f"DEBUG: Selected item for display: {selected_item.name if selected_item else 'None'}")
    return render_template('menu_items.html', items=items, restaurant=restaurant, selected_item=selected_item, categories=categories, menus=menus, stations=stations)

@admin_bp.route('/menu/menu/add', methods=['POST'])
@login_required
def menu_add_menu_item():
    if request.form.get('quick_add'):
        category_id = request.form.get('category_id')
        count = MenuItem.query.filter_by(restaurant_id=current_user.restaurant_id).count()
        new_item = MenuItem(
            name="New Item",
            sku=f"ITEM-{count + 1:03d}",
            price=0.0,
            restaurant_id=current_user.restaurant_id,
            is_available=True
        )
        
        if category_id:
            category = db.session.get(Category, category_id)
            if category:
                new_item.categories.append(category)
                
        db.session.add(new_item)
        db.session.commit()
        return redirect(url_for('admin.menu_manage_menu', item_id=new_item.id))

    name = request.form.get('name')
    sku = request.form.get('sku')
    price = request.form.get('price')
    compare_at_price = request.form.get('compare_at_price')
    description = request.form.get('description')
    
    new_item = MenuItem(
        name=name,
        sku=sku,
        price=float(price),
        compare_at_price=float(compare_at_price) if compare_at_price else None,
        description=description,
        restaurant_id=current_user.restaurant_id
    )
    
    category_ids = request.form.getlist('categories')
    for cat_id in category_ids:
        category = db.session.get(Category, cat_id)
        if category:
            new_item.categories.append(category)
    
    file = request.files.get('image')
    if file and file.filename != '':
        new_item.image_data = file.read()
        new_item.image_mimetype = file.mimetype

    db.session.add(new_item)
    db.session.commit()
    flash("Item added successfully!")
    return redirect(url_for('admin.menu_manage_menu'))

@admin_bp.route('/menu/menu/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def menu_edit_menu_item(item_id):
    item = MenuItem.query.filter_by(id=item_id, restaurant_id=current_user.restaurant_id).first_or_404()

    if request.method == 'POST':
        item.name = request.form.get('name')
        item.sku = request.form.get('sku')
        item.price = float(request.form.get('price'))
        compare_at_price = request.form.get('compare_at_price')
        item.compare_at_price = float(compare_at_price) if compare_at_price else None
        item.description = request.form.get('description')
        item.station_id = request.form.get('station_id') or None
        item.is_available = 'is_available' in request.form
        
        category_ids = request.form.getlist('categories')
        item.categories = []
        for cat_id in category_ids:
            category = db.session.get(Category, cat_id)
            if category:
                item.categories.append(category)
        
        file = request.files.get('image')
        if file and file.filename != '':
            item.image_data = file.read()
            item.image_mimetype = file.mimetype

        db.session.commit()
        flash("Menu item updated!")
        return redirect(url_for('admin.menu_manage_menu', item_id=item.id))

    return redirect(url_for('admin.menu_manage_menu', item_id=item_id))

@admin_bp.route('/menu/menu/delete/<int:item_id>', methods=['POST'])
@login_required
@admin_required
def menu_delete_menu_item(item_id):
    item = MenuItem.query.filter_by(id=item_id, restaurant_id=current_user.restaurant_id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    flash("Menu item deleted.")
    return redirect(url_for('admin.menu_manage_menu'))

@admin_bp.route('/menu/menu/modifier/group/add', methods=['POST'])
@login_required
def menu_add_modifier_group():
    item_id = request.form.get('item_id')
    name = request.form.get('name')
    selection_type = request.form.get('selection_type') # single, multiple
    is_required = request.form.get('is_required') == 'on'
    min_selection = request.form.get('min_selection')
    max_selection = request.form.get('max_selection')
    
    if item_id and name:
        group = ModifierGroup(
            name=name, 
            selection_type=selection_type, 
            is_required=is_required, 
            menu_item_id=item_id,
            min_selection=int(min_selection) if min_selection else 0,
            max_selection=int(max_selection) if max_selection else None
        )
        db.session.add(group)
        db.session.commit()
        flash("Modifier group added.")
        
    return redirect(url_for('admin.menu_manage_menu', item_id=item_id))

@admin_bp.route('/menu/menu/modifier/group/delete/<int:group_id>', methods=['POST'])
@login_required
def menu_delete_modifier_group(group_id):
    group = db.session.get(ModifierGroup, group_id)
    item_id = group.menu_item_id
    if group:
        db.session.delete(group)
        db.session.commit()
        flash("Modifier group deleted.")
    return redirect(url_for('admin.menu_manage_menu', item_id=item_id))

@admin_bp.route('/menu/menu/modifier/option/add', methods=['POST'])
@login_required
def menu_add_modifier_option():
    group_id = request.form.get('group_id')
    name = request.form.get('name')
    price = request.form.get('price', 0.0)
    
    if group_id and name:
        group = db.session.get(ModifierGroup, group_id)
        option = ModifierOption(
            name=name,
            price_override=float(price) if price else 0.0,
            group_id=group_id
        )
        db.session.add(option)
        db.session.commit()
        flash("Option added.")
        return redirect(url_for('admin.menu_manage_menu', item_id=group.menu_item_id))
    return redirect(url_for('admin.menu_manage_menu'))

@admin_bp.route('/menu/menu/modifier/option/delete/<int:option_id>', methods=['POST'])
@login_required
def menu_delete_modifier_option(option_id):
    option = db.session.get(ModifierOption, option_id)
    if option:
        group = option.group
        db.session.delete(option)
        db.session.commit()
        flash("Option deleted.")
        return redirect(url_for('admin.menu_manage_menu', item_id=group.menu_item_id))
    return redirect(url_for('admin.menu_manage_menu'))

@admin_bp.route('/storefront/order-item/status/<int:item_id>', methods=['POST'])
@login_required
def storefront_update_order_item_status(item_id):
    item = db.session.get(OrderItem, item_id)
    if item and item.order.restaurant_id == current_user.restaurant_id:
        new_status = request.json.get('status')
        if new_status in ['pending', 'preparing', 'ready']:
            item.status = new_status
            db.session.commit()
            
            order = item.order
            all_ready = all(i.status == 'ready' for i in order.items)
            if all_ready and order.status != 'ready':
                order.status = 'ready'
                db.session.commit()
                socketio.emit('status_change', {'order_id': order.id, 'new_status': 'ready'}, room=f"order_{order.id}")

            return jsonify({'success': True, 'item_id': item.id, 'new_status': new_status})
    return jsonify({'success': False}), 403

@admin_bp.route('/kitchen/item/<int:item_id>/assign-station', methods=['POST'])
@login_required
def kitchen_assign_item_to_station(item_id):
    menu_item = db.session.get(MenuItem, item_id)
    station_id = request.json.get('station_id')

    if menu_item and menu_item.restaurant_id == current_user.restaurant_id:
        # 'uncategorized' is a frontend concept, so None in backend
        menu_item.station_id = station_id if station_id != 'uncategorized' else None
        db.session.commit()
        return jsonify({'success': True, 'message': f'"{menu_item.name}" assigned to new station.'})

    return jsonify({'success': False, 'message': 'Item or station not found.'}), 404

@admin_bp.route('/kitchen/order/<int:order_id>/update', methods=['POST'])
@login_required
def kitchen_update_order_status(order_id):
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

@admin_bp.route('/kitchen/tables')
@login_required
def kitchen_tables():
    tables = Table.query.filter_by(restaurant_id=current_user.restaurant_id).all()
    tables.sort(key=lambda x: int(x.number) if x.number.isdigit() else x.number)

    active_orders = Order.query.filter_by(
        restaurant_id=current_user.restaurant_id
    ).filter(
        Order.status.in_(['pending', 'preparing', 'ready'])
    ).options(
        selectinload(Order.items)
    ).all()

    table_status = {}
    for table in tables:
        order = next((o for o in active_orders if o.table_id == table.id), None)
        if order:
            total_items = len(order.items)
            item_counts = {
                'total': total_items,
                'pending': sum(1 for item in order.items if item.status == 'pending'),
                'preparing': sum(1 for item in order.items if item.status == 'preparing'),
                'ready': sum(1 for item in order.items if item.status == 'ready')
            } if total_items > 0 else None
            table_status[table.id] = {
                'status': order.status,
                'created_at': order.created_at.isoformat() + "Z", # ISO format for JS
                'item_counts': item_counts
            }
        else:
            table_status[table.id] = { 'status': 'available', 'created_at': None, 'item_counts': None }

    return render_template('kitchen_tables.html', tables=tables, table_status=table_status)

@admin_bp.route('/kitchen/stations', methods=['GET', 'POST'])
@login_required
def kitchen_manage_stations():
    if request.method == 'POST':
        name = request.form.get('name')
        if name:
            new_station = Station(name=name, restaurant_id=current_user.restaurant_id)
            db.session.add(new_station)
            db.session.commit()
            flash('Station created.')
        return redirect(url_for('admin.kitchen_manage_stations'))
    
    stations = Station.query.filter_by(restaurant_id=current_user.restaurant_id).all()
    return render_template('kitchen_stations.html', stations=stations)

@admin_bp.route('/kitchen/stations/delete/<int:station_id>', methods=['POST'])
@login_required
def kitchen_delete_station(station_id):
    station = Station.query.filter_by(id=station_id, restaurant_id=current_user.restaurant_id).first_or_404()
    db.session.delete(station)
    db.session.commit()
    flash('Station deleted.')
    return redirect(url_for('admin.kitchen_manage_stations'))

@admin_bp.route('/office/completed')
@login_required
def completed():
    return render_template('base.html', content="Completed Orders - Coming Soon")

@admin_bp.route('/office/history')
@login_required
def history():
    return render_template('office_history.html')

@admin_bp.route('/office/payments')
@login_required
def payments():
    return render_template('office_payments.html')

@admin_bp.route('/storefront/walkin')
@login_required
def storefront_walkin():
    return render_template('base.html', content="Walk-in Orders - Coming Soon")

@admin_bp.route('/storefront/print-receipt')
@login_required
def storefront_print_receipt():
    return render_template('base.html', content="Print Receipt - Coming Soon")

@admin_bp.route('/menu/menus', methods=['GET', 'POST'])
@login_required
def menu_menus():
    if request.method == 'POST':
        menu_id = request.form.get('menu_id')
        name = request.form.get('name')
        description = request.form.get('description')
        
        # Parse Time and Date rules
        start_time_str = request.form.get('start_time')
        end_time_str = request.form.get('end_time')
        active_days_list = request.form.getlist('active_days') # Returns list like ['0', '1', '4']
        active_days_str = ",".join(active_days_list)
        
        start_time = datetime.strptime(start_time_str, '%H:%M').time() if start_time_str else None
        end_time = datetime.strptime(end_time_str, '%H:%M').time() if end_time_str else None

        if menu_id:
            # Update existing menu
            menu = Menu.query.filter_by(id=menu_id, restaurant_id=current_user.restaurant_id).first_or_404()
            menu.name = name
            menu.description = description
            menu.start_time = start_time
            menu.end_time = end_time
            menu.active_days = active_days_str
            menu.is_active = 'is_active' in request.form

            # Process categories
            category_ids = request.form.getlist('category_ids')
            menu.categories.clear()
            for cat_id in category_ids:
                category = db.session.get(Category, int(cat_id))
                if category and category.restaurant_id == current_user.restaurant_id:
                    menu.categories.append(category)

            db.session.commit()
            flash('Menu updated.')
            return redirect(url_for('admin.menu_menus', menu_id=menu.id))
        elif name:
            # Create new menu
            new_menu = Menu(name=name, description=description, restaurant_id=current_user.restaurant_id, start_time=start_time, end_time=end_time, active_days=active_days_str)
            db.session.add(new_menu)
            db.session.commit()
            flash('Menu created successfully.')
            return redirect(url_for('admin.menu_menus', menu_id=new_menu.id))
        
    menus = Menu.query.filter_by(restaurant_id=current_user.restaurant_id).all()
    categories = Category.query.filter_by(restaurant_id=current_user.restaurant_id).all()
    
    selected_menu = None
    menu_id = request.args.get('menu_id')
    if menu_id:
        selected_menu = next((m for m in menus if str(m.id) == str(menu_id)), None)
        
    if not selected_menu and menus:
        selected_menu = menus[0]
        
    return render_template('menus.html', menus=menus, selected_menu=selected_menu, categories=categories)

@admin_bp.route('/menu/menus/delete/<int:menu_id>', methods=['POST'])
@login_required
def menu_delete_menu(menu_id):
    menu = Menu.query.filter_by(id=menu_id, restaurant_id=current_user.restaurant_id).first_or_404()
    db.session.delete(menu)
    db.session.commit()
    flash('Menu deleted.')
    return redirect(url_for('admin.menu_menus'))

@admin_bp.route('/menu/menus/remove_category/<int:menu_id>/<int:category_id>', methods=['POST'])
@login_required
def menu_remove_category_from_menu(menu_id, category_id):
    menu = Menu.query.filter_by(id=menu_id, restaurant_id=current_user.restaurant_id).first_or_404()
    category = Category.query.filter_by(id=category_id, restaurant_id=current_user.restaurant_id).first_or_404()
    
    if category in menu.categories:
        menu.categories.remove(category)
        db.session.commit()
        flash(f'Category "{category.name}" removed from menu "{menu.name}".')
        
    return redirect(url_for('admin.menu_menus', menu_id=menu_id))

@admin_bp.route('/menu/menus/add_category/<int:menu_id>', methods=['POST'])
@login_required
def menu_add_category_to_menu(menu_id):
    menu = Menu.query.filter_by(id=menu_id, restaurant_id=current_user.restaurant_id).first_or_404()
    category_id = request.form.get('category_id')
    if category_id:
        category = Category.query.filter_by(id=category_id, restaurant_id=current_user.restaurant_id).first()
        if category and category not in menu.categories:
            menu.categories.append(category)
            db.session.commit()
            flash(f'Category "{category.name}" added to menu.')
    return redirect(url_for('admin.menu_menus', menu_id=menu_id))

@admin_bp.route('/menu/menus/toggle/<int:menu_id>', methods=['POST'])
@login_required
def menu_toggle_status(menu_id):
    menu = Menu.query.filter_by(id=menu_id, restaurant_id=current_user.restaurant_id).first_or_404()
    menu.is_active = not menu.is_active
    db.session.commit()
    flash(f'Menu {"enabled" if menu.is_active else "disabled"}.')
    return redirect(url_for('admin.menu_menus', menu_id=menu_id))

@admin_bp.route('/menu/categories', methods=['GET', 'POST'])
@login_required
def menu_categories():
    if request.method == 'POST':
        name = request.form.get('name')
        menu_ids = request.form.getlist('menu_ids')
        is_ajax = request.form.get('is_ajax') == '1'

        if name:
            try:
                # Check for duplicates
                existing = Category.query.filter_by(name=name, restaurant_id=current_user.restaurant_id).first()
                if existing:
                    if is_ajax:
                        return jsonify({'success': False, 'message': 'A category with this name already exists.'}), 400
                    else:
                        flash('A category with this name already exists.', 'danger')
                        return redirect(request.referrer or url_for('admin.menu_categories'))

                new_category = Category(name=name, restaurant_id=current_user.restaurant_id)
                for m_id in menu_ids:
                    menu = db.session.get(Menu, m_id)
                    if menu:
                        new_category.menus.append(menu)
                db.session.add(new_category)
                db.session.commit()

                if is_ajax:
                    return jsonify({
                        'success': True, 
                        'message': 'Category added successfully.',
                        'category': {
                            'id': new_category.id,
                            'name': new_category.name
                        }
                    })

                flash('Category added successfully.')
                
                # If returning to another page (e.g. item edit), honor that
                return_to = request.form.get('return_to')
                if return_to:
                    return redirect(return_to)

                # Otherwise go to the new category in the list
                return redirect(url_for('admin.menu_categories', category_id=new_category.id))
            except Exception as e:
                db.session.rollback()
                if is_ajax:
                    return jsonify({'success': False, 'message': str(e)}), 500
                flash(f'Error adding category: {str(e)}', 'danger')
                return redirect(url_for('admin.menu_categories'))
        
        if is_ajax:
            return jsonify({'success': False, 'message': 'Category name is required.'}), 400

        return_to = request.form.get('return_to')
        if return_to:
            return redirect(return_to)
            
        return redirect(url_for('admin.menu_categories'))
        
    categories = Category.query.filter_by(restaurant_id=current_user.restaurant_id).all()
    menus = Menu.query.filter_by(restaurant_id=current_user.restaurant_id).all()
    all_items = MenuItem.query.filter_by(restaurant_id=current_user.restaurant_id).order_by(MenuItem.name).all()
    
    selected_category = None
    category_id = request.args.get('category_id')
    if category_id:
        selected_category = next((c for c in categories if str(c.id) == str(category_id)), None)
        
    if not selected_category and categories:
        selected_category = categories[0]
        
    return render_template('menu_categories.html', categories=categories, menus=menus, selected_category=selected_category, all_items=all_items)

@admin_bp.route('/menu/categories/edit/<int:category_id>', methods=['POST'])
@login_required
def menu_edit_category(category_id):
    category = Category.query.filter_by(id=category_id, restaurant_id=current_user.restaurant_id).first_or_404()
    name = request.form.get('name')
    menu_ids = request.form.getlist('menu_ids')
    if name:
        category.name = name
        category.menus = [] # Clear existing associations
        for m_id in menu_ids:
            menu = db.session.get(Menu, m_id)
            if menu:
                category.menus.append(menu)
        db.session.commit()
        flash('Category updated.')
    return redirect(url_for('admin.menu_categories', category_id=category.id))

@admin_bp.route('/menu/categories/add_item', methods=['POST'])
@login_required
def menu_add_item_to_category():
    category_id = request.form.get('category_id')
    item_name = request.form.get('item_name')
    
    if not category_id or not item_name:
        return redirect(url_for('admin.menu_categories'))

    category = Category.query.filter_by(id=category_id, restaurant_id=current_user.restaurant_id).first_or_404()
    
    # Check if item exists
    item = MenuItem.query.filter_by(name=item_name, restaurant_id=current_user.restaurant_id).first()
    
    if not item:
        # Create new item
        count = MenuItem.query.filter_by(restaurant_id=current_user.restaurant_id).count()
        item = MenuItem(
            name=item_name,
            sku=f"ITEM-{count + 1:03d}",
            price=0.0,
            restaurant_id=current_user.restaurant_id,
            is_available=True
        )
        db.session.add(item)
    
    if category not in item.categories:
        item.categories.append(category)
        db.session.commit()
        flash(f'Item "{item.name}" added to category.')
    
    return redirect(url_for('admin.menu_categories', category_id=category_id))

@admin_bp.route('/menu/categories/remove_item/<int:category_id>/<int:item_id>', methods=['POST'])
@login_required
def menu_remove_item_from_category(category_id, item_id):
    category = Category.query.filter_by(id=category_id, restaurant_id=current_user.restaurant_id).first_or_404()
    item = MenuItem.query.filter_by(id=item_id, restaurant_id=current_user.restaurant_id).first_or_404()
    
    if category in item.categories:
        item.categories.remove(category)
        db.session.commit()
        
        # Store for undo
        session['last_removed_item_category'] = {
            'item_id': item.id,
            'category_id': category.id
        }
        
        undo_url = url_for('admin.menu_undo_remove_item_from_category')
        flash(f'Item removed from category. <a href="{undo_url}" class="fw-bold text-decoration-underline">Undo</a>')
        
    return redirect(url_for('admin.menu_categories', category_id=category_id))

@admin_bp.route('/menu/categories/undo_remove_item', methods=['GET'])
@login_required
def menu_undo_remove_item_from_category():
    data = session.get('last_removed_item_category')
    if data:
        item = MenuItem.query.filter_by(id=data['item_id'], restaurant_id=current_user.restaurant_id).first()
        category = Category.query.filter_by(id=data['category_id'], restaurant_id=current_user.restaurant_id).first()
        
        if item and category and category not in item.categories:
            item.categories.append(category)
            db.session.commit()
            flash('Item restored to category.')
            session.pop('last_removed_item_category', None)
            return redirect(url_for('admin.menu_categories', category_id=category.id))
            
    flash('Nothing to undo.')
    return redirect(url_for('admin.menu_categories'))

@admin_bp.route('/menu/categories/delete/<int:category_id>', methods=['POST'])
@login_required
def menu_delete_category(category_id):
    category = Category.query.filter_by(id=category_id, restaurant_id=current_user.restaurant_id).first_or_404()
    # Optional: Check if items exist before deleting, or set them to null
    # For now, we'll just delete the category. Items will have category_id set to NULL automatically if not cascaded, 
    # or we should handle it. SQLAlchemy default is usually SET NULL or RESTRICT depending on config.
    db.session.delete(category)
    db.session.commit()
    flash('Category deleted.')
    return redirect(url_for('admin.menu_categories'))

@admin_bp.route('/admin/categories/toggle/<int:category_id>', methods=['POST'])
@login_required
def toggle_category_status(category_id):
    category = Category.query.filter_by(id=category_id, restaurant_id=current_user.restaurant_id).first_or_404()
    category.is_active = not category.is_active
    db.session.commit()
    return {"success": True, "new_status": category.is_active}, 200

@admin_bp.route('/menu/availability')
@login_required
def menu_availability():
    categories = Category.query.filter_by(restaurant_id=current_user.restaurant_id).all()
    uncategorized_items = MenuItem.query.filter_by(restaurant_id=current_user.restaurant_id).filter(~MenuItem.categories.any()).all()
    return render_template('menu_availability.html', categories=categories, uncategorized_items=uncategorized_items)

@admin_bp.route('/menu/availability/toggle/<int:item_id>', methods=['POST'])
@login_required
def menu_toggle_availability(item_id):
    item = MenuItem.query.filter_by(id=item_id, restaurant_id=current_user.restaurant_id).first_or_404()
    item.is_available = not item.is_available
    db.session.commit()
    return {"success": True, "new_status": item.is_available}, 200

@admin_bp.route('/design/branding', methods=['GET', 'POST'])
@login_required
def design_branding():
    restaurant = db.session.get(Restaurant, current_user.restaurant_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        if name:
            restaurant.name = name
        restaurant.tagline = request.form.get('tagline')
        
        brand_color = request.form.get('primary_color')
        if brand_color:
            restaurant.brand_color = brand_color
        
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
        return redirect(url_for('admin.design_branding'))
        
    return render_template('design_branding.html', restaurant=restaurant)

@admin_bp.route('/design/menu', methods=['GET', 'POST'])
@login_required
def design_menu_design():
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
        return redirect(url_for('admin.design_menu_design'))

    return render_template('design_pages.html', config=config, restaurant=restaurant)

@admin_bp.route('/design/qr-design', methods=['GET', 'POST'])
@login_required
def design_qr_design():
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
        return redirect(url_for('admin.design_qr_design'))
        
    return render_template('design_qr.html', config=config)

@admin_bp.route('/storefront/tables', methods=['GET', 'POST'])
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
        
        state = {}
        
        # Determine table status based on a priority system
        if table.status == 'maintenance':
            state['status'] = 'Not Available'
            state['color'] = 'dark'
        elif table.reservation_info and table.reservation_info.get('name'):
            state['status'] = 'Not Available'
            state['color'] = 'info' # Reserved
        elif order:
            if order.status in ['paid', 'completed']:
                state['status'] = 'Not Available' # Needs clearing
                state['color'] = 'primary'
            else:
                state['status'] = 'Occupied'
                state['color'] = 'warning'
        elif table.status == 'occupied':
            state['status'] = 'Occupied'
            state['color'] = 'secondary'
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

@admin_bp.route('/storefront/tables/delete/<int:table_id>', methods=['POST'])
@login_required
def storefront_delete_table(table_id):
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
    
    undo_url = url_for('admin.storefront_undo_delete_table')
    flash(f"Table {table.number} deleted. <a href='{undo_url}' class='fw-bold text-decoration-underline'>Undo</a>")
    
    if next_id:
        return redirect(url_for('admin.storefront_tables', table_id=next_id))
    return redirect(url_for('admin.storefront_tables'))

@admin_bp.route('/storefront/tables/undo', methods=['GET'])
@login_required
def storefront_undo_delete_table():
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

@admin_bp.route('/storefront/tables/<int:table_id>/status', methods=['POST'])
@login_required
def storefront_set_table_status(table_id):
    table = Table.query.filter_by(id=table_id, restaurant_id=current_user.restaurant_id).first_or_404()
    new_status = request.form.get('status')
    
    valid_statuses = ['available', 'occupied', 'maintenance']
    if new_status in valid_statuses:
        table.status = new_status
        db.session.commit()
    else:
        flash("Invalid status.", "danger")
        
    return redirect(url_for('admin.storefront_tables', table_id=table.id))

@admin_bp.route('/storefront/orders', methods=['GET', 'POST'])
@login_required
def storefront_orders():
    restaurant = db.session.get(Restaurant, current_user.restaurant_id)
    
    if request.method == 'POST':
        action = request.form.get('action')
        order_id = request.form.get('order_id')
        
        if action == 'add_item':
            menu_item_id = request.form.get('menu_item_id')
            notes = request.form.get('notes')
            quantity = int(request.form.get('quantity', 1))
            if order_id and menu_item_id:
                # Only merge if notes are identical (or both are None/empty)
                existing_item = OrderItem.query.filter_by(order_id=order_id, menu_item_id=menu_item_id, notes=notes if notes else None).first()
                if existing_item:
                    existing_item.quantity += quantity
                    flash('Item quantity updated.')
                else:
                    order = Order.query.filter_by(id=order_id, restaurant_id=restaurant.id).first()
                    if order:
                        new_item = OrderItem(
                            order_id=order.id, 
                            menu_item_id=menu_item_id, 
                            quantity=quantity,
                            notes=notes
                        )
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
        
        elif action == 'update_status':
            status = request.form.get('status')
            if order_id and status:
                order = Order.query.get(order_id)
                if order and order.restaurant_id == restaurant.id:
                    order.status = status
                    db.session.commit()
                    flash(f'Order status updated to {status}.')
        
        elif action == 'create_order':
            table_id = request.form.get('table_id')
            table_number = request.form.get('table_number')
            
            if not table_id and table_number:
                table = Table.query.filter_by(restaurant_id=restaurant.id, number=table_number).first()
                if table:
                    table_id = table.id
                else:
                    flash(f'Table {table_number} not found.', 'danger')
            
            if table_id:
                blocking_statuses = ['pending', 'preparing', 'ready', 'served']
                existing_order = Order.query.filter_by(
                    table_id=table_id, 
                    restaurant_id=restaurant.id
                ).filter(
                    Order.status.in_(blocking_statuses)
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
            new_table_number = request.form.get('new_table_number')
            
            if not new_table_id and new_table_number:
                table = Table.query.filter_by(restaurant_id=restaurant.id, number=new_table_number).first()
                if table:
                    new_table_id = table.id
                else:
                    flash(f'Table {new_table_number} not found.', 'danger')

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
                        existing_item = OrderItem.query.filter_by(order_id=target_order.id, menu_item_id=item.menu_item_id, notes=item.notes).first()
                        if existing_item:
                            existing_item.quantity += item.quantity
                            db.session.delete(item)
                        else:
                            item.order_id = target_order.id
                    
                    source_order.status = 'cancelled' # Effectively closes the source order
                    db.session.commit()
                    flash(f'Order #{source_order.id} merged into Order #{target_order.id}.')
                    return redirect(url_for('admin.storefront_orders', order_id=target_order.id))
        
        elif action == 'cancel_order':
            if order_id:
                order = Order.query.get(order_id)
                if order and order.restaurant_id == restaurant.id:
                    order.status = 'cancelled'
                    db.session.commit()
                    flash(f'Order #{order.id} has been cancelled.')
                    # Redirect to the main list, as the selected order is no longer active
                    return redirect(url_for('admin.storefront_orders'))

        elif action == 'add_multiple_items':
            if order_id:
                items_added_count = 0
                for key, value in request.form.items():
                    if key.startswith('quantity_'):
                        try:
                            quantity = int(value)
                            if quantity > 0:
                                menu_item_id = key.split('_')[1]
                                
                                existing_item = OrderItem.query.filter_by(order_id=order_id, menu_item_id=menu_item_id).first()
                                if existing_item:
                                    existing_item.quantity += quantity
                                else:
                                    new_item = OrderItem(order_id=order_id, menu_item_id=menu_item_id, quantity=quantity)
                                    db.session.add(new_item)
                                
                                items_added_count += 1
                        except (ValueError, IndexError):
                            continue
                if items_added_count > 0:
                    db.session.commit()
                    flash(f'{items_added_count} item(s) added to the order.')

        elif action == 'update_item_quantity':
            item_id = request.form.get('item_id')
            quantity = request.form.get('quantity')
            if item_id and quantity:
                item = OrderItem.query.get(item_id)
                if item and item.order.restaurant_id == restaurant.id:
                    try:
                        new_quantity = int(quantity)
                        if new_quantity > 0:
                            item.quantity = new_quantity
                        else: # If quantity is 0 or less, remove the item
                            db.session.delete(item)
                    except ValueError:
                        flash('Invalid quantity.', 'danger')
                    db.session.commit()
                    flash('Item quantity updated.')
        
        return redirect(url_for('admin.storefront_orders', order_id=order_id))

    orders = Order.query.filter_by(restaurant_id=restaurant.id).filter(
        Order.status.in_(['pending', 'preparing', 'ready', 'served', 'paid'])
    ).order_by(Order.created_at.desc()).all()
    
    # Pre-calculate item counts and totals for each order
    for order in orders:
        total_items = len(order.items)
        if total_items > 0:
            order.item_counts = {
                'total': total_items,
                'pending': sum(1 for item in order.items if item.status == 'pending'),
                'preparing': sum(1 for item in order.items if item.status == 'preparing'),
                'ready': sum(1 for item in order.items if item.status == 'ready')
            }
            order.total_price = sum(item.menu_item.price * item.quantity for item in order.items)
        else:
            order.item_counts = None
            order.total_price = 0

    menu_items = MenuItem.query.filter_by(restaurant_id=restaurant.id, is_available=True).all()
    
    # A table is unavailable for a new order if it has an active, unpaid order.
    # 'paid' orders are still in the main `orders` list for display, but don't block a new order.
    blocking_statuses = ['pending', 'preparing', 'ready', 'served']
    unavailable_table_ids = [o.table_id for o in orders if o.status in blocking_statuses]

    available_tables = Table.query.filter(
        Table.restaurant_id == restaurant.id,
        Table.id.notin_(unavailable_table_ids), # Exclude tables with active, unpaid orders
        Table.status != 'maintenance'      # Exclude tables under maintenance
    ).all()
    
    selected_order = None
    selected_id = request.args.get('order_id')
    if selected_id:
        selected_order = next((o for o in orders if str(o.id) == str(selected_id)), None)
    
    if not selected_order and orders:
        selected_order = orders[0]

    categories = Category.query.filter_by(restaurant_id=restaurant.id, is_active=True).options(
        selectinload(Category.items)
    ).order_by(Category.name).all()


    return render_template('storefront_orders.html', orders=orders, selected_order=selected_order, menu_items=menu_items, available_tables=available_tables, categories=categories)

@admin_bp.route('/storefront/payment/<int:order_id>', methods=['GET', 'POST'])
@login_required
def storefront_payment(order_id):

    print("in storefront payment route")

    order = Order.query.filter_by(id=order_id, restaurant_id=current_user.restaurant_id).first_or_404()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'mark_as_paid':
            order.status = 'paid'
            # Here you would integrate with a real payment gateway if needed
            # For now, we just update the status
            db.session.commit()
            flash(f'Order #{order.id} for Table {order.table.number} marked as paid.')
            return redirect(url_for('admin.storefront_orders'))

    total = sum(item.menu_item.price * item.quantity for item in order.items)
    return render_template('storefront_payment.html', order=order, total=total)