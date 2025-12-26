from flask import session

MENU_STRUCTURE = {
    'kitchen': [
        {'label': 'Orders', 'endpoint': 'admin.staff_dashboard', 'icon': 'bi-speedometer2'},
        {'label': 'Tables', 'endpoint': 'admin.tables', 'icon': 'bi-grid-3x3'},
        {'label': 'Paid / Completed', 'endpoint': 'admin.completed', 'icon': 'bi-check-circle'},
    ],
    'office': [
        {'label': 'Analytics', 'endpoint': 'analytics.analytics_dashboard', 'icon': 'bi-graph-up'},
        {'label': 'Staff', 'endpoint': 'admin.manage_users', 'icon': 'bi-people'},
        {'label': 'Orders History', 'endpoint': 'admin.history', 'icon': 'bi-clock-history'},
        {'label': 'Payments', 'endpoint': 'admin.payments', 'icon': 'bi-credit-card'},
    ],
    'store_front': [
        {'label': 'Tables', 'endpoint': 'admin.storefront_tables', 'icon': 'bi-grid-3x3'},
        {'label': 'Active Orders', 'endpoint': 'admin.storefront_orders', 'icon': 'bi-receipt'},
        {'label': 'Payments', 'endpoint': 'admin.payments', 'icon': 'bi-credit-card'},
    ],
    'menu': [
        {'label': 'Menu Items', 'endpoint': 'admin.manage_menu', 'icon': 'bi-journal-text'},
        {'label': 'Categories', 'endpoint': 'admin.categories', 'icon': 'bi-tags'},
        {'label': 'Availability', 'endpoint': 'admin.availability', 'icon': 'bi-toggle-on'},
    ],
    'design_store': [
        {'label': 'Design', 'endpoint': 'admin.menu_design', 'icon': 'bi-pencil-square'},
        {'label': 'Branding', 'endpoint': 'admin.branding', 'icon': 'bi-palette'},
        {'label': 'QR Design', 'endpoint': 'admin.qr_design', 'icon': 'bi-palette2'},
    ]
}

def get_current_menu():
    """
    Returns the menu list for the current view stored in session.
    Defaults to 'kitchen' if not set.
    """
    view = session.get('current_view', 'kitchen')
    # Return the specific menu or default to kitchen if key not found
    return MENU_STRUCTURE.get(view, MENU_STRUCTURE['kitchen'])