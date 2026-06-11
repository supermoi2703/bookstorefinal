#!/bin/sh
set -e

echo "Waiting for MySQL..."
python - <<'PY'
import os, time, sys
import pymysql

host = os.getenv("DB_HOST", "localhost")
port = int(os.getenv("DB_PORT", "3306"))
user = os.getenv("DB_USER", "")
password = os.getenv("DB_PASSWORD", "")
db = os.getenv("DB_NAME", "")

for i in range(60):
    try:
        conn = pymysql.connect(host=host, port=port, user=user, password=password, database=db, connect_timeout=2)
        conn.close()
        print("MySQL is ready.")
        sys.exit(0)
    except Exception as e:
        time.sleep(2)
print("MySQL not ready after 120s", file=sys.stderr)
sys.exit(1)
PY

python manage.py makemigrations app --noinput
python manage.py migrate --noinput

# Seed data: tạo tài khoản customer + staff mẫu nếu chưa có
echo "Seeding customer data..."
python - <<'SEED'
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_service.settings')
django.setup()

from django.contrib.auth.models import User
from app.models import Customer
from rest_framework.authtoken.models import Token
import requests

CART_SERVICE_URL = os.environ.get('CART_SERVICE_URL', 'http://cart-service:8000')

if User.objects.count() == 0:
    # --- Tạo tài khoản Staff ---
    staff_user = User.objects.create_user(
        username='staff@productstore.com',
        email='staff@productstore.com',
        password='staff123',
        is_staff=True,
    )
    staff_customer = Customer.objects.create(
        user=staff_user,
        name='Nhân viên ProductStore',
        email='staff@productstore.com',
    )
    Token.objects.get_or_create(user=staff_user)
    print("Created staff account: staff@productstore.com / staff123")

    # --- Tạo tài khoản Customer ---
    customers_data = [
        {"name": "Nguyễn Văn A", "email": "customer1@gmail.com", "password": "customer123"},
        {"name": "Trần Thị B", "email": "customer2@gmail.com", "password": "customer123"},
        {"name": "Lê Văn C", "email": "customer3@gmail.com", "password": "customer123"},
    ]

    for c in customers_data:
        user = User.objects.create_user(
            username=c["email"],
            email=c["email"],
            password=c["password"],
        )
        customer = Customer.objects.create(
            user=user,
            name=c["name"],
            email=c["email"],
        )
        Token.objects.get_or_create(user=user)

        # Tạo cart cho customer
        try:
            requests.post(
                f"{CART_SERVICE_URL}/carts/",
                json={"customer_id": customer.id},
                timeout=5,
            )
        except Exception as e:
            print(f"Warning: Could not create cart for {c['email']}: {e}")

        print(f"Created customer: {c['email']} / {c['password']}")

    print("Seeding complete!")
else:
    print(f"Users already exist ({User.objects.count()} users). Skipping seed.")
SEED

exec "$@"
