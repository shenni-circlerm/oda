from flask import Blueprint, render_template, request, jsonify
from project.models import Restaurant, MenuItem, Table, Order, OrderItem
from extensions import db, socketio

customer_bp = Blueprint('customer', __name__)

@customer_bp.route('/')
def landing():
    return render_template('landing.html')

@customer_bp.route('/menu/<slug>')
def restaurant_menu(slug):
    restaurant = Restaurant.query.filter_by(slug=slug).first_or_404()
    table_number = request.args.get('table')
    
    table = None
    if table_number:
        table = Table.query.filter_by(restaurant_id=restaurant.id, number=table_number).first()
    
    menu = MenuItem.query.filter_by(restaurant_id=restaurant.id, is_available=True).all()
    
    return render_template('customer_menu.html', restaurant=restaurant, menu=menu, table=table)

@customer_bp.route('/place-order', methods=['POST'])
def place_order():
    data = request.get_json()
    table_id = data.get('table_id')
    items_data = data.get('items')
    
    if not table_id or not items_data:
        return jsonify({"error": "Missing table or items"}), 400
    
    table = db.session.get(Table, table_id)
    if not table:
        return jsonify({"error": "Table not found"}), 404
        
    new_order = Order(
        table_id=table.id,
        restaurant_id=table.restaurant_id,
        status='pending'
    )
    db.session.add(new_order)
    db.session.flush()
    
    for item in items_data:
        menu_item = db.session.get(MenuItem, item['id'])
        if menu_item:
            order_item = OrderItem(
                order_id=new_order.id,
                menu_item_id=menu_item.id
            )
            db.session.add(order_item)
            
    db.session.commit()
    
    # Notify Kitchen
    if socketio:
        socketio.emit('new_order', {'order_id': new_order.id}, room=f"restaurant_{table.restaurant_id}")
    
    return jsonify({"message": "Order placed successfully", "order_id": new_order.id}), 200