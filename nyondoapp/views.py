# IMPORT DJANGO CORE FUNCTIONS
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from datetime import datetime
from decimal import Decimal
from django.db.models import Q, Sum, F
from django.contrib.auth.decorators import login_required
from .models import StockItem, Sale, SaleItem, Supplier, SupplierTransaction, SupplierCredit, SupplierCreditPayment, Customer


# LOGIN VIEW
# Handles user login with role-based redirects
def login_view(request):
    if request.method == 'POST':
        # Get username and password from submitted form
        username = request.POST['username']
        password = request.POST['password']

        # Check if credentials match a real user
        user = authenticate(request, username=username, password=password)

        if user is not None:
            # Log them in and create a session
            login(request, user)

            # Redirect based on user role
            if user.groups.filter(name='Sales Attendant').exists():
                return redirect('sales_dashboard')
            if user.groups.filter(name='Accounts Admin').exists():
                return redirect('accounts_dashboard')
            return redirect('dashboard')
        else:
            # Wrong credentials - show error
            messages.error(request, 'Invalid username or password')

    # Show login form (GET request or failed login)
    return render(request, 'nyondoapp/login.html')


# LOGOUT VIEW
# Clears the session and redirects to login
def logout_view(request):
    logout(request)
    messages.success(request, 'Logged out successfully')
    return redirect('login')


# MANAGER DASHBOARD VIEW
# Main dashboard for Store Manager role
@login_required(login_url='login')
def dashboard_view(request):
    return render(request, 'nyondoapp/dashboard.html', {'now': datetime.now()})


# SALES ATTENDANT DASHBOARD VIEW
# Dashboard for Sales Attendant - limited features only
@login_required(login_url='login')
def sales_dashboard_view(request):
    return render(request, 'nyondoapp/sales_dashboard.html')


# ACCOUNTS ADMIN DASHBOARD VIEW
# Dashboard for Accounts Admin role
@login_required(login_url='login')
def admin_dashboard_view(request):
    return render(request, 'nyondoapp/accounts_dashboard.html', {'now': datetime.now()})


# STOCK LIST VIEW
# Handles viewing, adding, updating, and deleting stock items
@login_required(login_url='login')
def stock_view(request):

    # HANDLE POST REQUESTS (Create, Update, Delete)
    if request.method == 'POST':
        action = request.POST.get('action', 'create')

        # DELETE ACTION - remove a stock item
        if action == 'delete':
            item = get_object_or_404(StockItem, id=request.POST.get('item_id'))
            item.delete()
            messages.success(request, 'Stock item deleted successfully.')
            return redirect('stock')

        # UPDATE ACTION - edit an existing stock item
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

        # CREATE ACTION - add a new stock item
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

    # HANDLE GET REQUESTS - fetch and display all stock items
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
# Displays the blank sale form with available stock items
@login_required(login_url='login')
def record_sales_view(request):
    # Only show items that are currently in stock
    stock_items = StockItem.objects.filter(quantity__gt=0)
    context = {
        'now': datetime.now(),
        'stock_items': stock_items,
    }
    return render(request, 'nyondoapp/record_sales.html', context)


# ADD SALE VIEW
# Processes the sale form and saves everything to the database
@login_required(login_url='login')
def add_sale_view(request):
    if request.method == 'POST':

        # GET CUSTOMER DETAILS FROM FORM
        customer_name = request.POST.get('customer_name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()

        # GET ITEM DETAILS FROM FORM
        stock_item_id = request.POST.get('item')
        quantity = int(request.POST.get('quantity', 1))
        unit_price = Decimal(request.POST.get('unit_price') or 0)

        # GET DISTANCE AND CALCULATE SUBTOTAL FIRST
        distance = int(request.POST.get('distance') or 0)
        subtotal = quantity * unit_price

        # CALCULATE TRANSPORT CHARGE BASED ON BUSINESS RULES
        # Free delivery: within 10km AND order above UGX 500,000
        # No delivery: distance is 0
        # Otherwise: flat UGX 30,000 transport charge
        if distance == 0:
            transport_charge = Decimal('0')
        elif distance <= 10 and subtotal >= 500000:
            transport_charge = Decimal('0')
        else:
            transport_charge = Decimal('30000')

        # GET PAYMENT DETAILS FROM FORM
        payment_status = request.POST.get('payment_status', 'Pending')
        payment_method = request.POST.get('payment_method', 'Cash')
        notes = request.POST.get('notes', '').strip()

        # FIX PAYMENT STATUS CAPITALISATION
        # Form sends 'paid', 'pending', 'credit' - model expects 'Paid', 'Pending', 'Credit'
        payment_status = payment_status.capitalize()

        # FIX PAYMENT METHOD FORMAT
        # Form sends 'cash', 'mobile_money', 'bank_transfer'
        # Model expects 'Cash', 'Mobile Money', 'Bank Transfer'
        payment_method_map = {
            'cash': 'Cash',
            'mobile_money': 'Mobile Money',
            'bank_transfer': 'Bank Transfer',
        }
        payment_method = payment_method_map.get(payment_method, 'Cash')

        # VALIDATE QUANTITY
        if quantity <= 0:
            messages.error(request, 'Quantity must be greater than zero.')
            return redirect('record_sales')

        # VALIDATE UNIT PRICE
        if unit_price <= 0:
            messages.error(request, 'Unit price must be greater than zero.')
            return redirect('record_sales')

        # GET THE STOCK ITEM FROM DATABASE
        stock_item = get_object_or_404(StockItem, id=stock_item_id)

        # CHECK IF ENOUGH STOCK IS AVAILABLE BEFORE SAVING
        if quantity > stock_item.quantity:
            messages.error(
                request,
                f'Not enough stock. Only {stock_item.quantity} {stock_item.unit} available.'
            )
            return redirect('record_sales')

        # CALCULATE FINAL TOTAL AMOUNT
        total_amount = subtotal + transport_charge

        # SAVE THE SALE RECORD TO DATABASE
        sale = Sale.objects.create(
            customer_name=customer_name,
            phone_number=phone_number,
            subtotal=subtotal,
            transport_charge=transport_charge,
            total_amount=total_amount,
            payment_status=payment_status,
            payment_method=payment_method,
            notes=notes,
            sold_by=request.user,
        )

        # SAVE THE SALE ITEM (links sale to the stock item)
        SaleItem.objects.create(
            sale=sale,
            stock_item=stock_item,
            quantity=quantity,
            unit_price=unit_price,
            line_total=subtotal,
        )

        # REDUCE STOCK QUANTITY by the amount sold
        stock_item.quantity -= quantity
        stock_item.save()

        # SUCCESS MESSAGE
        messages.success(request, f'Sale #{sale.id} recorded successfully!')

        # REDIRECT based on which button was clicked
        if request.POST.get('action') == 'save_print':
            return redirect('print_receipt', sale_id=sale.id)

        return redirect('sales_list')

    # IF NOT A POST REQUEST, SEND BACK TO FORM
    return redirect('record_sales')


# DELETE SALE VIEW
# Deletes a sale and restores stock quantities
@login_required(login_url='login')
def delete_sale_view(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id)

    if request.method == 'POST':
        # RESTORE STOCK QUANTITY before deleting
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
        # UPDATE CUSTOMER DETAILS
        sale.customer_name = request.POST.get('customer_name', '').strip()
        sale.phone_number = request.POST.get('phone_number', '').strip()

        # UPDATE PAYMENT STATUS
        sale.payment_status = request.POST.get('payment_status', 'Pending').capitalize()

        # UPDATE PAYMENT METHOD
        payment_method_map = {
            'cash': 'Cash',
            'mobile_money': 'Mobile Money',
            'bank_transfer': 'Bank Transfer',
        }
        payment_method = request.POST.get('payment_method', 'cash')
        sale.payment_method = payment_method_map.get(payment_method, 'Cash')

        # UPDATE NOTES
        sale.notes = request.POST.get('notes', '').strip()
        sale.save()
        messages.success(request, f'Sale #{sale_id} updated successfully.')

    return redirect('sales_list')


# PRINT RECEIPT VIEW
# Renders a printable receipt for a specific sale
@login_required(login_url='login')
def print_receipt_view(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id)
    # Fetch all items in this sale with their stock item details
    items = sale.items.select_related('stock_item').all()

    context = {
        'sale': sale,
        'items': items,
    }
    return render(request, 'nyondoapp/receipt.html', context)


# SALES LIST VIEW
# Displays all sales with search and filter options
@login_required(login_url='login')
def sales_list_view(request):

    # PREFETCH LINE ITEMS to avoid N+1 queries on item names
    sales_list = Sale.objects.prefetch_related('items__stock_item').all()

    # GET FILTER PARAMETERS FROM URL
    search = request.GET.get('search', '')
    status = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    # APPLY SEARCH FILTER - matches customer name or phone number
    if search:
        sales_list = sales_list.filter(
            Q(customer_name__icontains=search) |
            Q(phone_number__icontains=search)
        )

    # APPLY STATUS FILTER
    if status and status != 'All Status':
        sales_list = sales_list.filter(payment_status=status)

    # APPLY DATE RANGE FILTERS
    if date_from:
        sales_list = sales_list.filter(sale_date__gte=date_from)
    if date_to:
        sales_list = sales_list.filter(sale_date__lte=date_to)

    # ORDER BY NEWEST FIRST
    sales_list = sales_list.order_by('-sale_date', '-id')

    # CALCULATE SUMMARY STATISTICS
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

    # START WITH ALL SUPPLIERS
    suppliers = Supplier.objects.all()

    # GET FILTER PARAMETERS FROM URL
    search = request.GET.get('search', '')
    status = request.GET.get('status', '')

    # APPLY SEARCH FILTER - matches supplier name or phone
    if search:
        suppliers = suppliers.filter(
            Q(supplier_name__icontains=search) |
            Q(phone__icontains=search)
        )

    # APPLY STATUS FILTER
    if status and status != 'All Status':
        suppliers = suppliers.filter(status=status)

    # ORDER BY ID - consistent display order
    suppliers = suppliers.order_by('id')

    # CALCULATE SUMMARY STATISTICS
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
# Processes the add supplier form and saves to database
@login_required(login_url='login')
def add_supplier_view(request):
    if request.method == 'POST':

        # GET SUPPLIER DETAILS FROM FORM
        supplier_name = request.POST.get('supplier_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        tin_number = request.POST.get('tin_number', '').strip() or None
        email = request.POST.get('email', '').strip() or None
        location = request.POST.get('location', '').strip() or None
        initial_balance = Decimal(request.POST.get('initial_balance', 0) or 0)
        payment_terms = int(request.POST.get('payment_terms', 30))
        notes = request.POST.get('notes', '').strip() or None

        # CHECK IF PHONE NUMBER ALREADY EXISTS
        if Supplier.objects.filter(phone=phone).exists():
            messages.error(request, 'A supplier with this phone number already exists.')
            return redirect('suppliers')

        # SAVE THE SUPPLIER TO DATABASE
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

    # IF NOT POST, REDIRECT BACK TO SUPPLIERS PAGE
    return redirect('suppliers')


# EDIT SUPPLIER VIEW
# Updates an existing supplier's details
@login_required(login_url='login')
def edit_supplier_view(request, supplier_id):
    # GET THE SUPPLIER OR RETURN 404 IF NOT FOUND
    supplier = get_object_or_404(Supplier, id=supplier_id)

    if request.method == 'POST':
        # UPDATE SUPPLIER FIELDS FROM FORM
        supplier.supplier_name = request.POST.get('supplier_name', '').strip()
        supplier.phone = request.POST.get('phone', '').strip()
        supplier.tin_number = request.POST.get('tin_number', '').strip() or None
        supplier.email = request.POST.get('email', '').strip() or None
        supplier.location = request.POST.get('location', '').strip() or None
        supplier.payment_terms = int(request.POST.get('payment_terms', 30))
        supplier.status = request.POST.get('status', 'Active')
        supplier.notes = request.POST.get('notes', '').strip() or None

        # SAVE UPDATED SUPPLIER
        supplier.save()
        messages.success(request, f'{supplier.supplier_name} updated successfully.')

    return redirect('suppliers')


# DELETE SUPPLIER VIEW
# Permanently removes a supplier from the database
@login_required(login_url='login')
def delete_supplier_view(request, supplier_id):
    # GET THE SUPPLIER OR RETURN 404 IF NOT FOUND
    supplier = get_object_or_404(Supplier, id=supplier_id)

    if request.method == 'POST':
        name = supplier.supplier_name
        supplier.delete()
        messages.success(request, f'{name} deleted successfully.')

    return redirect('suppliers')


# SUPPLIER TRANSACTIONS VIEW
# Shows all transactions for a specific supplier
@login_required(login_url='login')
def supplier_transactions_view(request, supplier_id):
    # GET THE SUPPLIER OR 404
    supplier = get_object_or_404(Supplier, id=supplier_id)

    # GET ALL TRANSACTIONS FOR THIS SUPPLIER, NEWEST FIRST
    transactions = supplier.transactions.all()

    context = {
        'supplier': supplier,
        'transactions': transactions,
    }
    return render(request, 'nyondoapp/supplier_transactions.html', context)


# RECORD PAYMENT VIEW
# Records a transaction (payment, credit, adjustment) for a supplier
@login_required(login_url='login')
def record_payment_view(request, supplier_id):
    supplier = get_object_or_404(Supplier, id=supplier_id)

    if request.method == 'POST':
        # GET TRANSACTION DETAILS FROM FORM
        transaction_type = request.POST.get('transaction_type', 'Payment')
        amount = Decimal(request.POST.get('amount', 0))
        payment_method = request.POST.get('payment_method', 'Cash')
        reference_number = request.POST.get('reference_number', '').strip() or None
        description = request.POST.get('description', '').strip() or None

        # SAVE THE TRANSACTION
        SupplierTransaction.objects.create(
            supplier=supplier,
            transaction_type=transaction_type,
            amount=amount,
            payment_method=payment_method,
            reference_number=reference_number,
            description=description,
            created_by=request.user,
        )

        # UPDATE SUPPLIER BALANCE
        if transaction_type == 'Credit':
            supplier.balance += amount
        elif transaction_type in ['Payment', 'Adjustment']:
            supplier.balance -= amount
        supplier.save()

        messages.success(request, f'Transaction of UGX {amount:,.0f} recorded successfully.')

    return redirect('supplier_transactions', supplier_id=supplier.id)


# SUPPLIER CREDIT DETAIL VIEW
# Shows all credits and payment history for one supplier
@login_required(login_url='login')
def supplier_credit_detail_view(request, supplier_id):
    supplier = get_object_or_404(Supplier, id=supplier_id)
    credits = supplier.credits.all()

    # CALCULATE SUMMARY STATS
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
# Records new goods taken from a supplier on credit
@login_required(login_url='login')
def add_supplier_credit_view(request, supplier_id):
    supplier = get_object_or_404(Supplier, id=supplier_id)

    if request.method == 'POST':
        # GET CREDIT DETAILS FROM FORM
        description = request.POST.get('description', '').strip()
        total_amount = Decimal(request.POST.get('total_amount') or 0)
        due_date = request.POST.get('due_date')

        # SAVE THE CREDIT RECORD
        SupplierCredit.objects.create(
            supplier=supplier,
            description=description,
            total_amount=total_amount,
            due_date=due_date,
            created_by=request.user,
        )

        # UPDATE SUPPLIER BALANCE AND STATUS
        supplier.balance += total_amount
        supplier.status = 'Credits Due'
        supplier.save()

        messages.success(request, f'Credit of UGX {total_amount:,.0f} recorded for {supplier.supplier_name}.')
        return redirect('supplier_credit_detail', supplier_id=supplier.id)

    return redirect('supplier_credit_detail', supplier_id=supplier.id)


# RECORD CREDIT PAYMENT VIEW
# Records a payment made against a specific supplier credit
@login_required(login_url='login')
def record_credit_payment_view(request, credit_id):
    credit = get_object_or_404(SupplierCredit, id=credit_id)

    if request.method == 'POST':
        # GET PAYMENT DETAILS FROM FORM
        amount = Decimal(request.POST.get('amount') or 0)
        payment_method = request.POST.get('payment_method', 'Cash')
        reference_number = request.POST.get('reference_number', '').strip() or None
        note = request.POST.get('note', '').strip() or None

        # SAVE THE PAYMENT RECORD
        SupplierCreditPayment.objects.create(
            credit=credit,
            amount=amount,
            payment_method=payment_method,
            reference_number=reference_number,
            note=note,
            paid_by=request.user,
        )

        # UPDATE CREDIT AMOUNT PAID AND STATUS
        credit.amount_paid += amount
        if credit.amount_paid >= credit.total_amount:
            credit.status = 'Cleared'
        else:
            credit.status = 'Partial'
        credit.save()

        # UPDATE SUPPLIER BALANCE
        # If fully paid off, reset status to Active
        supplier = credit.supplier
        supplier.balance -= amount
        if supplier.balance <= 0:
            supplier.balance = Decimal('0.00')
            supplier.status = 'Active'
        supplier.save()

        messages.success(request, f'Payment of UGX {amount:,.0f} recorded successfully.')
        return redirect('supplier_credit_detail', supplier_id=supplier.id)

    return redirect('supplier_credit_detail', supplier_id=credit.supplier.id)

 # CUSTOMER VIEWS
 # These views handle customer registration and listing, but are not fully implemented yet
@login_required(login_url='login')
def customers_view(request):
    return redirect('register_customer')

# REGISTER CUSTOMER VIEW
@login_required(login_url='login')
def register_customer_view(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        nin = request.POST.get('nin', '').strip().upper()
        area = request.POST.get('area', '').strip() or None
        notes = request.POST.get('notes', '').strip() or None

        # VALIDATE NIN LENGTH
        if len(nin) != 14:
            messages.error(request, 'NIN must be exactly 14 characters.')
            return render(request, 'nyondoapp/register_customer.html')

        # CHECK IF NIN ALREADY EXISTS
        if Customer.objects.filter(nin=nin).exists():
            messages.error(request, f'A customer with NIN {nin} is already registered.')
            return render(request, 'nyondoapp/register_customer.html')

        # CHECK IF PHONE ALREADY EXISTS
        if Customer.objects.filter(phone_number=phone_number).exists():
            messages.error(request, 'A customer with this phone number is already registered.')
            return render(request, 'nyondoapp/register_customer.html')

        # SAVE THE CUSTOMER
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
