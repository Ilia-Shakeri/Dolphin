"""Telephony's own signals, for the parts of Dolphin that react to calls
without the listener knowing them (the popup, from 2.23.0)."""

from django.dispatch import Signal

#: An inbound call is ringing `user_id`'s extension. `call` is saved.
call_ringing = Signal()
