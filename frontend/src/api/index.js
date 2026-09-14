/**
 * API 层出口。
 *
 * 特性模块一律从这里导入，不直接 import core/http.js ——
 * 这样「有多少个地方在自己拼 URL」这个问题的答案永远是 0，
 * 换传输实现（比如将来走 BFF）时也只有这一层要动。
 *
 * 用法：
 *   import { runsApi, jobsApi } from '../api/index.js';
 *   const runs = await runsApi.listRuns({ scope: 'ACTIVE' });
 */

export * as runsApi from './runs.js';
export * as jobsApi from './jobs.js';
export * as authApi from './auth.js';
export * as workspaceApi from './workspace.js';

export { paths } from './paths.js';
export { ApiError, onUnauthorized } from '../core/http.js';
