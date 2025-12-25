from flask import Blueprint, render_template, make_response
from flask_login import login_required, current_user
from sqlalchemy import func
from datetime import datetime, timedelta
from extensions import db
from project.models import Order, MenuItem, OrderItem, Restaurant
from routes.admin_routes import admin_required
import csv
from io import StringIO

analytics_bp = Blueprint('analytics', __name__)

@analytics_bp.route('/admin/analytics')
@login_required
@admin_required
def analytics_dashboard():
    r_id = current_user.restaurant_id
    
    # 1. Total Revenue (Last 30 Days)
    # Joining Order with MenuItem via OrderItems to sum prices
    total_revenue = db.session.query(func.sum(MenuItem.price))\
        .join(OrderItem)\
        .join(Order)\
        .filter(Order.restaurant_id == r_id, Order.status == 'completed')\
        .scalar() or 0.0

    # 2. Top 5 Best Selling Items
    top_items = db.session.query(MenuItem.name, func.count(OrderItem.id).label('total'))\
        .join(OrderItem)\
        .filter(MenuItem.restaurant_id == r_id)\
        .group_by(MenuItem.id)\
        .order_by(db.desc('total'))\
        .limit(5).all()

    # 3. Revenue by Date (for the Line Chart)
    daily_revenue = db.session.query(
        func.date(Order.created_at).label('date'),
        func.sum(MenuItem.price).label('daily_total')
    ).join(OrderItem).join(MenuItem)\
     .filter(Order.restaurant_id == r_id, Order.created_at >= datetime.now() - timedelta(days=7))\
     .group_by(func.date(Order.created_at)).all()

    return render_template('analytics.html', 
                           revenue=total_revenue, 
                           top_items=top_items,
                           daily_revenue=daily_revenue)

@analytics_bp.route('/admin/export-orders')
@login_required
@admin_required
def export_orders():
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Order ID', 'Table', 'Total', 'Date'])
    
    orders = Order.query.filter_by(restaurant_id=current_user.restaurant_id).all()
    for o in orders:
        cw.writerow([o.id, o.table.number, o.get_total(), o.created_at])
    
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=orders_export.csv"
    output.headers["Content-type"] = "text/csv"
    return output

def get_receipt_data(order_id):
    order = Order.query.get_or_404(order_id)
    restaurant = Restaurant.query.get(order.restaurant_id)
    
    items = []
    total = 0
    for oi in order.order_items:
        item_total = oi.menu_item.price
        items.append({
            'name': oi.menu_item.name,
            'price': item_total
        })
        total += item_total
        
    return {
        'restaurant_name': restaurant.name,
        'order_id': order.id,
        'date': order.created_at.strftime("%Y-%m-%d %H:%M"),
        'items': items,
        'total': total,
        'table': order.table.number
    }