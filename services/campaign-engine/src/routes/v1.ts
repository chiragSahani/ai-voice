/**
 * Campaign Engine v1 routes — /api/v1/campaigns prefix.
 */

import { Router } from 'express';
import { authMiddleware, requireRole } from '../../../shared/typescript/src';
import { config } from '../config';
import {
  createCampaign,
  getCampaign,
  updateCampaign,
  startCampaign,
  pauseCampaign,
  resumeCampaign,
  cancelCampaign,
  listCampaigns,
  getCampaignStats,
  listCampaignCalls,
  getCampaignAnalytics,
  getClinicAnalytics,
  previewReminder,
  getTemplates,
} from '../controllers';

const router = Router();

// Apply auth middleware to all routes
const auth = authMiddleware(config.jwt.secret);
router.use(auth);

// --- Campaign CRUD ---
router.post('/campaigns', requireRole('admin', 'staff'), createCampaign);
router.get('/campaigns', listCampaigns);
router.get('/campaigns/:id', getCampaign);
router.put('/campaigns/:id', requireRole('admin', 'staff'), updateCampaign);

// --- Campaign Lifecycle ---
router.post('/campaigns/:id/start', requireRole('admin', 'staff'), startCampaign);
router.post('/campaigns/:id/pause', requireRole('admin', 'staff'), pauseCampaign);
router.post('/campaigns/:id/resume', requireRole('admin', 'staff'), resumeCampaign);
router.post('/campaigns/:id/cancel', requireRole('admin', 'staff'), cancelCampaign);

// --- Campaign Stats & Calls ---
router.get('/campaigns/:id/stats', getCampaignStats);
router.get('/campaigns/:id/calls', listCampaignCalls);
router.get('/campaigns/:id/analytics', getCampaignAnalytics);

// --- Clinic Analytics ---
router.get('/analytics/clinic/:clinicId', getClinicAnalytics);

// --- Reminder Templates ---
router.post('/reminders/preview', previewReminder);
router.get('/reminders/templates', getTemplates);

export { router as v1Router };
