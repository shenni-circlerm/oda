function switchView(viewName) {
    fetch('/api/switch-view', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ view: viewName })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            window.location.reload(); // Reload to reflect new menu and context
        } else {
            console.error('Failed to switch view:', data.message);
        }
    });
}