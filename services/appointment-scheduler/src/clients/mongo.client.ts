/**
 * MongoDB client initialization for the Appointment Scheduler service.
 */

import { connectMongo, closeMongo } from '../../../../shared/typescript/src';
import { getConfig } from '../config';

export async function initMongo(): Promise<void> {
  const config = getConfig();
  await connectMongo(config.mongo.uri, config.mongo.database);
}

export { closeMongo };
