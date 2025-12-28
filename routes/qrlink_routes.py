from flask import Blueprint, render_template, request, jsonify, abort
from sqlalchemy.orm import joinedload
from datetime import datetime

from project.models import Restaurant, Table, Category, Order, OrderItem
from extensions import db, socketio

qrlink_bp = Blueprint('qrlink', __name__, url_prefix='/qrlink')

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

    categories = Category.query.filter(
        Category.restaurant_id == restaurant.id,
        Category.is_active == True
    ).options(
        joinedload(Category.items)
    ).order_by(Category.name).all()

    return render_template('qrlink_store.html', restaurant=restaurant, table=table, categories=categories)

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
        order_item = OrderItem(order_id=new_order.id, menu_item_id=item_data['menu_item_id'], quantity=item_data['quantity'])
        db.session.add(order_item)

    db.session.commit()
    socketio.emit('new_order', {'order_id': new_order.id}, room=f'restaurant_{new_order.restaurant_id}')
    return jsonify({'success': True, 'order_id': new_order.id})