from flask_login import UserMixin
import uuid
from datetime import datetime
from extensions import db

class Restaurant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(50), unique=True) # Used in URL: /menu/my-restaurant
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Branding Fields
    logo_path = db.Column(db.String(255), default='default_logo.png')
    logo_data = db.Column(db.LargeBinary)
    logo_mimetype = db.Column(db.String(50))
    brand_color = db.Column(db.String(7), default='#e74c3c') # Hex code
    banner_image = db.Column(db.String(255))
    banner_data = db.Column(db.LargeBinary)
    banner_mimetype = db.Column(db.String(50))
    tagline = db.Column(db.String(200))
    pages_config = db.Column(db.JSON, default={})
    qr_config = db.Column(db.JSON, default={})

    items = db.relationship('MenuItem', backref='restaurant')
    tables = db.relationship('Table', backref='restaurant')
    categories = db.relationship('Category', backref='restaurant')

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(255))
    role = db.Column(db.String(20)) # 'admin' or 'staff'
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    restaurant = db.relationship('Restaurant', backref='users')

    def is_admin(self):
        return self.role == 'admin'
    
    @property
    def is_superadmin(self):
        return self.role == 'superadmin'

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('MenuItem', backref='category')

class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    image_filename = db.Column(db.String(255), default="default_food.jpg")
    image_data = db.Column(db.LargeBinary)
    image_mimetype = db.Column(db.String(50))
    is_available = db.Column(db.Boolean, default=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'))
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Table(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(10))
    qr_identifier = db.Column(db.String(100), default=lambda: str(uuid.uuid4()))
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Configuration
    status = db.Column(db.String(20), default='available') # available, occupied, maintenance
    floor = db.Column(db.String(50))
    seating_capacity = db.Column(db.Integer)
    notes = db.Column(db.Text)
    
    # Reservation
    reservation_info = db.Column(db.JSON, default={}) # Stores: name, date, start, end

class ModifierGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50)) # e.g., "Choose your protein"
    is_required = db.Column(db.Boolean, default=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    options = db.relationship('ModifierOption', backref='group')

class ModifierOption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50)) # e.g., "Extra Beef"
    price_override = db.Column(db.Float, default=0.0) # e.g., +$2.00
    group_id = db.Column(db.Integer, db.ForeignKey('modifier_group.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class GlobalAnnouncement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    level = db.Column(db.String(20), default='info')

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(db.Integer, db.ForeignKey('table.id'))
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')
    items = db.relationship('OrderItem', backref='order')
    table = db.relationship('Table')

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    menu_item = db.relationship('MenuItem')