from flask import Blueprint, session, jsonify, request
from project.utils.admin_nav import get_current_menu, MENU_STRUCTURE

ui_bp = Blueprint('ui', __name__)

@ui_bp.route('/api/switch-view', methods=['POST'])
def switch_view():
    data = request.get_json()
    view = data.get('view')
    
    if view and view in MENU_STRUCTURE:
        session['current_view'] = view
        return jsonify({'status': 'success', 'view': view})
    
    return jsonify({'status': 'error', 'message': 'Invalid view requested'}), 400

@ui_bp.app_context_processor
def inject_admin_nav():
    """Injects sidebar_menu and current_view into all templates."""
    return dict(
        current_view=session.get('current_view', 'kitchen'),
        sidebar_menu=get_current_menu(),
        available_views=list(MENU_STRUCTURE.keys())
    )