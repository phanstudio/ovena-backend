from django.urls import path, include
import menu.views as views
import menu.views.business as bmenuview
import menu.views.delete as deleteview
from business_api.routers import BaseBranchRouter

router = BaseBranchRouter("")


business_urls = [
    *router.register("availability", bmenuview.AvailabilityListView),
    *router.register("availability/bulk-update", bmenuview.AvaliabilityView),
    path(
        "business/menu-list/",
        bmenuview.BusinessMenuView.as_view(),
        name="business-menu-list",
    ),
    path(
        "staff/menu-list/",
        bmenuview.BusinessStaffMenuView.as_view(),
        name="staff-menu-list",
    ),
    path("business/bulk-delete/", deleteview.BulkDeleteMenuView.as_view(), name="bulk-delete-menu"),
    path(
        "business/<str:menu_id>/delete/", 
        deleteview.DeleteMenuView.as_view(), 
        name="delete-menu"
    ),
    path("business/category/<str:category_id>/delete/", deleteview.DeleteMenuCategoryView.as_view(), name="delete-category"),
    path("business/item/<str:item_id>/delete/", deleteview.DeleteMenuItemView.as_view(), name="delete-menu-item"),
    path("business/addon/<str:addon_id>/delete/", deleteview.DeleteAddonView.as_view(), name="delete-addon"),
]

user_urls = [
    # Homepage with sections
    path('homepage/', views.HomePageView.as_view(), name='homepage'),
    
    # Infinite scroll list (ultra-lightweight)
    path('businesses/', views.BusinessListView.as_view(), name='business-list'),
    
    # List with menu names (no addons/variants)
    path('businesses/with-menus/', views.BusinessListWithMenuNamesView.as_view(), name='business-list-with-menus'),
    
    # Search and filter
    path('businesses/search/', views.BusinessSearchView.as_view(), name='business-search'),
    
    # Detail page (full menu)
    path('businesses/<int:business_id>/', views.BusinessDetailView.as_view(), name='business-detail'),
]

urlpatterns = [
    # path(
    #     "businesses/<int:business_id>/menus/",
    #     views.MenuView.as_view(),
    #     name="menu-list",
    # ),
    # path("restaurant-list/", views.RestaurantView.as_view(), name="restaurant-list"),
    # path("menuitem-search/", views.SearchMenuItems.as_view(), name="menuitem-search"),
    # path("home-page/", views.HomePageView.as_view(), name="home-page"),
    path(
        "restaurant-order/", views.ResturantOrderView.as_view(), name="restaurant-order"
    ),
    path("driver-order/", views.DriverOrderView.as_view(), name="driver-order"),
    path("order/", views.OrderView.as_view(), name="order"),
    path("orders/<int:order_id>/", views.OrderView.as_view(), name="order-detail"),
    path(
        "order/<int:order_id>/cancel/",
        views.OrderCancelView.as_view(),
        name="order-cancel",
    ),
    path("update-menus/", views.UpdateMenusView.as_view(), name="update-menus"),
    path("", include(business_urls)),
    path("", include(user_urls)),
]
