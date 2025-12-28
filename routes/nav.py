from flask import session
import copy

MENU_STRUCTURE = {
    'kitchen': {
        'label': 'Kitchen',
        'description': 'Track orders, stay on top of prep, and serve faster.',
        'items': [
            {'label': 'Orders', 'endpoint': 'admin.kitchen_orders', 'icon': 'bi-speedometer2'},
            {'label': 'Tables', 'endpoint': 'admin.kitchen_tables', 'icon': 'bi-grid-3x3'},
            {'label': 'Stations', 'endpoint': 'admin.kitchen_manage_stations', 'icon': 'bi-hdd-stack'}
        ]
    },
    'store_front': {
        'label': 'Store Front',
        'description': 'Handle tables and payments with confidence.',
        'items': [
            {'label': 'Tables', 'endpoint': 'admin.storefront_tables', 'icon': 'bi-grid-3x3'},
            {'label': 'Active Orders', 'endpoint': 'admin.storefront_orders', 'icon': 'bi-receipt'},
        ]
    },
    'menu': {
        'label': 'Menu',
        'description': 'Decide what’s on the menu — and what’s not.',
        'items': [
            {'label': 'Menus', 'endpoint': 'admin.menu_menus', 'icon': 'bi-journal-album'},
            {'label': 'Menu Items', 'endpoint': 'admin.menu_manage_menu', 'icon': 'bi-journal-text'},
            {'label': 'Categories', 'endpoint': 'admin.menu_categories', 'icon': 'bi-tags'},
        ]
    },
    'online_store': {
        'label': 'Online Store',
        'description': 'Shape the ordering experience your customers see.',
        'items': [
            {'label': 'Design', 'endpoint': 'admin.design_menu_design', 'icon': 'bi-pencil-square'},
            {'label': 'Branding', 'endpoint': 'admin.design_branding', 'icon': 'bi-palette'},
            {'label': 'QR Design', 'endpoint': 'admin.design_qr_design', 'icon': 'bi-palette2'},
        ]
    },
    'office': {
        'label': 'Office',
        'description': 'Understand your sales and run your restaurant better.',
        'items': [
            {'label': 'Analytics', 'endpoint': 'analytics.analytics_dashboard', 'icon': 'bi-graph-up'},
            {'label': 'Staff', 'endpoint': 'admin.office_users', 'icon': 'bi-people'},
            {'label': 'Orders History', 'endpoint': 'admin.history', 'icon': 'bi-clock-history'},
            {'label': 'Payments', 'endpoint': 'admin.payments', 'icon': 'bi-credit-card'},
        ]
    }
}

def get_current_menu():
    """
    Returns the menu list for the current view stored in session.
    Defaults to 'kitchen' if not set.
    """
    view = session.get('current_view', 'kitchen')
    # Return the specific menu or default to kitchen if key not found
    # Return a deep copy to allow modification (e.g. appending Logout) without affecting global state
    return copy.deepcopy(MENU_STRUCTURE.get(view, MENU_STRUCTURE['kitchen']))