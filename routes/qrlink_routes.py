from flask import Blueprint, render_template, request, jsonify, abort
from sqlalchemy.orm import joinedload, selectinload
from datetime import datetime
import pytz

from project.models import Restaurant, Table, Category, Order, OrderItem, Menu, MenuItem, ModifierGroup, ModifierOption
from extensions import db, socketio

qrlink_bp = Blueprint('qrlink', __name__, url_prefix='/qrlink')

@qrlink_bp.route('/')
def index():
    """Generic landing for users who navigate to /qrlink/ directly."""
    return render_template('qrlink_index.html')

@qrlink_bp.route('/<slug>')
def customer_view(slug):
    """Displays the customer ordering flow, starting with a welcome screen."""
    restaurant = Restaurant.query.filter_by(slug=slug).first_or_404()
    table_number = request.args.get('table')
    table = Table.query.filter_by(restaurant_id=restaurant.id, number=table_number).first()
    return render_template('qrlink_landing.html', restaurant=restaurant, table=table)

@qrlink_bp.route('/<slug>/menu')
def customer_menu(slug):
    """Displays the menu and categories for ordering."""
    restaurant = Restaurant.query.filter_by(slug=slug).first_or_404()
    table_number = request.args.get('table')
    table = Table.query.filter_by(restaurant_id=restaurant.id, number=table_number).first()

    # 1. Get current time and day in the restaurant's local timezone
    try:
        restaurant_tz = pytz.timezone(restaurant.timezone or 'UTC')
    except pytz.UnknownTimeZoneError:
        restaurant_tz = pytz.timezone('UTC')

    now_local = datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(restaurant_tz)
    current_time = now_local.time()
    current_day_index = str(now_local.weekday()) # Monday is 0, Sunday is 6
    
    print(f"\n--- DEBUG: customer_menu for slug: {slug} ---")
    print(f"Restaurant Timezone: {restaurant_tz}")
    print(f"Current Local Time: {current_time}, Day Index: {current_day_index} (Mon=0)")

    # 2. Find all potentially active menus
    all_menus = Menu.query.filter_by(restaurant_id=restaurant.id, is_active=True).options(selectinload(Menu.categories)).all()
    
    active_menus = []
    print(f"Checking {len(all_menus)} active menus for schedule...")
    for menu in all_menus:
        # Corrected logic: An empty string for active_days should mean it's inactive.
        # `None` means it has no day-based restrictions.
        day_match = menu.active_days and current_day_index in menu.active_days.split(',')
        
        time_match = False
        if not menu.start_time or not menu.end_time:
            time_match = True # No time restriction
        elif menu.start_time <= menu.end_time: # Same day schedule
            if menu.start_time <= current_time <= menu.end_time:
                time_match = True
        else: # Overnight schedule (e.g., 10pm - 2am)
            if current_time >= menu.start_time or current_time <= menu.end_time:
                time_match = True
        
        print(f"  - Menu: '{menu.name}' (Active Days: '{menu.active_days}') -> Day Match: {day_match}, Time Match: {time_match}")
        if day_match and time_match:
            active_menus.append(menu)

    print(f"Found {len(active_menus)} currently scheduled menus.")

    # 3. Get a unique set of active category IDs from the active menus
    active_category_ids = {cat.id for menu in active_menus for cat in menu.categories if cat.is_active}

    # 4. Fetch the final list of categories to display
    categories = Category.query.filter(
        Category.id.in_(list(active_category_ids))
    ).options(
        selectinload(Category.items).selectinload(MenuItem.modifiers).selectinload(ModifierGroup.options)
    ).order_by(Category.name).all()

    # Serialize data for JavaScript
    menu_data = {}
    all_items = [item for cat in categories for item in cat.items]
    for item in all_items:
        menu_data[item.id] = {
            'id': item.id,
            'name': item.name,
            'price': item.price,
            'description': item.description,
            'modifiers': [{
                'id': group.id,
                'name': group.name,
                'selection_type': group.selection_type,
                'is_required': group.is_required,
                'options': [{
                    'id': opt.id,
                    'name': opt.name,
                    'price_override': opt.price_override
                } for opt in group.options]
            } for group in item.modifiers]
        }

    return render_template('qrlink_store.html', restaurant=restaurant, table=table, categories=categories, menu_data_json=menu_data)

@qrlink_bp.route('/<slug>/checkout')
def customer_checkout(slug):
    """Displays the checkout page with the cart summary."""
    restaurant = Restaurant.query.filter_by(slug=slug).first_or_404()
    table_number = request.args.get('table')
    table = Table.query.filter_by(restaurant_id=restaurant.id, number=table_number).first()
    return render_template('qrlink_checkout.html', restaurant=restaurant, table=table)

@qrlink_bp.route('/<slug>/thanks/<int:order_id>')
def customer_thanks(slug, order_id):
    """Displays the thank you page after an order is placed."""
    restaurant = Restaurant.query.filter_by(slug=slug).first_or_404()
    order = Order.query.filter_by(id=order_id, restaurant_id=restaurant.id).first_or_404()
    return render_template('qrlink_thanks.html', restaurant=restaurant, order=order)

@qrlink_bp.route('/place-order', methods=['POST'])
def place_order():
    """Handles the submission of a new order from a customer."""
    data = request.get_json()
    if not data or not data.get('items'):
        return jsonify({'success': False, 'message': 'Invalid order data.'}), 400
    
    table_id = data.get('table_id')
    restaurant_id = data.get('restaurant_id')

    if table_id:
        table = Table.query.get(table_id)
        if not table:
            return jsonify({'success': False, 'message': 'Table not found.'}), 404
        restaurant_id = table.restaurant_id
    elif not restaurant_id:
        return jsonify({'success': False, 'message': 'Restaurant not identified for take-away order.'}), 400

    new_order = Order(
        table_id=table_id,
        restaurant_id=restaurant_id,
        status='pending',
        # order_type=data.get('order_type', 'dine-in'), # NOTE: This attribute needs to be added to the Order model to track dine-in vs take-away.
        created_at=datetime.utcnow()
    )
    db.session.add(new_order)
    db.session.flush() # Flush to get the new_order.id

    for item_data in data['items']:
        modifier_ids = item_data.get('modifiers', [])
        order_item = OrderItem(
            order_id=new_order.id, 
            menu_item_id=item_data['menu_item_id'], 
            quantity=item_data['quantity'],
            notes=item_data.get('notes')
        )
        if modifier_ids:
            options = ModifierOption.query.filter(ModifierOption.id.in_(modifier_ids)).all()
            for option in options:
                order_item.selected_modifiers.append(option)

        db.session.add(order_item)

    db.session.commit()
    socketio.emit('new_order', {'order_id': new_order.id}, room=f'restaurant_{new_order.restaurant_id}')
    return jsonify({'success': True, 'order_id': new_order.id})