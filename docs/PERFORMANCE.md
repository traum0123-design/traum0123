Performance Guide (p95 targets)

Goals (example, internal network)
- p95 for monthly list/detail/save: < 300–500 ms
- Excel export (10k–50k rows): streams without OOM/timeout

How to Measure
- Load: use k6 or Locust (samples in scripts/loadtest/)
- Metrics: scrape /metrics (Prometheus) and build a Grafana dashboard
- Trace: correlate via X-Request-ID in logs/responses

k6 Quick Start
1) Install k6: https://k6.io/docs/get-started/installation/
2) Run sample:

   k6 run scripts/loadtest/k6/payroll_smoke.js \
     --env BASE_URL=http://127.0.0.1:8000 \
     --env ADMIN_TOKEN=xxxx

3) Observe results: latency p(95), http_req_duration, http_reqs

Locust Quick Start
1) pip install locust
2) Run:

   locust -f scripts/loadtest/locustfile.py --host=http://127.0.0.1:8000 \
     --users 50 --spawn-rate 5

3) Open http://127.0.0.1:8089 and start a test

Prometheus/Grafana
- Scrape /metrics endpoint from the app
- Example query (5m window):
  - histogram_quantile(0.95, sum(rate(http_request_duration_bucket[5m])) by (le, handler, method))
- Build panels for p50/p95, error rate, throughput

Export Streaming Check
- Use scripts/loadtest/k6/payroll_smoke.js export task for >10k rows
- Verify memory stability and completion time > throughput

