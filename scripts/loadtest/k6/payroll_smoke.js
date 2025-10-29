import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 10,
  duration: '30s',
  thresholds: {
    http_req_duration: ['p(95)<500'], // 95% under 500ms
    http_req_failed: ['rate<0.01'],
  },
};

const BASE = __ENV.BASE_URL || 'http://127.0.0.1:8000';
const ADMIN = __ENV.ADMIN_TOKEN || '';

export default function () {
  const params = ADMIN ? { headers: { 'X-Admin-Token': ADMIN } } : {};
  // Health
  let res = http.get(`${BASE}/api/healthz`);
  check(res, { 'health ok': (r) => r.status === 200 });

  // Companies page (admin)
  res = http.get(`${BASE}/api/v1/admin/companies/page?limit=20`, params);
  check(res, { 'companies 200': (r) => r.status === 200 });

  // Optional: export endpoint (adjust slug/year/month)
  const slug = __ENV.SLUG || 'demo';
  const year = __ENV.YEAR || '2025';
  const month = __ENV.MONTH || '7';
  res = http.get(`${BASE}/api/portal/${slug}/export/${year}/${month}`, params);
  check(res, { 'export 200/stream': (r) => r.status === 200 || r.status === 404 });

  sleep(1);
}

