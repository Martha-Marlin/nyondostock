from django.urls import path
from . import views

urlpatterns = [
    # AUTHENTICATION URLS
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # DASHBOARD URLS
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('sales-dashboard/', views.sales_dashboard_view, name='sales_dashboard'),
    path('admin-dashboard/', views.admin_dashboard_view, name='admin_dashboard'),
    path('accounts-dashboard/', views.admin_dashboard_view, name='accounts_dashboard'),

    # STOCK URLS
    path('stock/', views.stock_view, name='stock'),

    # SALES URLS
    path('record_sales/', views.record_sales_view, name='record_sales'),
    path('add-sale/', views.add_sale_view, name='add_sale'),
    path('sales/', views.sales_list_view, name='sales_list'),
    path('sales/<int:sale_id>/edit/', views.edit_sale_view, name='edit_sale'),
    path('sales/<int:sale_id>/delete/', views.delete_sale_view, name='delete_sale'),
    path('sales/<int:sale_id>/receipt/', views.print_receipt_view, name='print_receipt'),

    # SUPPLIER URLS
    path('suppliers/', views.suppliers_view, name='suppliers'),
    path('suppliers/add/', views.add_supplier_view, name='add_supplier'),
    path('suppliers/edit/<int:supplier_id>/', views.edit_supplier_view, name='edit_supplier'),
    path('suppliers/delete/<int:supplier_id>/', views.delete_supplier_view, name='delete_supplier'),
    path('suppliers/<int:supplier_id>/transactions/', views.supplier_transactions_view, name='supplier_transactions'),
    path('suppliers/<int:supplier_id>/record-payment/', views.record_payment_view, name='record_payment'),

    # SUPPLIER CREDIT URLS
    path('suppliers/<int:supplier_id>/credits/', views.supplier_credit_detail_view, name='supplier_credit_detail'),
    path('suppliers/<int:supplier_id>/credits/add/', views.add_supplier_credit_view, name='add_supplier_credit'),
    path('credits/<int:credit_id>/pay/', views.record_credit_payment_view, name='record_credit_payment'),

    # CUSTOMER URLS
    path('customers/', views.customers_view, name='customers'),
    path('customers/register/', views.register_customer_view, name='register_customer'),
    path('customers/<int:customer_id>/edit/', views.edit_customer_view, name='edit_customer'),
    path('customers/<int:customer_id>/delete/', views.delete_customer_view, name='delete_customer'),
    path('customers/<int:customer_id>/', views.customer_detail_view, name='customer_detail'),

    # CUSTOMER CREDIT URLS
    path('sales/<int:sale_id>/credit-payment/', views.record_customer_credit_payment_view, name='record_customer_credit_payment'),


    # PLACEHOLDER URLS (pages not built yet)
    path('deposits/', views.dashboard_view, name='deposits'),
    path('reports/', views.dashboard_view, name='reports'),
]