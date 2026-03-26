from django.urls import path

from notifications import views


urlpatterns = [
    path("notifications/", views.DriverNotificationListView.as_view(), name="driver-notifications"),
    path("notifications/unread-count/", views.DriverNotificationUnreadCountView.as_view(), name="driver-notifications-unread-count"),
    path("notifications/<int:notification_id>/read/", views.DriverNotificationMarkReadView.as_view(), name="driver-notification-read"),
    path("notifications/read-all/", views.DriverNotificationReadAllView.as_view(), name="driver-notification-read-all"),
]

