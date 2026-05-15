from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal


#  STOCK ITEM MODEL 
# Represents a product/item stored in the hardware shop
class StockItem(models.Model):

    # CATEGORY CHOICES - types of hardware items sold
    CATEGORY_CHOICES = [
        ("Nails", "Nails"),
        ("Building", "Building"),
        ("Plumbing", "Plumbing"),
        ("Paint", "Paint"),
        ("Steel", "Steel"),
        ("Roofing", "Roofing"),
        ("Equipment", "Equipment"),
    ]

    # UNIT CHOICES - how each item is measured/sold
    UNIT_CHOICES = [
        ("Pieces", "Pieces"),
        ("Bags", "Bags"),
        ("Bundles", "Bundles"),
        ("Litres", "Litres"),
        ("Kilograms", "Kilograms"),
        ("Metres", "Metres"),
    ]

    # BASIC ITEM INFORMATION
    item_name = models.CharField(max_length=120)           # Name of the product
    category = models.CharField(max_length=40, choices=CATEGORY_CHOICES)  # Product category
    quantity = models.PositiveIntegerField(default=0)      # Current stock quantity
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default="Pieces")  # Unit of measurement
    minimum_stock = models.PositiveIntegerField(default=0) # Minimum before low stock warning triggers

    # PRICING INFORMATION
    buying_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)   # Price we buy from supplier
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # Price we sell to customer

    # SUPPLIER REFERENCE (plain text for now, not linked to Supplier model yet)
    supplier = models.CharField(max_length=120, blank=True)

    # TIMESTAMPS - auto set when record is created or updated
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # STOCK STATUS PROPERTY
    # Automatically calculates status based on current quantity vs minimum stock
    @property
    def stock_status(self):
        if self.quantity == 0:
            return "Out of Stock"
        if self.quantity <= self.minimum_stock:
            return "Low Stock"
        return "In Stock"

    # STRING REPRESENTATION - shown in admin and dropdowns
    def __str__(self):
        return f"{self.item_name} ({self.quantity})"


#  SALE MODEL
# Represents one complete sale transaction made to a customer
class Sale(models.Model):

    # PAYMENT STATUS CHOICES - current state of payment
    PAYMENT_STATUS_CHOICES = [
        ('Paid', 'Paid'),         # Customer has fully paid
        ('Pending', 'Pending'),   # Payment not yet received
        ('Credit', 'Credit'),     # Customer owes money
    ]

    # PAYMENT METHOD CHOICES - how the customer paid
    PAYMENT_METHOD_CHOICES = [
        ('Cash', 'Cash'),
        ('Mobile Money', 'Mobile Money'),
        ('Bank Transfer', 'Bank Transfer'),
    ]

    # CUSTOMER INFORMATION
    customer_name = models.CharField(max_length=200)   # Full name of the customer
    phone_number = models.CharField(max_length=20)     # Customer phone number

    # FINANCIAL TOTALS
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)        # Total before transport
    transport_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0) # Delivery charge if any
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)    # Final amount (subtotal + transport)

    # PAYMENT INFORMATION
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='Pending')
    payment_method = models.CharField(max_length=50, choices=PAYMENT_METHOD_CHOICES, default='Cash')

    # EXTRA DETAILS
    notes = models.TextField(blank=True, null=True)  # Any extra notes about the sale

    # STAFF TRACKING - who recorded this sale
    sold_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True)

    # TIMESTAMP - automatically set when sale is created
    sale_date = models.DateTimeField(auto_now_add=True)

    # STRING REPRESENTATION
    def __str__(self):
        return f"Sale #{self.id} - {self.customer_name}"

    # META - default ordering: newest sales first
    class Meta:
        ordering = ['-sale_date']


#  SALE ITEM MODEL 
# Represents one line item inside a sale (one product sold)
# A single Sale can have multiple SaleItems (e.g. nails + cement + paint)
class SaleItem(models.Model):

    # LINK TO PARENT SALE
    # If the sale is deleted, all its items are deleted too (CASCADE)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')

    # LINK TO STOCK ITEM
    # PROTECT means you cannot delete a stock item that has been sold
    stock_item = models.ForeignKey(StockItem, on_delete=models.PROTECT)

    # QUANTITY AND PRICING FOR THIS LINE
    quantity = models.PositiveIntegerField()                                    # How many units sold
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)          # Price per unit at time of sale
    line_total = models.DecimalField(max_digits=12, decimal_places=2)          # quantity x unit_price

    # AUTO CALCULATE LINE TOTAL BEFORE SAVING
    # Overrides the default save() to compute line_total automatically
    def save(self, *args, **kwargs):
        self.line_total = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    # STRING REPRESENTATION
    def __str__(self):
        return f"{self.stock_item.item_name} x {self.quantity}"


#  SUPPLIER MODEL 
# Represents a supplier/vendor that provides stock to the hardware shop
class Supplier(models.Model):

    # STATUS CHOICES - current account standing of the supplier
    STATUS_CHOICES = [
        ('Active', 'Active'),           # Supplier is in good standing
        ('Credits Due', 'Credits Due'), # We owe them money but not yet overdue
        ('Overdue', 'Overdue'),         # Payment is past the due date
        ('Inactive', 'Inactive'),       # No longer doing business with them
    ]

    # SUPPLIER CONTACT INFORMATION
    supplier_name = models.CharField(max_length=200)              # Full name of supplier/company
    phone = models.CharField(max_length=20, unique=True)          # Phone (unique - no duplicates)
    tin_number = models.CharField(max_length=20, blank=True, null=True, unique=True)  # Tax Identification Number (optional, unique if provided)
    email = models.EmailField(blank=True, null=True)              # Email address (optional)
    location = models.CharField(max_length=200, blank=True, null=True)  # Physical location (optional)

    # FINANCIAL INFORMATION
    balance = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')   # Amount we currently owe this supplier
    )

    # PAYMENT TERMS - number of days allowed before payment is due
    payment_terms = models.IntegerField(default=30)  # e.g. 30 means pay within 30 days

    # ACCOUNT STATUS
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')

    # EXTRA DETAILS
    notes = models.TextField(blank=True, null=True)  # Any special terms or notes

    # TIMESTAMPS
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # STAFF TRACKING - who added this supplier
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='suppliers_created'
    )

    # META - suppliers listed alphabetically by name
    class Meta:
        ordering = ['supplier_name']

    # STRING REPRESENTATION
    def __str__(self):
        return self.supplier_name


#  SUPPLIER TRANSACTION MODEL 
# Tracks every financial transaction with a supplier
# (goods received on credit, payments made, balance adjustments)
class SupplierTransaction(models.Model):

    # TRANSACTION TYPE CHOICES
    TRANSACTION_TYPES = [
        ('Credit', 'Credit (Purchase/Goods)'),  # We received goods, now owe money
        ('Payment', 'Payment Made'),             # We paid the supplier
        ('Adjustment', 'Balance Adjustment'),    # Manual correction to balance
    ]

    # PAYMENT METHOD CHOICES - how we paid the supplier
    PAYMENT_METHODS = [
        ('Cash', 'Cash'),
        ('Bank Transfer', 'Bank Transfer'),
        ('Cheque', 'Cheque'),
        ('Mobile Money', 'Mobile Money'),
    ]

    # LINK TO SUPPLIER
    # If supplier is deleted, all their transactions are deleted too (CASCADE)
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name='transactions'
    )

    # TRANSACTION DETAILS
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=15, decimal_places=2)              # Amount of this transaction
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, blank=True, null=True)
    reference_number = models.CharField(max_length=100, blank=True, null=True) # e.g. cheque number or transfer ID
    description = models.TextField(blank=True, null=True)                      # Extra details about this transaction

    # TIMESTAMP - automatically set when transaction is recorded
    transaction_date = models.DateTimeField(auto_now_add=True)

    # STAFF TRACKING - who recorded this transaction
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supplier_transactions'
    )

    # META - newest transactions shown first
    class Meta:
        ordering = ['-transaction_date']

    # STRING REPRESENTATION
    def __str__(self):
        return f"{self.transaction_type} - {self.supplier.supplier_name} - UGX {self.amount:,.2f}"
    

#  SUPPLIER CREDIT MODEL 
# Records stock taken from a supplier on credit (we owe them)
class SupplierCredit(models.Model):

    STATUS_CHOICES = [
        ('Unpaid', 'Unpaid'),       # No payment made yet
        ('Partial', 'Partial'),     # Some payment made
        ('Cleared', 'Cleared'),     # Fully paid off
    ]

    # LINK TO SUPPLIER
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name='credits'
    )

    # CREDIT DETAILS
    description = models.TextField()  # What goods were taken
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)   # Total owed
    amount_paid = models.DecimalField(max_digits=15, decimal_places=2, default=0)  # Paid so far
    due_date = models.DateField()     # When payment is due

    # STATUS - auto managed when payments are recorded
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Unpaid')

    # TIMESTAMPS AND TRACKING
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='credits_created'
    )

    # OUTSTANDING BALANCE PROPERTY
    @property
    def balance_due(self):
        return self.total_amount - self.amount_paid

    class Meta:
        ordering = ['due_date']

    def __str__(self):
        return f"Credit #{self.id} - {self.supplier.supplier_name} - UGX {self.total_amount:,.0f}"


# ========== SUPPLIER CREDIT PAYMENT MODEL ==========
# Records one payment made against a specific supplier credit
class SupplierCreditPayment(models.Model):

    PAYMENT_METHOD_CHOICES = [
        ('Cash', 'Cash'),
        ('Bank Transfer', 'Bank Transfer'),
        ('Cheque', 'Cheque'),
        ('Mobile Money', 'Mobile Money'),
    ]

    # LINK TO CREDIT
    credit = models.ForeignKey(
        SupplierCredit,
        on_delete=models.CASCADE,
        related_name='payments'
    )

    # PAYMENT DETAILS
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    note = models.TextField(blank=True, null=True)

    # TIMESTAMPS AND TRACKING
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
# Only customers using the deposit scheme are registered here
class Customer(models.Model):
    full_name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=20)
    nin = models.CharField(max_length=14, unique=True)
    area = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    registered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    registered_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name 