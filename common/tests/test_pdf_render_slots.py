"""One PDF render at a time, so a download cannot take the whole site down.

Gunicorn runs synchronous workers and a render holds one for as long as the
browser takes. With three workers and no bound, three simultaneous downloads
answered nothing else at all.
"""

from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from common import pdf


class RenderSlotTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_a_slot_is_released_when_the_render_finishes(self):
        with pdf._render_slot():
            pass
        # Free again, so the next request is served rather than refused.
        with pdf._render_slot():
            pass

    def test_a_slot_is_released_even_when_the_render_fails(self):
        with self.assertRaises(RuntimeError):
            with pdf._render_slot():
                raise RuntimeError("chromium fell over")
        with pdf._render_slot():
            pass

    def test_a_second_render_is_refused_rather_than_queued(self):
        with pdf._render_slot():
            with self.assertRaises(pdf.PdfRendererBusy):
                with pdf._render_slot():
                    pass

    def test_being_busy_is_a_kind_of_unavailable(self):
        """Callers that only know `PdfRendererUnavailable` still behave."""
        self.assertTrue(issubclass(pdf.PdfRendererBusy, pdf.PdfRendererUnavailable))

    @override_settings(PDF_RENDERER="chromium")
    def test_a_busy_renderer_never_starts_a_browser(self):
        with mock.patch.object(pdf, "_chromium_binary", return_value="/usr/bin/chromium"):
            with mock.patch.object(pdf, "_print_with_chromium") as printer:
                with pdf._render_slot():
                    with self.assertRaises(pdf.PdfRendererBusy):
                        pdf.render_html_to_pdf("<p>سند</p>")
                printer.assert_not_called()
