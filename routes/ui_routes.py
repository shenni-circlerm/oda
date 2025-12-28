from flask import Blueprint, session, jsonify, request, url_for
from flask_login import current_user
from routes.nav import get_current_menu, MENU_STRUCTURE

ui_bp = Blueprint('ui', __name__)

@ui_bp.route('/api/switch-view', methods=['POST'])
def switch_view():
    data = request.get_json()
    view = data.get('view')
    
    if view and view in MENU_STRUCTURE:
        session['current_view'] = view
        
        # Get the default endpoint (first item in the menu)
        menu_items = MENU_STRUCTURE[view]['items']
        default_endpoint = menu_items[0]['endpoint'] if menu_items else 'customer.landing'
        
        return jsonify({'status': 'success', 'view': view, 'redirect_url': url_for(default_endpoint)})
    
    return jsonify({'status': 'error', 'message': 'Invalid view requested'}), 400

@ui_bp.app_context_processor
def inject_admin_nav():
    """Injects sidebar_menu and current_view into all templates."""
    
    sidebar_menu = []
    available_views = []
    current_view = session.get('current_view', 'kitchen')
    
    if current_user.is_authenticated:
        # 1. Get the menu structure for the current view (for ALL roles)
        sidebar_menu = get_current_menu()
        
        if current_user.role == 'admin':
            # Admins can switch between all views
            available_views = list(MENU_STRUCTURE.keys())
        else:
            # Non-admins are locked to their current view
            available_views = [current_view] if current_view else []

    return dict(
        current_view=current_view,
        sidebar_menu=sidebar_menu,
        available_views=available_views,
        MENU_STRUCTURE=MENU_STRUCTURE
    )