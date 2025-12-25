import os
from flask import Flask
from flask_migrate import Migrate
from extensions import db, socketio, login_manager
from project.models import User
from config import config

def create_app(config_name='default'):
    app = Flask(
        __name__,
        template_folder='project/templates',
        static_folder='project/static',
        static_url_path='/static'
    )
    app.config.from_object(config[config_name])

    db.init_app(app)
    socketio.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    Migrate(app, db)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from routes.admin_routes import admin_bp
    from routes.customer_routes import customer_bp
    from routes.super_admin_routes import super_admin_bp
    from routes.admin_analytics import analytics_bp
    from routes.auth_routes import auth_bp
    from routes.ui_routes import ui_bp

    app.register_blueprint(admin_bp)
    app.register_blueprint(customer_bp)
    app.register_blueprint(super_admin_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(ui_bp)

    # with app.app_context():
    #     db.create_all()
    if app.config.get('SQLALCHEMY_DATABASE_URI') and app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:'):
        with app.app_context():
            db.create_all()
    return app

app = create_app(os.getenv('FLASK_CONFIG') or 'default')

if __name__ == '__main__':
    socketio.run(app)
