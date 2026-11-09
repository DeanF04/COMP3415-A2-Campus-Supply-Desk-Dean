"""Operations used by the command-line order desk."""

from supplydesk.storage import JsonStore


VALID_CUSTOMER_TYPES = ("regular", "student")
VALID_FULFILLMENTS = ("pickup", "delivery")
MIN_QUANTITY = 1
MAX_QUANTITY = 99
STUDENT_DISCOUNT_THRESHOLD_CENTS = 5000
STUDENT_DISCOUNT_PERCENT = 10
DISCOUNT_ROUNDING_BIAS = 50
STANDARD_DELIVERY_FEE_CENTS = 600
FREE_DELIVERY_THRESHOLD_CENTS = 10000


class OrderService:
    def __init__(self, state_path=".supplydesk/state.json"):
        self.store = JsonStore(state_path)

    def catalog(self):
        return self.store.load()["catalog"]

    def quote(self, customer_type, items, fulfillment="pickup"):
        state = self.store.load()
        return self._build_pricing(state, customer_type, items, fulfillment)

    def place_order(self, customer_type, items, fulfillment="pickup"):
        state = self.store.load()
        pricing = self._build_pricing(state, customer_type, items, fulfillment)
        order = {
            "order_id": "ORD-" + str(state["next_order_number"]).zfill(4),
            "status": "placed",
            **pricing,
        }

        self._change_stock(state["catalog"], pricing["items"], -1)
        state["next_order_number"] += 1
        state["orders"].append(order)
        self.store.save(state)
        return order

    def list_orders(self):
        return self.store.load()["orders"]

    def get_order(self, order_id):
        state = self.store.load()
        for order in state["orders"]:
            if order["order_id"] == order_id:
                return order
        raise ValueError("Unknown order: " + order_id)

    def cancel_order(self, order_id):
        state = self.store.load()
        order = self._find_order(state["orders"], order_id)
        if order["status"] == "cancelled":
            return order
        self._change_stock(state["catalog"], order["items"], 1)
        order["status"] = "cancelled"
        self.store.save(state)
        return order

    def _build_pricing(self, state, customer_type, items, fulfillment):
        self._validate_request(customer_type, items, fulfillment)
        item_lines = self._build_item_lines(state["catalog"], items)
        subtotal_cents = sum(line["line_total_cents"] for line in item_lines)
        discount_cents = self._calculate_discount(customer_type, subtotal_cents)
        delivery_cents = self._calculate_delivery(
            fulfillment, subtotal_cents, discount_cents
        )
        return {
            "customer_type": customer_type,
            "fulfillment": fulfillment,
            "items": item_lines,
            "subtotal_cents": subtotal_cents,
            "discount_cents": discount_cents,
            "delivery_cents": delivery_cents,
            "total_cents": subtotal_cents - discount_cents + delivery_cents,
        }

    def _validate_request(self, customer_type, items, fulfillment):
        if customer_type not in VALID_CUSTOMER_TYPES:
            raise ValueError("Customer type must be regular or student.")
        if fulfillment not in VALID_FULFILLMENTS:
            raise ValueError("Fulfillment must be pickup or delivery.")
        if not isinstance(items, list) or not items:
            raise ValueError("An order must contain at least one item.")

    def _build_item_lines(self, catalog, items):
        item_lines = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Each item must contain a product_id and quantity.")

            product = self._find_product(catalog, item.get("product_id"))
            quantity = item.get("quantity")
            if type(quantity) is not int or quantity < MIN_QUANTITY or quantity > MAX_QUANTITY:
                raise ValueError("Quantity must be an integer from 1 to 99.")
            if quantity > product["stock"]:
                raise ValueError("Not enough stock for " + product["product_id"] + ".")

            line_total_cents = product["unit_price_cents"] * quantity
            item_lines.append({
                "product_id": product["product_id"],
                "name": product["name"],
                "unit_price_cents": product["unit_price_cents"],
                "quantity": quantity,
                "line_total_cents": line_total_cents,
            })
        return item_lines

    def _calculate_discount(self, customer_type, subtotal_cents):
        if customer_type == "student" and subtotal_cents > STUDENT_DISCOUNT_THRESHOLD_CENTS:
            return (
                subtotal_cents * STUDENT_DISCOUNT_PERCENT + DISCOUNT_ROUNDING_BIAS
            ) // 100
        return 0

    def _calculate_delivery(self, fulfillment, subtotal_cents, discount_cents):
        if (
            fulfillment == "delivery"
            and subtotal_cents - discount_cents < FREE_DELIVERY_THRESHOLD_CENTS
        ):
            return STANDARD_DELIVERY_FEE_CENTS
        return 0

    @staticmethod
    def _find_product(catalog, product_id):
        for product in catalog:
            if product["product_id"] == product_id:
                return product
        raise ValueError("Unknown product.")

    @staticmethod
    def _find_order(orders, order_id):
        for order in orders:
            if order["order_id"] == order_id:
                return order
        raise ValueError("Unknown order: " + order_id)

    @staticmethod
    def _change_stock(catalog, item_lines, direction):
        for line in item_lines:
            for product in catalog:
                if product["product_id"] == line["product_id"]:
                    product["stock"] += direction * line["quantity"]
                    break
