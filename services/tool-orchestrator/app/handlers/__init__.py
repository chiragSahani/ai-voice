"""Tool handler implementations.

Each handler is an async function that accepts keyword arguments matching
its parameter schema and returns a result dict.
"""

from app.handlers.book_appointment import handle_book_appointment
from app.handlers.cancel_appointment import handle_cancel_appointment
from app.handlers.check_availability import handle_check_availability
from app.handlers.lookup_patient import handle_lookup_patient
from app.handlers.reschedule_appointment import handle_reschedule_appointment

__all__ = [
    "handle_check_availability",
    "handle_book_appointment",
    "handle_cancel_appointment",
    "handle_reschedule_appointment",
    "handle_lookup_patient",
]
