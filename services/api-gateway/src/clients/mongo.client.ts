/**
 * MongoDB client placeholder for the API Gateway.
 *
 * The gateway itself does not use MongoDB directly (it proxies to services
 * that do), but this module is provided for consistency with the service
 * template and to support future features such as API key storage.
 */

import { connectMongo, closeMongo } from '@shared/mongo-client';

export { connectMongo, closeMongo };
