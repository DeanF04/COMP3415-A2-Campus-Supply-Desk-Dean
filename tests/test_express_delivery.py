"""Tests for CR-01 express delivery."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from supplydesk.cli import build_parser
from supplydesk.menu import read_request
from supplydesk.service import OrderService


class ExpressDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        self.service = OrderService(self.path)

    def test_regular_express_quote_adds_fixed_1200_cent_fee(self):
        quote = self.service.quote(
            "regular", [{"product_id": "notebook", "quantity": 2}], "express"
        )
        self.assertEqual(quote["subtotal_cents"], 1000)
        self.assertEqual(quote["discount_cents"], 0)
        self.assertEqual(quote["delivery_cents"], 1200)
        self.assertEqual(quote["total_cents"], 2200)

    def test_student_express_quote_keeps_discount_on_merchandise_only(self):
        quote = self.service.quote(
            "student", [{"product_id": "hoodie", "quantity": 2}], "express"
        )
        self.assertEqual(quote["subtotal_cents"], 8000)
        self.assertEqual(quote["discount_cents"], 800)
        self.assertEqual(quote["delivery_cents"], 1200)
        self.assertEqual(quote["total_cents"], 8400)

    def test_express_fee_is_not_waived_above_standard_free_delivery_threshold(self):
        standard = self.service.quote(
            "regular", [{"product_id": "hoodie", "quantity": 3}], "delivery"
        )
        express = self.service.quote(
            "regular", [{"product_id": "hoodie", "quantity": 3}], "express"
        )
        self.assertEqual(standard["delivery_cents"], 0)
        self.assertEqual(standard["total_cents"], 12000)
        self.assertEqual(express["delivery_cents"], 1200)
        self.assertEqual(express["total_cents"], 13200)

    def test_express_quote_and_order_match_and_survive_reopen_and_cancel(self):
        items = [{"product_id": "notebook", "quantity": 2}]
        quote = self.service.quote("regular", items, "express")
        order = self.service.place_order("regular", items, "express")

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

        reopened = OrderService(self.path)
        stored = reopened.get_order(order["order_id"])
        self.assertEqual(stored["fulfillment"], "express")
        self.assertEqual(stored["delivery_cents"], 1200)
        self.assertEqual(stored["total_cents"], 2200)

        cancelled = reopened.cancel_order(order["order_id"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["fulfillment"], "express")
        self.assertEqual(cancelled["items"], order["items"])
        self.assertEqual(cancelled["discount_cents"], order["discount_cents"])
        self.assertEqual(cancelled["delivery_cents"], 1200)
        self.assertEqual(cancelled["total_cents"], order["total_cents"])

    def test_cli_parser_accepts_express_for_quote_and_place(self):
        parser = build_parser()
        quote_args = parser.parse_args([
            "quote", "--fulfillment", "express", "--item", "notebook:2"
        ])
        place_args = parser.parse_args([
            "place", "--fulfillment", "express", "--item", "notebook:2"
        ])
        self.assertEqual(quote_args.fulfillment, "express")
        self.assertEqual(place_args.fulfillment, "express")

    @patch("builtins.input", side_effect=["regular", "notebook", "2", "", "express"])
    @patch("supplydesk.menu.show_catalog")
    def test_interactive_request_accepts_express(self, _show_catalog, _input):
        customer, items, fulfillment = read_request(self.service)
        self.assertEqual(customer, "regular")
        self.assertEqual(items, [{"product_id": "notebook", "quantity": 2}])
        self.assertEqual(fulfillment, "express")

    def test_pickup_and_standard_delivery_behavior_remain_unchanged(self):
        pickup = self.service.quote(
            "regular", [{"product_id": "notebook", "quantity": 2}]
        )
        standard = self.service.quote(
            "student", [{"product_id": "hoodie", "quantity": 2}], "delivery"
        )
        self.assertEqual(pickup["fulfillment"], "pickup")
        self.assertEqual(pickup["total_cents"], 1000)
        self.assertEqual(standard["discount_cents"], 800)
        self.assertEqual(standard["delivery_cents"], 600)
        self.assertEqual(standard["total_cents"], 7800)

    def test_other_fulfillment_values_remain_invalid(self):
        with self.assertRaisesRegex(
            ValueError, "Fulfillment must be pickup, delivery, or express"
        ):
            self.service.quote(
                "regular", [{"product_id": "notebook", "quantity": 1}], "drone"
            )


if __name__ == "__main__":
    unittest.main()
