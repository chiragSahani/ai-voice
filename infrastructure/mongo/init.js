/**
 * MongoDB initialization script.
 * Creates database, collections, indexes, and initial admin user.
 * Run via: docker-compose exec mongo mongosh < infrastructure/mongo/init.js
 */

// Switch to voice_agent database
db = db.getSiblingDB('voice_agent');

// --- Create collections with validation ---

db.createCollection('patients', {
  validator: {
    $jsonSchema: {
      bsonType: 'object',
      required: ['firstName', 'lastName', 'phone', 'clinicId', 'medicalRecordNumber'],
      properties: {
        firstName: { bsonType: 'string' },
        lastName: { bsonType: 'string' },
        phone: { bsonType: 'string' },
        email: { bsonType: 'string' },
        clinicId: { bsonType: 'string' },
        medicalRecordNumber: { bsonType: 'string' },
        preferredLanguage: { enum: ['en', 'hi', 'ta'] },
        gender: { enum: ['male', 'female', 'other', 'prefer_not_to_say'] },
        isActive: { bsonType: 'bool' },
      },
    },
  },
});

db.createCollection('doctors', {
  validator: {
    $jsonSchema: {
      bsonType: 'object',
      required: ['name', 'specialization', 'clinicId'],
      properties: {
        name: { bsonType: 'string' },
        specialization: { bsonType: 'string' },
        clinicId: { bsonType: 'string' },
        isActive: { bsonType: 'bool' },
      },
    },
  },
});

db.createCollection('appointmentSlots');
db.createCollection('appointments');
db.createCollection('campaigns');
db.createCollection('campaignCalls');
db.createCollection('conversationSummaries');
db.createCollection('auditLogs');
db.createCollection('users');

// --- Create indexes ---

// Patients
db.patients.createIndex({ phone: 1 });
db.patients.createIndex({ clinicId: 1, phone: 1 });
db.patients.createIndex({ clinicId: 1, lastName: 1, firstName: 1 });
db.patients.createIndex({ medicalRecordNumber: 1 }, { unique: true });

// Doctors
db.doctors.createIndex({ clinicId: 1 });
db.doctors.createIndex({ specialization: 1 });
db.doctors.createIndex({ clinicId: 1, specialization: 1, isActive: 1 });

// Appointment Slots
db.appointmentSlots.createIndex({ doctorId: 1, date: 1, status: 1 });
db.appointmentSlots.createIndex({ clinicId: 1, date: 1, status: 1 });
db.appointmentSlots.createIndex({ heldUntil: 1 }, { expireAfterSeconds: 0 });

// Appointments
db.appointments.createIndex({ patientId: 1, date: -1 });
db.appointments.createIndex({ doctorId: 1, date: 1 });
db.appointments.createIndex({ clinicId: 1, date: 1, status: 1 });
db.appointments.createIndex({ slotId: 1 }, { unique: true });

// Campaigns
db.campaigns.createIndex({ clinicId: 1 });
db.campaigns.createIndex({ status: 1 });

// Campaign Calls
db.campaignCalls.createIndex({ campaignId: 1, status: 1 });
db.campaignCalls.createIndex({ patientId: 1, campaignId: 1 });
db.campaignCalls.createIndex({ scheduledAt: 1, status: 1 });

// Conversation Summaries
db.conversationSummaries.createIndex({ sessionId: 1 }, { unique: true });
db.conversationSummaries.createIndex({ patientId: 1, createdAt: -1 });

// Audit Logs
db.auditLogs.createIndex({ userId: 1, createdAt: -1 });
db.auditLogs.createIndex({ resourceType: 1, resourceId: 1 });
db.auditLogs.createIndex({ clinicId: 1, createdAt: -1 });
db.auditLogs.createIndex({ createdAt: 1 }, { expireAfterSeconds: 365 * 24 * 3600 }); // 1 year TTL

// Users
db.users.createIndex({ email: 1 }, { unique: true });
db.users.createIndex({ clinicId: 1, role: 1 });

// --- Create admin user ---

db.users.insertOne({
  email: 'admin@voiceagent.local',
  passwordHash: '$2b$12$placeholder_hash_replace_in_production',
  firstName: 'System',
  lastName: 'Admin',
  role: 'admin',
  clinicId: 'clinic_001',
  permissions: ['patients:read', 'patients:write', 'appointments:read', 'appointments:write', 'campaigns:read', 'campaigns:write', 'admin:all'],
  isActive: true,
  createdAt: new Date(),
  updatedAt: new Date(),
});

print('✓ Database initialized: collections, indexes, and admin user created.');
