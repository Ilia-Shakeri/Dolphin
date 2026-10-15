"""Signals other modules listen to without `accounts` knowing them."""

from django.dispatch import Signal

#: Sent inside the transaction that deactivates an account (2.40.48), with
#: `actor` (who did it) and `user` (the account). `sales.returned_work` takes
#: the account's open work back to the managers on it.
user_deactivated = Signal()
