from django.urls import path

from points import views

app_name = "points"
external_name = "customer-"

urlpatterns = [
    path("me/balance/", views.CustomerMyPointsBalanceView.as_view(), name=external_name+"my-balance"),
    path("me/history/", views.CustomerMyPointsHistoryListView.as_view(), name=external_name+"my-history"),
    path("me/withdrawals/", views.CustomerMyPointsWithdrawalRequestListView.as_view(), name=external_name+"my-withdrawals"),
    path("withdrawals/", views.CustomerPointsWithdrawalRequestCreateView.as_view(), name=external_name+"withdrawal-create"),
    path("leaderboard/", views.CustomerLeaderboardCurrentView.as_view(), name=external_name+"leaderboard-current"),
    path("leaderboard/me/", views.CustomerMyLeaderboardRankView.as_view(), name=external_name+"leaderboard-my-rank"),
]
