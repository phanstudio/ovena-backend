from django.urls import path

from points import views

app_name = "points_admin"
external_name = "admin-"

urlpatterns = [
    path("balances/", views.AdminPointsBalanceListView.as_view(), name="balance-list"),
    path(
        "withdrawals/admin/",
        views.AdminPointsWithdrawalRequestAdminListView.as_view(),
        name="withdrawal-admin-list",
    ),
    path(
        "withdrawals/<uuid:pk>/resolve/",
        views.AdminPointsWithdrawalRequestResolveView.as_view(),
        name="withdrawal-resolve",
    ),
    path("rules/", views.AdminPointsEventRuleListView.as_view(), name="rule-list"),
    path("rules/<int:pk>/", views.AdminPointsEventRuleDetailView.as_view(), name="rule-detail"),
    path("leaderboard/", views.AdminLeaderboardCurrentView.as_view(), name="leaderboard-current"),
    path(
        "leaderboard/periods/",
        views.AdminLeaderboardSnapshotPeriodListView.as_view(),
        name="leaderboard-periods",
    ),
    path("leaderboard/<str:period>/", views.AdminLeaderboardSnapshotView.as_view(), name="leaderboard-snapshot"),
]