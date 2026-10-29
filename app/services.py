import json
import time
import urllib.error
import urllib.request

from flask import current_app

_cache = {'rate': None, 'at': 0.0}


def get_usd_rate(ttl=3600):
    """Tỷ giá 1 USD = ? VND, đọc JSON từ API công khai bằng urllib.
    Cache 1 giờ; nếu API lỗi thì dùng giá trị cũ (hoặc None), không làm hỏng trang."""
    now = time.time()
    if _cache['rate'] and now - _cache['at'] < ttl:
        return _cache['rate']
    try:
        req = urllib.request.Request(current_app.config['RATE_API_URL'],
                                     headers={'User-Agent': 'FlaskShop/1.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        rate = float(data['rates']['VND'])
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
        return _cache['rate']
    _cache.update(rate=rate, at=now)
    return rate
