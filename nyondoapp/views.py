# IMPORT DJANGO CORE FUNCTIONS
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.staticfiles import finders
from datetime import datetime
from decimal import Decimal
from django.db.models import Q, Sum, F
from django.contrib.auth.decorators import login_required
from .models import StockItem, Sale, SaleItem, Supplier, SupplierTransaction, SupplierCredit, SupplierCreditPayment, Customer, CustomerCreditPayment, Deposit, DepositPayment


def _get_receipt_css():
    css_path = finders.find('deposit_receipt.css')
    if not css_path:
        return ''
    with open(css_path, encoding='utf-8') as css_file:
        return css_file.read()


# LANDING PAGE VIEW
def landing_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'nyondoapp/landing.html')



def render_receipt_response(request, template_name, context, download_filename):
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


# LOGIN VIEW
# Handles user login with role-based redirects
def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)

            if user.groups.filter(name='Sales Attendant').exists():
                return redirect('sales_dashboard')
            if user.groups.filter(name='Accounts Admin').exists():
                return redirect('accounts_dashboard')
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password')

    return render(request, 'nyondoapp/login.html')


# LOGOUT VIEW
# Clears the session and redirects to login
def logout_view(request):
    logout(request)
    messages.success(request, 'Logged out successfully')
    return redirect('login')


# MANAGER DASHBOARD VIEW
@login_required(login_url='login')
def dashboard_view(request):
    return render(request, 'nyondoapp/dashboard.html', {'now': datetime.now()})


# SALES ATTENDANT DASHBOARD VIEW
@login_required(login_url='login')
def sales_dashboard_view(request):
    return render(request, 'nyondoapp/sales_dashboard.html')


# ACCOUNTS ADMIN DASHBOARD VIEW
@login_required(login_url='login')
def admin_dashboard_view(request):
    return render(request, 'nyondoapp/accounts_dashboard.html', {'now': datetime.now()})


# STOCK LIST VIEW
# Handles viewing, adding, updating, and deleting stock items
@login_required(login_url='login')
def stock_view(request):

    if request.method == 'POST':
        action = request.POST.get('action', 'create')

        if action == 'delete':
            item = get_object_or_404(StockItem, id=request.POST.get('item_id'))
            item.delete()
            messages.success(request, 'Stock item deleted successfully.')
            return redirect('stock')

        if action == 'update':
            item = get_object_or_404(StockItem, id=request.POST.get('item_id'))
            item.item_name = request.POST.get('item_name', '').strip()
            item.category = request.POST.get('category', 'Building')
            item.quantity = int(request.POST.get('quantity', 0) or 0)
            item.unit = request.POST.get('unit', 'Pieces')
            item.minimum_stock = int(request.POST.get('minimum_stock', 0) or 0)
            item.buying_price = request.POST.get('buying_price', 0) or 0
            item.selling_price = request.POST.get('selling_price', 0) or 0
            item.supplier = request.POST.get('supplier', '').strip()
            item.save()
            messages.success(request, 'Stock item updated successfully.')
            return redirect('stock')

        StockItem.objects.create(
            item_name=request.POST.get('item_name', '').strip(),
            category=request.POST.get('category', 'Building'),
            quantity=int(request.POST.get('quantity', 0) or 0),
            unit=request.POST.get('unit', 'Pieces'),
            minimum_stock=int(request.POST.get('minimum_stock', 0) or 0),
            buying_price=request.POST.get('buying_price', 0) or 0,
            selling_price=request.POST.get('selling_price', 0) or 0,
            supplier=request.POST.get('supplier', '').strip(),
        )
        messages.success(request, 'Stock item added successfully.')
        return redirect('stock')

    items = StockItem.objects.all().order_by('-id')
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
    }
    return render(request, 'nyondoapp/stock.html', context)


# RECORD SALES PAGE VIEW
# Displays the blank sale form with available stock items and registered customers
@login_required(login_url='login')
def record_sales_view(request):
    stock_items = StockItem.objects.filter(quantity__gt=0)
    registered_customers = Customer.objects.all().order_by('full_name')
    context = {
        'now': datetime.now(),
        'stock_items': stock_items,
        'registered_customers': registered_customers,
    }
    return render(request, 'nyondoapp/record_sales.html', context)

# ADD SALE VIEW
# Processes the sale form with multiple items and delivery checkbox
@login_required(login_url='login')
def add_sale_view(request):
    if request.method == 'POST':

        customer_name = request.POST.get('customer_name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()

        # Get multiple item lists from form
        item_ids = request.POST.getlist('item[]')
        quantities = request.POST.getlist('quantity[]')

        # Check delivery checkbox
        wants_delivery = request.POST.get('wants_delivery', '') == 'yes'
        distance = int(request.POST.get('distance') or 0) if wants_delivery else 0

        payment_status = request.POST.get('payment_status', 'Pending')
        payment_method = request.POST.get('payment_method', 'Cash')
        notes = request.POST.get('notes', '').strip()

        # Validate credit sale has a registered customer
        registered_customer = None
        if payment_status.capitalize() == 'Credit':
            registered_customer_id = request.POST.get('registered_customer_id')
            if not registered_customer_id:
                messages.error(request, 'Credit sales must be linked to a registered customer.')
                return redirect('record_sales')
            registered_customer = get_object_or_404(Customer, id=registered_customer_id)
            customer_name = registered_customer.full_name
            phone_number = registered_customer.phone_number

        # Fix payment status and method
        payment_status = payment_status.capitalize()
        payment_method_map = {
            'cash': 'Cash',
            'mobile_money': 'Mobile Money',
            'bank_transfer': 'Bank Transfer',
        }
        payment_method = payment_method_map.get(payment_method, 'Cash')

        # Validate at least one item selected
        if not item_ids:
            messages.error(request, 'Please add at least one item.')
            return redirect('record_sales')

        # Validate and fetch all stock items
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

        # Calculate transport charge
        if not wants_delivery:
            # Walk-in customer - no transport charge
            transport_charge = Decimal('0')
        elif distance <= 10 and subtotal >= 500000:
            # Free delivery: within 10km and order above UGX 500,000
            transport_charge = Decimal('0')
        else:
            # Flat transport charge
            transport_charge = Decimal('30000')

        total_amount = subtotal + transport_charge

        # Save the sale record
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

        # Save all sale items and reduce stock
        for item_data in sale_items:
            SaleItem.objects.create(
                sale=sale,
                stock_item=item_data['stock_item'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                line_total=item_data['line_total'],
            )
            # Reduce stock quantity
            item_data['stock_item'].quantity -= item_data['quantity']
            item_data['stock_item'].save()

        messages.success(request, f'Sale #{sale.id} recorded successfully!')

        if request.POST.get('action') == 'save_print':
            return redirect('print_receipt', sale_id=sale.id)

        return redirect('sales_list')

    return redirect('record_sales')


# DELETE SALE VIEW
# Deletes a sale and restores stock quantities
@login_required(login_url='login')
def delete_sale_view(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id)

    if request.method == 'POST':
        for item in sale.items.all():
            item.stock_item.quantity += item.quantity
            item.stock_item.save()

        sale.delete()
        messages.success(request, f'Sale #{sale_id} deleted successfully.')

    return redirect('sales_list')


# EDIT SALE VIEW
# Updates customer details and payment info for an existing sale
@login_required(login_url='login')
def edit_sale_view(request, sale_id):
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
        payment_method = request.POST.get('payment_method', 'cash')
        sale.payment_method = payment_method_map.get(payment_method, 'Cash')
        sale.notes = request.POST.get('notes', '').strip()
        sale.save()
        messages.success(request, f'Sale #{sale_id} updated successfully.')

    return redirect('sales_list')


# PRINT RECEIPT VIEW
# Renders a printable receipt for a specific sale
@login_required(login_url='login')
def print_receipt_view(request, sale_id):
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
# Displays all sales with search and filter options
@login_required(login_url='login')
def sales_list_view(request):

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

    total_sales = sales_list.count()
    total_revenue = sales_list.aggregate(total=Sum('total_amount'))['total'] or 0
    pending_count = sales_list.filter(payment_status='Pending').count()
    credit_count = sales_list.filter(payment_status='Credit').count()

    context = {
        'sales': sales_list,
        'search': search,
        'status': status,
        'date_from': date_from,
        'date_to': date_to,
        'total_sales': total_sales,
        'total_revenue': total_revenue,
        'pending_count': pending_count,
        'credit_count': credit_count,
        'now': datetime.now(),
    }
    return render(request, 'nyondoapp/sales_list.html', context)


# SUPPLIERS LIST VIEW
# Displays all suppliers with search and filter options
@login_required(login_url='login')
def suppliers_view(request):

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

    total_suppliers = suppliers.count()
    credits_due = suppliers.filter(status='Credits Due').count()
    overdue = suppliers.filter(status='Overdue').count()
    total_owed = suppliers.aggregate(total=Sum('balance'))['total'] or 0

    context = {
        'suppliers': suppliers,
        'search': search,
        'status': status,
        'total_suppliers': total_suppliers,
        'credits_due': credits_due,
        'overdue': overdue,
        'total_owed': total_owed,
    }
    return render(request, 'nyondoapp/suppliers.html', context)


# ADD SUPPLIER VIEW
@login_required(login_url='login')
def add_supplier_view(request):
    if request.method == 'POST':

        supplier_name = request.POST.get('supplier_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        tin_number = request.POST.get('tin_number', '').strip() or None
        email = request.POST.get('email', '').strip() or None
        location = request.POST.get('location', '').strip() or None
        initial_balance = Decimal(request.POST.get('initial_balance', 0) or 0)
        payment_terms = int(request.POST.get('payment_terms', 30))
        notes = request.POST.get('notes', '').strip() or None

        if Supplier.objects.filter(phone=phone).exists():
            messages.error(request, 'A supplier with this phone number already exists.')
            return redirect('suppliers')

        Supplier.objects.create(
            supplier_name=supplier_name,
            phone=phone,
            tin_number=tin_number,
            email=email,
            location=location,
            balance=initial_balance,
            payment_terms=payment_terms,
            notes=notes,
            created_by=request.user,
        )

        messages.success(request, f'{supplier_name} added successfully!')
        return redirect('suppliers')

    return redirect('suppliers')


# EDIT SUPPLIER VIEW
@login_required(login_url='login')
def edit_supplier_view(request, supplier_id):
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
    supplier = get_object_or_404(Supplier, id=supplier_id)

    if request.method == 'POST':
        name = supplier.supplier_name
        supplier.delete()
        messages.success(request, f'{name} deleted successfully.')

    return redirect('suppliers')


# SUPPLIER TRANSACTIONS VIEW
@login_required(login_url='login')
def supplier_transactions_view(request, supplier_id):
    supplier = get_object_or_404(Supplier, id=supplier_id)
    transactions = supplier.transactions.all()

    context = {
        'supplier': supplier,
        'transactions': transactions,
    }
    return render(request, 'nyondoapp/supplier_transactions.html', context)


# RECORD PAYMENT VIEW
# Records a transaction for a supplier
@login_required(login_url='login')
def record_payment_view(request, supplier_id):
    supplier = get_object_or_404(Supplier, id=supplier_id)

    if request.method == 'POST':
        transaction_type = request.POST.get('transaction_type', 'Payment')
        amount = Decimal(request.POST.get('amount', 0))
        payment_method = request.POST.get('payment_method', 'Cash')
        reference_number = request.POST.get('reference_number', '').strip() or None
        description = request.POST.get('description', '').strip() or None

        SupplierTransaction.objects.create(
            supplier=supplier,
            transaction_type=transaction_type,
            amount=amount,
            payment_method=payment_method,
            reference_number=reference_number,
            description=description,
            created_by=request.user,
        )

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
    supplier = get_object_or_404(Supplier, id=supplier_id)
    credits = supplier.credits.all()

    total_owed = sum(c.total_amount for c in credits)
    total_paid = sum(c.amount_paid for c in credits)
    total_outstanding = total_owed - total_paid
    unpaid_count = credits.filter(status='Unpaid').count()
    partial_count = credits.filter(status='Partial').count()

    context = {
        'supplier': supplier,
        'credits': credits,
        'total_owed': total_owed,
        'total_paid': total_paid,
        'total_outstanding': total_outstanding,
        'unpaid_count': unpaid_count,
        'partial_count': partial_count,
    }
    return render(request, 'nyondoapp/supplier_credit_detail.html', context)


# ADD SUPPLIER CREDIT VIEW
@login_required(login_url='login')
def add_supplier_credit_view(request, supplier_id):
    supplier = get_object_or_404(Supplier, id=supplier_id)

    if request.method == 'POST':
        description = request.POST.get('description', '').strip()
        total_amount = Decimal(request.POST.get('total_amount') or 0)
        due_date = request.POST.get('due_date')

        SupplierCredit.objects.create(
            supplier=supplier,
            description=description,
            total_amount=total_amount,
            due_date=due_date,
            created_by=request.user,
        )

        supplier.balance += total_amount
        supplier.status = 'Credits Due'
        supplier.save()

        messages.success(request, f'Credit of UGX {total_amount:,.0f} recorded for {supplier.supplier_name}.')
        return redirect('supplier_credit_detail', supplier_id=supplier.id)

    return redirect('supplier_credit_detail', supplier_id=supplier.id)


# RECORD CREDIT PAYMENT VIEW
@login_required(login_url='login')
def record_credit_payment_view(request, credit_id):
    credit = get_object_or_404(SupplierCredit, id=credit_id)

    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount') or 0)
        payment_method = request.POST.get('payment_method', 'Cash')
        reference_number = request.POST.get('reference_number', '').strip() or None
        note = request.POST.get('note', '').strip() or None

        SupplierCreditPayment.objects.create(
            credit=credit,
            amount=amount,
            payment_method=payment_method,
            reference_number=reference_number,
            note=note,
            paid_by=request.user,
        )

        credit.amount_paid += amount
        if credit.amount_paid >= credit.total_amount:
            credit.status = 'Cleared'
        else:
            credit.status = 'Partial'
        credit.save()

        supplier = credit.supplier
        supplier.balance -= amount
        if supplier.balance <= 0:
            supplier.balance = Decimal('0.00')
            supplier.status = 'Active'
        supplier.save()

        messages.success(request, f'Payment of UGX {amount:,.0f} recorded successfully.')
        return redirect('supplier_credit_detail', supplier_id=supplier.id)

    return redirect('supplier_credit_detail', supplier_id=credit.supplier.id)


# CUSTOMERS LIST VIEW
@login_required(login_url='login')
def customers_view(request):
    customers = Customer.objects.all().order_by('-registered_on')

    search = request.GET.get('search', '')
    if search:
        customers = customers.filter(
            Q(full_name__icontains=search) |
            Q(phone_number__icontains=search) |
            Q(nin__icontains=search)
        )

    total_customers = customers.count()

    context = {
        'customers': customers,
        'search': search,
        'total_customers': total_customers,
    }
    return render(request, 'nyondoapp/customers_list.html', context)


# REGISTER CUSTOMER VIEW
@login_required(login_url='login')
def register_customer_view(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        nin = request.POST.get('nin', '').strip().upper()
        area = request.POST.get('area', '').strip() or None
        notes = request.POST.get('notes', '').strip() or None

        if len(nin) != 14:
            messages.error(request, 'NIN must be exactly 14 characters.')
            return render(request, 'nyondoapp/register_customer.html')

        if Customer.objects.filter(nin=nin).exists():
            messages.error(request, f'A customer with NIN {nin} is already registered.')
            return render(request, 'nyondoapp/register_customer.html')

        if Customer.objects.filter(phone_number=phone_number).exists():
            messages.error(request, 'A customer with this phone number is already registered.')
            return render(request, 'nyondoapp/register_customer.html')

        Customer.objects.create(
            full_name=full_name,
            phone_number=phone_number,
            nin=nin,
            area=area,
            notes=notes,
            registered_by=request.user,
        )

        messages.success(request, f'{full_name} registered successfully!')
        return redirect('customers')

    return render(request, 'nyondoapp/register_customer.html')


# EDIT CUSTOMER VIEW
@login_required(login_url='login')
def edit_customer_view(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id)
    if request.method == 'POST':
        customer.full_name = request.POST.get('full_name', '').strip()
        customer.phone_number = request.POST.get('phone_number', '').strip()
        customer.nin = request.POST.get('nin', '').strip().upper()
        customer.area = request.POST.get('area', '').strip() or None
        customer.notes = request.POST.get('notes', '').strip() or None
        customer.save()
        messages.success(request, f'{customer.full_name} updated successfully.')
    return redirect('customers')


# DELETE CUSTOMER VIEW
@login_required(login_url='login')
def delete_customer_view(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id)
    if request.method == 'POST':
        # Block deletion if customer has deposits
        if customer.deposits.exists():
            messages.error(request, f'Cannot delete {customer.full_name}. They have deposits on record. Cancel or complete all deposits first.')
            return redirect('customers')
        
        name = customer.full_name
        customer.delete()
        messages.success(request, f'{name} removed successfully.')
    return redirect('customers')


# CUSTOMER DETAIL VIEW
# Shows full customer info and credit history
@login_required(login_url='login')
def customer_detail_view(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id)

    # Get all sales linked to this customer
    credit_sales = Sale.objects.filter(
        customer=customer,
    ).prefetch_related('items__stock_item', 'credit_payments').order_by('-sale_date')

    # Calculate amount paid and balance for each sale
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

        payment_method = request.POST.get('payment_method', 'Cash')
        reference_number = request.POST.get('reference_number', '').strip() or None
        note = request.POST.get('note', '').strip() or None

        CustomerCreditPayment.objects.create(
            sale=sale,
            amount=amount,
            payment_method=payment_method,
            reference_number=reference_number,
            note=note,
            paid_by=request.user,
        )

        total_paid = sale.credit_payments.aggregate(total=Sum('amount'))['total'] or 0

        if total_paid >= sale.total_amount:
            sale.payment_status = 'Paid'
            sale.save()
            messages.success(request, f'Payment recorded. Sale #{sale.id} is now fully paid!')
        else:
            balance = sale.total_amount - total_paid
            messages.success(request, f'Payment of UGX {amount:,.0f} recorded. Balance remaining: UGX {balance:,.0f}.')

    return redirect('customer_detail', customer_id=sale.customer.id)

# DEPOSITS LIST VIEW
@login_required(login_url='login')
def deposits_view(request):
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

    total_deposits = deposits.count()
    active_count = deposits.filter(status='Active').count()
    completed_count = deposits.filter(status='Completed').count()
    total_balance_due = deposits.filter(status='Active').aggregate(
        total=Sum('total_amount')
    )['total'] or 0
    total_paid_active = deposits.filter(status='Active').aggregate(
        total=Sum('amount_paid')
    )['total'] or 0
    total_balance_due = total_balance_due - total_paid_active

    low_stock_count = StockItem.objects.filter(
        quantity__gt=0, quantity__lte=F('minimum_stock')
    ).count()

    context = {
        'deposits': deposits,
        'search': search,
        'status': status,
        'item_type': item_type,
        'total_deposits': total_deposits,
        'active_count': active_count,
        'completed_count': completed_count,
        'total_balance_due': total_balance_due,
        'low_stock_count': low_stock_count,
        'today': datetime.now().date(),
    }
    return render(request, 'nyondoapp/deposits.html', context)


# CREATE DEPOSIT VIEW
# Handles the new deposit form and reserves stock immediately
@login_required(login_url='login')
def create_deposit_view(request):
    customers = Customer.objects.all().order_by('full_name')
    low_stock_count = StockItem.objects.filter(
        quantity__gt=0, quantity__lte=F('minimum_stock')
    ).count()

    if request.method == 'POST':
        customer_id = request.POST.get('customer_id')
        item_type = request.POST.get('item_type', '').strip()
        quantity_ordered = int(request.POST.get('quantity_ordered') or 0)
        unit = request.POST.get('unit', 'Bags')
        due_date = request.POST.get('due_date')
        notes = request.POST.get('notes', '').strip() or None

        customer = get_object_or_404(Customer, id=customer_id)

        if quantity_ordered <= 0:
            messages.error(request, 'Quantity must be greater than zero.')
            return render(request, 'nyondoapp/create_deposit.html', {
                'customers': customers,
                'low_stock_count': low_stock_count,
            })

        # Find stock item with available quantity and auto-calculate total
        stock_item = StockItem.objects.filter(
            item_name__icontains=item_type,
            quantity__gt=0
        ).first()

        if not stock_item:
            messages.error(request, f'No stock available for {item_type}. Cannot create deposit.')
            return render(request, 'nyondoapp/create_deposit.html', {
                'customers': customers,
                'low_stock_count': low_stock_count,
            })

        # Auto-calculate total from selling price
        total_amount = stock_item.selling_price * quantity_ordered

        if stock_item.quantity < quantity_ordered:
            messages.error(
                request,
                f'Not enough stock. Only {stock_item.quantity} {stock_item.unit} of {item_type} available.'
            )
            return render(request, 'nyondoapp/create_deposit.html', {
                'customers': customers,
                'low_stock_count': low_stock_count,
            })

        # Reserve stock immediately
        stock_item.quantity -= quantity_ordered
        stock_item.save()

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

        messages.success(request, f'Deposit #{deposit.id} created for {customer.full_name}. Stock reserved. Total: UGX {total_amount:,.0f}.')
        return redirect('deposit_detail', deposit_id=deposit.id)

    return render(request, 'nyondoapp/create_deposit.html', {
        'customers': customers,
        'low_stock_count': low_stock_count,
    })


# DEPOSIT DETAIL VIEW
@login_required(login_url='login')
def deposit_detail_view(request, deposit_id):
    deposit = get_object_or_404(Deposit, id=deposit_id)
    payments = deposit.payments.all().order_by('-paid_at')
    low_stock_count = StockItem.objects.filter(
        quantity__gt=0, quantity__lte=F('minimum_stock')
    ).count()

    context = {
        'deposit': deposit,
        'payments': payments,
        'low_stock_count': low_stock_count,
        'today': datetime.now().date(),
    }
    return render(request, 'nyondoapp/deposit_detail.html', context)


# RECORD DEPOSIT PAYMENT VIEW
# Records an instalment payment against a deposit
@login_required(login_url='login')
def record_deposit_payment_view(request, deposit_id):
    deposit = get_object_or_404(Deposit, id=deposit_id)

    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount') or 0)
        payment_method = request.POST.get('payment_method', 'Cash')
        reference_number = request.POST.get('reference_number', '').strip() or None
        note = request.POST.get('note', '').strip() or None

        if amount <= 0:
            messages.error(request, 'Payment amount must be greater than zero.')
            return redirect('deposit_detail', deposit_id=deposit.id)

        if amount > deposit.balance_remaining:
            messages.error(
                request,
                f'Amount exceeds balance remaining. Maximum payable is UGX {deposit.balance_remaining:,.0f}.'
            )
            return redirect('deposit_detail', deposit_id=deposit.id)

        payment = DepositPayment.objects.create(
            deposit=deposit,
            amount=amount,
            payment_method=payment_method,
            reference_number=reference_number,
            note=note,
            paid_by=request.user,
        )

        deposit.amount_paid += amount

        if deposit.amount_paid >= deposit.total_amount:
            deposit.status = 'Completed'
            messages.success(
                request,
                f'Payment of UGX {amount:,.0f} recorded. Deposit #{deposit.id} is now fully paid. Customer can collect their goods!'
            )
        else:
            messages.success(
                request,
                f'Payment of UGX {amount:,.0f} recorded. Balance remaining: UGX {deposit.balance_remaining:,.0f}.'
            )

        deposit.save()

        # Redirect to collection receipt if completed, otherwise deposit receipt
        if deposit.status == 'Completed':
            return redirect('collection_receipt', deposit_id=deposit.id)

        return redirect('deposit_receipt', payment_id=payment.id)

    return redirect('deposit_detail', deposit_id=deposit.id)


# CANCEL DEPOSIT VIEW
# Cancels a deposit and restores reserved stock
@login_required(login_url='login')
def cancel_deposit_view(request, deposit_id):
    deposit = get_object_or_404(Deposit, id=deposit_id)

    if request.method == 'POST':
        if deposit.status != 'Active':
            messages.error(request, 'Only active deposits can be cancelled.')
            return redirect('deposit_detail', deposit_id=deposit.id)

        # Restore stock
        stock_item = StockItem.objects.filter(
            item_name__icontains=deposit.item_type,
        ).first()

        if stock_item:
            stock_item.quantity += deposit.quantity_ordered
            stock_item.save()

        deposit.status = 'Cancelled'
        deposit.save()

        messages.success(request, f'Deposit #{deposit.id} cancelled. Stock has been restored.')

    return redirect('deposits')


# DEPOSIT RECEIPT VIEW
# Prints a temporary deposit receipt for a specific payment
@login_required(login_url='login')
def deposit_receipt_view(request, payment_id):
    payment = get_object_or_404(DepositPayment, id=payment_id)

    context = {
        'payment': payment,
        'deposit': payment.deposit,
    }
    filename = f'deposit-receipt-{payment.deposit.id}-payment-{payment.id}.html'
    return render_receipt_response(
        request,
        'nyondoapp/deposit_receipt.html',
        context,
        filename,
    )


# COLLECTION RECEIPT VIEW
# Prints the official collection receipt for a completed deposit
@login_required(login_url='login')
def collection_receipt_view(request, deposit_id):
    deposit = get_object_or_404(Deposit, id=deposit_id)

    if deposit.status != 'Completed':
        messages.error(request, 'Collection receipt is only available for completed deposits.')
        return redirect('deposit_detail', deposit_id=deposit.id)

    payments = deposit.payments.all().order_by('paid_at')

    context = {
        'deposit': deposit,
        'payments': payments,
    }
    return render_receipt_response(
        request,
        'nyondoapp/collection_receipt.html',
        context,
        f'collection-receipt-{deposit.id}.html',
    )
