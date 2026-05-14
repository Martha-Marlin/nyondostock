from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="StockItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("item_name", models.CharField(max_length=120)),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("Nails", "Nails"),
                            ("Building", "Building"),
                            ("Plumbing", "Plumbing"),
                            ("Paint", "Paint"),
                            ("Steel", "Steel"),
                            ("Roofing", "Roofing"),
                            ("Equipment", "Equipment"),
                        ],
                        max_length=40,
                    ),
                ),
                ("quantity", models.PositiveIntegerField(default=0)),
                (
                    "unit",
                    models.CharField(
                        choices=[
                            ("Pieces", "Pieces"),
                            ("Bags", "Bags"),
                            ("Bundles", "Bundles"),
                            ("Litres", "Litres"),
                            ("Kilograms", "Kilograms"),
                            ("Metres", "Metres"),
                        ],
                        default="Pieces",
                        max_length=20,
                    ),
                ),
                ("minimum_stock", models.PositiveIntegerField(default=0)),
                ("buying_price", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("selling_price", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("supplier", models.CharField(blank=True, max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
