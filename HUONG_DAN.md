# Hướng Dẫn Sử Dụng ProductStore Microservice

## Yêu Cầu Hệ Thống

- Docker
- Docker Compose

## Cài Đặt và Chạy Project

### 1. Khởi động tất cả services

```bash
docker-compose up --build
```

Lệnh này sẽ:
- Build tất cả các Docker images
- Tạo các database **MySQL** riêng biệt cho từng service
- Chạy tất cả các microservices

### 2. Kiểm tra services đã chạy

Sau khi chạy, các service sẽ có sẵn tại:

- **API Gateway**: http://localhost:8000
- **Customer Service**: http://localhost:8001
- **Product Service**: http://localhost:8002
- **Cart Service**: http://localhost:8003
- **Order Service**: http://localhost:8004
- **Payment Service**: http://localhost:8005
- **Shipping Service**: http://localhost:8006
- **Rating Service**: http://localhost:8007

## Test Các Chức Năng

> Lưu ý: Theo yêu cầu “tất cả endpoint phải qua gateway”, bạn **chỉ gọi API qua API Gateway**: `http://localhost:8000/api/...`

### 0. Đăng ký / Đăng nhập (Token)

#### Đăng ký

**Endpoint (Gateway)**: `POST http://localhost:8000/api/auth/register/`

**Request Body**:
```json
{
  "name": "Nguyễn Văn A",
  "email": "nguyenvana@example.com",
  "password": "12345678"
}
```

**Ví dụ với curl**:
```bash
curl -X POST http://localhost:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"name":"Nguyễn Văn A","email":"nguyenvana@example.com","password":"12345678"}'
```

Kết quả trả về có `token` và `customer_id`.

#### Đăng nhập

**Endpoint (Gateway)**: `POST http://localhost:8000/api/auth/login/`

**Request Body**:
```json
{
  "email": "nguyenvana@example.com",
  "password": "12345678"
}
```

**Ví dụ với curl**:
```bash
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"nguyenvana@example.com","password":"12345678"}'
```

> Hiện tại các service chưa bắt buộc token cho các endpoint nghiệp vụ; nếu bạn muốn mình có thể bật yêu cầu `Authorization: Token <token>` cho từng API.

### 1. Đăng ký khách hàng (Tự động tạo giỏ hàng)

**Endpoint (Gateway)**: `POST http://localhost:8000/api/customers/`

**Request Body**:
```json
{
  "name": "Nguyễn Văn A",
  "email": "nguyenvana@example.com"
}
```

**Ví dụ với curl**:
```bash
curl -X POST http://localhost:8000/api/customers/ \
  -H "Content-Type: application/json" \
  -d '{"name": "Nguyễn Văn A", "email": "nguyenvana@example.com"}'
```

**Kết quả**: Khách hàng được tạo và giỏ hàng tự động được tạo trong cart-service.

### 2. Staff quản lý sách

**Tạo sách mới (Gateway)**: `POST http://localhost:8000/api/products/`

**Request Body**:
```json
{
  "title": "Django for Beginners",
  "author": "William S. Vincent",
  "price": "29.99",
  "stock": 100
}
```

**Ví dụ với curl**:
```bash
curl -X POST http://localhost:8000/api/products/ \
  -H "Content-Type: application/json" \
  -d '{"title": "Django for Beginners", "author": "William S. Vincent", "price": "29.99", "stock": 100}'
```

**Xem danh sách sách (Gateway)**: `GET http://localhost:8000/api/products/`

**Xem chi tiết sách (Gateway)**: `GET http://localhost:8000/api/products/{id}/`

**Web Interface**: http://localhost:8000/products/ (Hiển thị danh sách sách cho staff)

### 3. Khách hàng thêm sách vào giỏ hàng

**Endpoint (Gateway)**: `POST http://localhost:8000/api/cart-items/`

**Request Body**:
```json
{
  "customer_id": 1,
  "product_id": 1,
  "quantity": 2
}
```

**Lưu ý**: 
- `cart` là ID của giỏ hàng (được tạo tự động khi đăng ký khách hàng)
- `product_id` phải tồn tại trong product-service
- Service sẽ tự động kiểm tra sách có tồn tại không

**Ví dụ với curl**:
```bash
curl -X POST http://localhost:8000/api/cart-items/ \
  -H "Content-Type: application/json" \
  -d '{"customer_id": 1, "product_id": 1, "quantity": 2}'
```

### 4. Xem giỏ hàng

**Endpoint (Gateway)**: `GET http://localhost:8000/api/carts/{customer_id}/`

**Ví dụ với curl**:
```bash
curl http://localhost:8000/api/carts/1/
```

**Web Interface**: http://localhost:8000/cart/1/ (Thay 1 bằng customer_id)

### 5. Cập nhật giỏ hàng

**Cập nhật số lượng (Gateway)**: `PUT http://localhost:8000/api/cart-items/{id}/`

**Request Body**:
```json
{
  "quantity": 5
}
```

**Xóa sách khỏi giỏ (Gateway)**: `DELETE http://localhost:8000/api/cart-items/{id}/`

### 6. Đặt hàng (Kích hoạt payment và shipping)

**Endpoint (Gateway)**: `POST http://localhost:8000/api/orders/`

**Request Body**:
```json
{
  "customer_id": 1,
  "payment_method": "credit_card",
  "shipping_method": "express"
}
```

**Ví dụ với curl**:
```bash
curl -X POST http://localhost:8000/api/orders/ \
  -H "Content-Type: application/json" \
  -d '{"customer_id": 1, "payment_method": "credit_card", "shipping_method": "express"}'
```

**Kết quả**: 
- Đơn hàng được tạo
- Payment tự động được tạo trong payment-service
- Shipping tự động được tạo trong shipping-service

**Xem chi tiết đơn hàng (Gateway)**: `GET http://localhost:8000/api/orders/{id}/`

### 7. Đánh giá sách

**Endpoint (Gateway)**: `POST http://localhost:8000/api/ratings/`

**Request Body**:
```json
{
  "product_id": 1,
  "customer_id": 1,
  "rating": 5,
  "comment": "Sách rất hay!"
}
```

**Lưu ý**: 
- `rating` phải từ 1-5
- Mỗi khách hàng chỉ đánh giá một lần cho mỗi sách

**Ví dụ với curl**:
```bash
curl -X POST http://localhost:8000/api/ratings/ \
  -H "Content-Type: application/json" \
  -d '{"product_id": 1, "customer_id": 1, "rating": 5, "comment": "Sách rất hay!"}'
```

**Xem đánh giá của sách (Gateway)**: `GET http://localhost:8000/api/ratings/list/?product_id=1`

## Luồng Hoạt Động

### Luồng 1: Đăng ký khách hàng → Tự động tạo giỏ hàng

1. POST `/customers/` → Customer Service tạo khách hàng
2. Customer Service tự động gọi Cart Service để tạo giỏ hàng
3. Giỏ hàng được tạo với `customer_id` tương ứng

### Luồng 2: Thêm sách vào giỏ → Kiểm tra sách tồn tại

1. POST `/cart-items/` → Cart Service nhận request
2. Cart Service gọi Product Service để kiểm tra sách có tồn tại không
3. Nếu sách tồn tại → Thêm vào giỏ hàng
4. Nếu không → Trả về lỗi

### Luồng 3: Đặt hàng → Kích hoạt Payment và Shipping

1. POST `/orders/` → Order Service nhận request
2. Order Service lấy thông tin giỏ hàng từ Cart Service
3. Tạo đơn hàng và các order items
4. Tự động gọi Payment Service để tạo payment
5. Tự động gọi Shipping Service để tạo shipping record

## Kiểm Tra Database

Mỗi service có database riêng. Bạn có thể kiểm tra bằng cách:

```bash
# Ví dụ vào container MySQL của customer-db
docker exec -it productstore_micro_05-customer-db-1 mysql -u customer_user -pcustomer_pass -D customer_db

# Xem tables
SHOW TABLES;

# Xem dữ liệu
SELECT * FROM app_customer;
```

### Xem database bằng MySQL Workbench

Trong `docker-compose.yml` đã mở port ra máy host:
- `customer-db`: `127.0.0.1:33061` (schema `customer_db`, user `customer_user`, pass `customer_pass`)
- `product-db`: `127.0.0.1:33062` (schema `product_db`, user `product_user`, pass `product_pass`)
- `cart-db`: `127.0.0.1:33063`
- `order-db`: `127.0.0.1:33064`
- `payment-db`: `127.0.0.1:33065`
- `shipping-db`: `127.0.0.1:33066`
- `rating-db`: `127.0.0.1:33067`

Workbench → New Connection:
- **Hostname**: `127.0.0.1`
- **Port**: (ví dụ `33061`)
- **Username**: (ví dụ `customer_user`)
- **Password**: (ví dụ `customer_pass`)

## Troubleshooting

### Service không khởi động được

1. Kiểm tra logs: `docker-compose logs [service-name]`
2. Kiểm tra database đã sẵn sàng chưa
3. Kiểm tra network: `docker network ls`

### Lỗi kết nối giữa các service

- Đảm bảo các service đã khởi động xong
- Kiểm tra tên service trong docker-compose (ví dụ: `cart-service`, `product-service`)
- Kiểm tra environment variables trong docker-compose.yml

### Database migration lỗi

- Xóa volumes và chạy lại: `docker-compose down -v && docker-compose up --build`

## Dừng Services

```bash
docker-compose down
```

Để xóa cả volumes (database):
```bash
docker-compose down -v
```
