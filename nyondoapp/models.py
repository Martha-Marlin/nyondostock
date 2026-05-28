from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal


# STOCK ITEM MODEL
# Represents a product or item stored in the hardware shop
class StockItem(models.Model):

    CATEGORY_CHOICES = [
        ("Cement", "Cement"),
        ("Iron Bars", "Iron Bars"),
        ("Iron Sheets", "Iron Sheets"),
        ("Nails", "Nails"),
        ("Wheelbarrows", "Wheelbarrows"),
        ("Wire Mesh", "Wire Mesh"),
        ("Barbed Wire", "Barbed Wire"),
    ]

    UNIT_CHOICES = [
        ("Pieces", "Pieces"),
        ("Bags", "Bags"),
        ("Sheets", "Sheets"),
        ("Packs", "Packs"),
        ("Rolls", "Rolls"),
        ("Bundles", "Bundles"),
        ("Kilograms", "Kilograms"),
        ("Metres", "Metres"),
    ]

    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Discontinued', 'Discontinued'),
        ('Seasonal', 'Seasonal'),
    ]

    item_name = models.CharField(max_length=120)
    category = models.CharField(max_length=40, choices=CATEGORY_CHOICES)
    quantity = models.PositiveIntegerField(default=0)
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default="Pieces")
    minimum_stock = models.PositiveIntegerField(default=0)  # Triggers low stock warning when quantity drops to or below this value
    buying_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    supplier = models.CharField(max_length=120, blank=True)  # Plain text reference to the supplier name
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def stock_status(self):
        # Returns a human-readable stock level based on current quantity vs minimum stock
        if self.quantity == 0:
            return "Out of Stock"
        if self.quantity <= self.minimum_stock:
            return "Low Stock"
        return "In Stock"

    def __str__(self):
        return f"{self.item_name} ({self.quantity})"


# SALE MODEL
# Represents one complete sale transaction made to a customer
class Sale(models.Model):

    PAYMENT_STATUS_CHOICES = [
        ('Paid', 'Paid'),
        ('Pending', 'Pending'),
        ('Credit', 'Credit'),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('Cash', 'Cash'),
        ('Mobile Money', 'Mobile Money'),
        ('Bank Transfer', 'Bank Transfer'),
    ]

    customer_name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=20)
    customer = models.ForeignKey(
        'Customer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales'
    )  # Optional link to a registered deposit scheme customer

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)         # Total before transport charge
    transport_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0) # Delivery fee if applicable
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)     # Final amount: subtotal + transport charge

    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='Pending')
    payment_method = models.CharField(max_length=50, choices=PAYMENT_METHOD_CHOICES, default='Cash')
    wants_delivery = models.BooleanField(default=False)  # True if the customer requested delivery
    notes = models.TextField(blank=True, null=True)

    sold_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True)  # Staff member who recorded this sale
    sale_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Sale #{self.id} - {self.customer_name}"

    class Meta:
        ordering = ['-sale_date']  # Newest sales appear first


# SALE ITEM MODEL
# Represents one product line inside a sale
# A single sale can have multiple sale items (e.g. nails + cement + iron bars)
class SaleItem(models.Model):

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    # CASCADE means if a sale is deleted, all its items are deleted too

    stock_item = models.ForeignKey(StockItem, on_delete=models.SET_NULL, null=True, blank=True)
    # SET_NULL means if a stock item is deleted, this field becomes null
    # The __str__ method handles this gracefully by showing "Deleted Item"

    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)  # Price per unit at the time of sale
    line_total = models.DecimalField(max_digits=12, decimal_places=2)  # Calculated as quantity x unit_price

    def save(self, *args, **kwargs):
        # Automatically calculate line_total before saving to the database
        self.line_total = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        if self.stock_item:
            return f"{self.stock_item.item_name} x {self.quantity}"
        return f"Deleted Item x {self.quantity}"


# SUPPLIER MODEL
# Represents a supplier or vendor that provides stock to the hardware shop
class Supplier(models.Model):

    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Credits Due', 'Credits Due'),
        ('Overdue', 'Overdue'),
        ('Inactive', 'Inactive'),
    ]

    supplier_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, unique=True)
    tin_number = models.CharField(max_length=20, blank=True, null=True, unique=True)  # Tax Identification Number, optional
    email = models.EmailField(blank=True, null=True)
    location = models.CharField(max_length=200, blank=True, null=True)

    balance = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )  # Amount the shop currently owes this supplier

    payment_terms = models.IntegerField(default=30)  # Number of days allowed before payment becomes due
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='suppliers_created'
    )

    class Meta:
        ordering = ['supplier_name']  # Suppliers listed alphabetically

    def __str__(self):
        return self.supplier_name


# SUPPLIER TRANSACTION MODEL
# Tracks every financial event with a supplier:
# goods received on credit, payments made, and manual balance adjustments
class SupplierTransaction(models.Model):

    TRANSACTION_TYPES = [
        ('Credit', 'Credit (Purchase/Goods)'),  # Shop received goods and now owes money
        ('Payment', 'Payment Made'),             # Shop paid the supplier
        ('Adjustment', 'Balance Adjustment'),    # Manual correction to the balance
    ]

    PAYMENT_METHODS = [
        ('Cash', 'Cash'),
        ('Bank Transfer', 'Bank Transfer'),
        ('Cheque', 'Cheque'),
        ('Mobile Money', 'Mobile Money'),
    ]

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name='transactions'
    )  # Deleting a supplier also deletes all their transaction history

    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, blank=True, null=True)
    reference_number = models.CharField(max_length=100, blank=True, null=True)  # e.g. cheque number or bank transfer ID
    description = models.TextField(blank=True, null=True)
    transaction_date = models.DateTimeField(auto_now_add=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supplier_transactions'
    )

    class Meta:
        ordering = ['-transaction_date']  # Newest transactions appear first

    def __str__(self):
        return f"{self.transaction_type} - {self.supplier.supplier_name} - UGX {self.amount:,.2f}"


# SUPPLIER CREDIT MODEL
# Records stock taken from a supplier on credit (the shop owes them)
class SupplierCredit(models.Model):

    STATUS_CHOICES = [
        ('Unpaid', 'Unpaid'),
        ('Partial', 'Partial'),
        ('Cleared', 'Cleared'),
    ]

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name='credits'
    )

    description = models.TextField()  # Description of the goods taken on credit
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Unpaid')
    created_at = models.DateTimeField(auto_now_add=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='credits_created'
    )

    @property
    def balance_due(self):
        # Returns how much is still owed on this credit
        return self.total_amount - self.amount_paid

    class Meta:
        ordering = ['due_date']  # Credits with the nearest due date appear first

    def __str__(self):
        return f"Credit #{self.id} - {self.supplier.supplier_name} - UGX {self.total_amount:,.0f}"


# SUPPLIER CREDIT PAYMENT MODEL
# Records one payment made against a specific supplier credit
# A single supplier credit can have multiple payments over time
class SupplierCreditPayment(models.Model):

    PAYMENT_METHOD_CHOICES = [
        ('Cash', 'Cash'),
        ('Bank Transfer', 'Bank Transfer'),
        ('Cheque', 'Cheque'),
        ('Mobile Money', 'Mobile Money'),
    ]

    credit = models.ForeignKey(
        SupplierCredit,
        on_delete=models.CASCADE,
        related_name='payments'
    )

    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    note = models.TextField(blank=True, null=True)
    paid_at = models.DateTimeField(auto_now_add=True)

    paid_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='credit_payments_made'
    )

    class Meta:
        ordering = ['-paid_at']

    def __str__(self):
        return f"Payment of UGX {self.amount:,.0f} on Credit #{self.credit.id}"


# CUSTOMER MODEL
# Only customers using the deposit scheme are formally registered here
# Walk-in customers are recorded directly on the Sale model by name only
class Customer(models.Model):

    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
    ]

    full_name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=20)
    nin = models.CharField(max_length=14, unique=True)  # National Identification Number, must be unique
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True, null=True)
    area = models.CharField(max_length=100, blank=True, null=True)  # Neighbourhood or town the customer is from
    notes = models.TextField(blank=True, null=True)
    registered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    registered_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name

    def get_gender_from_nin(self):
        # Ugandan NIDs start with CM for male and CF for female
        # This method reads the prefix and returns the gender code
        if self.nin and len(self.nin) >= 2:
            prefix = self.nin[:2].upper()
            if prefix == 'CM':
                return 'M'
            elif prefix == 'CF':
                return 'F'
        return None


# CUSTOMER CREDIT PAYMENT MODEL
# Records instalment payments made by a customer against a credit sale
# A single credit sale can be paid off in multiple instalments over time
class CustomerCreditPayment(models.Model):

    PAYMENT_METHOD_CHOICES = [
        ('Cash', 'Cash'),
        ('Mobile Money', 'Mobile Money'),
        ('Bank Transfer', 'Bank Transfer'),
    ]

    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name='credit_payments'
    )

    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    note = models.TextField(blank=True, null=True)
    paid_at = models.DateTimeField(auto_now_add=True)

    paid_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='customer_credit_payments'
    )

    class Meta:
        ordering = ['-paid_at']

    def __str__(self):
        return f"Payment of UGX {self.amount:,.0f} on Sale #{self.sale.id}"


# DEPOSIT MODEL
# Records orders placed by customers who pay in instalments before collecting goods
# Only cement, iron sheets, and iron bars qualify for the deposit scheme
# Stock is deducted only on the day the customer collects, not when the deposit is created
class Deposit(models.Model):

    ITEM_TYPE_CHOICES = [
        ('Cement CEM II N', 'Cement CEM II N'),
        ('Cement CEM III N', 'Cement CEM III N'),
        ('Iron Sheets', 'Iron Sheets'),
        ('Iron Bars 10mm', 'Iron Bars 10mm'),
        ('Iron Bars 12mm', 'Iron Bars 12mm'),
        ('Iron Bars 16mm', 'Iron Bars 16mm'),
    ]

    UNIT_CHOICES = [
        ('Bags', 'Bags'),
        ('Sheets', 'Sheets'),
        ('Pieces', 'Pieces'),
    ]

    STATUS_CHOICES = [
        ('Active', 'Active'),       # Customer is still paying in instalments
        ('Completed', 'Completed'), # Fully paid, customer may collect goods
        ('Cancelled', 'Cancelled'), # Order was dropped, stock restored
    ]

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='deposits'
    )  # PROTECT prevents deleting a customer who has an active deposit

    item_type = models.CharField(max_length=20, choices=ITEM_TYPE_CHOICES)
    quantity_ordered = models.PositiveIntegerField()
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)    # Estimated total; finalised at collection
    amount_paid = models.DecimalField(max_digits=15, decimal_places=2, default=0)  # Running total of all instalments received
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')

    receipt_number = models.CharField(max_length=20, blank=True, null=True, unique=True)
    # Receipt number is only assigned when the deposit is Completed (official collection receipt)
    # While Active, the deposit ID is used as a temporary reference on instalment receipts

    due_date = models.DateField()  # Expected collection date
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='deposits_created'
    )

    @property
    def balance_remaining(self):
        # Returns how much the customer still needs to pay
        return self.total_amount - self.amount_paid

    @property
    def percent_paid(self):
        # Returns payment progress as a percentage, used to render the progress bar
        if self.total_amount > 0:
            return int((self.amount_paid / self.total_amount) * 100)
        return 0

    class Meta:
        ordering = ['-created_at']  # Newest deposits appear first

    def __str__(self):
        return f"Deposit #{self.id} - {self.customer.full_name} - {self.item_type}"


# DEPOSIT PAYMENT MODEL
# Records one instalment payment made against a deposit
# Each payment generates a temporary deposit receipt
class DepositPayment(models.Model):

    PAYMENT_METHOD_CHOICES = [
        ('Cash', 'Cash'),
        ('Mobile Money', 'Mobile Money'),
        ('Bank Transfer', 'Bank Transfer'),
    ]

    deposit = models.ForeignKey(
        Deposit,
        on_delete=models.CASCADE,
        related_name='payments'
    )  # Deleting a deposit also deletes all its payment records

    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    reference_number = models.CharField(max_length=100, blank=True, null=True)  # e.g. MTN Mobile Money transaction ID
    note = models.TextField(blank=True, null=True)
    paid_at = models.DateTimeField(auto_now_add=True)

    paid_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='deposit_payments_made'
    )

    class Meta:
        ordering = ['-paid_at']  # Newest payments appear first

    def __str__(self):
        return f"Payment of UGX {self.amount:,.0f} on Deposit #{self.deposit.id}"