/**
 * Re-export booking service functions for backwards compatibility.
 * The primary implementation lives in booking.service.ts.
 */

export {
  bookAppointment,
  cancelAppointment,
  rescheduleAppointment,
  getAppointment,
  listAppointments,
} from './booking.service';
