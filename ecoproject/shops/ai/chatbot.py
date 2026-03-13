import re
import unicodedata

from django.db.models import Avg, Count, F, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from shops.discount_utils import calculate_rank_discount
from shops.models import Category, Coupon, FlashSale, Order, Product, Review

from .gemini_ai import ask_gemini


SEARCH_HINTS = (
    "tim",
    "kiem",
    "san pham",
    "goi y",
    "mua",
    "co gi",
    "duoi",
    "tren",
    "tu",
    "gia",
    "mau",
)
REVIEW_HINTS = ("review", "danh gia", "nhan xet", "cam nhan", "phan hoi")
COUPON_HINTS = ("coupon", "voucher", "ma giam", "giam gia", "uu dai")
ORDER_HINTS = ("don hang", "kiem tra don", "tracking", "van don", "trang thai don", "ma don")
SUPPORT_HINTS = (
    "ho tro",
    "cham soc",
    "doi tra",
    "hoan tien",
    "thanh toan",
    "van chuyen",
    "giao hang",
    "bao hanh",
)
BEST_SELLING_HINTS = (
    "ban chay",
    "ban chay nhat",
    "noi bat",
    "pho bien",
    "hot",
    "top",
    "mua nhieu",
)
STOPWORDS = {
    "toi",
    "moi",
    "cho",
    "xin",
    "hay",
    "giup",
    "tim",
    "kiem",
    "san",
    "pham",
    "goi",
    "y",
    "mua",
    "va",
    "voi",
    "gia",
    "la",
    "co",
    "nao",
    "nhung",
    "cua",
    "shop",
    "qshop",
    "review",
    "danh",
    "nhan",
    "xet",
    "coupon",
    "voucher",
    "ma",
    "giam",
    "uu",
    "dai",
    "don",
    "hang",
    "kiem",
    "tra",
    "trang",
    "thai",
    "ho",
    "tro",
    "van",
    "chuyen",
    "giao",
    "thanh",
    "toan",
    "doi",
    "tra",
    "hoan",
    "tien",
    "ban",
    "chay",
    "nhat",
    "top",
    "hot",
    "pho",
    "bien",
}


def _normalize_text(value):
    text = unicodedata.normalize("NFD", value or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.lower().strip()


def _extract_keywords(message):
    normalized = _normalize_text(message)
    keywords = re.findall(r"[a-z0-9]+", normalized)
    return [kw for kw in keywords if len(kw) > 1 and kw not in STOPWORDS]


def _extract_price_bounds(message):
    normalized = _normalize_text(message)

    def parse_money(raw_number, unit):
        amount = float(raw_number.replace(",", "."))
        if unit == "k":
            return int(amount * 1_000)
        if unit in {"tr", "trieu", "m"}:
            return int(amount * 1_000_000)
        return int(amount)

    amount_pattern = r"(\d+(?:[.,]\d+)?)\s*(k|tr|trieu|m)?"
    between_match = re.search(
        rf"(?:tu|khoang)\s*{amount_pattern}\s*(?:den|toi|-)\s*{amount_pattern}",
        normalized,
    )
    if between_match:
        min_price = parse_money(between_match.group(1), between_match.group(2))
        max_price = parse_money(between_match.group(3), between_match.group(4))
        return min(min_price, max_price), max(min_price, max_price)

    under_match = re.search(rf"(?:duoi|nho hon)\s*{amount_pattern}", normalized)
    if under_match:
        return None, parse_money(under_match.group(1), under_match.group(2))

    above_match = re.search(rf"(?:tren|hon)\s*{amount_pattern}", normalized)
    if above_match:
        return parse_money(above_match.group(1), above_match.group(2)), None

    return None, None


def _is_best_selling_query(message):
    normalized = _normalize_text(message)
    return any(token in normalized for token in BEST_SELLING_HINTS)


def _top_selling_products(limit=8):
    return list(
        Product.objects.filter(available=True)
        .select_related("category")
        .prefetch_related("options", "colors")
        .annotate(
            avg_rating=Coalesce(Avg("reviews__rating", filter=Q(reviews__parent__isnull=True)), 0.0),
            rating_count=Count("reviews", filter=Q(reviews__parent__isnull=True), distinct=True),
            available_stock_count=F("stock") - F("reserved_stock"),
        )
        .order_by("-sold", "-id")[:limit]
    )


def _find_products(message, limit=8):
    keywords = _extract_keywords(message)
    min_price, max_price = _extract_price_bounds(message)
    best_selling_query = _is_best_selling_query(message)

    qs = (
        Product.objects.filter(available=True)
        .select_related("category")
        .prefetch_related("options", "colors")
        .annotate(
            avg_rating=Coalesce(Avg("reviews__rating", filter=Q(reviews__parent__isnull=True)), 0.0),
            rating_count=Count("reviews", filter=Q(reviews__parent__isnull=True), distinct=True),
            available_stock_count=F("stock") - F("reserved_stock"),
        )
    )

    if min_price is not None:
        qs = qs.filter(price__gte=min_price)
    if max_price is not None:
        qs = qs.filter(price__lte=max_price)

    if keywords:
        keyword_query = Q()
        for kw in keywords:
            keyword_query |= Q(name__icontains=kw)
            keyword_query |= Q(description__icontains=kw)
            keyword_query |= Q(category__name__icontains=kw)
            keyword_query |= Q(options__name__icontains=kw)
            keyword_query |= Q(colors__name__icontains=kw)
        qs = qs.filter(keyword_query).distinct()
    elif best_selling_query:
        qs = qs.order_by("-sold", "-id")
    else:
        qs = qs.order_by("-id")

    products = list(qs[:limit])
    if not products and best_selling_query:
        products = _top_selling_products(limit=limit)
    return products, min_price, max_price, keywords


def _match_product_from_message(message):
    products, _, _, _ = _find_products(message, limit=3)
    return products[0] if products else None


def _extract_order_ids(message):
    normalized = _normalize_text(message)
    return [int(value) for value in re.findall(r"\b\d{1,10}\b", normalized)]


def _extract_tracking_codes(message):
    return re.findall(r"\bQSHOP\d{4,}\b", (message or "").upper())


def _build_order_tracking_context(user, message):
    if not getattr(user, "is_authenticated", False):
        return (
            "Order tracking: nguoi dung chua dang nhap, chi co the huong dan vao trang "
            "lich su don hang hoac cung cap ma don trong tai khoan."
        )

    order_ids = _extract_order_ids(message)
    tracking_codes = _extract_tracking_codes(message)
    qs = (
        Order.objects.all()
        .select_related("coupon")
        .prefetch_related("items__product", "status_logs")
        .order_by("-created_at")
    )
    if not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
        qs = qs.filter(user=user)
    if order_ids:
        qs = qs.filter(id__in=order_ids)
    if tracking_codes:
        qs = qs.filter(tracking_code__in=tracking_codes)

    orders = list(qs[:5])
    if not orders:
        return "Order tracking: khong tim thay don hang nao phu hop trong tai khoan nay."

    lines = ["Don hang cua nguoi dung:"]
    for order in orders:
        items = ", ".join(
            f"{item.product.name} x{item.quantity}" for item in order.items.all()[:4]
        ) or "Khong co san pham"
        latest_log = order.status_logs.first()
        latest_change = (
            f"{latest_log.from_status} -> {latest_log.to_status} luc {latest_log.changed_at.strftime('%d/%m/%Y %H:%M')}"
            if latest_log
            else "Khong co lich su chuyen trang thai"
        )
        lines.append(
            f"- Don #{order.id}: trang thai {order.status}, thanh toan {order.payment_method}, "
            f"paid={order.paid}, tong {order.total_price} VND, tao luc {order.created_at.strftime('%d/%m/%Y %H:%M')}, "
            f"tracking code {order.tracking_code or 'khong co'}, san pham {items}"
        )
        lines.append(f"  Cap nhat trang thai moi nhat: {latest_change}")
    return "\n".join(lines)


def _summarize_reviews_context(product):
    if not product:
        return "Khong xac dinh duoc san pham de tom tat review."

    reviews = list(
        Review.objects.filter(product=product, parent__isnull=True)
        .annotate(
            likes=Count("reactions", filter=Q(reactions__is_like=True)),
            dislikes=Count("reactions", filter=Q(reactions__is_like=False)),
        )
        .select_related("user")
        .order_by("-created_at")[:12]
    )

    if not reviews:
        return f"San pham {product.name} hien chua co review."

    positive = []
    critical = []
    for review in reviews:
        row = (
            f"- {review.user.username}: {review.rating}/5 sao, "
            f"{review.likes} like, noi dung: {review.content}"
        )
        if review.rating >= 4:
            positive.append(row)
        elif review.rating <= 2:
            critical.append(row)

    lines = [
        f"San pham review: {product.name}",
        f"Gia: {product.price} VND",
        f"So review: {product.rating_count()}",
        f"Diem trung binh: {round(product.average_rating(), 1)}/5",
        "Review gan day:",
    ]
    lines.extend(
        f"- {review.user.username}: {review.rating}/5 sao, {review.content}"
        for review in reviews[:8]
    )
    if positive:
        lines.append("Review tich cuc noi bat:")
        lines.extend(positive[:4])
    if critical:
        lines.append("Review can luu y:")
        lines.extend(critical[:3])
    return "\n".join(lines)


def _coupon_discount_for_scope(coupon, subtotal_after_rank, eligible_subtotal):
    base_subtotal = eligible_subtotal if coupon.categories.exists() else subtotal_after_rank
    discount = int(base_subtotal * coupon.discount / 100)
    if coupon.max_discount > 0:
        discount = min(discount, coupon.max_discount)
    return max(discount, 0)


def _coupon_context(user, cart, matched_products):
    now = timezone.now()
    cart = cart or {}
    cart_product_ids = [int(pid) for pid in cart.keys() if str(pid).isdigit()]
    cart_products = list(
        Product.objects.filter(id__in=cart_product_ids).select_related("category")
    )
    cart_total = sum(item.get("quantity", 0) * item.get("price", 0) for item in cart.values())
    rank_discount = calculate_rank_discount(user, cart_total)
    subtotal_after_rank = max(cart_total - rank_discount, 0)

    coupon_qs = (
        Coupon.objects.filter(active=True, valid_from__lte=now, valid_to__gte=now)
        .prefetch_related("categories")
        .exclude(usage_limit__gt=0, used_count__gte=F("usage_limit"))
        .order_by("valid_to", "-discount", "id")
    )

    if getattr(user, "is_authenticated", False):
        coupon_qs = coupon_qs.filter(Q(owner=user) | Q(owner__isnull=True)).exclude(
            couponusage__user=user
        )
    else:
        coupon_qs = coupon_qs.filter(owner__isnull=True)

    coupons = []
    for coupon in coupon_qs[:12]:
        target_products = cart_products or matched_products
        if coupon.categories.exists():
            valid_category_ids = set(coupon.categories.values_list("id", flat=True))
            eligible_subtotal = 0
            for product in target_products:
                quantity = cart.get(str(product.id), {}).get("quantity", 1)
                if product.category_id in valid_category_ids:
                    eligible_subtotal += product.price * quantity
            if eligible_subtotal <= 0:
                continue
        else:
            eligible_subtotal = subtotal_after_rank if cart_total else sum(
                product.price for product in matched_products[:3]
            )

        estimated_discount = _coupon_discount_for_scope(
            coupon,
            subtotal_after_rank or eligible_subtotal,
            eligible_subtotal,
        )
        categories = list(coupon.categories.values_list("name", flat=True))
        coupons.append(
            {
                "code": coupon.code,
                "discount": coupon.discount,
                "max_discount": coupon.max_discount,
                "expires": coupon.valid_to.strftime("%d/%m/%Y %H:%M"),
                "categories": categories,
                "estimated_discount": estimated_discount,
            }
        )

    lines = [
        f"Gio hang hien tai: {len(cart_products)} san pham, tong tam tinh {cart_total} VND",
        f"Rank discount uoc tinh: {rank_discount} VND",
        f"Tam tinh sau rank: {subtotal_after_rank} VND",
    ]
    if matched_products:
        lines.append("San pham dang duoc quan tam:")
        lines.extend(f"- {product.name}: {product.price} VND" for product in matched_products[:4])

    if coupons:
        lines.append("Coupon phu hop:")
        for coupon in coupons[:5]:
            category_text = ", ".join(coupon["categories"]) if coupon["categories"] else "Tat ca danh muc"
            lines.append(
                f"- {coupon['code']}: giam {coupon['discount']}%, toi da {coupon['max_discount']} VND, "
                f"uoc tinh giam {coupon['estimated_discount']} VND, ap dung cho {category_text}, "
                f"het han {coupon['expires']}"
            )
    else:
        lines.append("Khong tim thay coupon phu hop voi ngu canh hien tai.")
    return "\n".join(lines)


def _schema_context():
    return "\n".join(
        [
            "Schema shop:",
            "- Category: ten danh muc, trang thai hoat dong.",
            "- Product: ten, gia, gia cu, mo ta, ton kho, da ban, danh muc, mau sac, tuy chon, review.",
            "- Review: noi dung, rating 1-5, nguoi viet, ngay tao, like/dislike.",
            "- Coupon: ma, phan tram giam, muc giam toi da, thoi gian hieu luc, gioi han luot dung, danh muc ap dung, owner.",
            "- Cart: session cart gom product id, quantity, price.",
            "- Order: id, trang thai, thanh toan, tong tien, tracking_code, lich su status, san pham trong don.",
            "- Ho tro khach hang: co thong tin ve thanh toan, van chuyen, don hang, doi tra/hoan tien qua after-sales request.",
        ]
    )


def _catalog_overview_context():
    now = timezone.now()
    active_categories = Category.objects.filter(is_active=True).count()
    total_products = Product.objects.count()
    available_products = Product.objects.filter(available=True).count()
    low_stock_products = Product.objects.filter(
        available=True,
        stock__gt=0,
        stock__lte=F("reserved_stock") + 5,
    ).count()
    active_flash_sales = FlashSale.objects.filter(
        is_active=True,
        start_time__lte=now,
        end_time__gte=now,
    ).count()
    top_products = _top_selling_products(limit=5)

    lines = [
        "Tong quan database shop:",
        f"- So danh muc dang hoat dong: {active_categories}",
        f"- Tong so san pham: {total_products}",
        f"- San pham dang ban: {available_products}",
        f"- San pham sap het hang: {low_stock_products}",
        f"- Flash sale dang hoat dong: {active_flash_sales}",
    ]
    if top_products:
        lines.append("Top san pham ban chay tu database:")
        for product in top_products:
            lines.append(
                f"- {product.name}: da ban {product.sold}, gia {product.price} VND, ton {max(product.available_stock_count, 0)}"
            )
    return "\n".join(lines)


def _products_context(products, min_price, max_price, keywords):
    lines = []
    if keywords:
        lines.append(f"Tu khoa tim kiem: {', '.join(keywords)}")
    if min_price is not None or max_price is not None:
        lines.append(
            f"Khoang gia phat hien: tu {min_price or 0} den {max_price or 'khong gioi han'} VND"
        )

    if not products:
        lines.append("Khong tim thay san pham khop dieu kien tu database.")
        return "\n".join(lines)

    lines.append("San pham tim thay tu database:")
    for product in products:
        options = ", ".join(opt.name for opt in product.options.all()[:4]) or "Khong co"
        colors = ", ".join(color.name for color in product.colors.all()[:4]) or "Khong co"
        category_name = product.category.name if product.category_id else "Chua phan loai"
        lines.append(
            f"- {product.name} | danh muc: {category_name} | gia: {product.price} VND | "
            f"gia cu: {product.old_price or 0} VND | ton kha dung: {max(product.available_stock_count, 0)} | "
            f"da ban: {product.sold} | rating: {round(product.avg_rating or 0, 1)}/5 ({product.rating_count} review) | "
            f"mau: {colors} | tuy chon: {options}"
        )
        if product.description:
            lines.append(f"  Mo ta: {product.description[:220]}")
    return "\n".join(lines)


def _build_prompt(message, user, cart):
    matched_products, min_price, max_price, keywords = _find_products(message)
    target_product = _match_product_from_message(message)
    if target_product is None and matched_products:
        target_product = matched_products[0]

    normalized = _normalize_text(message)
    intents = []
    if any(token in normalized for token in SEARCH_HINTS) or matched_products:
        intents.append("product_recommendation")
    if any(token in normalized for token in REVIEW_HINTS):
        intents.append("review_summary")
    if any(token in normalized for token in COUPON_HINTS):
        intents.append("coupon_recommendation")
    if any(token in normalized for token in ORDER_HINTS):
        intents.append("order_tracking")
    if any(token in normalized for token in SUPPORT_HINTS):
        intents.append("customer_support")
    if not intents:
        intents.append("customer_support")

    context_parts = [
        _schema_context(),
        _catalog_overview_context(),
        f"User authenticated: {getattr(user, 'is_authenticated', False)}",
        f"Detected intents: {', '.join(intents)}",
        _products_context(matched_products, min_price, max_price, keywords),
    ]

    if "review_summary" in intents:
        context_parts.append(_summarize_reviews_context(target_product))

    if "coupon_recommendation" in intents or cart:
        context_parts.append(_coupon_context(user, cart, matched_products))

    if "order_tracking" in intents:
        context_parts.append(_build_order_tracking_context(user, message))

    if "customer_support" in intents:
        context_parts.append(
            "\n".join(
                [
                    "Chinh sach va thong tin ho tro co the suy ra tu he thong:",
                    "- Thanh toan ho tro: COD, BANK, MOMO, VNPAY.",
                    "- Don hang co cac trang thai: Pending, Processing, Shipped, Delivered, Cancelled.",
                    "- Co quy trinh after-sales: doi hang, hoan tra, hoan tien.",
                    "- Neu can kiem tra don, uu tien huong dan vao lich su don hang khi thieu du lieu.",
                    "- Neu can coupon, uu tien coupon hop le va giai thich dieu kien ap dung.",
                ]
            )
        )

    instruction = """
Ban la tro ly AI cua QShop. Hay chi dua tren du lieu database duoc cung cap.
Nhiem vu:
1. Hieu ngu canh shop va tra loi bang tieng Viet.
2. Neu nguoi dung dang tim san pham, goi y san pham phu hop nhat theo du lieu tim thay.
3. Neu nguoi dung hoi review, tom tat diem manh, diem yeu, muc do phu hop tu review that.
4. Neu nguoi dung hoi coupon, goi y coupon phu hop nhat va giai thich vi sao.
5. Neu nguoi dung hoi don hang, tom tat trang thai, tracking code, moc cap nhat quan trong va neu gioi han truy cap.
6. Neu nguoi dung can ho tro khach hang, tra loi ngan gon, thuc dung, dua tren du lieu he thong va quy trinh dang co.
7. Khong duoc noi da tim thay thong tin neu context khong co du lieu. Khi khong du du lieu, noi ro dieu do.
8. Neu co nhieu san pham, uu tien toi da 3 san pham va neu ro gia, rating, ton kho khi can.
"""

    prompt = "\n\n".join(
        [
            instruction.strip(),
            "\n\n".join(context_parts),
            f"Cau hoi nguoi dung: {message}",
        ]
    )
    return prompt, matched_products


def ecommerce_chatbot(message, user=None, cart=None):
    prompt, matched_products = _build_prompt(message, user, cart or {})
    reply = ask_gemini(prompt)
    return {
        "reply": reply,
        "products": matched_products[:3],
    }
