# IMPORT DJANGO CORE FUNCTIONS
import re
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.staticfiles import finders
from datetime import datetime
from decimal import Decimal, ROUND_FLOOR
from django.db.models import Q, Sum, F
from django.contrib.auth.decorators import login_required
from .models import (
    StockItem, Sale, SaleItem,
    Supplier, SupplierTransaction, SupplierCredit, SupplierCreditPayment,
    Customer, CustomerCreditPayment,
    Deposit, DepositPayment,
)


# MIDDLEWARE - prevents browser back button from showing protected pages after logout
class NoCacheMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response


# ROLE CONSTANTS
SALES_ROLE = 'Sales Attendant'
MANAGER_ROLE = 'Store Manager'
ACCOUNTS_ROLE = 'Accounts Admin'
STOCK_MANAGER_ROLE = 'Stock Manager'


def user_has_role(user, *roles):
    # Superuser bypasses all role checks
    return user.is_superuser or user.groups.filter(name__in=roles).exists()


def role_home_url(user):
    # Returns the correct dashboard URL for each role
    if user.groups.filter(name=SALES_ROLE).exists():
        return 'sales_dashboard'
    if user.groups.filter(name=ACCOUNTS_ROLE).exists():
        return 'accounts_dashboard'
    if user.groups.filter(name=STOCK_MANAGER_ROLE).exists():
        return 'stock'
    return 'store_manager_dashboard'


def require_roles(request, *roles):
    # Redirects to role home if user doesn't have required role
    if user_has_role(request.user, *roles):
        return None
    messages.error(request, 'You do not have permission to access that page.')
    return redirect(role_home_url(request.user))


def find_deposit_stock_item(item_type, available_only=True):
    # Finds a stock item matching the deposit item type
    stock_items = StockItem.objects.all()
    if available_only:
        stock_items = stock_items.filter(quantity__gt=0)
    for token in item_type.split():
        stock_items = stock_items.filter(item_name__icontains=token)
    return stock_items.first()


def calculate_collectable_quantity(deposit, stock_item):
    # Calculates how many units a customer can collect based on amount paid
    if not stock_item or stock_item.selling_price <= 0:
        return 0
    quantity = (deposit.amount_paid / stock_item.selling_price).to_integral_value(rounding=ROUND_FLOOR)
    return int(quantity)


def _get_receipt_css():
    # Reads the receipt CSS file for inline download rendering
    css_path = finders.find('deposit_receipt.css')
    if not css_path:
        return ''
    with open(css_path, encoding='utf-8') as f:
        return f.read()


def render_receipt_response(request, template_name, context, download_filename):
    # Renders a receipt — either inline or as a downloadable HTML file
    is_download = request.GET.get('download') == '1'
    if is_download:
        context = {
            **context,
            'inline_css': True,
            'receipt_css': _get_receipt_css(),
        }
    response = render(request, template_name, context)
    if is_download:
        response['Content-Disposition'] = f'attachment; filename="{download_filename}"'
    return response


# LANDING PAGE VIEW
def landing_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'nyondoapp/index.html')


# LOGIN VIEW
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()

        # Django server-side validation
        if not username and not password:
            messages.error(request, 'Please enter your username and password.')
        elif not username:
            messages.error(request, 'Please enter your username.')
        elif not password:
            messages.error(request, 'Please enter your password.')
        else:
            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                # Redirect to role-specific dashboard after login
                if user.groups.filter(name='Sales Attendant').exists():
                    return redirect('sales_dashboard')
                if user.groups.filter(name='Accounts Admin').exists():
                    return redirect('accounts_dashboard')
                if user.groups.filter(name='Stock Manager').exists():
                    return redirect('stock')
                return redirect('dashboard')
            else:
                messages.error(request, 'Incorrect username or password. Please try again.')

    return render(request, 'nyondoapp/login.html')


# LOGOUT VIEW
def logout_view(request):
    logout(request)
    messages.success(request, 'Logged out successfully')
    response = redirect('login')
    # Prevent browser back button from showing protected pages after logout
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


# DASHBOARD REDIRECT VIEW - routes user to their role dashboard
@login_required(login_url='login')
def dashboard_view(request):
    return redirect(role_home_url(request.user))


# STORE MANAGER DASHBOARD VIEW
@login_required(login_url='login')
def store_manager_dashboard_view(request):
    denied = require_roles(request, MANAGER_ROLE)
    if denied:
        return denied

    from django.utils import timezone
    today = timezone.now().date()

    all_items = StockItem.objects.all()
    total_items = all_items.count()
    out_of_stock = all_items.filter(quantity=0).count()
    low_stock = all_items.filter(quantity__gt=0, quantity__lte=F('minimum_stock')).count()
    in_stock = total_items - low_stock - out_of_stock

    stock_value = all_items.aggregate(
        total=Sum(F('buying_price') * F('quantity'))
    )['total'] or 0

    low_stock_items = StockItem.objects.filter(
        quantity__gt=0, quantity__lte=F('minimum_stock')
    ).order_by('quantity')[:8]

    out_of_stock_items = StockItem.objects.filter(quantity=0).order_by('item_name')[:8]
    recent_stock = StockItem.objects.all().order_by('-updated_at')[:5]

    supplier_credits_due = SupplierCredit.objects.filter(
        status__in=['Unpaid', 'Partial']
    ).select_related('supplier').order_by('due_date')[:5]

    context = {
        'now': datetime.now(),
        'total_items': total_items,
        'in_stock': in_stock,
        'low_stock': low_stock,
        'out_of_stock': out_of_stock,
        'stock_value': stock_value,
        'low_stock_items': low_stock_items,
        'out_of_stock_items': out_of_stock_items,
        'recent_stock': recent_stock,
        'supplier_credits_due': supplier_credits_due,
    }
    return render(request, 'nyondoapp/store_manager_dashboard.html', context)


# SALES ATTENDANT DASHBOARD VIEW
@login_required(login_url='login')
def sales_dashboard_view(request):
    denied = require_roles(request, SALES_ROLE)
    if denied:
        return denied

    from django.utils import timezone
    today = timezone.now().date()

    todays_sales = Sale.objects.filter(
        sale_date__date=today
    ).prefetch_related('items__stock_item').order_by('-sale_date')

    my_sales_today = todays_sales.filter(sold_by=request.user)

    sales_today_count = todays_sales.count()
    revenue_today = todays_sales.aggregate(total=Sum('total_amount'))['total'] or 0
    pending_credits = Sale.objects.filter(payment_status__in=['Pending', 'Credit']).count()

    stock_items = StockItem.objects.all().order_by('quantity')
    low_stock_count = StockItem.objects.filter(
        quantity__gt=0, quantity__lte=F('minimum_stock')
    ).count()
    out_of_stock_count = StockItem.objects.filter(quantity=0).count()

    context = {
        'now': datetime.now(),
        'todays_sales': todays_sales[:5],
        'my_sales_today': my_sales_today[:5],
        'sales_today_count': sales_today_count,
        'revenue_today': revenue_today,
        'pending_credits': pending_credits,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'stock_items': stock_items[:8],
    }
    return render(request, 'nyondoapp/sales_dashboard.html', context)


# ACCOUNTS ADMIN DASHBOARD VIEW
@login_required(login_url='login')
def admin_dashboard_view(request):
    denied = require_roles(request, ACCOUNTS_ROLE)
    if denied:
        return denied

    from django.utils import timezone
    today = timezone.now().date()
    first_of_month = today.replace(day=1)

    revenue_today = Sale.objects.filter(
        sale_date__date=today, payment_status='Paid'
    ).aggregate(total=Sum('total_amount'))['total'] or 0

    pending_credits_total = Sale.objects.filter(
        payment_status__in=['Pending', 'Credit']
    ).aggregate(total=Sum('total_amount'))['total'] or 0

    supplier_debt_total = Supplier.objects.aggregate(
        total=Sum('balance')
    )['total'] or 0

    active_deposits_paid = Deposit.objects.filter(status='Active').aggregate(
        total=Sum('amount_paid')
    )['total'] or 0

    recent_sales = Sale.objects.select_related('customer').order_by('-sale_date')[:5]

    supplier_credits_due = SupplierCredit.objects.filter(
        status__in=['Unpaid', 'Partial']
    ).select_related('supplier').order_by('due_date')[:5]

    recent_deposits = Deposit.objects.filter(
        status='Active'
    ).select_related('customer').order_by('-created_at')[:5]

    monthly_revenue = Sale.objects.filter(
        sale_date__date__gte=first_of_month, payment_status='Paid'
    ).aggregate(total=Sum('total_amount'))['total'] or 0

    monthly_expenses = SupplierCreditPayment.objects.filter(
        paid_at__date__gte=first_of_month
    ).aggregate(total=Sum('amount'))['total'] or 0

    net_profit = monthly_revenue - monthly_expenses
    outstanding_debt = pending_credits_total + supplier_debt_total

    context = {
        'now': datetime.now(),
        'revenue_today': revenue_today,
        'pending_credits_total': pending_credits_total,
        'supplier_debt_total': supplier_debt_total,
        'active_deposits_paid': active_deposits_paid,
        'recent_sales': recent_sales,
        'supplier_credits_due': supplier_credits_due,
        'recent_deposits': recent_deposits,
        'monthly_revenue': monthly_revenue,
        'monthly_expenses': monthly_expenses,
        'net_profit': net_profit,
        'outstanding_debt': outstanding_debt,
    }
    return render(request, 'nyondoapp/accounts_dashboard.html', context)


# STOCK LIST VIEW
@login_required(login_url='login')
def stock_view(request):
    denied = require_roles(request, SALES_ROLE, MANAGER_ROLE, STOCK_MANAGER_ROLE)
    if denied:
        return denied

    if request.method == 'POST':
        # Only managers can add, edit or delete stock
        denied = require_roles(request, MANAGER_ROLE, STOCK_MANAGER_ROLE)
        if denied:
            return denied

        action = request.POST.get('action', 'create')

        if action == 'delete':
            item = get_object_or_404(StockItem, id=request.POST.get('item_id'))
            item.delete()
            messages.success(request, 'Stock item deleted successfully.')
            return redirect('stock')

        if action == 'create':
            item_name = request.POST.get('item_name', '').strip()
            category = request.POST.get('category', 'Cement')
            unit = request.POST.get('unit', 'Pieces')
            supplier = request.POST.get('supplier', '').strip()

            # If item already exists with same details, add to its quantity
            existing_item = StockItem.objects.filter(
                item_name=item_name,
                category=category,
                unit=unit,
                supplier=supplier
            ).first()

            if existing_item:
                additional_quantity = int(request.POST.get('quantity', 0) or 0)
                existing_item.quantity += additional_quantity
                existing_item.buying_price = request.POST.get('buying_price', 0) or 0
                existing_item.selling_price = request.POST.get('selling_price', 0) or 0
                existing_item.minimum_stock = int(request.POST.get('minimum_stock', 0) or 0)
                existing_item.save()
                messages.success(request, f'Added {additional_quantity} to existing {item_name}. New total: {existing_item.quantity}')
            else:
                StockItem.objects.create(
                    item_name=item_name,
                    category=category,
                    quantity=int(request.POST.get('quantity', 0) or 0),
                    unit=unit,
                    minimum_stock=int(request.POST.get('minimum_stock', 0) or 0),
                    buying_price=request.POST.get('buying_price', 0) or 0,
                    selling_price=request.POST.get('selling_price', 0) or 0,
                    supplier=supplier,
                )
                messages.success(request, 'New stock item added successfully.')

            return redirect('stock')

        if action == 'update':
            item = get_object_or_404(StockItem, id=request.POST.get('item_id'))
            item.item_name = request.POST.get('item_name', '').strip()
            item.category = request.POST.get('category', 'Cement')
            item.quantity = int(request.POST.get('quantity', 0) or 0)
            item.unit = request.POST.get('unit', 'Pieces')
            item.minimum_stock = int(request.POST.get('minimum_stock', 0) or 0)
            item.buying_price = request.POST.get('buying_price', 0) or 0
            item.selling_price = request.POST.get('selling_price', 0) or 0
            item.supplier = request.POST.get('supplier', '').strip()
            item.save()
            messages.success(request, 'Stock item updated successfully.')
            return redirect('stock')

    # GET - filter and search stock items
    stock_filter = request.GET.get('filter', '')
    search = request.GET.get('search', '')
    items = StockItem.objects.all()

    if search:
        items = items.filter(item_name__icontains=search)

    if stock_filter == 'in_stock':
        items = items.filter(quantity__gt=F('minimum_stock'))
    elif stock_filter == 'low':
        items = items.filter(quantity__gt=0, quantity__lte=F('minimum_stock'))
    elif stock_filter == 'out':
        items = items.filter(quantity=0)

    items = items.order_by('-id')
    total_items = items.count()
    out_of_stock = items.filter(quantity=0).count()
    low_stock = items.filter(quantity__gt=0, quantity__lte=F('minimum_stock')).count()
    in_stock = total_items - low_stock - out_of_stock

    context = {
        'items': items,
        'total_items': total_items,
        'in_stock': in_stock,
        'low_stock': low_stock,
        'out_of_stock': out_of_stock,
        'stock_filter': stock_filter,
        'search': search,
        'low_stock_count': StockItem.objects.filter(quantity__gt=0, quantity__lte=F('minimum_stock')).count(),
        'suppliers': Supplier.objects.all().order_by('supplier_name'),
    }
    return render(request, 'nyondoapp/stock.html', context)


# RECORD SALES PAGE VIEW
@login_required(login_url='login')
def record_sales_view(request):
    denied = require_roles(request, SALES_ROLE)
    if denied:
        return denied

    stock_items = StockItem.objects.filter(quantity__gt=0)
    registered_customers = Customer.objects.all().order_by('full_name')
    context = {
        'now': datetime.now(),
        'stock_items': stock_items,
        'registered_customers': registered_customers,
    }
    return render(request, 'nyondoapp/record_sales.html', context)

# ADD SALE VIEW
@login_required(login_url='login')
def add_sale_view(request):
    denied = require_roles(request, SALES_ROLE)
    if denied:
        return denied

    if request.method == 'POST':
        customer_name = request.POST.get('customer_name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        item_ids = request.POST.getlist('item[]')
        quantities = request.POST.getlist('quantity[]')
        wants_delivery = request.POST.get('wants_delivery', '') == 'yes'
        distance = int(request.POST.get('distance') or 0) if wants_delivery else 0
        payment_status = request.POST.get('payment_status', 'Pending')
        payment_method = request.POST.get('payment_method', 'Cash')
        notes = request.POST.get('notes', '').strip()

        # ---- SERVER-SIDE VALIDATION ----
        if not customer_name:
            messages.error(request, 'Customer name is required.')
            return redirect('record_sales')

        if not phone_number:
            messages.error(request, 'Phone number is required.')
            return redirect('record_sales')

        if not re.match(r'^(07|03)\d{8}$', phone_number.replace(' ', '')):
            messages.error(request, 'Enter a valid Ugandan phone number (e.g. 0701234567).')
            return redirect('record_sales')

        if not item_ids or all(not i for i in item_ids):
            messages.error(request, 'Please select at least one item.')
            return redirect('record_sales')
        # ---- END VALIDATION ----

        # Credit sales must be linked to a registered customer
        registered_customer = None
        if payment_status.capitalize() == 'Credit':
            registered_customer_id = request.POST.get('registered_customer_id')
            if not registered_customer_id:
                messages.error(request, 'Credit sales must be linked to a registered customer.')
                return redirect('record_sales')
            registered_customer = get_object_or_404(Customer, id=registered_customer_id)
            customer_name = registered_customer.full_name
            phone_number = registered_customer.phone_number

        payment_status = payment_status.capitalize()
        payment_method_map = {
            'cash': 'Cash',
            'mobile_money': 'Mobile Money',
            'bank_transfer': 'Bank Transfer',
        }
        payment_method = payment_method_map.get(payment_method, 'Cash')

        if not item_ids:
            messages.error(request, 'Please add at least one item.')
            return redirect('record_sales')

        sale_items = []
        subtotal = Decimal('0')

        for i, item_id in enumerate(item_ids):
            if not item_id:
                continue
            quantity = int(quantities[i]) if i < len(quantities) else 1
            if quantity <= 0:
                messages.error(request, 'Quantity must be greater than zero for all items.')
                return redirect('record_sales')
            stock_item = get_object_or_404(StockItem, id=item_id)
            unit_price = stock_item.selling_price
            if quantity > stock_item.quantity:
                messages.error(
                    request,
                    f'Not enough stock for {stock_item.item_name}. Only {stock_item.quantity} {stock_item.unit} available.'
                )
                return redirect('record_sales')
            line_total = unit_price * quantity
            subtotal += line_total
            sale_items.append({
                'stock_item': stock_item,
                'quantity': quantity,
                'unit_price': unit_price,
                'line_total': line_total,
            })

        # Transport rule: free within 10km for orders above 500k, else 30k flat
        if not wants_delivery:
            transport_charge = Decimal('0')
        elif distance <= 10 and subtotal >= 500000:
            transport_charge = Decimal('0')
        else:
            transport_charge = Decimal('30000')

        total_amount = subtotal + transport_charge

        sale = Sale.objects.create(
            customer_name=customer_name,
            phone_number=phone_number,
            customer=registered_customer,
            subtotal=subtotal,
            transport_charge=transport_charge,
            total_amount=total_amount,
            payment_status=payment_status,
            payment_method=payment_method,
            notes=notes,
            sold_by=request.user,
        )

        # Save sale items and reduce stock quantities
        for item_data in sale_items:
            SaleItem.objects.create(
                sale=sale,
                stock_item=item_data['stock_item'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                line_total=item_data['line_total'],
            )
            item_data['stock_item'].quantity -= item_data['quantity']
            item_data['stock_item'].save()

        messages.success(request, f'Sale #{sale.id} recorded successfully!')

        if request.POST.get('action') == 'save_print':
            return redirect('print_receipt', sale_id=sale.id)

        return redirect('sales_list')

    return redirect('record_sales')


# DELETE SALE VIEW - restores stock quantities on deletion
@login_required(login_url='login')
def delete_sale_view(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id)
    if request.method == 'POST':
        for item in sale.items.all():
            if item.stock_item:
                item.stock_item.quantity += item.quantity
                item.stock_item.save()
        sale.delete()
        messages.success(request, f'Sale #{sale_id} deleted successfully.')
    return redirect('sales_list')


# EDIT SALE VIEW - updates customer info and payment details only
@login_required(login_url='login')
def edit_sale_view(request, sale_id):
    denied = require_roles(request, SALES_ROLE)
    if denied:
        return denied

    sale = get_object_or_404(Sale, id=sale_id)
    if request.method == 'POST':
        sale.customer_name = request.POST.get('customer_name', '').strip()
        sale.phone_number = request.POST.get('phone_number', '').strip()
        sale.payment_status = request.POST.get('payment_status', 'Pending').capitalize()
        payment_method_map = {
            'cash': 'Cash',
            'mobile_money': 'Mobile Money',
            'bank_transfer': 'Bank Transfer',
        }
        sale.payment_method = payment_method_map.get(request.POST.get('payment_method', 'cash'), 'Cash')
        sale.notes = request.POST.get('notes', '').strip()
        sale.save()
        messages.success(request, f'Sale #{sale_id} updated successfully.')
    return redirect('sales_list')


# PRINT RECEIPT VIEW
@login_required(login_url='login')
def print_receipt_view(request, sale_id):
    denied = require_roles(request, SALES_ROLE)
    if denied:
        return denied

    sale = get_object_or_404(Sale, id=sale_id)
    items = sale.items.select_related('stock_item').all()
    context = {
        'sale': sale,
        'items': items,
    }
    return render_receipt_response(
        request,
        'nyondoapp/receipt.html',
        context,
        f'sale-receipt-{sale.id}.html',
    )


# SALES LIST VIEW
@login_required(login_url='login')
def sales_list_view(request):
    denied = require_roles(request, SALES_ROLE, STOCK_MANAGER_ROLE)
    if denied:
        return denied

    sales_list = Sale.objects.prefetch_related('items__stock_item').all()

    search = request.GET.get('search', '')
    status = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if search:
        sales_list = sales_list.filter(
            Q(customer_name__icontains=search) |
            Q(phone_number__icontains=search)
        )
    if status and status != 'All Status':
        sales_list = sales_list.filter(payment_status=status)
    if date_from:
        sales_list = sales_list.filter(sale_date__gte=date_from)
    if date_to:
        sales_list = sales_list.filter(sale_date__lte=date_to)

    sales_list = sales_list.order_by('-sale_date', '-id')

    context = {
        'sales': sales_list,
        'search': search,
        'status': status,
        'date_from': date_from,
        'date_to': date_to,
        'total_sales': sales_list.count(),
        'total_revenue': sales_list.aggregate(total=Sum('total_amount'))['total'] or 0,
        'pending_count': sales_list.filter(payment_status='Pending').count(),
        'credit_count': sales_list.filter(payment_status='Credit').count(),
        'low_stock_count': StockItem.objects.filter(quantity__gt=0, quantity__lte=F('minimum_stock')).count(),
        'now': datetime.now(),
    }
    return render(request, 'nyondoapp/sales_list.html', context)


# SUPPLIERS LIST VIEW
@login_required(login_url='login')
def suppliers_view(request):
    denied = require_roles(request, ACCOUNTS_ROLE, MANAGER_ROLE)
    if denied:
        return denied

    suppliers = Supplier.objects.all()
    search = request.GET.get('search', '')
    status = request.GET.get('status', '')

    if search:
        suppliers = suppliers.filter(
            Q(supplier_name__icontains=search) |
            Q(phone__icontains=search)
        )
    if status and status != 'All Status':
        suppliers = suppliers.filter(status=status)

    suppliers = suppliers.order_by('id')

    context = {
        'suppliers': suppliers,
        'search': search,
        'status': status,
        'total_suppliers': suppliers.count(),
        'credits_due': suppliers.filter(status='Credits Due').count(),
        'overdue': suppliers.filter(status='Overdue').count(),
        'total_owed': suppliers.aggregate(total=Sum('balance'))['total'] or 0,
    }
    return render(request, 'nyondoapp/suppliers.html', context)


# ADD SUPPLIER VIEW
@login_required(login_url='login')
def add_supplier_view(request):
    denied = require_roles(request, ACCOUNTS_ROLE, MANAGER_ROLE)
    if denied:
        return denied

    if request.method == 'POST':
        phone = request.POST.get('phone', '').strip()
        if Supplier.objects.filter(phone=phone).exists():
            messages.error(request, 'A supplier with this phone number already exists.')
            return redirect('suppliers')

        Supplier.objects.create(
            supplier_name=request.POST.get('supplier_name', '').strip(),
            phone=phone,
            tin_number=request.POST.get('tin_number', '').strip() or None,
            email=request.POST.get('email', '').strip() or None,
            location=request.POST.get('location', '').strip() or None,
            balance=Decimal(request.POST.get('initial_balance', 0) or 0),
            payment_terms=int(request.POST.get('payment_terms', 30)),
            notes=request.POST.get('notes', '').strip() or None,
            created_by=request.user,
        )
        messages.success(request, f'{request.POST.get("supplier_name")} added successfully!')
    return redirect('suppliers')


# EDIT SUPPLIER VIEW
@login_required(login_url='login')
def edit_supplier_view(request, supplier_id):
    denied = require_roles(request, ACCOUNTS_ROLE, MANAGER_ROLE)
    if denied:
        return denied

    supplier = get_object_or_404(Supplier, id=supplier_id)
    if request.method == 'POST':
        supplier.supplier_name = request.POST.get('supplier_name', '').strip()
        supplier.phone = request.POST.get('phone', '').strip()
        supplier.tin_number = request.POST.get('tin_number', '').strip() or None
        supplier.email = request.POST.get('email', '').strip() or None
        supplier.location = request.POST.get('location', '').strip() or None
        supplier.payment_terms = int(request.POST.get('payment_terms', 30))
        supplier.status = request.POST.get('status', 'Active')
        supplier.notes = request.POST.get('notes', '').strip() or None
        supplier.save()
        messages.success(request, f'{supplier.supplier_name} updated successfully.')
    return redirect('suppliers')


# DELETE SUPPLIER VIEW
@login_required(login_url='login')
def delete_supplier_view(request, supplier_id):
    denied = require_roles(request, ACCOUNTS_ROLE, MANAGER_ROLE)
    if denied:
        return denied

    supplier = get_object_or_404(Supplier, id=supplier_id)
    if request.method == 'POST':
        name = supplier.supplier_name
        supplier.delete()
        messages.success(request, f'{name} deleted successfully.')
    return redirect('suppliers')


# SUPPLIER TRANSACTIONS VIEW
@login_required(login_url='login')
def supplier_transactions_view(request, supplier_id):
    denied = require_roles(request, ACCOUNTS_ROLE, MANAGER_ROLE)
    if denied:
        return denied

    supplier = get_object_or_404(Supplier, id=supplier_id)
    context = {
        'supplier': supplier,
        'transactions': supplier.transactions.all(),
        'low_stock_count': StockItem.objects.filter(quantity__gt=0, quantity__lte=F('minimum_stock')).count(),
    }
    return render(request, 'nyondoapp/supplier_transactions.html', context)


# RECORD SUPPLIER TRANSACTION VIEW
@login_required(login_url='login')
def record_payment_view(request, supplier_id):
    denied = require_roles(request, ACCOUNTS_ROLE, MANAGER_ROLE)
    if denied:
        return denied

    supplier = get_object_or_404(Supplier, id=supplier_id)
    if request.method == 'POST':
        transaction_type = request.POST.get('transaction_type', 'Payment')
        amount = Decimal(request.POST.get('amount', 0))

        SupplierTransaction.objects.create(
            supplier=supplier,
            transaction_type=transaction_type,
            amount=amount,
            payment_method=request.POST.get('payment_method', 'Cash'),
            reference_number=request.POST.get('reference_number', '').strip() or None,
            description=request.POST.get('description', '').strip() or None,
            created_by=request.user,
        )

        # Update supplier balance based on transaction type
        if transaction_type == 'Credit':
            supplier.balance += amount
        elif transaction_type in ['Payment', 'Adjustment']:
            supplier.balance -= amount
        supplier.save()

        messages.success(request, f'Transaction of UGX {amount:,.0f} recorded successfully.')
    return redirect('supplier_transactions', supplier_id=supplier.id)


# SUPPLIER CREDIT DETAIL VIEW
@login_required(login_url='login')
def supplier_credit_detail_view(request, supplier_id):
    denied = require_roles(request, ACCOUNTS_ROLE, MANAGER_ROLE)
    if denied:
        return denied

    supplier = get_object_or_404(Supplier, id=supplier_id)
    credits = supplier.credits.all()
    total_owed = sum(c.total_amount for c in credits)
    total_paid = sum(c.amount_paid for c in credits)

    context = {
        'supplier': supplier,
        'credits': credits,
        'total_owed': total_owed,
        'total_paid': total_paid,
        'total_outstanding': total_owed - total_paid,
        'unpaid_count': credits.filter(status='Unpaid').count(),
        'partial_count': credits.filter(status='Partial').count(),
    }
    return render(request, 'nyondoapp/supplier_credit_detail.html', context)


# ADD SUPPLIER CREDIT VIEW
@login_required(login_url='login')
def add_supplier_credit_view(request, supplier_id):
    denied = require_roles(request, ACCOUNTS_ROLE, MANAGER_ROLE)
    if denied:
        return denied

    supplier = get_object_or_404(Supplier, id=supplier_id)
    if request.method == 'POST':
        total_amount = Decimal(request.POST.get('total_amount') or 0)
        SupplierCredit.objects.create(
            supplier=supplier,
            description=request.POST.get('description', '').strip(),
            total_amount=total_amount,
            due_date=request.POST.get('due_date'),
            created_by=request.user,
        )
        supplier.balance += total_amount
        supplier.status = 'Credits Due'
        supplier.save()
        messages.success(request, f'Credit of UGX {total_amount:,.0f} recorded for {supplier.supplier_name}.')
    return redirect('supplier_credit_detail', supplier_id=supplier.id)


# RECORD CREDIT PAYMENT VIEW
@login_required(login_url='login')
def record_credit_payment_view(request, credit_id):
    denied = require_roles(request, ACCOUNTS_ROLE, MANAGER_ROLE)
    if denied:
        return denied

    credit = get_object_or_404(SupplierCredit, id=credit_id)
    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount') or 0)

        SupplierCreditPayment.objects.create(
            credit=credit,
            amount=amount,
            payment_method=request.POST.get('payment_method', 'Cash'),
            reference_number=request.POST.get('reference_number', '').strip() or None,
            note=request.POST.get('note', '').strip() or None,
            paid_by=request.user,
        )

        credit.amount_paid += amount
        credit.status = 'Cleared' if credit.amount_paid >= credit.total_amount else 'Partial'
        credit.save()

        # Reduce supplier balance and mark active if fully cleared
        supplier = credit.supplier
        supplier.balance -= amount
        if supplier.balance <= 0:
            supplier.balance = Decimal('0.00')
            supplier.status = 'Active'
        supplier.save()

        messages.success(request, f'Payment of UGX {amount:,.0f} recorded successfully.')
    return redirect('supplier_credit_detail', supplier_id=credit.supplier.id)


# CUSTOMERS LIST VIEW
@login_required(login_url='login')
def customers_view(request):
    customers = Customer.objects.all().order_by('-registered_on')
    search = request.GET.get('search', '')
    gender = request.GET.get('gender', '')

    if search:
        customers = customers.filter(
            Q(full_name__icontains=search) |
            Q(phone_number__icontains=search) |
            Q(nin__icontains=search)
        )
    if gender:
        customers = customers.filter(gender=gender)

    context = {
        'customers': customers,
        'search': search,
        'gender': request.GET.get('gender', ''),
        'total_customers': customers.count(),
        'low_stock_count': StockItem.objects.filter(quantity__gt=0, quantity__lte=F('minimum_stock')).count(),
    }
    return render(request, 'nyondoapp/customers_list.html', context)


# REGISTER CUSTOMER VIEW - only Accounts Admin can register
@login_required(login_url='login')
def register_customer_view(request):
    denied = require_roles(request, ACCOUNTS_ROLE)
    if denied:
        return denied

    low_stock_count = StockItem.objects.filter(quantity__gt=0, quantity__lte=F('minimum_stock')).count()
    context = {'low_stock_count': low_stock_count}

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        nin = request.POST.get('nin', '').strip().upper()
        area = request.POST.get('area', '').strip() or None
        notes = request.POST.get('notes', '').strip() or None

        # ---- SERVER-SIDE VALIDATION ----
        if not full_name:
            messages.error(request, 'Full name is required.')
            return render(request, 'nyondoapp/register_customer.html', context)

        if not phone_number:
            messages.error(request, 'Phone number is required.')
            return render(request, 'nyondoapp/register_customer.html', context)

        if not re.match(r'^(07|03)\d{8}$', phone_number.replace(' ', '')):
            messages.error(request, 'Enter a valid Ugandan phone number (e.g. 0701234567).')
            return render(request, 'nyondoapp/register_customer.html', context)

        if not nin:
            messages.error(request, 'NIN is required.')
            return render(request, 'nyondoapp/register_customer.html', context)

        if len(nin) != 14:
            messages.error(request, 'NIN must be exactly 14 characters.')
            return render(request, 'nyondoapp/register_customer.html', context)

        nin_prefix = nin[:2]
        if nin_prefix not in ['CM', 'CF']:
            messages.error(request, 'Invalid NIN format. Must start with CM (Male) or CF (Female).')
            return render(request, 'nyondoapp/register_customer.html', context)
        # ---- END VALIDATION ----

        gender = 'M' if nin_prefix == 'CM' else 'F'

        if Customer.objects.filter(nin=nin).exists():
            messages.error(request, f'A customer with NIN {nin} is already registered.')
            return render(request, 'nyondoapp/register_customer.html', context)

        if Customer.objects.filter(phone_number=phone_number).exists():
            messages.error(request, 'A customer with this phone number is already registered.')
            return render(request, 'nyondoapp/register_customer.html', context)

        Customer.objects.create(
            full_name=full_name,
            phone_number=phone_number,
            nin=nin,
            gender=gender,
            area=area,
            notes=notes,
            registered_by=request.user,
        )
        messages.success(request, f'{full_name} registered successfully!')
        return redirect('customers')

    return render(request, 'nyondoapp/register_customer.html', context) 

# EDIT CUSTOMER VIEW
@login_required(login_url='login')
def edit_customer_view(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id)
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        nin = request.POST.get('nin', '').strip().upper()
        area = request.POST.get('area', '').strip() or None
        notes = request.POST.get('notes', '').strip() or None

        if len(nin) != 14:
            messages.error(request, 'NIN must be exactly 14 characters.')
            return redirect('customers')

        nin_prefix = nin[:2]
        if nin_prefix not in ['CM', 'CF']:
            messages.error(request, 'Invalid NIN format. Must start with CM (Male) or CF (Female).')
            return redirect('customers')

        if Customer.objects.filter(nin=nin).exclude(id=customer.id).exists():
            messages.error(request, f'A customer with NIN {nin} is already registered.')
            return redirect('customers')

        gender = 'M' if nin_prefix == 'CM' else 'F'

        customer.full_name = full_name
        customer.phone_number = phone_number
        customer.nin = nin
        customer.gender = gender
        customer.area = area
        customer.notes = notes
        customer.save()
        messages.success(request, f'{customer.full_name} updated successfully.')
    return redirect('customers')


# DELETE CUSTOMER VIEW - blocked if customer has deposits
@login_required(login_url='login')
def delete_customer_view(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id)
    if request.method == 'POST':
        if customer.deposits.exists():
            messages.error(request, f'Cannot delete {customer.full_name}. They have deposits on record. Cancel or complete all deposits first.')
            return redirect('customers')
        name = customer.full_name
        customer.delete()
        messages.success(request, f'{name} removed successfully.')
    return redirect('customers')


# CUSTOMER DETAIL VIEW - shows credit history and payment tracking
@login_required(login_url='login')
def customer_detail_view(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id)
    credit_sales = Sale.objects.filter(
        customer=customer
    ).prefetch_related('items__stock_item', 'credit_payments').order_by('-sale_date')

    credit_sales_data = []
    for sale in credit_sales:
        total_paid = sale.credit_payments.aggregate(total=Sum('amount'))['total'] or 0
        balance_due = sale.total_amount - total_paid
        percent_paid = int((total_paid / sale.total_amount) * 100) if sale.total_amount > 0 else 0
        credit_sales_data.append({
            'sale': sale,
            'total_paid': total_paid,
            'balance_due': balance_due,
            'percent_paid': percent_paid,
        })

    context = {
        'customer': customer,
        'credit_sales_data': credit_sales_data,
        'low_stock_count': StockItem.objects.filter(quantity__gt=0, quantity__lte=F('minimum_stock')).count(),
    }
    return render(request, 'nyondoapp/customer_detail.html', context)


# RECORD CUSTOMER CREDIT PAYMENT VIEW
@login_required(login_url='login')
def record_customer_credit_payment_view(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id)
    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount') or 0)
        total_already_paid = sale.credit_payments.aggregate(total=Sum('amount'))['total'] or 0

        if amount > (sale.total_amount - total_already_paid):
            messages.error(request, f'Amount exceeds balance due. Maximum payable is UGX {sale.total_amount - total_already_paid:,.0f}.')
            return redirect('customer_detail', customer_id=sale.customer.id)

        CustomerCreditPayment.objects.create(
            sale=sale,
            amount=amount,
            payment_method=request.POST.get('payment_method', 'Cash'),
            reference_number=request.POST.get('reference_number', '').strip() or None,
            note=request.POST.get('note', '').strip() or None,
            paid_by=request.user,
        )

        total_paid = sale.credit_payments.aggregate(total=Sum('amount'))['total'] or 0
        if total_paid >= sale.total_amount:
            sale.payment_status = 'Paid'
            sale.save()
            messages.success(request, f'Payment recorded. Sale #{sale.id} is now fully paid!')
        else:
            messages.success(request, f'Payment of UGX {amount:,.0f} recorded. Balance remaining: UGX {sale.total_amount - total_paid:,.0f}.')

    return redirect('customer_detail', customer_id=sale.customer.id)


# DEPOSITS LIST VIEW
@login_required(login_url='login')
def deposits_view(request):
    denied = require_roles(request, ACCOUNTS_ROLE)
    if denied:
        return denied

    deposits = Deposit.objects.all().order_by('-created_at')
    search = request.GET.get('search', '')
    status = request.GET.get('status', '')
    item_type = request.GET.get('item_type', '')

    if search:
        deposits = deposits.filter(
            Q(customer__full_name__icontains=search) |
            Q(customer__phone_number__icontains=search)
        )
    if status:
        deposits = deposits.filter(status=status)
    if item_type:
        deposits = deposits.filter(item_type=item_type)

    active_deps = deposits.filter(status='Active')
    total_active_paid = active_deps.aggregate(total=Sum('amount_paid'))['total'] or 0

    context = {
        'deposits': deposits,
        'search': search,
        'status': status,
        'item_type': item_type,
        'total_deposits': deposits.count(),
        'active_count': deposits.filter(status='Active').count(),
        'completed_count': deposits.filter(status='Completed').count(),
        'total_active_paid': total_active_paid,
        'low_stock_count': StockItem.objects.filter(quantity__gt=0, quantity__lte=F('minimum_stock')).count(),
        'today': datetime.now().date(),
    }
    return render(request, 'nyondoapp/deposits.html', context)


# CREATE DEPOSIT VIEW
@login_required(login_url='login')
def create_deposit_view(request):
    denied = require_roles(request, ACCOUNTS_ROLE)
    if denied:
        return denied

    customers = Customer.objects.all().order_by('full_name')
    low_stock_count = StockItem.objects.filter(quantity__gt=0, quantity__lte=F('minimum_stock')).count()

    if request.method == 'POST':
        customer_id = request.POST.get('customer_id', '').strip()
        item_type = request.POST.get('item_type', '').strip()
        quantity_ordered = request.POST.get('quantity_ordered', '').strip()
        unit = request.POST.get('unit', 'Bags')
        due_date = request.POST.get('due_date', '').strip()
        notes = request.POST.get('notes', '').strip() or None

        context = {
            'customers': customers,
            'low_stock_count': low_stock_count,
        }

        # ---- SERVER-SIDE VALIDATION ----
        if not customer_id:
            messages.error(request, 'Please select a registered customer.')
            return render(request, 'nyondoapp/create_deposit.html', context)

        if not item_type:
            messages.error(request, 'Please select an item type.')
            return render(request, 'nyondoapp/create_deposit.html', context)

        if not due_date:
            messages.error(request, 'Expected collection date is required.')
            return render(request, 'nyondoapp/create_deposit.html', context)

        # Due date must not be in the past
        from django.utils import timezone
        due_date_parsed = datetime.strptime(due_date, '%Y-%m-%d').date()
        if due_date_parsed < timezone.now().date():
            messages.error(request, 'Expected collection date cannot be in the past.')
            return render(request, 'nyondoapp/create_deposit.html', context)

        quantity_ordered = int(quantity_ordered) if quantity_ordered else 0

        if quantity_ordered < 0:
            messages.error(request, 'Estimated quantity cannot be negative.')
            return render(request, 'nyondoapp/create_deposit.html', context)
        # ---- END VALIDATION ----

        customer = get_object_or_404(Customer, id=customer_id)
        stock_item = find_deposit_stock_item(item_type, available_only=False)
        total_amount = stock_item.selling_price * quantity_ordered if stock_item and quantity_ordered > 0 else Decimal('0')

        deposit = Deposit.objects.create(
            customer=customer,
            item_type=item_type,
            quantity_ordered=quantity_ordered,
            unit=unit,
            total_amount=total_amount,
            due_date=due_date,
            notes=notes,
            created_by=request.user,
        )
        messages.success(request, f'Deposit #{deposit.id} opened for {customer.full_name}. Goods will be calculated from amount paid on collection day.')
        return redirect('deposit_detail', deposit_id=deposit.id)

    return render(request, 'nyondoapp/create_deposit.html', {'customers': customers, 'low_stock_count': low_stock_count})

# DEPOSIT DETAIL VIEW
@login_required(login_url='login')
def deposit_detail_view(request, deposit_id):
    denied = require_roles(request, ACCOUNTS_ROLE)
    if denied:
        return denied

    deposit = get_object_or_404(Deposit, id=deposit_id)
    context = {
        'deposit': deposit,
        'payments': deposit.payments.all().order_by('-paid_at'),
        'low_stock_count': StockItem.objects.filter(quantity__gt=0, quantity__lte=F('minimum_stock')).count(),
        'today': datetime.now().date(),
    }
    return render(request, 'nyondoapp/deposit_detail.html', context)


# RECORD DEPOSIT PAYMENT VIEW
@login_required(login_url='login')
def record_deposit_payment_view(request, deposit_id):
    denied = require_roles(request, ACCOUNTS_ROLE)
    if denied:
        return denied

    deposit = get_object_or_404(Deposit, id=deposit_id)
    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount') or 0)

        if amount <= 0:
            messages.error(request, 'Payment amount must be greater than zero.')
            return redirect('deposit_detail', deposit_id=deposit.id)

        payment = DepositPayment.objects.create(
            deposit=deposit,
            amount=amount,
            payment_method=request.POST.get('payment_method', 'Cash'),
            reference_number=request.POST.get('reference_number', '').strip() or None,
            note=request.POST.get('note', '').strip() or None,
            paid_by=request.user,
        )

        deposit.amount_paid += amount
        deposit.save()
        messages.success(request, f'Temporary receipt created for UGX {amount:,.0f}. Goods will be determined on collection day.')
        return redirect('deposit_receipt', payment_id=payment.id)

    return redirect('deposit_detail', deposit_id=deposit.id)


# CANCEL DEPOSIT VIEW
@login_required(login_url='login')
def cancel_deposit_view(request, deposit_id):
    denied = require_roles(request, ACCOUNTS_ROLE)
    if denied:
        return denied

    deposit = get_object_or_404(Deposit, id=deposit_id)
    if request.method == 'POST':
        if deposit.status != 'Active':
            messages.error(request, 'Only active deposits can be cancelled.')
            return redirect('deposit_detail', deposit_id=deposit.id)
        deposit.status = 'Cancelled'
        deposit.save()
        messages.success(request, f'Deposit #{deposit.id} cancelled.')
    return redirect('deposits')


# DEPOSIT RECEIPT VIEW - temporary receipt per payment
@login_required(login_url='login')
def deposit_receipt_view(request, payment_id):
    denied = require_roles(request, ACCOUNTS_ROLE)
    if denied:
        return denied

    payment = get_object_or_404(DepositPayment, id=payment_id)
    context = {
        'payment': payment,
        'deposit': payment.deposit,
    }
    return render_receipt_response(
        request,
        'nyondoapp/deposit_receipt.html',
        context,
        f'deposit-receipt-{payment.deposit.id}-payment-{payment.id}.html',
    )


# COLLECT DEPOSIT VIEW - deducts stock and marks deposit as completed
@login_required(login_url='login')
def collect_deposit_view(request, deposit_id):
    denied = require_roles(request, ACCOUNTS_ROLE)
    if denied:
        return denied

    deposit = get_object_or_404(Deposit, id=deposit_id)
    if request.method != 'POST':
        return redirect('deposit_detail', deposit_id=deposit.id)

    if deposit.status != 'Active':
        messages.error(request, 'Only active deposits can be collected.')
        return redirect('deposit_detail', deposit_id=deposit.id)

    stock_item = find_deposit_stock_item(deposit.item_type)
    if not stock_item:
        messages.error(request, f'No available stock found for {deposit.item_type}.')
        return redirect('deposit_detail', deposit_id=deposit.id)

    quantity = calculate_collectable_quantity(deposit, stock_item)
    if quantity <= 0:
        messages.error(request, f'The amount paid is not enough to collect one {stock_item.unit} of {deposit.item_type}.')
        return redirect('deposit_detail', deposit_id=deposit.id)

    if stock_item.quantity < quantity:
        messages.error(request, f'Not enough stock for collection. {stock_item.quantity} {stock_item.unit} available, but paid amount covers {quantity}.')
        return redirect('deposit_detail', deposit_id=deposit.id)

    collected_value = stock_item.selling_price * quantity
    stock_item.quantity -= quantity
    stock_item.save()

    deposit.quantity_ordered = quantity
    deposit.unit = stock_item.unit
    deposit.total_amount = collected_value
    deposit.status = 'Completed'
    deposit.save()

    messages.success(request, f'Deposit #{deposit.id} collected: {quantity} {stock_item.unit} of {deposit.item_type}.')
    return redirect('collection_receipt', deposit_id=deposit.id)


# EDIT DEPOSIT VIEW - only active deposits can be edited
@login_required(login_url='login')
def edit_deposit_view(request, deposit_id):
    denied = require_roles(request, ACCOUNTS_ROLE)
    if denied:
        return denied

    deposit = get_object_or_404(Deposit, id=deposit_id)

    if deposit.status != 'Active':
        messages.error(request, 'Only active deposits can be edited.')
        return redirect('deposit_detail', deposit_id=deposit.id)

    if request.method == 'POST':
        new_item_type = request.POST.get('item_type', '').strip()
        new_quantity = int(request.POST.get('quantity_ordered') or 0)

        if new_quantity < 0:
            messages.error(request, 'Estimated quantity cannot be negative.')
            return redirect('deposit_detail', deposit_id=deposit.id)

        stock_item = find_deposit_stock_item(new_item_type, available_only=False)
        new_total = stock_item.selling_price * new_quantity if stock_item and new_quantity > 0 else Decimal('0')
        deposit.item_type = new_item_type
        deposit.quantity_ordered = new_quantity
        deposit.unit = request.POST.get('unit', 'Bags')
        deposit.due_date = request.POST.get('due_date')
        deposit.notes = request.POST.get('notes', '').strip() or None
        deposit.total_amount = new_total
        deposit.save()

        messages.success(request, f'Deposit #{deposit.id} updated successfully. Stock will still be deducted only on collection day.')
    return redirect('deposit_detail', deposit_id=deposit.id)


# COLLECTION RECEIPT VIEW - official receipt for completed deposits
@login_required(login_url='login')
def collection_receipt_view(request, deposit_id):
    denied = require_roles(request, ACCOUNTS_ROLE)
    if denied:
        return denied

    deposit = get_object_or_404(Deposit, id=deposit_id)
    if deposit.status != 'Completed':
        messages.error(request, 'Collection receipt is only available for completed deposits.')
        return redirect('deposit_detail', deposit_id=deposit.id)

    context = {
        'deposit': deposit,
        'payments': deposit.payments.all().order_by('paid_at'),
    }
    return render_receipt_response(
        request,
        'nyondoapp/collection_receipt.html',
        context,
        f'collection-receipt-{deposit.id}.html',
    )


# REPORTS VIEW
@login_required(login_url='login')
def reports_view(request):
    denied = require_roles(request, ACCOUNTS_ROLE)
    if denied:
        return denied

    from django.utils import timezone
    today = timezone.now().date()

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    report_type = request.GET.get('report_type', 'sales')

    date_from = datetime.strptime(date_from, '%Y-%m-%d').date() if date_from else today.replace(day=1)
    date_to = datetime.strptime(date_to, '%Y-%m-%d').date() if date_to else today

    # Summary stat cards - all time totals
    total_revenue = Sale.objects.filter(payment_status='Paid').aggregate(total=Sum('total_amount'))['total'] or 0
    total_transport = Sale.objects.filter(transport_charge__gt=0).aggregate(total=Sum('transport_charge'))['total'] or 0
    total_deposits = Deposit.objects.aggregate(total=Sum('amount_paid'))['total'] or 0
    total_supplier_credit = SupplierCredit.objects.filter(status__in=['Unpaid', 'Partial']).aggregate(total=Sum('total_amount'))['total'] or 0

    # Sales filtered by date range
    sales = Sale.objects.filter(
        sale_date__date__gte=date_from,
        sale_date__date__lte=date_to
    ).select_related('customer', 'sold_by').order_by('-sale_date')

    sales_total = sales.aggregate(total=Sum('total_amount'))['total'] or 0
    sales_transport = sales.aggregate(total=Sum('transport_charge'))['total'] or 0
    sales_outstanding = sales.filter(payment_status__in=['Pending', 'Credit']).aggregate(total=Sum('total_amount'))['total'] or 0

    # Transport report - sales where company absorbed delivery cost
    transport_sales = Sale.objects.filter(
        sale_date__date__gte=date_from,
        sale_date__date__lte=date_to,
        wants_delivery=True,
        transport_charge=0
    ).select_related('customer').order_by('-sale_date')

    deposits = Deposit.objects.filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to
    ).select_related('customer').order_by('-created_at')

    supplier_credits = SupplierCredit.objects.filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to
    ).select_related('supplier').order_by('-created_at')

    context = {
        'now': datetime.now(),
        'report_type': report_type,
        'date_from': date_from,
        'date_to': date_to,
        'total_revenue': total_revenue,
        'total_transport': total_transport,
        'total_deposits': total_deposits,
        'total_supplier_credit': total_supplier_credit,
        'sales': sales,
        'sales_total': sales_total,
        'sales_transport': sales_transport,
        'sales_outstanding': sales_outstanding,
        'transport_sales': transport_sales,
        'transport_total_absorbed': transport_sales.count() * 30000,
        'deposits': deposits,
        'deposits_total': deposits.aggregate(total=Sum('amount_paid'))['total'] or 0,
        'supplier_credits': supplier_credits,
        'credits_total': supplier_credits.aggregate(total=Sum('total_amount'))['total'] or 0,
        'credits_outstanding': supplier_credits.filter(status__in=['Unpaid', 'Partial']).aggregate(total=Sum('total_amount'))['total'] or 0,
        'credits_cleared': supplier_credits.filter(status='Cleared').count(),
    }
    return render(request, 'nyondoapp/reports.html', context)