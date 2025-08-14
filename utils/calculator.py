def calculate_subtotal(items):
    """items: list of dicts with price and quantity"""
    return sum(float(it["price"]) * int(it["quantity"]) for it in items)

def calculate_gst(subtotal, gst_rate=5.0):
    return subtotal * (gst_rate / 100.0)

def calculate_discount(subtotal, discount_type, discount_value):
    if discount_type == "Percentage":
        return subtotal * (discount_value / 100.0)
    elif discount_type == "Fixed amount":
        return float(discount_value)
    return 0.0

def calculate_total(subtotal, gst_amount, discount_amount):
    total = subtotal + gst_amount - discount_amount
    return max(total, 0.0)
