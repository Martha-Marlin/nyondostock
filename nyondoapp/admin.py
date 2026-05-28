from django.contrib import admin
from .models import (
    StockItem,
    Sale,
    SaleItem,
    Supplier,
    SupplierTransaction,
    SupplierCredit,
    SupplierCreditPayment,
    Customer,
    CustomerCreditPayment,
    Deposit,
    DepositPayment,
)


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ('item_name', 'category', 'quantity', 'unit', 'selling_price', 'stock_status', 'status')
    list_filter = ('category', 'status', 'unit')
    search_fields = ('item_name', 'supplier')


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer_name', 'phone_number', 'total_amount', 'payment_status', 'payment_method', 'sale_date')
    list_filter = ('payment_status', 'payment_method')
    search_fields = ('customer_name', 'phone_number')


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ('sale', 'stock_item', 'quantity', 'unit_price', 'line_total')


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('supplier_name', 'phone', 'balance', 'status', 'payment_terms')
    list_filter = ('status',)
    search_fields = ('supplier_name', 'phone', 'tin_number')


@admin.register(SupplierTransaction)
class SupplierTransactionAdmin(admin.ModelAdmin):
    list_display = ('supplier', 'transaction_type', 'amount', 'payment_method', 'transaction_date')
    list_filter = ('transaction_type', 'payment_method')


@admin.register(SupplierCredit)
class SupplierCreditAdmin(admin.ModelAdmin):
    list_display = ('id', 'supplier', 'total_amount', 'amount_paid', 'due_date', 'status')
    list_filter = ('status',)


@admin.register(SupplierCreditPayment)
class SupplierCreditPaymentAdmin(admin.ModelAdmin):
    list_display = ('credit', 'amount', 'payment_method', 'paid_at')


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'phone_number', 'nin', 'gender', 'area', 'registered_on')
    search_fields = ('full_name', 'phone_number', 'nin')


@admin.register(CustomerCreditPayment)
class CustomerCreditPaymentAdmin(admin.ModelAdmin):
    list_display = ('sale', 'amount', 'payment_method', 'paid_at')


@admin.register(Deposit)
class DepositAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'item_type', 'quantity_ordered', 'total_amount', 'amount_paid', 'status', 'due_date')
    list_filter = ('status', 'item_type')
    search_fields = ('customer__full_name',)


@admin.register(DepositPayment)
class DepositPaymentAdmin(admin.ModelAdmin):
    list_display = ('deposit', 'amount', 'payment_method', 'paid_at')
