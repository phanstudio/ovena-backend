from django.urls import path

from . import admin_views as views

order_endpoints = [
    path('orders/', views.AdminOrderListView.as_view(), name='admin-order-list'),
    path('orders/dashboard/', views.AdminDashboardView.as_view(), name='admin-order-dashboard'),
    path('orders/cancelled/', views.AdminCancelledOrdersView.as_view(), name='admin-order-cancelled'),
    path('orders/<int:pk>/', views.AdminOrderDetailView.as_view(), name='admin-order-detail'),
    path('orders/<int:order_id>/events/', views.AdminOrderEventsView.as_view(), name='admin-order-events'),
    path('orders/<int:order_id>/assign-driver/', views.AdminAssignDriverView.as_view(), name='admin-order-assign-driver'),
    path('orders/<int:order_id>/force-status/', views.AdminForceStatusView.as_view(), name='admin-order-force-status'),
    path('orders/<int:order_id>/cancel/', views.AdminCancelOrderView.as_view(), name='admin-order-cancel'),
]
