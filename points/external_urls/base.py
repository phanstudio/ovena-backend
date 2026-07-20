from django.urls import path

from points import views

app_name = "points"

urlpatterns = [
    path("balances/", views.PointsBalanceListView.as_view(), name="balance-list"),
    path("me/balance/", views.MyPointsBalanceView.as_view(), name="my-balance"),
    path("me/history/", views.MyPointsHistoryListView.as_view(), name="my-history"),
    path("me/withdrawals/", views.MyPointsWithdrawalRequestListView.as_view(), name="my-withdrawals"),
    path("withdrawals/", views.PointsWithdrawalRequestCreateView.as_view(), name="withdrawal-create"),
    path(
        "withdrawals/admin/",
        views.PointsWithdrawalRequestAdminListView.as_view(),
        name="withdrawal-admin-list",
    ),
    path(
        "withdrawals/<uuid:pk>/resolve/",
        views.PointsWithdrawalRequestResolveView.as_view(),
        name="withdrawal-resolve",
    ),
    path("rules/", views.PointsEventRuleListView.as_view(), name="rule-list"),
    path("rules/<int:pk>/", views.PointsEventRuleDetailView.as_view(), name="rule-detail"),
    path("leaderboard/", views.LeaderboardCurrentView.as_view(), name="leaderboard-current"),
    path("leaderboard/me/", views.MyLeaderboardRankView.as_view(), name="leaderboard-my-rank"),
    path(
        "leaderboard/periods/",
        views.LeaderboardSnapshotPeriodListView.as_view(),
        name="leaderboard-periods",
    ),
    path("leaderboard/<str:period>/", views.LeaderboardSnapshotView.as_view(), name="leaderboard-snapshot"),
]
