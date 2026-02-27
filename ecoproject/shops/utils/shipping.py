import math
import requests
from django.conf import settings
from datetime import datetime

def geocode_address(address: str):
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": address,
        "format": "json",
        "limit": 1
    }
    headers = {
        "User-Agent": "QShop/1.0"
    }
    r = requests.get(url, params=params, headers=headers, timeout=5)
    data = r.json()
    if not data:
        return None, None
    return float(data[0]["lat"]), float(data[0]["lon"])


def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi/2)**2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def is_peak_hour():
    now = datetime.now().hour
    for start, end in settings.PEAK_HOURS:
        if start <= now < end:
            return True
    return False

def calculate_shipping_cost(address, profile=None):

    if profile and profile.latitude and profile.longitude:
        lat, lng = profile.latitude, profile.longitude

    else:
        lat, lng = geocode_address(address)

        if lat is None or lng is None:
            for district, cost in settings.DISTRICT_SHIPPING.items():
                if district.lower() in address.lower():
                    return cost, None
            return settings.MIN_SHIPPING_COST, None

    # 3️⃣ TÍNH KHOẢNG CÁCH (KM)
    distance_km = haversine(
        settings.SHOP_LAT,
        settings.SHOP_LNG,
        lat,
        lng
    )

    # 4️⃣ MIỄN SHIP < X KM
    if distance_km <= settings.FREE_SHIP_DISTANCE_KM:
        return 0, round(distance_km, 2)

    # 5️⃣ TÍNH PHÍ THEO KM
    cost = int(distance_km * settings.SHIPPING_PRICE_PER_KM)
    cost = max(cost, settings.MIN_SHIPPING_COST)
    cost = min(cost, settings.MAX_SHIPPING_COST)

    if is_peak_hour():
        cost += settings.PEAK_EXTRA_FEE


    return round(cost, -3), round(distance_km, 2)

