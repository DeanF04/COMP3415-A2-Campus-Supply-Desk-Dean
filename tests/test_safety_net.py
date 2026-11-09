"""Additional tests that protect behavior before refactoring."""

from pathlib import Path
import tempfile
import unittest

from supplydesk.service import OrderService


class OrderSafetyNetTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        self.service = OrderService(self.path)

    def test_quote_and_placed_order_have_matching_pricing(self):
        items = [{"product_id": "notebook", "quantity": 2}]
        quote = self.service.quote("regular", items, "delivery")
        order = self.service.place_order("regular", items, "delivery")

        for key in (
            "customer_type",
            "fulfillment",
            "items",
            "subtotal_cents",
            "discount_cents",
            "delivery_cents",
            "total_cents",
        ):
            self.assertEqual(order[key], quote[key])

    def test_quantity_one_is_accepted_at_lower_boundary(self):
        quote = self.service.quote(
            "regular", [{"product_id": "bag", "quantity": 1}], "pickup"
        )
        self.assertEqual(quote["subtotal_cents"], 2500)
        self.assertEqual(quote["total_cents"], 2500)

    def test_zero_quantity_is_rejected_without_saving_state(self):
        with self.assertRaisesRegex(ValueError, "Quantity must be an integer from 1 to 99"):
            self.service.place_order(
                "regular", [{"product_id": "notebook", "quantity": 0}], "pickup"
            )
        self.assertFalse(self.path.exists())

    def test_string_quantity_is_rejected_by_service_api(self):
        with self.assertRaisesRegex(ValueError, "Quantity must be an integer from 1 to 99"):
            self.service.quote(
                "regular", [{"product_id": "notebook", "quantity": "2"}], "pickup"
            )

    def test_invalid_fulfillment_is_rejected_without_saving_state(self):
        with self.assertRaisesRegex(ValueError, "Fulfillment must be pickup, delivery, or express"):
            self.service.place_order(
                "regular", [{"product_id": "notebook", "quantity": 1}], "drone"
            )
        self.assertFalse(self.path.exists())

    def test_quote_does_not_create_save_file_or_change_stock(self):
        before = self.service.catalog()
        self.service.quote(
            "student", [{"product_id": "hoodie", "quantity": 2}], "delivery"
        )
        self.assertFalse(self.path.exists())
        self.assertEqual(self.service.catalog(), before)

    def test_cancelling_already_cancelled_order_does_not_restore_stock_twice(self):
        initial_stock = next(
            product["stock"]
            for product in self.service.catalog()
            if product["product_id"] == "pen-pack"
        )
        order = self.service.place_order(
            "regular", [{"product_id": "pen-pack", "quantity": 2}], "pickup"
        )
        self.service.cancel_order(order["order_id"])
        stock_after_first_cancel = next(
            product["stock"]
            for product in self.service.catalog()
            if product["product_id"] == "pen-pack"
        )

        second_cancel = self.service.cancel_order(order["order_id"])
        stock_after_second_cancel = next(
            product["stock"]
            for product in self.service.catalog()
            if product["product_id"] == "pen-pack"
        )

        self.assertEqual(second_cancel["status"], "cancelled")
        self.assertEqual(stock_after_first_cancel, initial_stock)
        self.assertEqual(stock_after_second_cancel, initial_stock)


if __name__ == "__main__":
    unittest.main()
