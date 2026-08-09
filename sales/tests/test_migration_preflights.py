from importlib import import_module
from unittest import mock

from django.test import SimpleTestCase


class SalesMigrationPreflightTests(SimpleTestCase):
    def _apps_with_model(self, model):
        apps = mock.Mock()
        apps.get_model.return_value = model
        return apps

    def test_sale_snapshot_preflight_fails_before_constraints(self):
        model = mock.Mock()
        bad_pair = mock.Mock()
        bad_pair.exists.return_value = True
        product_rows = mock.Mock()
        product_rows.exclude.return_value.exists.return_value = False
        model.objects.filter.side_effect = [bad_pair, product_rows]
        migration = import_module("sales.migrations.0005_sale_integrity_constraints")

        with self.assertRaisesRegex(RuntimeError, "product snapshot rules"):
            migration.validate_existing_sales(self._apps_with_model(model), None)

    def test_global_phone_preflight_fails_on_duplicate_identity(self):
        model = mock.Mock()
        duplicate_rows = model.objects.filter.return_value.values.return_value.annotate.return_value.filter.return_value
        duplicate_rows.exists.return_value = True
        migration = import_module("sales.migrations.0006_global_active_phone_identity")

        with self.assertRaisesRegex(RuntimeError, "conflict across Customers"):
            migration.validate_active_phone_identities(self._apps_with_model(model), None)

    def test_positive_product_preflight_fails_on_zero_or_negative_price(self):
        model = mock.Mock()
        model.objects.filter.return_value.exists.return_value = True
        migration = import_module("sales.migrations.0007_product_price_positive")

        with self.assertRaisesRegex(RuntimeError, "non-positive prices"):
            migration.validate_product_prices(self._apps_with_model(model), None)

    def test_phone_shape_preflight_lists_id_but_not_stored_value(self):
        marker = "private-bad-phone-marker"
        model = mock.Mock()
        model.objects.values_list.return_value.iterator.return_value = [(77, marker)]
        migration = import_module("sales.migrations.0008_customer_phone_normalized_shape")

        with self.assertRaises(RuntimeError) as caught:
            migration.validate_normalized_phone_shape(self._apps_with_model(model), None)

        self.assertIn("77", str(caught.exception))
        self.assertNotIn(marker, str(caught.exception))
