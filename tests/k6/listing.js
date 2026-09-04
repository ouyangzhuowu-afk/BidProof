# BidProof k6 压测基线（规划假设，非 SLA）

# 用法：
#   k6 run tests/k6/listing.js -e BASE=https://bidproof.marketcase.net
#
# 第一批假设对应成熟度报告的崩溃顺序：列表内存、连接池、限流表、inline 作业。

import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    listing: {
      executor: 'constant-vus',
      vus: 20,
      duration: '2m',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.05'],
    http_req_duration: ['p(95)<3000'],
  },
};

const BASE = __ENV.BASE || 'http://127.0.0.1:8080';

export default function () {
  const health = http.get(`${BASE}/healthz`);
  check(health, { 'healthz 200': (r) => r.status === 200 });
  const app = http.get(`${BASE}/app`);
  check(app, { 'app 200': (r) => r.status === 200 });
  sleep(1);
}
