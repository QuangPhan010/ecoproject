from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import UpdateView, DeleteView
from django.urls import reverse_lazy, reverse
from django.db import transaction
from django.db.models import Case, When, Count, Sum
from django.utils.text import slugify
from django.contrib import messages
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from .models import Product, FlashSale, ProductColor, Category, Review, ReviewReaction, Order, OrderItem, Coupon, CouponUsage
from .forms import ProductForm, ReviewForm, CouponForm, CouponCreateForm
from users.forms import ProfileEditForm
from .color_map import COLOR_MAP
from django.utils import timezone
from django.conf import settings
import os
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.db import models
from django.db.models import Count, Sum, F, ExpressionWrapper, IntegerField
from datetime import timedelta
from io import BytesIO
from .utils.shipping import calculate_shipping_cost
from django.db.models.functions import TruncMonth, TruncDay, TruncHour
from collections import OrderedDict
from shops.discount_utils import calculate_rank_discount

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    from reportlab.graphics.barcode import qr
    from reportlab.graphics.barcode import code128
    from reportlab.graphics import renderPDF
    from reportlab.graphics.shapes import Drawing
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
except Exception:
    A4 = None
    canvas = None


# ================= HOME =================

def index(request):
    featured_products = Product.objects.filter(available=True).order_by('-id')[:8]
    flash_products = Product.objects.filter(available=True, stock__gt=0).order_by('?')[:4]
    now = timezone.now()
    flash_sale = FlashSale.objects.filter(is_active=True, start_time__lte=now,end_time__gte=now).first()    

    return render(request, 'shops/index.html', {
        'featured_products': featured_products,
        'flash_products': flash_products,
        'flash_sale': flash_sale
    })

def save(self, *args, **kwargs):
    if self.end_time < timezone.now():
        self.is_active = False
    super().save(*args, **kwargs)

# ================= PRODUCT LIST =================

def product(request):
    category_slug = request.GET.get("category")

    products = Product.objects.filter(available=True).order_by('-id')

    if category_slug:
        products = products.filter(category__slug=category_slug)

    categories = Category.objects.all()

    return render(request, 'shops/product.html', {
        'products': products,
        'categories': categories,
        'current_category': category_slug
    })


# ================= PRODUCT DETAIL =================

def detail(request, slug):
    product = get_object_or_404(Product, slug=slug, available=True)

    reviews = product.reviews.filter(parent__isnull=True)
    review_form = ReviewForm()

    user_review = None
    if request.user.is_authenticated:
        user_review = Review.objects.filter(product=product, user=request.user, parent__isnull=True).first()

    # viewed products giữ nguyên code của bạn
    viewed = request.session.get("viewed_products", [])
    if product.id in viewed:
        viewed.remove(product.id)
    viewed.insert(0, product.id)
    request.session["viewed_products"] = viewed[:6]
    avg_rating = round(product.average_rating(), 1)
    rating_count = product.rating_count()

    preserved = Case(*[When(pk=pk, then=pos) for pos, pk in enumerate(viewed)])
    viewed_products = Product.objects.filter(id__in=viewed).order_by(preserved)
    suggest_products = Product.objects.exclude(id=product.id).order_by('?')[:6]

    return render(request, 'shops/detail.html', {
        'product': product,
        'reviews': reviews,
        'review_form': review_form,
        'viewed_products': viewed_products,
        'suggest_products': suggest_products,
        "avg_rating": avg_rating,
        "rating_count": rating_count,
        "user_review": user_review,
    })

@login_required
def add_review(request, slug):
    if request.method == "POST":
        product = get_object_or_404(Product, slug=slug)
        content = request.POST.get("content")
        rating = request.POST.get("rating", 5)
        parent_id = request.POST.get("parent_id")

        if not parent_id:
            if Review.objects.filter(product=product, user=request.user, parent__isnull=True).exists():
                return JsonResponse({"error": "Bạn đã đánh giá sản phẩm này rồi."}, status=400)

        review = Review.objects.create(
            product=product,
            user=request.user,
            content=content,
            rating=rating,
            parent_id=parent_id if parent_id else None
        )

        return JsonResponse({
            "id": review.id,
            "user": review.user.username,
            "content": review.content,
            "rating": review.rating,
            "created": review.created_at.strftime("%d/%m/%Y %H:%M")
        })
    
@login_required
def review_react(request):
    review_id = request.POST.get("review_id")
    is_like = request.POST.get("is_like") == "true"

    review = get_object_or_404(Review, id=review_id)

    reaction, created = ReviewReaction.objects.update_or_create(
        review=review,
        user=request.user,
        defaults={"is_like": is_like}
    )

    return JsonResponse({
        "likes": review.reactions.filter(is_like=True).count(),
        "dislikes": review.reactions.filter(is_like=False).count()
    })

@login_required
def edit_review(request, id):
    review = get_object_or_404(
        Review,
        id=id,
        user=request.user,
        parent__isnull=True
    )

    if request.method == "POST":
        content = request.POST.get("content", "").strip()
        rating = int(request.POST.get("rating", review.rating))

        if not content:
            return JsonResponse({"error": "Nội dung trống"}, status=400)

        review.content = content
        review.rating = rating
        review.save()

        return JsonResponse({
            "content": review.content,
            "rating": review.rating
        })

@login_required
def delete_review(request, id):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    review = Review.objects.filter(
        id=id,
        user=request.user
    ).first()

    if not review:
        return JsonResponse({"error": "Not found"}, status=404)

    review_id = review.id
    review.delete()
    return JsonResponse({"success": True, "review_id": review_id})


# ================= CART =================

def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    if product.stock <= 0:
        return JsonResponse({
            'status': 'error',
            'message': 'Sản phẩm đã hết hàng'
        }, status=400)

    cart = request.session.get('cart', {})
    product_id_str = str(product_id)

    if product_id_str in cart:
        # chặn vượt quá stock
        if cart[product_id_str]['quantity'] + 1 > product.stock:
            return JsonResponse({
                'status': 'error',
                'message': f'Chỉ còn {product.stock} sản phẩm'
            }, status=400)

        cart[product_id_str]['quantity'] += 1
    else:
        cart[product_id_str] = {
            'quantity': 1,
            'price': product.price,
            'name': product.name,
            'image': product.image
        }

    request.session['cart'] = cart
    return JsonResponse({'status': 'success', 'cart': cart})


def cart_detail(request):
    cart = request.session.get('cart', {})
    total_price = 0
    for item_id, item in cart.items():
        item['total'] = item['quantity'] * item['price']
        total_price += item['total']
    
    return render(request, 'shops/cart_detail.html', {'cart': cart, 'total_price': total_price})

def remove_from_cart(request, product_id):
    cart = request.session.get('cart', {})
    product_id_str = str(product_id)

    if product_id_str in cart:
        del cart[product_id_str]
        request.session['cart'] = cart
    
    return redirect('shops:cart_detail')

def update_cart(request, product_id):
    cart = request.session.get('cart', {})
    product_id_str = str(product_id)
    quantity = int(request.POST.get('quantity', 1))

    if product_id_str in cart:
        if quantity > 0:
            cart[product_id_str]['quantity'] = quantity
        else:
            del cart[product_id_str]
        request.session['cart'] = cart
        
    return redirect('shops:cart_detail')

@login_required
def checkout(request):

    cart = request.session.get("cart", {})

    if not cart:
        messages.warning(request, "Giỏ hàng trống.")
        return redirect("shops:product")

    # ===== SUBTOTAL =====

    subtotal = sum(
        item["quantity"] * item["price"]
        for item in cart.values()
    )

    # ===== RANK DISCOUNT =====

    rank_discount = calculate_rank_discount(
        request.user,
        subtotal
    )

    # ===== COUPON (optional) =====

    coupon_discount = 0
    coupon = None

    coupon_id = request.session.get("coupon_id")

    if coupon_id:
        try:
            coupon = Coupon.objects.get(id=coupon_id)
            
            if coupon.categories.exists():
                eligible_subtotal = 0
                cart_product_ids = [int(pid) for pid in cart.keys()]
                products_in_cart = Product.objects.filter(id__in=cart_product_ids)
                
                for product in products_in_cart:
                    if product.category in coupon.categories.all():
                        eligible_subtotal += cart[str(product.id)]['quantity'] * cart[str(product.id)]['price']
                
                coupon_discount = int(eligible_subtotal * coupon.discount / 100)
            else:
                coupon_discount = int(
                    (subtotal - rank_discount)
                    * coupon.discount / 100
                )

            if coupon.max_discount > 0:
                coupon_discount = min(
                    coupon_discount,
                    coupon.max_discount
                )
        except Coupon.DoesNotExist:
            pass

    # ===== TOTAL AFTER DISCOUNT =====

    total_after_discount = (
        subtotal
        - rank_discount
        - coupon_discount
    )

    # ===== DEFAULT SHIPPING =====

    shipping_cost = 0
    distance = None
    final_total = total_after_discount

    # ===== FORM =====

    profile_form = ProfileEditForm(
        request.POST or None,
        instance=request.user.profile
    )
    coupon_form = CouponForm()
    payment_choices = {code for code, _ in Order.PAYMENT_CHOICES}
    selected_payment = request.POST.get("payment_method", "COD")
    if selected_payment not in payment_choices:
        selected_payment = "COD"

    # ===== POST =====

    if request.method == "POST":

        action = request.POST.get("action")

        if profile_form.is_valid():

            address = profile_form.cleaned_data["address"]

            # backend tính shipping
            shipping_cost, distance = calculate_shipping_cost(address)

            final_total = (
                total_after_discount
                + shipping_cost
            )

            # ===== PLACE ORDER =====

            if action == "place_order":

                order = Order.objects.create(
                    user=request.user,
                    address=address,
                    phone=profile_form.cleaned_data["phone"],
                    total_price=final_total,
                    shipping_cost=shipping_cost,
                    rank_discount=rank_discount,
                    discount=coupon_discount,
                    coupon=coupon,
                    payment_method=selected_payment
                )

                # create order items
                for product_id, item in cart.items():

                    product = get_object_or_404(
                        Product,
                        id=product_id
                    )

                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        price=item["price"],
                        quantity=item["quantity"]
                    )

                    # giảm stock
                    product.stock -= item["quantity"]
                    product.save()

                # clear cart
                request.session.pop("cart", None)
                request.session.pop("coupon_id", None)

                request.session["order_id"] = order.id

                _send_order_email(order, request)

                messages.success(
                    request,
                    "Đặt hàng thành công!"
                )

                if selected_payment == "BANK":
                    return redirect("shops:bank_transfer")

                return redirect("shops:order_created")

    # ===== CONTEXT =====

    context = {

        "cart": cart,

        "subtotal": subtotal,

        "rank_discount": rank_discount,

        "coupon_discount": coupon_discount,

        "shipping_cost": shipping_cost,

        "distance": distance,

        "final_total": final_total,

        "profile_form": profile_form,
        "coupon_form": coupon_form,
        "selected_payment": selected_payment,
    }

    return render(
        request,
        "shops/checkout.html",
        context
    )
@login_required
def checkout_preview_api(request):

    address = request.GET.get("address", "")

    cart = request.session.get("cart", {})

    subtotal = sum(
        item["quantity"] * item["price"]
        for item in cart.values()
    )

    # rank discount
    rank_discount = calculate_rank_discount(
        request.user,
        subtotal
    )

    subtotal_after_rank = subtotal - rank_discount

    # coupon
    coupon_discount = 0
    coupon_id = request.session.get("coupon_id")

    if coupon_id:

        try:

            coupon = Coupon.objects.get(id=coupon_id)

            if coupon.categories.exists():
                eligible_subtotal = 0
                cart_product_ids = [int(pid) for pid in cart.keys()]
                products_in_cart = Product.objects.filter(id__in=cart_product_ids)
                
                for product in products_in_cart:
                    if product.category in coupon.categories.all():
                        eligible_subtotal += cart[str(product.id)]['quantity'] * cart[str(product.id)]['price']
                
                coupon_discount = int(eligible_subtotal * coupon.discount / 100)
            else:
                coupon_discount = int(
                    subtotal_after_rank * coupon.discount / 100
                )

            if coupon.max_discount > 0:
                coupon_discount = min(
                    coupon_discount,
                    coupon.max_discount
                )

        except:
            pass

    total_after_discount = subtotal - rank_discount - coupon_discount

    # SHIPPING — BACKEND ONLY
    shipping_cost, distance = calculate_shipping_cost(address)

    final_total = total_after_discount + shipping_cost

    return JsonResponse({

        "shipping_cost": shipping_cost,

        "distance": distance,

        "final_total": final_total

    })

@login_required
def checkout_summary_api(request):

    address = request.GET.get("address", "")

    cart = request.session.get("cart", {})

    subtotal = sum(
        item["quantity"] * item["price"]
        for item in cart.values()
    )

    rank_discount = calculate_rank_discount(
        request.user,
        subtotal
    )

    subtotal_after_discount = subtotal - rank_discount

    shipping_cost, distance = calculate_shipping_cost(address)

    final_total = subtotal_after_discount + shipping_cost

    return JsonResponse({

        "subtotal": subtotal,

        "rank_discount": rank_discount,

        "shipping_cost": shipping_cost,

        "distance": distance,

        "final_total": final_total

    })

def _send_order_email(order, request):
    if not order.user.email:
        return

    base_url = getattr(settings, "PUBLIC_BASE_URL", "").rstrip("/")
    history_path = reverse('shops:order_history')
    if base_url:
        order_history_url = f"{base_url}{history_path}"
    else:
        order_history_url = request.build_absolute_uri(history_path)

    context = {
        'order': order,
        'order_items': order.items.select_related('product').all(),
        'order_history_url': order_history_url,
        'payment_label': order.get_payment_method_display(),
        'status_label': order.get_status_display(),
    }

    subject = f"QSHOP - Xác nhận đơn hàng #{order.id}"
    html_content = render_to_string('shops/emails/order_confirmation.html', context)
    text_content = strip_tags(html_content)

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[order.user.email],
    )
    email.attach_alternative(html_content, "text/html")
    email.send(fail_silently=True)

@login_required
def bank_transfer(request):
    order_id = request.session.get('order_id')
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'shops/bank_transfer.html', {'order': order})

@login_required
def order_created(request):
    order_id = request.session.get('order_id')
    order = get_object_or_404(Order, id=order_id)
    return render(request, 'shops/order_created.html', {'order': order})

@login_required
def order_history(request):
    is_admin = request.user.is_staff or request.user.is_superuser
    if is_admin:
        orders = Order.objects.select_related('user').prefetch_related('items__product').order_by('-created_at')
    else:
        orders = request.user.orders.select_related('user').prefetch_related('items__product').order_by('-created_at')

    selected_customer = request.GET.get("customer", "").strip()
    selected_status = request.GET.get("status", "").strip()

    if is_admin:
        if selected_customer:
            orders = orders.filter(user_id=selected_customer)
        if selected_status:
            orders = orders.filter(status=selected_status)

    for order in orders:
        base_url = getattr(settings, "PUBLIC_BASE_URL", "").rstrip("/")
        path = reverse('shops:order_qr_public', args=[order.qr_token])
        if base_url:
            order.qr_shipper_url = f"{base_url}{path}"
        else:
            order.qr_shipper_url = request.build_absolute_uri(path)

    return render(request, 'shops/order_history.html', {
        'orders': orders,
        'is_admin': is_admin,
        'customers': (
            Order.objects.select_related('user')
            .values('user_id', 'user__username', 'user__email', 'user__first_name', 'user__last_name')
            .distinct()
            .order_by('user__username')
            if is_admin else []
        ),
        'status_choices': Order.STATUS_CHOICES,
        'selected_customer': selected_customer,
        'selected_status': selected_status,
    })

@login_required
@require_POST
def admin_update_order_status(request, order_id):
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden("Bạn không có quyền thực hiện.")
    order = get_object_or_404(Order, id=order_id)
    new_status = request.POST.get("status", "").strip()
    valid_statuses = {s for s, _ in Order.STATUS_CHOICES}
    if new_status and new_status in valid_statuses:
        order.status = new_status
        order.save(update_fields=["status", "updated_at"])

    # ================= UPDATE USER RANK =================
        if new_status == "Delivered":
            update_user_rank(order.user)

    return redirect("shops:order_history")

def save_model(self, request, obj, form, change):
    if obj.status == 'Delivered':
        obj.paid = True
    super().save_model(request, obj, form, change)

def get_readonly_fields(self, request, obj=None):
    if obj and obj.status == 'Cancelled':
        return ('status',)
    return ()

def can_cancel(self):
    return self.status in ['Pending', 'Processing']

@login_required
@require_POST
def cancel_order(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    if not order.can_cancel():
        return redirect('shops:order_history')

    order.status = 'Cancelled'
    order.save()

    return redirect('shops:order_history')

def _can_view_order(request, order):
    return (
        request.user.is_authenticated and
        (request.user.is_staff or request.user.is_superuser or order.user_id == request.user.id)
    )

@login_required
def order_qr_detail(request, order_id):
    order = get_object_or_404(
        Order,
        id=order_id
    )
    if not _can_view_order(request, order):
        return HttpResponseForbidden("Bạn không có quyền xem đơn hàng này.")
    return render(request, 'shops/order_qr_detail.html', {
        'order': order
    })

def order_qr_public(request, token):
    order = get_object_or_404(Order, qr_token=token)
    if order.status in ['Pending', 'Processing']:
        order.status = 'Shipped'
        order.save(update_fields=['status', 'updated_at'])
    return render(request, 'shops/order_qr_shipper.html', {
        'order': order
    })

def _ensure_pdf_font():
    if canvas is None or A4 is None:
        return None, None, "Chưa cài thư viện tạo PDF (reportlab)."

    font_path = os.path.join(settings.BASE_DIR, "shops", "static", "fonts", "DejaVuSans.ttf")
    if not os.path.exists(font_path):
        return None, None, "Thiếu font DejaVuSans.ttf tại shops/static/fonts."

    try:
        pdfmetrics.registerFont(TTFont("DejaVuSans", font_path))
    except Exception:
        return None, None, "Không load được font DejaVuSans.ttf."

    return "DejaVuSans", "DejaVuSans", None

def _render_order_invoice(pdf, order, show_price, request, base_font, bold_font):
    width, height = A4
    left = 40
    right = width - 40
    top = height - 40
    content_width = right - left
    currency = lambda v: f"{v:,}".replace(",", ".")
    name_col_right = left + 300
    qty_col_right = left + 360
    price_col_right = right - 10

    def draw_qr(x, y, size, value):
        widget = qr.QrCodeWidget(value)
        bounds = widget.getBounds()
        width_w = bounds[2] - bounds[0]
        height_w = bounds[3] - bounds[1]
        d = Drawing(size, size, transform=[size / width_w, 0, 0, size / height_w, 0, 0])
        d.add(widget)
        renderPDF.draw(d, pdf, x, y)

    def truncate_text(text, max_width, font_name, font_size):
        if pdf.stringWidth(text, font_name, font_size) <= max_width:
            return text
        ellipsis = "..."
        available = max_width - pdf.stringWidth(ellipsis, font_name, font_size)
        if available <= 0:
            return ellipsis
        cut = len(text)
        while cut > 0:
            candidate = text[:cut]
            if pdf.stringWidth(candidate, font_name, font_size) <= available:
                return candidate + ellipsis
            cut -= 1
        return ellipsis

    def draw_header():
        pdf.setFillColor(colors.HexColor("#F8FAFC"))
        pdf.rect(left, top - 70, content_width, 70, fill=1, stroke=0)
        pdf.setFillColor(colors.HexColor("#111827"))
        pdf.setFont(bold_font, 16)
        pdf.drawString(left + 14, top - 30, f"QSHOP - Đơn hàng #{order.id}")
        pdf.setFont(base_font, 10)
        pdf.setFillColor(colors.HexColor("#6B7280"))
        pdf.drawString(left + 14, top - 48, f"Ngày tạo: {order.created_at.strftime('%d/%m/%Y %H:%M')}")
        pdf.setFillColor(colors.HexColor("#111827"))
        pdf.setFont(base_font, 9)
        pdf.drawRightString(right - 80, top - 48, "Quét QR để xem đơn hàng")
        draw_qr(
            right - 70,
            top - 64,
            56,
            request.build_absolute_uri(reverse('shops:order_qr_public', args=[order.qr_token]))
        )

    def draw_table_header(y_pos):
        pdf.setFillColor(colors.HexColor("#E5E7EB"))
        pdf.rect(left, y_pos - 14, right - left, 18, fill=1, stroke=0)
        pdf.setFillColor(colors.black)
        pdf.setFont(bold_font, 10)
        if show_price:
            pdf.drawString(left + 8, y_pos - 10, "Sản phẩm")
            pdf.drawRightString(qty_col_right, y_pos - 10, "SL")
            pdf.drawRightString(price_col_right, y_pos - 10, "Đơn giá")
        else:
            pdf.drawString(left + 8, y_pos - 10, "Sản phẩm")
            pdf.drawRightString(right - 10, y_pos - 10, "SL")
        return y_pos - 24

    draw_header()
    y = top - 90

    pdf.setFont(bold_font, 9)
    pdf.drawRightString(right - 40, y + 4, f"Mã vận đơn: {order.tracking_code}")
    barcode = code128.Code128(order.tracking_code, barHeight=18, barWidth=0.6)
    barcode.drawOn(pdf, right - 150, y - 18)

    pdf.setFont(bold_font, 11)
    pdf.drawString(left, y, "Thông tin giao hàng")
    y -= 16
    pdf.setFont(base_font, 10)
    pdf.drawString(left, y, f"Người nhận: {order.user.get_full_name() or order.user.username}")
    y -= 14
    pdf.drawString(left, y, f"SDT: {order.phone}")
    y -= 14
    pdf.drawString(left, y, f"Địa chỉ: {order.address}")
    y -= 18

    pdf.setFont(bold_font, 11)
    pdf.drawString(left, y, "Chi tiết sản phẩm")
    y -= 12
    y = draw_table_header(y)

    pdf.setFont(base_font, 10)
    for item in order.items.all():
        if y < 120:
            pdf.showPage()
            draw_header()
            y = top - 90
            y = draw_table_header(y)
            pdf.setFont(base_font, 10)

        pdf.setFillColor(colors.black)
        name = item.product.name
        name = truncate_text(name, (name_col_right - (left + 8)) - 4, base_font, 10)
        pdf.drawString(left + 8, y, name)
        if show_price:
            pdf.drawRightString(qty_col_right, y, f"{item.quantity}")
            pdf.setFont(base_font, 9)
            pdf.drawRightString(price_col_right, y, f"{currency(item.price)} VND")
            pdf.setFont(base_font, 10)
        else:
            pdf.drawRightString(right - 10, y, f"{item.quantity}")
        y -= 14

    y -= 8
    pdf.setStrokeColor(colors.HexColor("#E5E7EB"))
    pdf.line(left, y, right, y)
    y -= 16

    pdf.setFont(bold_font, 10)
    pdf.drawString(left, y, f"Trạng thái: {order.get_status_display()}")
    if show_price:
        pdf.drawRightString(right - 10, y, f"Tổng cộng: {currency(order.total_price)} VND")

def _render_shipper_invoice(pdf, order, request, base_font, bold_font):
    width, height = A4
    left = 40
    right = width - 40
    top = height - 40
    content_width = right - left
    currency = lambda v: f"{v:,}".replace(",", ".")
    name_col_right = left + 320
    qty_col_right = right - 10

    def draw_qr(x, y, size, value):
        widget = qr.QrCodeWidget(value)
        bounds = widget.getBounds()
        width_w = bounds[2] - bounds[0]
        height_w = bounds[3] - bounds[1]
        d = Drawing(size, size, transform=[size / width_w, 0, 0, size / height_w, 0, 0])
        d.add(widget)
        renderPDF.draw(d, pdf, x, y)

    def truncate_text(text, max_width, font_name, font_size):
        if pdf.stringWidth(text, font_name, font_size) <= max_width:
            return text
        ellipsis = "..."
        available = max_width - pdf.stringWidth(ellipsis, font_name, font_size)
        if available <= 0:
            return ellipsis
        cut = len(text)
        while cut > 0:
            candidate = text[:cut]
            if pdf.stringWidth(candidate, font_name, font_size) <= available:
                return candidate + ellipsis
            cut -= 1
        return ellipsis

    def draw_header():
        pdf.setFillColor(colors.HexColor("#F8FAFC"))
        pdf.rect(left, top - 70, content_width, 70, fill=1, stroke=0)
        pdf.setFillColor(colors.HexColor("#111827"))
        pdf.setFont(bold_font, 16)
        pdf.drawString(left + 14, top - 30, f"QSHOP - Phiếu giao hàng #{order.id}")
        pdf.setFont(base_font, 10)
        pdf.setFillColor(colors.HexColor("#6B7280"))
        pdf.drawString(left + 14, top - 48, f"Ngày tạo: {order.created_at.strftime('%d/%m/%Y %H:%M')}")
        pdf.setFillColor(colors.HexColor("#111827"))
        pdf.setFont(base_font, 9)
        pdf.drawRightString(right - 80, top - 48, "Quét QR để xem đơn hàng")
        draw_qr(
            right - 70,
            top - 64,
            56,
            request.build_absolute_uri(reverse('shops:order_qr_public', args=[order.qr_token]))
        )

    def draw_table_header(y_pos):
        pdf.setFillColor(colors.HexColor("#E5E7EB"))
        pdf.rect(left, y_pos - 14, right - left, 18, fill=1, stroke=0)
        pdf.setFillColor(colors.black)
        pdf.setFont(bold_font, 10)
        pdf.drawString(left + 8, y_pos - 10, "Sản phẩm")
        pdf.drawRightString(qty_col_right, y_pos - 10, "SL")
        return y_pos - 24

    draw_header()
    y = top - 90

    pdf.setFont(bold_font, 9)
    pdf.drawRightString(right - 40, y + 4, f"Mã vận đơn: {order.tracking_code}")
    barcode = code128.Code128(order.tracking_code, barHeight=18, barWidth=0.6)
    barcode.drawOn(pdf, right - 150, y - 18)

    pdf.setFont(bold_font, 11)
    pdf.drawString(left, y, "Thông tin giao hàng")
    y -= 16
    pdf.setFont(base_font, 10)
    pdf.drawString(left, y, f"Người nhận: {order.user.get_full_name() or order.user.username}")
    y -= 14
    pdf.drawString(left, y, f"SDT: {order.phone}")
    y -= 14
    pdf.drawString(left, y, f"Địa chỉ: {order.address}")
    y -= 18

    pdf.setFont(bold_font, 11)
    pdf.drawString(left, y, "Chi tiết sản phẩm")
    y -= 12
    y = draw_table_header(y)

    pdf.setFont(base_font, 10)
    for item in order.items.all():
        if y < 120:
            pdf.showPage()
            draw_header()
            y = top - 90
            y = draw_table_header(y)
            pdf.setFont(base_font, 10)

        pdf.setFillColor(colors.black)
        name = truncate_text(item.product.name, (name_col_right - (left + 8)) - 4, base_font, 10)
        pdf.drawString(left + 8, y, name)
        pdf.drawRightString(qty_col_right, y, f"{item.quantity}")
        y -= 14

    y -= 8
    pdf.setStrokeColor(colors.HexColor("#E5E7EB"))
    pdf.line(left, y, right, y)
    y -= 16

    pdf.setFont(bold_font, 10)
    pdf.drawString(left, y, f"Trạng thái: {order.get_status_display()}")
    payment_label = order.get_payment_method_display()
    pdf.setFont(base_font, 10)
    pdf.drawRightString(right - 10, y, f"Thanh toán: {payment_label}")
    y -= 16

    cod_amount = order.total_price if order.payment_method == 'COD' else 0
    pdf.setFont(bold_font, 12)
    pdf.drawString(left, y, "COD thu hộ")
    pdf.drawRightString(right - 10, y, f"{currency(cod_amount)} VND")

def order_bill_pdf(request, token):
    order = get_object_or_404(Order, qr_token=token)
    show_price = _can_view_order(request, order)
    base_font, bold_font, err = _ensure_pdf_font()
    if err:
        return HttpResponse(err, status=500)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    _render_order_invoice(pdf, order, show_price, request, base_font, bold_font)
    pdf.save()

    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename=\"order_{order.id}.pdf\"'
    return response

def order_shipper_pdf(request, token):
    order = get_object_or_404(Order, qr_token=token)
    base_font, bold_font, err = _ensure_pdf_font()
    if err:
        return HttpResponse(err, status=500)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    _render_shipper_invoice(pdf, order, request, base_font, bold_font)
    pdf.save()

    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename=\"shipper_{order.id}.pdf\"'
    return response

@login_required
def order_bills_all_pdf(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden("Bạn không có quyền thực hiện.")

    base_font, bold_font, err = _ensure_pdf_font()
    if err:
        return HttpResponse(err, status=500)

    orders = Order.objects.prefetch_related('items__product').order_by('-created_at')
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)

    first = True
    for order in orders:
        if not first:
            pdf.showPage()
        _render_order_invoice(pdf, order, True, request, base_font, bold_font)
        first = False

    pdf.showPage()
    pdf.save()

    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename=\"orders_all.pdf\"'
    return response



# ================= CATEGORY MANAGE =================

@login_required
@permission_required('shops.view_category', raise_exception=True)
def category_list(request):
    categories = Category.objects.all().order_by('name')
    return render(request, 'shops/category_manage.html', {
        'categories': categories
    })


@login_required
@permission_required('shops.add_category', raise_exception=True)
def category_create(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            Category.objects.get_or_create(
                name=name,
                defaults={'slug': slugify(name)}
            )
    return redirect('shops:category_manage')

@login_required
@permission_required('shops.change_category', raise_exception=True)
def category_edit(request, id):
    category = get_object_or_404(Category, id=id)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            category.name = name
            category.slug = slugify(name)
            category.save()
            return redirect('shops:category_manage')

    return render(request, 'shops/category_edit.html', {
        'category': category
    })

@login_required
@permission_required('shops.delete_category', raise_exception=True)
def category_delete(request, id):
    category = get_object_or_404(Category, id=id)

    if request.method == 'POST':
        category.delete()
        return redirect('shops:category_manage')

    return render(request, 'shops/category_confirm_delete.html', {
        'category': category
    })


# ================= CREATE PRODUCT =================

@login_required
@permission_required('shops.add_product', raise_exception=True)
def product_create(request):
    categories = Category.objects.all()

    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                product = form.save(commit=False)

                # category
                category_id = request.POST.get("category")
                if category_id:
                    product.category_id = category_id

                product.save()

                # options
                options_raw = request.POST.get("options_raw", "")
                if options_raw:
                    for opt in options_raw.split(","):
                        opt = opt.strip()
                        if opt:
                            product.options.create(name=opt)

                # colors
                colors_raw = request.POST.get("colors_raw", "")
                if colors_raw:
                    for c in colors_raw.split(","):
                        name = c.strip().lower()
                        if not name:
                            continue
                        hex_code = COLOR_MAP.get(name, "#cccccc")

                        ProductColor.objects.create(
                            product=product,
                            name=name.title(),
                            code=hex_code
                        )

            return redirect('shops:product')
    else:
        form = ProductForm()

    return render(request, 'shops/create.html', {
        'form': form,
        'categories': categories
    })


# ================= UPDATE PRODUCT =================

@login_required
@permission_required('shops.change_product', raise_exception=True)
def product_edit(request, slug):
    product = get_object_or_404(Product, slug=slug)
    categories = Category.objects.all()

    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            with transaction.atomic():
                product = form.save(commit=False)

                # category
                category_id = request.POST.get("category")
                if category_id:
                    product.category_id = category_id
                else:
                    product.category = None
                product.save()

                # options
                product.options.all().delete()
                options_raw = request.POST.get("options_raw", "")
                if options_raw:
                    for opt in options_raw.split(","):
                        opt = opt.strip()
                        if opt:
                            product.options.create(name=opt)

                # colors
                product.colors.all().delete()
                colors_raw = request.POST.get("colors_raw", "")
                if colors_raw:
                    for c in colors_raw.split(","):
                        name = c.strip().lower()
                        if not name:
                            continue
                        hex_code = COLOR_MAP.get(name, "#cccccc")
                        product.colors.create(
                            name=name.title(),
                            code=hex_code
                        )
            return redirect('shops:product')
    else:
        form = ProductForm(instance=product)

    return render(request, 'shops/edit.html', {
        'form': form,
        'product': product,
        'categories': categories
    })


# ================= DELETE PRODUCT =================

@login_required
@permission_required('shops.delete_product', raise_exception=True)
def product_delete(request, slug):
    product = get_object_or_404(Product, slug=slug)
    if request.method == 'POST':
        product.delete()
        return redirect('shops:product')
    return render(request, 'shops/product_confirm_delete.html', {'object': product})

@login_required
@permission_required('shops.add_coupon', raise_exception=True)
def create_coupon(request):
    form = CouponCreateForm(request.POST or None)
    if form.is_valid():
        form.save()
        return redirect('shops:coupon_stats')
    return render(request, 'shops/coupon_create.html', {'form': form})


from .models import CouponUsage

@login_required
@require_POST
def apply_coupon(request):
    form = CouponForm(request.POST)
    if form.is_valid():
        code = form.cleaned_data['code']
        now = timezone.now()

        try:
            coupon = Coupon.objects.get(
                code__iexact=code,
                valid_from__lte=now,
                valid_to__gte=now,
                active=True
            )

            if coupon.categories.exists():
                cart = request.session.get('cart', {})
                cart_product_ids = [int(pid) for pid in cart.keys()]
                products_in_cart = Product.objects.filter(id__in=cart_product_ids)
                
                is_applicable = False
                for product in products_in_cart:
                    if product.category in coupon.categories.all():
                        is_applicable = True
                        break
                
                if not is_applicable:
                    messages.error(request, "Mã giảm giá không áp dụng cho các sản phẩm trong giỏ hàng.")
                    return redirect('shops:checkout')

            # ❌ user đã dùng chưa
            if CouponUsage.objects.filter(coupon=coupon, user=request.user).exists():
                messages.error(request, "Mã giảm giá này bạn đã sử dụng rồi.")
                return redirect('shops:checkout')

            request.session['coupon_id'] = coupon.id
            messages.success(request, f"Áp dụng mã {coupon.code} thành công!")

        except Coupon.DoesNotExist:
            messages.error(request, "Mã giảm giá không hợp lệ hoặc đã hết hạn.")

    return redirect('shops:checkout')


@login_required
@permission_required('shops.view_coupon', raise_exception=True)
def coupon_stats(request):
    coupons = Coupon.objects.annotate(
        total_orders=Count('order'),
        total_used=Count('couponusage')
    )

    # auto update active
    for c in coupons:

        if c.is_expired and c.active:
            c.active = False
            c.save(update_fields=["active"])

    return render(request, 'shops/coupon_stats.html', {
        'coupons': coupons
    })


class CouponUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Coupon
    form_class = CouponCreateForm
    template_name = 'shops/coupon_edit.html'
    success_url = reverse_lazy('shops:coupon_stats')
    permission_required = 'shops.change_coupon'

class CouponDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Coupon
    template_name = 'shops/coupon_confirm_delete.html'
    success_url = reverse_lazy('shops:coupon_stats')
    permission_required = 'shops.delete_coupon'



@login_required
def shop_stats(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden("Bạn không có quyền truy cập.")

    now = timezone.now()

    # ===== QUERYSET =====
    revenue_orders = Order.objects.exclude(status="Cancelled")
    all_orders = Order.objects.all()

    # ===== SUMMARY =====
    total_revenue = revenue_orders.aggregate(total=Sum("total_price"))["total"] or 0
    weekly_revenue = revenue_orders.filter(
        created_at__gte=now - timedelta(days=7)
    ).aggregate(total=Sum("total_price"))["total"] or 0
    monthly_revenue = revenue_orders.filter(
        created_at__gte=now - timedelta(days=30)
    ).aggregate(total=Sum("total_price"))["total"] or 0

    # ===== TOP PRODUCT =====
    revenue_expr = ExpressionWrapper(
        F("price") * F("quantity"),
        output_field=IntegerField()
    )

    top_product = (
        OrderItem.objects
        .filter(order__in=revenue_orders)
        .values("product__name")
        .annotate(
            total_qty=Sum("quantity"),
            total_revenue=Sum(revenue_expr)
        )
        .order_by("-total_qty")
        .first()
    )

    # ===== PIE CHART (KỂ CẢ CANCELLED) =====
    status_map = dict(Order.STATUS_CHOICES)

    status_rows = (
        all_orders
        .values("status")
        .annotate(count=Count("id"))
    )

    pie_labels = [status_map.get(r["status"], r["status"]) for r in status_rows]
    pie_data = [r["count"] for r in status_rows]

    # ==================================================
    # ================= LINE CHART =====================
    # ==================================================

    # ===== 24 GIỜ QUA =====
    hours = OrderedDict()
    for i in range(23, -1, -1):
        h = (now - timedelta(hours=i)).replace(minute=0, second=0, microsecond=0)
        hours[h] = 0

    hour_qs = (
        revenue_orders
        .filter(created_at__gte=now - timedelta(hours=24))
        .annotate(h=TruncHour("created_at"))
        .values("h")
        .annotate(total=Sum("total_price"))
    )

    for r in hour_qs:
        if r["h"] in hours:
            hours[r["h"]] = r["total"] or 0

    day_labels = [h.strftime("%H:%M") for h in hours.keys()]
    day_data = list(hours.values())

    # ===== 7 NGÀY QUA =====
    week_qs = (
        revenue_orders
        .filter(created_at__gte=now - timedelta(days=7))
        .annotate(d=TruncDay("created_at"))
        .values("d")
        .annotate(total=Sum("total_price"))
        .order_by("d")
    )

    week_labels = [r["d"].strftime("%d/%m") for r in week_qs]
    week_data = [r["total"] or 0 for r in week_qs]

    # ===== 30 NGÀY QUA =====
    month_qs = (
        revenue_orders
        .filter(created_at__gte=now - timedelta(days=30))
        .annotate(d=TruncDay("created_at"))
        .values("d")
        .annotate(total=Sum("total_price"))
        .order_by("d")
    )

    month_labels = [r["d"].strftime("%d/%m") for r in month_qs]
    month_data = [r["total"] or 0 for r in month_qs]

    # ===== CHỌN THÁNG CỤ THỂ =====
    selected_month = request.GET.get("month")
    picked_labels, picked_data = [], []

    if selected_month:
        y, m = map(int, selected_month.split("-"))
        picked_qs = (
            revenue_orders
            .filter(created_at__year=y, created_at__month=m)
            .annotate(d=TruncDay("created_at"))
            .values("d")
            .annotate(total=Sum("total_price"))
            .order_by("d")
        )
        picked_labels = [r["d"].strftime("%d/%m") for r in picked_qs]
        picked_data = [r["total"] or 0 for r in picked_qs]

    return render(request, "shops/shop_stats.html", {
        "total_revenue": total_revenue,
        "weekly_revenue": weekly_revenue,
        "monthly_revenue": monthly_revenue,
        "top_product": top_product,

        "day_labels": day_labels,
        "day_data": day_data,
        "week_labels": week_labels,
        "week_data": week_data,
        "month_labels": month_labels,
        "month_data": month_data,

        "picked_labels": picked_labels,
        "picked_data": picked_data,
        "selected_month": selected_month,

        "pie_labels": pie_labels,
        "pie_data": pie_data,
    })




def dashboard(request):
    now = timezone.now()
    start_date = now - timedelta(days=365)

    orders = Order.objects.exclude(status='Cancelled')

    revenue_by_month_qs = (
        orders
        .filter(created_at__gte=start_date)
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(total=Sum('total_price'))
        .order_by('month')
    )

    # chuẩn hóa đủ 12 tháng (kể cả tháng không có đơn)
    revenue_map = {
        r['month'].strftime('%Y-%m'): r['total'] or 0
        for r in revenue_by_month_qs
    }

    labels = []
    data = []

    for i in range(11, -1, -1):
        m = (now - timedelta(days=30*i)).strftime('%Y-%m')
        labels.append(m)
        data.append(revenue_map.get(m, 0))

    context = {
        # các biến cũ của bạn
        "revenue_labels": labels,
        "revenue_data": data,
    }

    return render(request, "shops/dashboard.html", context)

@login_required
def calc_shipping(request):
    address = request.GET.get("address", "")
    cost, distance_km = calculate_shipping_cost(address)

    return JsonResponse({
        "shipping_cost": cost,
        "distance_km": distance_km
    })

# ================= RANK SYSTEM =================

def update_user_rank(user):
    from django.db.models import Sum
    from shops.models import Order
    from users.models import Profile

    total_spent = (
        Order.objects
        .filter(user=user, status="Delivered")
        .aggregate(total=Sum("total_price"))["total"] or 0
    )

    profile = user.profile

    if total_spent >= 100_000_000:
        new_rank = Profile.RANK_PLATINUM

    elif total_spent >= 50_000_000:
        new_rank = Profile.RANK_GOLD

    elif total_spent >= 20_000_000:
        new_rank = Profile.RANK_SILVER

    else:
        new_rank = Profile.RANK_BRONZE

    if profile.rank != new_rank:
        profile.rank = new_rank
        profile.save()
