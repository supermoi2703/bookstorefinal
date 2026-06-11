from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("slug", models.SlugField(max_length=120, unique=True)),
                ("icon", models.CharField(blank=True, default="", max_length=16)),
                ("description", models.TextField(blank=True, default="")),
                ("is_active", models.BooleanField(db_index=True, default=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Product",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("author", models.CharField(blank=True, default="", max_length=255)),
                ("creator_or_brand", models.CharField(blank=True, default="", max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("price", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("discount_price", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("stock", models.PositiveIntegerField(default=0)),
                ("domain", models.CharField(choices=[("book", "Book"), ("electronics", "Electronics"), ("fashion", "Fashion"), ("general", "General")], db_index=True, default="book", max_length=32)),
                ("source", models.CharField(db_index=True, default="local", max_length=64)),
                ("external_id", models.CharField(blank=True, max_length=128, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("image_url", models.URLField(blank=True, default="", max_length=1000)),
                ("publisher", models.CharField(blank=True, default="", max_length=255)),
                ("published_year", models.PositiveIntegerField(blank=True, null=True)),
                ("pages", models.PositiveIntegerField(blank=True, null=True)),
                ("language", models.CharField(blank=True, default="", max_length=64)),
                ("isbn", models.CharField(blank=True, default="", max_length=32)),
                ("is_featured", models.BooleanField(db_index=True, default=False)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="products", to="app.category")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["domain", "is_active"], name="app_product_domain_393e48_idx"),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["source", "external_id"], name="app_product_source_3c6c80_idx"),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.UniqueConstraint(fields=("source", "external_id"), name="unique_product_source_external_id"),
        ),
    ]
