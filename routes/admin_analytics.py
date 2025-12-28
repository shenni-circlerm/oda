from flask import Blueprint, render_template, Response
from flask_login import login_required, current_user
from sqlalchemy import func
from datetime import datetime, timedelta
import csv
import io

from project.models import Order, OrderItem, MenuItem
from extensions import db

analytics_bp = Blueprint('analytics', __name__, url_prefix='/office/analytics')

@analytics_bp.route('/')
@login_required
def analytics_dashboard():
    # --- Total Revenue (Last 30 Days) ---
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    revenue_query = db.session.query(
        func.sum(MenuItem.price * OrderItem.quantity)
    ).select_from(Order).join(OrderItem).join(MenuItem).filter(
        Order.restaurant_id == current_user.restaurant_id,
        Order.status.in_(['paid', 'completed']),
        Order.created_at >= thirty_days_ago
    )
    total_revenue = revenue_query.scalar() or 0.0

    # --- Top Selling Items (Last 30 Days) ---
    top_items_query = db.session.query(
        MenuItem.name,
        func.sum(OrderItem.quantity).label('total_sold')
    ).select_from(OrderItem).join(MenuItem).join(Order).filter(
        Order.restaurant_id == current_user.restaurant_id,
        Order.status.in_(['paid', 'completed']),
        Order.created_at >= thirty_days_ago
    ).group_by(MenuItem.name).order_by(func.sum(OrderItem.quantity).desc()).limit(5)
    top_items = top_items_query.all()

    # --- Daily Revenue (Last 7 Days) ---
    seven_days_ago = datetime.utcnow().date() - timedelta(days=7)
    daily_revenue_query = db.session.query(
        func.date(Order.created_at).label('date'),
        func.sum(MenuItem.price * OrderItem.quantity).label('daily_total')
    ).select_from(Order).join(OrderItem).join(MenuItem).filter(
        Order.restaurant_id == current_user.restaurant_id,
        Order.status.in_(['paid', 'completed']),
        func.date(Order.created_at) > seven_days_ago
    ).group_by(func.date(Order.created_at)).order_by(func.date(Order.created_at))
    daily_revenue = daily_revenue_query.all()

    return render_template(
        'analytics.html',
        revenue=total_revenue,
        top_items=top_items,
        daily_revenue=daily_revenue
    )

@analytics_bp.route('/export/orders')
@login_required
def export_orders():
    """Exports all paid/completed orders to a CSV file."""
    # This is a placeholder. A full implementation would query the database.
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Order ID', 'Date', 'Total'])
    output.seek(0)
    return Response(output, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=orders_export.csv"})