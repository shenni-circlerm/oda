from flask_login import UserMixin
import uuid
from datetime import datetime
from extensions import db
from itsdangerous import URLSafeTimedSerializer
from flask import current_app

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
    password = db.Column(db.String(255), nullable=True)
    role = db.Column(db.String(20)) # 'admin' or 'staff'
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'))
    password_version = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    restaurant = db.relationship('Restaurant', backref='users')
    is_active = db.Column(db.Boolean, default=False, nullable=False)

    def is_admin(self):
        return self.role == 'admin'
    
    @property
    def is_superadmin(self):
        from flask import current_app
        return self.email == current_app.config.get('MASTER_SYSTEM_ADMIN_EMAIL')

    def get_token(self, salt, expires_sec=1800):
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=salt)
        return s.dumps({'user_id': self.id, 'pw_version': self.password_version})

    @staticmethod
    def verify_token(token, salt, expires_sec=1800):
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=salt)
        try:
            data = s.loads(
                token,
                max_age=expires_sec
            )
            user_id = data['user_id']
            token_pw_version = data['pw_version']
        except Exception:
            return None
        user = db.session.get(User, user_id)
        if user and user.password_version == token_pw_version:
            return user
        return None

menu_category_association = db.Table('menu_category_association',
    db.Column('menu_id', db.Integer, db.ForeignKey('menu.id'), primary_key=True),
    db.Column('category_id', db.Integer, db.ForeignKey('category.id'), primary_key=True)
)

class Menu(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'))
    start_time = db.Column(db.Time, nullable=True)
    end_time = db.Column(db.Time, nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    active_days = db.Column(db.String(20), nullable=True) # Comma separated indices 0-6
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    categories = db.relationship('Category', secondary=menu_category_association, backref='menus')

menu_item_categories = db.Table('menu_item_categories',
    db.Column('menu_item_id', db.Integer, db.ForeignKey('menu_item.id'), primary_key=True),
    db.Column('category_id', db.Integer, db.ForeignKey('category.id'), primary_key=True)
)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # items relationship is defined via backref in MenuItem
    # menus relationship is defined via backref in Menu

class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    compare_at_price = db.Column(db.Float, nullable=True)
    description = db.Column(db.Text)
    image_filename = db.Column(db.String(255), default="default_food.jpg")
    image_data = db.Column(db.LargeBinary)
    image_mimetype = db.Column(db.String(50))
    is_available = db.Column(db.Boolean, default=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'))
    station_id = db.Column(db.Integer, db.ForeignKey('station.id'), nullable=True)
    categories = db.relationship('Category', secondary=menu_item_categories, backref=db.backref('items', lazy='subquery'))
    modifiers = db.relationship('ModifierGroup', backref='menu_item', cascade="all, delete-orphan")
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
    selection_type = db.Column(db.String(20), default='single') # 'single' or 'multiple'
    min_selection = db.Column(db.Integer, default=0)
    max_selection = db.Column(db.Integer, nullable=True)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    options = db.relationship('ModifierOption', backref='group', cascade="all, delete-orphan")

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
    quantity = db.Column(db.Integer, default=1)
    status = db.Column(db.String(20), default='pending') # 'pending', 'preparing', 'ready'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    menu_item = db.relationship('MenuItem')

class Station(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'))
    restaurant = db.relationship('Restaurant', backref='stations')