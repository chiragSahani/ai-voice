/**
 * MongoDB seed data for development/testing.
 * Run via: docker-compose exec mongo mongosh < infrastructure/mongo/seed.js
 */

db = db.getSiblingDB('voice_agent');

// --- Seed Doctors ---

const doctors = [
  {
    name: 'Dr. Priya Sharma',
    specialization: 'general_medicine',
    clinicId: 'clinic_001',
    schedule: [
      { dayOfWeek: 1, startTime: '09:00', endTime: '13:00', slotDurationMinutes: 30 },
      { dayOfWeek: 1, startTime: '14:00', endTime: '17:00', slotDurationMinutes: 30 },
      { dayOfWeek: 2, startTime: '09:00', endTime: '13:00', slotDurationMinutes: 30 },
      { dayOfWeek: 2, startTime: '14:00', endTime: '17:00', slotDurationMinutes: 30 },
      { dayOfWeek: 3, startTime: '09:00', endTime: '13:00', slotDurationMinutes: 30 },
      { dayOfWeek: 4, startTime: '09:00', endTime: '13:00', slotDurationMinutes: 30 },
      { dayOfWeek: 4, startTime: '14:00', endTime: '17:00', slotDurationMinutes: 30 },
      { dayOfWeek: 5, startTime: '09:00', endTime: '13:00', slotDurationMinutes: 30 },
    ],
    overrides: [],
    isActive: true,
    createdAt: new Date(),
    updatedAt: new Date(),
  },
  {
    name: 'Dr. Rajesh Kumar',
    specialization: 'cardiology',
    clinicId: 'clinic_001',
    schedule: [
      { dayOfWeek: 1, startTime: '10:00', endTime: '14:00', slotDurationMinutes: 45 },
      { dayOfWeek: 3, startTime: '10:00', endTime: '14:00', slotDurationMinutes: 45 },
      { dayOfWeek: 5, startTime: '10:00', endTime: '14:00', slotDurationMinutes: 45 },
    ],
    overrides: [],
    isActive: true,
    createdAt: new Date(),
    updatedAt: new Date(),
  },
  {
    name: 'Dr. Anitha Rajan',
    specialization: 'pediatrics',
    clinicId: 'clinic_001',
    schedule: [
      { dayOfWeek: 1, startTime: '08:00', endTime: '12:00', slotDurationMinutes: 20 },
      { dayOfWeek: 2, startTime: '08:00', endTime: '12:00', slotDurationMinutes: 20 },
      { dayOfWeek: 3, startTime: '08:00', endTime: '12:00', slotDurationMinutes: 20 },
      { dayOfWeek: 4, startTime: '08:00', endTime: '12:00', slotDurationMinutes: 20 },
      { dayOfWeek: 5, startTime: '08:00', endTime: '12:00', slotDurationMinutes: 20 },
    ],
    overrides: [],
    isActive: true,
    createdAt: new Date(),
    updatedAt: new Date(),
  },
  {
    name: 'Dr. Vikram Patel',
    specialization: 'dermatology',
    clinicId: 'clinic_001',
    schedule: [
      { dayOfWeek: 2, startTime: '09:00', endTime: '13:00', slotDurationMinutes: 30 },
      { dayOfWeek: 4, startTime: '09:00', endTime: '13:00', slotDurationMinutes: 30 },
    ],
    overrides: [],
    isActive: true,
    createdAt: new Date(),
    updatedAt: new Date(),
  },
];

db.doctors.insertMany(doctors);
print(`✓ Inserted ${doctors.length} doctors`);

// --- Seed Patients ---

const patients = [
  {
    firstName: 'Amit',
    lastName: 'Verma',
    dateOfBirth: new Date('1985-03-15'),
    gender: 'male',
    phone: '+919876543210',
    email: 'amit.verma@example.com',
    address: { street: '42 MG Road', city: 'Mumbai', state: 'Maharashtra', zipCode: '400001', country: 'IN' },
    preferredLanguage: 'en',
    medicalRecordNumber: 'MRN-001',
    clinicId: 'clinic_001',
    tags: ['diabetes', 'regular'],
    isActive: true,
    consentVoiceRecording: true,
    createdAt: new Date(),
    updatedAt: new Date(),
  },
  {
    firstName: 'Lakshmi',
    lastName: 'Sundaram',
    dateOfBirth: new Date('1972-08-22'),
    gender: 'female',
    phone: '+919876543211',
    email: 'lakshmi.s@example.com',
    address: { street: '15 Anna Salai', city: 'Chennai', state: 'Tamil Nadu', zipCode: '600002', country: 'IN' },
    preferredLanguage: 'ta',
    medicalRecordNumber: 'MRN-002',
    clinicId: 'clinic_001',
    tags: ['hypertension'],
    isActive: true,
    consentVoiceRecording: false,
    createdAt: new Date(),
    updatedAt: new Date(),
  },
  {
    firstName: 'Rahul',
    lastName: 'Singh',
    dateOfBirth: new Date('1990-11-05'),
    gender: 'male',
    phone: '+919876543212',
    email: 'rahul.singh@example.com',
    address: { street: '8 Connaught Place', city: 'New Delhi', state: 'Delhi', zipCode: '110001', country: 'IN' },
    preferredLanguage: 'hi',
    medicalRecordNumber: 'MRN-003',
    clinicId: 'clinic_001',
    tags: [],
    isActive: true,
    consentVoiceRecording: true,
    createdAt: new Date(),
    updatedAt: new Date(),
  },
];

db.patients.insertMany(patients);
print(`✓ Inserted ${patients.length} patients`);

// --- Seed Voice Agent User ---

db.users.updateOne(
  { email: 'voice-agent@voiceagent.local' },
  {
    $setOnInsert: {
      email: 'voice-agent@voiceagent.local',
      passwordHash: '$2b$12$placeholder_hash_for_service_account',
      firstName: 'Voice',
      lastName: 'Agent',
      role: 'voice_agent',
      clinicId: 'clinic_001',
      permissions: ['patients:read', 'appointments:read', 'appointments:write'],
      isActive: true,
      createdAt: new Date(),
      updatedAt: new Date(),
    },
  },
  { upsert: true },
);

print('✓ Seed data inserted successfully.');
