"""Quota is measured in percentage points: one full weekly quota = 100."""
from decimal import Decimal, ROUND_FLOOR


def shares(usage, resets):
    if not usage:
        return []
    if isinstance(resets, bool) or not isinstance(resets, int) or resets < 0:
        raise ValueError('重置次数必须是非负整数')
    values = [Decimal(str(x)) for x in usage]
    capacity = Decimal(100) * (1 + resets)
    if any(not x.is_finite() or x < 0 for x in values):
        raise ValueError('用量必须是非负有限数值')
    if sum(values) > capacity:
        raise ValueError('累计消耗超过名义额度，请核对重置记录')
    unused = (capacity - sum(values)) / len(values)
    exact = [(x + unused) / capacity * 10000 for x in values]
    rounded = [int(x.to_integral_value(rounding=ROUND_FLOOR)) for x in exact]
    for i in sorted(range(len(values)), key=lambda i: exact[i] - rounded[i], reverse=True)[:10000-sum(rounded)]:
        rounded[i] += 1
    return [x / 100 for x in rounded]


def allocate(delta, weights):
    delta = Decimal(str(delta))
    w = {str(k): Decimal(str(v)) for k, v in weights.items()}
    if not delta.is_finite() or delta < 0 or any(not x.is_finite() or x < 0 for x in w.values()):
        raise ValueError('无效的额度变化或用量权重')
    total = sum(w.values())
    if delta > 0 and total <= 0:
        raise ValueError('额度增加但没有可归属的用量，请核对账号是否在站外使用')
    return {k: float(delta * v / total) if total else 0 for k, v in w.items()}
