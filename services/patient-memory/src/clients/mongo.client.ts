/**
 * MongoDB client initialization for Patient Memory service.
 */

import { connectMongo, closeMongo } from '../../../shared/typescript/src/mongo-client';
import { getConfig } from '../config';
import { getLogger } from '../../../shared/typescript/src/logger';

const logger = getLogger();

export async function initMongo(): Promise<void> {
  const config = getConfig();
  logger.info({ uri: config.mongo.uri, database: config.mongo.database }, 'Connecting to MongoDB');
  await connectMongo(config.mongo.uri, config.mongo.database);
}

export async function shutdownMongo(): Promise<void> {
  await closeMongo();
}
