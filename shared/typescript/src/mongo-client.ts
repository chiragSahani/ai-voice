/**
 * Mongoose connection factory.
 */

import mongoose from 'mongoose';
import { getLogger } from './logger';

let isConnected = false;

export async function connectMongo(uri: string, database?: string): Promise<typeof mongoose> {
  if (isConnected) {
    return mongoose;
  }

  const logger = getLogger();

  mongoose.set('strictQuery', true);

  mongoose.connection.on('connected', () => {
    isConnected = true;
    logger.info({ database }, 'MongoDB connected');
  });

  mongoose.connection.on('error', (err: Error) => {
    logger.error({ error: err.message }, 'MongoDB error');
  });

  mongoose.connection.on('disconnected', () => {
    isConnected = false;
    logger.warn('MongoDB disconnected');
  });

  await mongoose.connect(uri, {
    dbName: database,
    maxPoolSize: 20,
    minPoolSize: 5,
    serverSelectionTimeoutMS: 5000,
    socketTimeoutMS: 10000,
    connectTimeoutMS: 5000,
  });

  return mongoose;
}

export async function closeMongo(): Promise<void> {
  if (isConnected) {
    await mongoose.disconnect();
    isConnected = false;
  }
}

export async function pingMongo(): Promise<boolean> {
  try {
    if (!mongoose.connection.db) return false;
    const result = await mongoose.connection.db.admin().ping();
    return result.ok === 1;
  } catch {
    return false;
  }
}

export { mongoose };
