from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
import requests
import os

PRODUCT_SERVICE_URL = os.environ.get('PRODUCT_SERVICE_URL', 'http://product-service:8000')
CART_SERVICE_URL = os.environ.get('CART_SERVICE_URL', 'http://cart-service:8000')
CUSTOMER_SERVICE_URL = os.environ.get('CUSTOMER_SERVICE_URL', 'http://customer-service:8000')
ORDER_SERVICE_URL = os.environ.get('ORDER_SERVICE_URL', 'http://order-service:8000')
RATING_SERVICE_URL = os.environ.get('RATING_SERVICE_URL', 'http://rating-service:8000')
PAYMENT_SERVICE_URL = os.environ.get('PAYMENT_SERVICE_URL', 'http://payment-service:8000')
SHIPPING_SERVICE_URL = os.environ.get('SHIPPING_SERVICE_URL', 'http://shipping-service:8000')
AI_SERVICE_URL = os.environ.get('AI_SERVICE_URL', 'http://ai-service:8000')


def _base_context(request):
    """Context chung cho tất cả template."""
    return {
        'customer_id': request.session.get('customer_id'),
        'email': request.session.get('email'),
        'is_staff': request.session.get('is_staff'),
        'customer_name': request.session.get('customer_name', ''),
    }


def _track_event(request, event_type, payload=None):
    customer_id = request.session.get('customer_id')
    event_payload = {
        "event_type": event_type,
        "customer_id": customer_id,
        "session_id": request.session.session_key or "",
        "payload": payload or {},
    }
    try:
        requests.post(f"{AI_SERVICE_URL}/events/ingest/", json=event_payload, timeout=2)
    except requests.exceptions.RequestException:
        pass


def home(request):
    context = _base_context(request)
    customer_id = request.session.get('customer_id')

    # Lấy sách nổi bật
    try:
        r = requests.get(f"{PRODUCT_SERVICE_URL}/products/?featured=1", timeout=5)
        context['featured_products'] = r.json() if r.status_code == 200 else []
    except requests.exceptions.RequestException:
        context['featured_products'] = []

    # Lấy danh mục
    try:
        r = requests.get(f"{PRODUCT_SERVICE_URL}/categories/", timeout=5)
        context['categories'] = r.json() if r.status_code == 200 else []
    except requests.exceptions.RequestException:
        context['categories'] = []

    # Recommendation block for logged-in users
    personalized_products = []
    if customer_id:
        try:
            rr = requests.post(
                f"{AI_SERVICE_URL}/behavior/recommend-products/",
                json={"customer_id": customer_id, "limit": 4},
                timeout=3,
            )
            if rr.status_code == 200:
                personalized_products = rr.json().get("items", [])
        except requests.exceptions.RequestException:
            pass
    context["personalized_products"] = personalized_products

    return render(request, 'home.html', context)


def register_page(request):
    error = None
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        password = request.POST.get('password')
        try:
            r = requests.post(
                f"{CUSTOMER_SERVICE_URL}/auth/register/",
                json={'name': name, 'email': email, 'password': password},
                timeout=5,
            )
            if r.status_code in (200, 201):
                data = r.json()
                request.session['token'] = data.get('token')
                request.session['customer_id'] = data.get('customer_id')
                request.session['email'] = data.get('email')
                request.session['customer_name'] = data.get('name', '')
                request.session['is_staff'] = False
                return redirect('home')
            else:
                error = f"Lỗi đăng ký: {r.status_code} - {r.text}"
        except requests.exceptions.RequestException as e:
            error = f"Lỗi kết nối tới customer-service: {e}"

    return render(request, 'auth_register.html', {'error': error})


def login_page(request):
    error = None
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        try:
            r = requests.post(
                f"{CUSTOMER_SERVICE_URL}/auth/login/",
                json={'email': email, 'password': password},
                timeout=5,
            )
            if r.status_code == 200:
                data = r.json()
                request.session['token'] = data.get('token')
                request.session['customer_id'] = data.get('customer_id')
                request.session['email'] = email
                request.session['customer_name'] = data.get('name', '')
                request.session['is_staff'] = data.get('is_staff', False)
                if request.session['is_staff']:
                    return redirect('staff_products')
                return redirect('home')
            else:
                error = "Sai email hoặc mật khẩu."
        except requests.exceptions.RequestException as e:
            error = f"Lỗi kết nối tới customer-service: {e}"

    return render(request, 'auth_login.html', {'error': error})


def logout_view(request):
    request.session.flush()
    return redirect('home')


# ===== PRODUCTS =====

def product_list(request):
    ctx = _base_context(request)

    # Lấy categories để hiển thị filter
    try:
        r = requests.get(f"{PRODUCT_SERVICE_URL}/categories/", timeout=5)
        ctx['categories'] = r.json() if r.status_code == 200 else []
    except requests.exceptions.RequestException:
        ctx['categories'] = []

    # Build query params
    params = {}
    q = request.GET.get('q')
    category = request.GET.get('category')
    sort = request.GET.get('sort', '-created_at')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')

    if q:
        params['q'] = q
    if category:
        params['category'] = category
    if sort:
        params['sort'] = sort
    if min_price:
        params['min_price'] = min_price
    if max_price:
        params['max_price'] = max_price

    try:
        r = requests.get(f"{PRODUCT_SERVICE_URL}/products/", params=params, timeout=5)
        ctx['products'] = r.json() if r.status_code == 200 else []
    except requests.exceptions.RequestException:
        ctx['products'] = []
    _track_event(request, "search_products" if q else "view_product_list", {"q": q or "", "category": category or ""})

    ctx['current_q'] = q or ''
    ctx['current_category'] = category or ''
    ctx['current_sort'] = sort
    ctx['current_min_price'] = min_price or ''
    ctx['current_max_price'] = max_price or ''

    # AI Graph Recommendations cho logged-in users
    graph_recommendations = []
    customer_id = request.session.get('customer_id')
    if customer_id:
        try:
            rr = requests.post(
                f"{AI_SERVICE_URL}/behavior/recommend-products/",
                json={"customer_id": customer_id, "limit": 4, "query": q or ""},
                timeout=3,
            )
            if rr.status_code == 200:
                graph_recommendations = rr.json().get("items", [])
        except requests.exceptions.RequestException:
            pass
    ctx['graph_recommendations'] = graph_recommendations

    return render(request, 'products.html', ctx)


def product_detail(request, product_id):
    ctx = _base_context(request)

    product = None
    try:
        r = requests.get(f"{PRODUCT_SERVICE_URL}/products/{product_id}/", timeout=5)
        if r.status_code == 200:
            product = r.json()
    except requests.exceptions.RequestException:
        pass

    if not product:
        return redirect('product_list')
    _track_event(
        request,
        "view_product",
        {
            "product_id": product_id,
            "category": product.get("category"),
            "domain": product.get("domain", "general"),
        },
    )

    # Get ratings
    ratings = []
    try:
        r = requests.get(f"{RATING_SERVICE_URL}/ratings/list/", params={'product_id': product_id}, timeout=5)
        if r.status_code == 200:
            ratings = r.json()
    except requests.exceptions.RequestException:
        pass

    avg_rating = 0
    if ratings:
        avg_rating = sum(r.get('rating', 0) for r in ratings) / len(ratings)

    customer_id = request.session.get('customer_id')
    already_rated = False
    if customer_id and ratings:
        already_rated = any(r.get('customer_id') == customer_id for r in ratings)

    # Check wishlist
    in_wishlist = False
    if customer_id:
        try:
            wr = requests.get(
                f"{CUSTOMER_SERVICE_URL}/customers/{customer_id}/wishlist/{product_id}/check/",
                timeout=5,
            )
            if wr.status_code == 200:
                in_wishlist = wr.json().get('in_wishlist', False)
        except requests.exceptions.RequestException:
            pass

    # Related products (same category)
    related_products = []
    if product.get('category'):
        try:
            rr = requests.get(
                f"{PRODUCT_SERVICE_URL}/products/",
                params={'category': product['category']},
                timeout=5,
            )
            if rr.status_code == 200:
                related_products = [b for b in rr.json() if b['id'] != product_id][:4]
        except requests.exceptions.RequestException:
            pass

    recommended_products = []
    customer_id = request.session.get('customer_id')
    if customer_id:
        try:
            rr = requests.post(
                f"{AI_SERVICE_URL}/behavior/recommend-products/",
                json={
                    "customer_id": customer_id,
                    "limit": 4,
                    "domain": product.get("domain", "general"),
                },
                timeout=3,
            )
            if rr.status_code == 200:
                recommended_products = rr.json().get("items", [])
        except requests.exceptions.RequestException:
            pass

    ctx.update({
        'product': product,
        'ratings': ratings,
        'avg_rating': round(avg_rating, 1),
        'rating_count': len(ratings),
        'already_rated': already_rated,
        'in_wishlist': in_wishlist,
        'related_products': related_products,
        'recommended_products': recommended_products,
    })
    return render(request, 'product_detail.html', ctx)


def rate_product(request, product_id):
    customer_id = request.session.get('customer_id')
    if not customer_id:
        return redirect('login_page')

    if request.method == 'POST':
        rating = request.POST.get('rating')
        comment = request.POST.get('comment', '')
        try:
            requests.post(
                f"{RATING_SERVICE_URL}/ratings/",
                json={'product_id': product_id, 'customer_id': customer_id, 'rating': int(rating), 'comment': comment},
                timeout=5,
            )
        except requests.exceptions.RequestException:
            pass

    return redirect('product_detail', product_id=product_id)


# ===== CART =====

def view_cart(request, customer_id):
    ctx = _base_context(request)
    message = request.GET.get('message')
    try:
        r = requests.get(f"{CART_SERVICE_URL}/carts/{customer_id}/", timeout=5)
        items = r.json() if r.status_code == 200 else []
    except requests.exceptions.RequestException:
        items = []

    for item in items:
        try:
            br = requests.get(f"{PRODUCT_SERVICE_URL}/products/{item['product_id']}/", timeout=5)
            if br.status_code == 200:
                product_data = br.json()
                item['product_title'] = product_data.get('title', f"Product #{item['product_id']}")
                item['product_price'] = product_data.get('price', '0')
                item['product_image'] = product_data.get('image_url')
                item['product_author'] = product_data.get('author', '')
            else:
                item['product_title'] = f"Product #{item['product_id']}"
                item['product_price'] = '0'
        except requests.exceptions.RequestException:
            item['product_title'] = f"Product #{item['product_id']}"
            item['product_price'] = '0'

    # AI Graph Recommendations cho giỏ hàng
    graph_recommendations = []
    if customer_id:
        try:
            rr = requests.post(
                f"{AI_SERVICE_URL}/behavior/recommend-products/",
                json={"customer_id": customer_id, "limit": 4},
                timeout=3,
            )
            if rr.status_code == 200:
                graph_recommendations = rr.json().get("items", [])
        except requests.exceptions.RequestException:
            pass

    ctx.update({'items': items, 'customer_id': customer_id, 'message': message, 'graph_recommendations': graph_recommendations})
    return render(request, 'cart.html', ctx)


def my_cart(request):
    customer_id = request.session.get('customer_id')
    if not customer_id:
        return redirect('login_page')
    return view_cart(request, customer_id)


def add_to_cart(request, product_id):
    customer_id = request.session.get('customer_id')
    if not customer_id:
        return redirect('login_page')

    if request.method == 'POST':
        quantity = request.POST.get('quantity') or 1
        try:
            r = requests.post(
                f"{CART_SERVICE_URL}/cart-items/",
                json={'customer_id': customer_id, 'product_id': product_id, 'quantity': int(quantity)},
                timeout=5,
            )
            if r.status_code in (200, 201):
                _track_event(request, "add_to_cart", {"product_id": product_id, "quantity": int(quantity)})
                return redirect('my_cart')
        except requests.exceptions.RequestException:
            pass

    return redirect('product_list')


def remove_cart_item(request, item_id):
    customer_id = request.session.get('customer_id')
    if not customer_id:
        return redirect('login_page')

    if request.method == 'POST':
        try:
            requests.delete(f"{CART_SERVICE_URL}/cart-items/{item_id}/", timeout=5)
        except requests.exceptions.RequestException:
            pass

    return redirect('my_cart')


def update_cart_item(request, item_id):
    customer_id = request.session.get('customer_id')
    if not customer_id:
        return redirect('login_page')

    if request.method == 'POST':
        quantity = request.POST.get('quantity')
        try:
            requests.put(
                f"{CART_SERVICE_URL}/cart-items/{item_id}/",
                json={'quantity': int(quantity)},
                timeout=5,
            )
        except requests.exceptions.RequestException:
            pass

    return redirect('my_cart')


# ===== CHECKOUT =====

def checkout(request):
    customer_id = request.session.get('customer_id')
    if not customer_id:
        return redirect('login_page')

    try:
        r = requests.get(f"{CART_SERVICE_URL}/carts/{customer_id}/", timeout=5)
        items = r.json() if r.status_code == 200 else []
    except requests.exceptions.RequestException:
        items = []

    if not items:
        return redirect('my_cart')
    _track_event(request, "checkout_start", {"item_count": len(items)})

    total = 0
    for item in items:
        try:
            br = requests.get(f"{PRODUCT_SERVICE_URL}/products/{item['product_id']}/", timeout=5)
            if br.status_code == 200:
                product_data = br.json()
                item['product_title'] = product_data.get('title', f"Product #{item['product_id']}")
                item['product_price'] = float(product_data.get('price', 0))
            else:
                item['product_title'] = f"Product #{item['product_id']}"
                item['product_price'] = 0
        except requests.exceptions.RequestException:
            item['product_title'] = f"Product #{item['product_id']}"
            item['product_price'] = 0
        item['subtotal'] = item['product_price'] * item['quantity']
        total += item['subtotal']

    # Get saved addresses
    addresses = []
    try:
        ar = requests.get(f"{CUSTOMER_SERVICE_URL}/customers/{customer_id}/addresses/", timeout=5)
        if ar.status_code == 200:
            addresses = ar.json()
    except requests.exceptions.RequestException:
        pass

    ctx = _base_context(request)
    ctx.update({'items': items, 'total': total, 'addresses': addresses})
    return render(request, 'checkout.html', ctx)


def place_order(request):
    customer_id = request.session.get('customer_id')
    if not customer_id:
        return redirect('login_page')

    if request.method == 'POST':
        payment_method = request.POST.get('payment_method', 'cod')
        shipping_method = request.POST.get('shipping_method', 'standard')
        address = request.POST.get('address', '')
        phone = request.POST.get('phone', '')
        notes = request.POST.get('notes', '')

        try:
            r = requests.post(
                f"{ORDER_SERVICE_URL}/orders/",
                json={
                    'customer_id': customer_id,
                    'payment_method': payment_method,
                    'shipping_method': shipping_method,
                    'address': address,
                    'phone': phone,
                    'notes': notes,
                },
                timeout=10,
            )
            if r.status_code in (200, 201):
                order_data = r.json()
                _track_event(
                    request,
                    "order_created",
                    {
                        "order_id": order_data.get("id"),
                        "total_amount": order_data.get("total_amount"),
                        "payment_method": payment_method,
                        "shipping_method": shipping_method,
                    },
                )

                pay_map = {'cod': '💵 COD', 'bank_transfer': '🏦 Chuyển khoản', 'credit_card': '💳 Thẻ tín dụng'}
                ship_map = {'standard': '📦 Tiêu chuẩn (3-5 ngày)', 'express': '⚡ Nhanh (1-2 ngày)'}
                status_map = {'pending': '⏳ Đang xử lý', 'confirmed': '✅ Đã xác nhận', 'completed': '🎉 Hoàn thành', 'shipping': '🚚 Đang giao'}

                ctx = _base_context(request)
                ctx.update({
                    'order': order_data,
                    'order_total': order_data.get('total_amount', '0'),
                    'order_status_display': status_map.get(order_data.get('status', ''), order_data.get('status', '')),
                    'payment_display': pay_map.get(payment_method, payment_method),
                    'shipping_display': ship_map.get(shipping_method, shipping_method),
                    'address': address,
                    'phone': phone,
                })
                return render(request, 'order_success.html', ctx)
            else:
                error = f"Lỗi đặt hàng: {r.status_code} - {r.text}"
                ctx = _base_context(request)
                ctx.update({'error': error, 'items': [], 'total': 0})
                return render(request, 'checkout.html', ctx)
        except requests.exceptions.RequestException as e:
            ctx = _base_context(request)
            ctx.update({'error': f"Lỗi kết nối: {e}", 'items': [], 'total': 0})
            return render(request, 'checkout.html', ctx)

    return redirect('checkout')


# ===== STAFF =====

def staff_products(request):
    if not request.session.get('is_staff'):
        return redirect('home')

    ctx = _base_context(request)
    error = None
    success = None

    if request.method == 'POST':
        title = request.POST.get('title')
        author = request.POST.get('author')
        price = request.POST.get('price')
        stock = request.POST.get('stock')
        category = request.POST.get('category')
        description = request.POST.get('description', '')
        discount_price = request.POST.get('discount_price') or None
        is_featured = request.POST.get('is_featured') == 'on'

        product_data = {
            'title': title,
            'author': author,
            'price': price,
            'stock': int(stock),
            'description': description,
            'is_featured': is_featured,
        }
        if category:
            product_data['category'] = int(category)
        if discount_price:
            product_data['discount_price'] = discount_price

        try:
            r = requests.post(f"{PRODUCT_SERVICE_URL}/products/", json=product_data, timeout=5)
            if r.status_code in (200, 201):
                success = "Tạo sách mới thành công."
            else:
                error = f"Lỗi tạo sách: {r.status_code} - {r.text}"
        except requests.exceptions.RequestException as e:
            error = f"Lỗi kết nối tới product-service: {e}"

    try:
        r = requests.get(f"{PRODUCT_SERVICE_URL}/products/", timeout=5)
        ctx['products'] = r.json() if r.status_code == 200 else []
    except requests.exceptions.RequestException:
        ctx['products'] = []

    try:
        r = requests.get(f"{PRODUCT_SERVICE_URL}/categories/", timeout=5)
        ctx['categories'] = r.json() if r.status_code == 200 else []
    except requests.exceptions.RequestException:
        ctx['categories'] = []

    ctx['error'] = error
    ctx['success'] = success
    return render(request, 'staff_products.html', ctx)


def staff_edit_product(request, product_id):
    if not request.session.get('is_staff'):
        return redirect('home')

    if request.method == 'POST':
        product_data = {
            'title': request.POST.get('title'),
            'author': request.POST.get('author'),
            'price': request.POST.get('price'),
            'stock': int(request.POST.get('stock', 0)),
        }
        category = request.POST.get('category')
        if category:
            product_data['category'] = int(category)
        description = request.POST.get('description')
        if description is not None:
            product_data['description'] = description
        discount_price = request.POST.get('discount_price')
        if discount_price:
            product_data['discount_price'] = discount_price

        try:
            requests.put(f"{PRODUCT_SERVICE_URL}/products/{product_id}/", json=product_data, timeout=5)
        except requests.exceptions.RequestException:
            pass
    return redirect('staff_products')


def staff_delete_product(request, product_id):
    if not request.session.get('is_staff'):
        return redirect('home')

    if request.method == 'POST':
        try:
            requests.delete(f"{PRODUCT_SERVICE_URL}/products/{product_id}/", timeout=5)
        except requests.exceptions.RequestException:
            pass
    return redirect('staff_products')


# ===== ORDER HISTORY =====

def order_history(request):
    customer_id = request.session.get('customer_id')
    if not customer_id:
        return redirect('login_page')

    ctx = _base_context(request)
    orders = []
    try:
        r = requests.get(f"{ORDER_SERVICE_URL}/orders/customer/{customer_id}/", timeout=5)
        if r.status_code == 200:
            orders = r.json()
    except requests.exceptions.RequestException:
        pass

    for order in orders:
        try:
            pr = requests.get(f"{PAYMENT_SERVICE_URL}/payments/order/{order['id']}/", timeout=5)
            if pr.status_code == 200:
                order['payment'] = pr.json()
        except requests.exceptions.RequestException:
            pass

        try:
            sr = requests.get(f"{SHIPPING_SERVICE_URL}/shippings/order/{order['id']}/", timeout=5)
            if sr.status_code == 200:
                order['shipping'] = sr.json()
        except requests.exceptions.RequestException:
            pass

        for item in order.get('items', []):
            try:
                br = requests.get(f"{PRODUCT_SERVICE_URL}/products/{item['product_id']}/", timeout=5)
                if br.status_code == 200:
                    item['product_title'] = br.json().get('title', f"Product #{item['product_id']}")
                else:
                    item['product_title'] = f"Product #{item['product_id']}"
            except requests.exceptions.RequestException:
                item['product_title'] = f"Product #{item['product_id']}"

    ctx['orders'] = orders
    return render(request, 'order_history.html', ctx)


# ===== PROFILE =====

def profile_page(request):
    customer_id = request.session.get('customer_id')
    if not customer_id:
        return redirect('login_page')

    ctx = _base_context(request)
    error = None
    success = None

    # Get profile
    profile = {}
    try:
        r = requests.get(f"{CUSTOMER_SERVICE_URL}/customers/{customer_id}/profile/", timeout=5)
        if r.status_code == 200:
            profile = r.json()
    except requests.exceptions.RequestException:
        pass

    # Update profile
    if request.method == 'POST':
        update_data = {}
        for field in ['name', 'phone', 'address', 'gender']:
            val = request.POST.get(field)
            if val is not None:
                update_data[field] = val
        dob = request.POST.get('date_of_birth')
        if dob:
            update_data['date_of_birth'] = dob

        try:
            r = requests.put(
                f"{CUSTOMER_SERVICE_URL}/customers/{customer_id}/profile/",
                json=update_data,
                timeout=5,
            )
            if r.status_code == 200:
                profile = r.json()
                request.session['customer_name'] = profile.get('name', '')
                success = "Cập nhật hồ sơ thành công!"
            else:
                error = "Lỗi cập nhật hồ sơ."
        except requests.exceptions.RequestException as e:
            error = f"Lỗi kết nối: {e}"

    ctx.update({'profile': profile, 'error': error, 'success': success})
    return render(request, 'profile.html', ctx)


# ===== WISHLIST =====

def wishlist_page(request):
    customer_id = request.session.get('customer_id')
    if not customer_id:
        return redirect('login_page')

    ctx = _base_context(request)

    # Get wishlist items
    wishlist_items = []
    try:
        r = requests.get(f"{CUSTOMER_SERVICE_URL}/customers/{customer_id}/wishlist/", timeout=5)
        if r.status_code == 200:
            wishlist_items = r.json()
    except requests.exceptions.RequestException:
        pass

    # Enrich with product data
    for item in wishlist_items:
        try:
            br = requests.get(f"{PRODUCT_SERVICE_URL}/products/{item['product_id']}/", timeout=5)
            if br.status_code == 200:
                product = br.json()
                item['product'] = product
            else:
                item['product'] = {'title': f"Product #{item['product_id']}", 'price': 0}
        except requests.exceptions.RequestException:
            item['product'] = {'title': f"Product #{item['product_id']}", 'price': 0}

    ctx['wishlist_items'] = wishlist_items
    return render(request, 'wishlist.html', ctx)


def toggle_wishlist(request, product_id):
    customer_id = request.session.get('customer_id')
    if not customer_id:
        return redirect('login_page')

    if request.method == 'POST':
        action = request.POST.get('action', 'add')
        try:
            if action == 'remove':
                requests.delete(
                    f"{CUSTOMER_SERVICE_URL}/customers/{customer_id}/wishlist/{product_id}/",
                    timeout=5,
                )
                _track_event(request, "wishlist_remove", {"product_id": product_id})
            else:
                requests.post(
                    f"{CUSTOMER_SERVICE_URL}/customers/{customer_id}/wishlist/",
                    json={'product_id': product_id},
                    timeout=5,
                )
                _track_event(request, "wishlist_add", {"product_id": product_id})
        except requests.exceptions.RequestException:
            pass

    # Redirect back
    next_url = request.POST.get('next', '')
    if next_url == 'wishlist':
        return redirect('wishlist_page')
    return redirect('product_detail', product_id=product_id)


# ===== JSON API PROXY =====

def _proxy(request, url, allowed_methods=None):
    if allowed_methods and request.method not in allowed_methods:
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        headers = {}
        content_type = request.META.get('CONTENT_TYPE')
        if content_type:
            headers['Content-Type'] = content_type
        auth = request.META.get('HTTP_AUTHORIZATION')
        if auth:
            headers['Authorization'] = auth

        if request.method == 'GET':
            resp = requests.get(url, params=request.GET, timeout=5)
        elif request.method == 'POST':
            resp = requests.post(url, data=request.body, headers=headers, timeout=5)
        elif request.method in ['PUT', 'PATCH']:
            resp = requests.request(request.method, url, data=request.body, headers=headers, timeout=5)
        elif request.method == 'DELETE':
            resp = requests.delete(url, timeout=5)
        else:
            return JsonResponse({'error': 'Method not allowed'}, status=405)

        return HttpResponse(resp.content, status=resp.status_code, content_type=resp.headers.get('Content-Type', 'application/json'))
    except requests.exceptions.RequestException as e:
        return JsonResponse({'error': f'Upstream error: {e}'}, status=502)


# --- Customer ---
@csrf_exempt
def api_customers(request):
    return _proxy(request, f"{CUSTOMER_SERVICE_URL}/customers/", allowed_methods=['GET', 'POST'])

@csrf_exempt
def api_auth_register(request):
    return _proxy(request, f"{CUSTOMER_SERVICE_URL}/auth/register/", allowed_methods=['POST'])

@csrf_exempt
def api_auth_login(request):
    return _proxy(request, f"{CUSTOMER_SERVICE_URL}/auth/login/", allowed_methods=['POST'])

# --- Product ---
@csrf_exempt
def api_products(request):
    return _proxy(request, f"{PRODUCT_SERVICE_URL}/products/", allowed_methods=['GET', 'POST'])

@csrf_exempt
def api_product_detail(request, pk):
    return _proxy(request, f"{PRODUCT_SERVICE_URL}/products/{pk}/", allowed_methods=['GET', 'PUT', 'DELETE'])

@csrf_exempt
def api_categories(request):
    return _proxy(request, f"{PRODUCT_SERVICE_URL}/categories/", allowed_methods=['GET', 'POST'])

@csrf_exempt
def api_product_search(request):
    return _proxy(request, f"{PRODUCT_SERVICE_URL}/products/search/", allowed_methods=['GET'])

# --- Cart ---
@csrf_exempt
def api_cart_items(request):
    return _proxy(request, f"{CART_SERVICE_URL}/cart-items/", allowed_methods=['POST'])

@csrf_exempt
def api_cart_item_detail(request, pk):
    return _proxy(request, f"{CART_SERVICE_URL}/cart-items/{pk}/", allowed_methods=['PUT', 'PATCH', 'DELETE'])

@csrf_exempt
def api_cart_detail(request, customer_id):
    return _proxy(request, f"{CART_SERVICE_URL}/carts/{customer_id}/", allowed_methods=['GET'])

# --- Order ---
@csrf_exempt
def api_orders(request):
    return _proxy(request, f"{ORDER_SERVICE_URL}/orders/", allowed_methods=['POST'])

@csrf_exempt
def api_order_detail(request, pk):
    return _proxy(request, f"{ORDER_SERVICE_URL}/orders/{pk}/", allowed_methods=['GET'])

# --- Rating ---
@csrf_exempt
def api_ratings(request):
    return _proxy(request, f"{RATING_SERVICE_URL}/ratings/", allowed_methods=['POST'])

@csrf_exempt
def api_ratings_list(request):
    return _proxy(request, f"{RATING_SERVICE_URL}/ratings/list/", allowed_methods=['GET'])


# --- AI ---
@csrf_exempt
def api_behavior_score(request):
    return _proxy(request, f"{AI_SERVICE_URL}/behavior/score/", allowed_methods=['POST'])


@csrf_exempt
def api_behavior_recommend(request):
    return _proxy(request, f"{AI_SERVICE_URL}/behavior/recommend-products/", allowed_methods=['POST'])


@csrf_exempt
def api_graph_recommend(request):
    return _proxy(request, f"{AI_SERVICE_URL}/graph/recommendations/", allowed_methods=['POST'])


@csrf_exempt
def api_chat_advice(request):
    if not request.session.get('customer_id'):
        return JsonResponse({'error': 'Authentication required'}, status=401)
    return _proxy(request, f"{AI_SERVICE_URL}/chat/advice/", allowed_methods=['POST'])


def health(request):
    return JsonResponse({"status": "ok", "service": "api-gateway"})
