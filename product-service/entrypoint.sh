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
    except Exception:
        time.sleep(2)
print("MySQL not ready after 120s", file=sys.stderr)
sys.exit(1)
PY

python manage.py migrate --noinput

# Seed data: tạo categories + sách mẫu phong phú
echo "Seeding product data..."
python - <<'SEED'
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'product_service.settings')
django.setup()

from app.models import Category, Product

if Category.objects.count() == 0:
    categories = [
        {"name": "Văn học", "slug": "van-hoc", "icon": "📖", "description": "Tiểu thuyết, truyện ngắn, thơ ca và các tác phẩm văn học kinh điển"},
        {"name": "Kỹ năng sống", "slug": "ky-nang-song", "icon": "🌟", "description": "Phát triển bản thân, kỹ năng mềm, tư duy tích cực"},
        {"name": "Khoa học", "slug": "khoa-hoc", "icon": "🔬", "description": "Khoa học tự nhiên, vũ trụ, sinh học, vật lý"},
        {"name": "Công nghệ", "slug": "cong-nghe", "icon": "💻", "description": "Lập trình, phần mềm, công nghệ thông tin"},
        {"name": "Kinh doanh", "slug": "kinh-doanh", "icon": "💼", "description": "Quản trị, marketing, tài chính, khởi nghiệp"},
        {"name": "Lịch sử", "slug": "lich-su", "icon": "🏛️", "description": "Lịch sử thế giới, lịch sử Việt Nam, nhân vật lịch sử"},
        {"name": "Thiếu nhi", "slug": "thieu-nhi", "icon": "🧸", "description": "Truyện tranh, sách giáo dục, sách tô màu cho trẻ em"},
        {"name": "Tâm lý", "slug": "tam-ly", "icon": "🧠", "description": "Tâm lý học, triết học, thiền định và chánh niệm"},
    ]
    cat_map = {}
    for c in categories:
        cat = Category.objects.create(**c)
        cat_map[c["slug"]] = cat
    print(f"Seeded {len(categories)} categories!")

    products = [
        # Văn học
        {"title": "Đắc Nhân Tâm", "author": "Dale Carnegie", "price": 5.99, "stock": 50, "category": cat_map["van-hoc"], "is_featured": True,
         "description": "Cuốn sách kinh điển về nghệ thuật giao tiếp và ứng xử, giúp bạn gây ảnh hưởng đến người khác.", "publisher": "NXB Tổng Hợp", "pages": 320, "published_year": 2019},
        {"title": "Nhà Giả Kim", "author": "Paulo Coelho", "price": 4.99, "stock": 35, "category": cat_map["van-hoc"], "is_featured": True,
         "description": "Câu chuyện về chàng chăn cừu Santiago và hành trình theo đuổi giấc mơ.", "publisher": "NXB Hội Nhà Văn", "pages": 228, "published_year": 2020},
        {"title": "Muôn Kiếp Nhân Sinh", "author": "Nguyên Phong", "price": 5.49, "stock": 55, "category": cat_map["van-hoc"],
         "description": "Những câu chuyện về luân hồi và triết lý sống sâu sắc.", "publisher": "NXB Tổng Hợp", "pages": 400, "published_year": 2021},
        {"title": "Cho Tôi Xin Một Vé Đi Tuổi Thơ", "author": "Nguyễn Nhật Ánh", "price": 3.99, "stock": 40, "category": cat_map["van-hoc"],
         "description": "Hành trình trở về tuổi thơ đầy xúc cảm của nhà văn Nguyễn Nhật Ánh.", "publisher": "NXB Trẻ", "pages": 216, "published_year": 2018},

        # Kỹ năng sống
        {"title": "Tuổi Trẻ Đáng Giá Bao Nhiêu", "author": "Rosie Nguyễn", "price": 3.99, "stock": 40, "category": cat_map["ky-nang-song"], "is_featured": True,
         "description": "Chia sẻ kinh nghiệm sống và làm việc cho người trẻ.", "publisher": "NXB Hội Nhà Văn", "pages": 286, "published_year": 2019},
        {"title": "Atomic Habits", "author": "James Clear", "price": 6.99, "stock": 45, "category": cat_map["ky-nang-song"], "is_featured": True,
         "description": "Xây dựng thói quen tốt và loại bỏ thói quen xấu với phương pháp khoa học.", "publisher": "NXB Thế Giới", "pages": 352, "published_year": 2020},
        {"title": "Dám Bị Ghét", "author": "Kishimi Ichiro & Koga Fumitake", "price": 4.49, "stock": 30, "category": cat_map["ky-nang-song"],
         "description": "Triết học Adler về lòng can đảm được hạnh phúc.", "publisher": "NXB Lao Động", "pages": 296, "published_year": 2019},
        {"title": "Cà Phê Cùng Tony", "author": "Tony Buổi Sáng", "price": 3.49, "stock": 60, "category": cat_map["ky-nang-song"],
         "description": "Những bài viết truyền cảm hứng về cuộc sống và công việc.", "publisher": "NXB Trẻ", "pages": 268, "published_year": 2018},

        # Khoa học
        {"title": "Sapiens: Lược Sử Loài Người", "author": "Yuval Noah Harari", "price": 8.99, "stock": 25, "category": cat_map["khoa-hoc"], "is_featured": True,
         "description": "Hành trình 70.000 năm của loài người từ thời đồ đá đến kỷ nguyên số.", "publisher": "NXB Tri Thức", "pages": 560, "published_year": 2020},
        {"title": "Homo Deus", "author": "Yuval Noah Harari", "price": 9.49, "stock": 22, "category": cat_map["khoa-hoc"],
         "description": "Tương lai của loài người trong kỷ nguyên công nghệ.", "publisher": "NXB Tri Thức", "pages": 520, "published_year": 2021},
        {"title": "Lược Sử Thời Gian", "author": "Stephen Hawking", "price": 7.99, "stock": 18, "category": cat_map["khoa-hoc"],
         "description": "Từ Big Bang đến lỗ đen - hành trình khám phá vũ trụ.", "publisher": "NXB Trẻ", "pages": 256, "published_year": 2019},

        # Công nghệ
        {"title": "Clean Code", "author": "Robert C. Martin", "price": 12.99, "stock": 15, "category": cat_map["cong-nghe"], "is_featured": True,
         "description": "Nghệ thuật viết code sạch, dễ đọc và dễ bảo trì.", "publisher": "NXB Bách Khoa", "pages": 464, "published_year": 2019, "language": "Song ngữ"},
        {"title": "Design Patterns", "author": "Gang of Four", "price": 14.99, "stock": 10, "category": cat_map["cong-nghe"],
         "description": "23 design patterns kinh điển trong lập trình hướng đối tượng.", "publisher": "NXB Bách Khoa", "pages": 395, "published_year": 2018, "language": "English"},
        {"title": "The Pragmatic Programmer", "author": "David Thomas & Andrew Hunt", "price": 11.99, "stock": 18, "category": cat_map["cong-nghe"],
         "description": "Hành trình từ apprentice đến master trong lập trình.", "publisher": "NXB Bách Khoa", "pages": 352, "published_year": 2020, "language": "English"},
        {"title": "Python Crash Course", "author": "Eric Matthes", "price": 10.99, "stock": 28, "category": cat_map["cong-nghe"],
         "description": "Hướng dẫn Python cơ bản đến nâng cao dành cho người mới.", "publisher": "NXB Bách Khoa", "pages": 560, "published_year": 2021, "language": "English"},
        {"title": "Refactoring", "author": "Martin Fowler", "price": 13.49, "stock": 12, "category": cat_map["cong-nghe"],
         "description": "Cải thiện thiết kế code hiện có một cách có hệ thống.", "publisher": "NXB Bách Khoa", "pages": 448, "published_year": 2019, "language": "English"},

        # Kinh doanh
        {"title": "Từ Tốt Đến Vĩ Đại", "author": "Jim Collins", "price": 7.99, "stock": 20, "category": cat_map["kinh-doanh"],
         "description": "Nghiên cứu về các công ty chuyển đổi từ tốt thành vĩ đại.", "publisher": "NXB Trẻ", "pages": 368, "published_year": 2019},
        {"title": "Khởi Nghiệp Tinh Gọn", "author": "Eric Ries", "price": 6.49, "stock": 25, "category": cat_map["kinh-doanh"],
         "description": "Phương pháp Lean Startup cho doanh nghiệp mới.", "publisher": "NXB Thế Giới", "pages": 304, "published_year": 2020},

        # Tâm lý
        {"title": "Tư Duy Nhanh Và Chậm", "author": "Daniel Kahneman", "price": 7.99, "stock": 20, "category": cat_map["tam-ly"], "is_featured": True,
         "description": "Hai hệ thống tư duy của con người và cách chúng ảnh hưởng quyết định.", "publisher": "NXB Thế Giới", "pages": 520, "published_year": 2020},
        {"title": "Nghĩ Giàu Làm Giàu", "author": "Napoleon Hill", "price": 4.99, "stock": 35, "category": cat_map["tam-ly"],
         "description": "13 nguyên tắc tư duy để thành công trong cuộc sống.", "publisher": "NXB Tổng Hợp", "pages": 384, "published_year": 2019},

        # Lịch sử
        {"title": "Việt Nam Sử Lược", "author": "Trần Trọng Kim", "price": 6.99, "stock": 15, "category": cat_map["lich-su"],
         "description": "Tổng quan lịch sử Việt Nam từ thời Hùng Vương.", "publisher": "NXB Văn Học", "pages": 620, "published_year": 2018},

        # Thiếu nhi
        {"title": "Hoàng Tử Bé", "author": "Antoine de Saint-Exupéry", "price": 3.49, "stock": 45, "category": cat_map["thieu-nhi"], "is_featured": True,
         "description": "Câu chuyện triết lý nhẹ nhàng về tình bạn và tình yêu.", "publisher": "NXB Kim Đồng", "pages": 120, "published_year": 2020},
        {"title": "Dế Mèn Phiêu Lưu Ký", "author": "Tô Hoài", "price": 2.99, "stock": 50, "category": cat_map["thieu-nhi"],
         "description": "Cuộc phiêu lưu của chú Dế Mèn qua thế giới côn trùng.", "publisher": "NXB Kim Đồng", "pages": 180, "published_year": 2019},
    ]

    for b in products:
        Product.objects.create(**b)
    print(f"Seeded {len(products)} products with categories!")
else:
    print(f"Data already exists ({Category.objects.count()} categories, {Product.objects.count()} products). Skipping seed.")
SEED

exec "$@"
