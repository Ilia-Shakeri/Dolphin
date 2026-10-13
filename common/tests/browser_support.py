"""What the real-browser tests (`*_browser.py`) share (2.40.42).

Every «ثبت» form in the panel is a step wizard now (`ui/wizard.js`): a field on
a later step is not interactable until the reader has moved to that step, and
the submit button exists only on the last one. These helpers do what a reader
does — fill each field on its own step, move on with «بعدی», submit at the end —
so a test can name the fields it fills without restating the wizard's layout.
They also accept the panel's own confirmation dialog (`confirmDialog`), which
replaced the browser's `confirm()`.

Not a test module: no `test_` prefix, so the runner does not collect it.
"""

import importlib.util
import time

if importlib.util.find_spec("selenium") is not None:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions
    from selenium.webdriver.support.ui import Select, WebDriverWait

STEP_INDEX = """
const dialog = arguments[0];
return [...dialog.querySelectorAll('[data-dolphin-stepper-element="content"]')]
    .findIndex((step) => step.classList.contains('current'));
"""


class BrowserFlowMixin:
    """Mixed into a `StaticLiveServerTestCase` that sets `self.browser` and `self.wait`."""

    def _step(self, dialog):
        return self.browser.execute_script(STEP_INDEX, dialog)

    def _next_step(self, dialog):
        buttons = [
            button for button in dialog.find_elements(By.CSS_SELECTOR, "[data-dolphin-stepper-action='next']")
            if button.is_displayed()
        ]
        if not buttons:
            return False
        before = self._step(dialog)
        buttons[0].click()
        try:
            WebDriverWait(self.browser, 5).until(lambda driver: self._step(dialog) != before)
        except Exception as exc:  # noqa: BLE001 - name the step that refused
            errors = [node.text for node in dialog.find_elements(By.CSS_SELECTOR, "[data-error-for]") if node.text.strip()]
            raise AssertionError(f"the wizard did not leave step {before}: {errors}") from exc
        return True

    def _settled(self, dialog):
        """The dialog is open and its entrance has finished: while it fades in
        (`@starting-style`, opacity 0) nothing inside counts as displayed."""
        self.wait.until(lambda driver: driver.execute_script(
            "const d = arguments[0]; return d.open && getComputedStyle(d).opacity === '1';", dialog
        ))

    def reveal(self, dialog_id, field_id):
        """The field, with the wizard moved forward to the step that holds it."""
        dialog = self.browser.find_element(By.ID, dialog_id)
        self._settled(dialog)
        for _ in range(8):
            field = self.browser.find_element(By.ID, field_id)
            try:
                WebDriverWait(self.browser, 1.5, poll_frequency=0.1).until(lambda driver: field.is_displayed())
                return field
            except Exception:  # noqa: BLE001 - not on this step
                pass
            if not self._next_step(dialog):
                break
        self.fail(f"{field_id} is on no step of {dialog_id}")

    def set_field(self, field, value):
        if field.tag_name == "select":
            self.wait.until(lambda driver: any(
                option.text.strip() == value or option.get_attribute("value") == value
                for option in Select(field).options
            ))
            def choose(driver):
                # A list the page fills twice (a placeholder, then the real
                # options) can drop a choice made in between: choose again
                # until it holds.
                select = Select(field)
                matches = [option for option in select.options if option.text.strip() == value]
                if matches:
                    if select.first_selected_option.text.strip() != value:
                        select.select_by_visible_text(matches[0].text)
                    return select.first_selected_option.text.strip() == value
                if field.get_attribute("value") != value:
                    select.select_by_value(value)
                return field.get_attribute("value") == value

            self.wait.until(choose)
            # Held for a moment, not just at the instant it was made.
            time.sleep(0.4)
            self.wait.until(choose)
        elif field.get_attribute("type") == "checkbox":
            if field.is_selected() != bool(value):
                field.click()
        else:
            field.clear()
            field.send_keys(value)

    def fill_wizard(self, dialog_id, fields, submit=True):
        """Fill `fields` — `[(id, value), …]` in the order a reader meets them —
        each on its own step, then move to the last step and submit."""
        for field_id, value in fields:
            self.set_field(self.reveal(dialog_id, field_id), value)
        if not submit:
            return
        dialog = self.browser.find_element(By.ID, dialog_id)
        self._settled(dialog)
        while self._next_step(dialog):
            pass
        self.wait.until(expected_conditions.element_to_be_clickable(
            (By.CSS_SELECTOR, f"#{dialog_id} [data-dolphin-stepper-action='submit'], #{dialog_id} button[type='submit']")
        )).click()

    def confirm(self):
        """Accept the panel's own confirmation dialog."""
        self.wait.until(expected_conditions.element_to_be_clickable(
            (By.CSS_SELECTOR, "#dolphin-confirm-dialog [data-confirm-ok]")
        )).click()
        self.wait.until(lambda driver: not driver.execute_script(
            "return document.getElementById('dolphin-confirm-dialog')?.open"
        ))
