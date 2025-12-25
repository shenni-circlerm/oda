from flask import session

MENU_STRUCTURE = {
    'kitchen': [
        {'label': 'Orders', 'endpoint': 'admin.orders', 'icon': 'fa-list'},
        {'label': 'Tables', 'endpoint': 'admin.tables', 'icon': 'fa-chair'},
        {'label': 'Paid / Completed', 'endpoint': 'admin.completed', 'icon': 'fa-check-circle'},
    ],
    'office': [
        {'label': 'Dashboard', 'endpoint': 'admin.dashboard', 'icon': 'fa-tachometer-alt'},
        {'label': 'Orders History', 'endpoint': 'admin.history', 'icon': 'fa-history'},
        {'label': 'Payments', 'endpoint': 'admin.payments', 'icon': 'fa-credit-card'},
        {'label': 'Reports', 'endpoint': 'admin.reports', 'icon': 'fa-chart-bar'},
        {'label': 'Staff', 'endpoint': 'admin.staff', 'icon': 'fa-users'},
    ],
    'storefront': [
        {'label': 'Active Tables', 'endpoint': 'admin.active_tables', 'icon': 'fa-utensils'},
        {'label': 'Walk-in Orders', 'endpoint': 'admin.walkin', 'icon': 'fa-walking'},
        {'label': 'Mark Paid', 'endpoint': 'admin.mark_paid', 'icon': 'fa-money-bill-wave'},
        {'label': 'Print Receipt', 'endpoint': 'admin.print_receipt', 'icon': 'fa-print'},
    ],
    'menu': [
        {'label': 'Categories', 'endpoint': 'admin.categories', 'icon': 'fa-tags'},
        {'label': 'Items', 'endpoint': 'admin.items', 'icon': 'fa-hamburger'},
        {'label': 'Availability', 'endpoint': 'admin.availability', 'icon': 'fa-toggle-on'},
        # {'label': 'Modifiers', 'endpoint': 'admin.modifiers', 'icon': 'fa-plus'}, # Coming later
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