from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase, TestCase


class KarizHomeTests(TestCase):
    def setUp(self):
        from accounts.models import User

        self.user = User.objects.create_user(username="home.brand", password="Strong-pass-937!")
        self.client.force_login(self.user)

    def test_home_is_persian_rtl_and_uses_only_local_brand_assets(self):
        response = self.client.get("/")
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('<html lang="fa" dir="rtl">', content)
        self.assertIn('<title>میز کار بازاریاب | ForooshBin</title>', content)
        self.assertIn('<meta name="robots" content="noindex,nofollow,noarchive" />', content)
        self.assertContains(response, "ForooshBin | فروش‌بین")
        self.assertContains(response, "میز کار بازاریاب")
        self.assertContains(response, "پروفایل من")
        self.assertNotContains(response, "Metronic")
        self.assertNotContains(response, "KeenThemes")
        self.assertNotIn('href="http', content)

    def test_home_stylesheet_is_first_party_static(self):
        self.assertIsNotNone(finders.find("common/kariz.css"))
        favicon = settings.BASE_DIR / "assets" / "media" / "logos" / "favicon.ico"
        self.assertTrue(favicon.is_file())
        self.assertContains(self.client.get("/"), '/static/kariz-brand/favicon.ico')


class PersianAdminBrandTests(SimpleTestCase):
    def test_default_language_and_admin_brand_are_persian(self):
        self.assertEqual(settings.LANGUAGE_CODE, "fa")
        self.assertEqual(admin.site.site_header, "مدیریت فروش‌بین")
        self.assertEqual(admin.site.site_title, "ForooshBin | فروش‌بین")
        self.assertEqual(admin.site.index_title, "پنل مدیریت فروش‌بین")

    # The admin login page is no longer routed by default: ENABLE_DJANGO_ADMIN
    # is false, so /admin/ does not exist on a customer deployment. Its Persian
    # RTL branding is still asserted, under an explicitly admin-enabled URLConf,
    # in common/tests/test_admin_exposure.py.
