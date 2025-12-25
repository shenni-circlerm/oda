function completeOrder(orderId) {
    fetch(`/admin/order/${orderId}/update`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({status: 'completed'})
    }).then(() => {
        document.getElementById(`order-${orderId}`).remove();
    });
}