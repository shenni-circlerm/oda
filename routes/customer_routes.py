from flask import Blueprint, request, render_template, send_file, current_app
from project.models import Table, Restaurant, MenuItem, Order, OrderItem
from extensions import db, socketio
import qrcode
from io import BytesIO

customer_bp = Blueprint('customer', __name__)

@customer_bp.route('/')
def landing():
    return render_template('landing.html')

@customer_bp.route('/generate_qr/<table_uuid>')
def generate_qr(table_uuid):
    url = f"https://yourdomain.com/menu/order/{table_uuid}"
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')
    buf = BytesIO()
    img.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@customer_bp.route('/menu/order/<qr_uuid>')
def customer_menu(qr_uuid):
    table = Table.query.filter_by(qr_identifier=qr_uuid).first_or_404()
    restaurant = Restaurant.query.get(table.restaurant_id)
    menu_items = MenuItem.query.filter_by(restaurant_id=restaurant.id).all()
    return render_template('customer_menu.html', restaurant=restaurant, menu=menu_items, table=table)

@customer_bp.route('/place-order', methods=['POST'])
def place_order():
    data = request.get_json()
    table_id = data.get('table_id')
    items = data.get('items')
    
    table = Table.query.get(table_id)
    
    new_order = Order(
        table_id=table.id,
        restaurant_id=table.restaurant_id,
        status='pending'
    )
    db.session.add(new_order)
    db.session.flush()
    
    for item in items:
        oi = OrderItem(order_id=new_order.id, menu_item_id=item['id'])
        db.session.add(oi)
    
    db.session.commit()

    # Notify Kitchen
    order_data = {
        'id': new_order.id,
        'table': table.number,
        'items': [item['name'] for item in items],
        'total': sum(item['price'] for item in items)
    }
    socketio.emit('new_order', order_data, room=f"restaurant_{table.restaurant_id}")
    
    return {"message": "Order Placed"}, 200

@customer_bp.route('/request-service', methods=['POST'])
def request_service():
    data = request.get_json()
    table = Table.query.get(data['table_id'])
    
    socketio.emit('staff_alert', {
        'message': f"Table {table.number} needs assistance!",
        'type': 'warning'
    }, room=f"restaurant_{table.restaurant_id}")
    
    return {"status": "sent"}, 200

# SocketIO Events
from flask_login import current_user
from flask_socketio import join_room

@socketio.on('join')
def on_join(data):
    if current_user.is_authenticated:
        room = f"restaurant_{current_user.restaurant_id}"
        join_room(room)