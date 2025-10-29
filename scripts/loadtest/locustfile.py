from locust import HttpUser, task, between
import os


class PayrollUser(HttpUser):
    wait_time = between(0.5, 2.0)
    headers = {}

    def on_start(self):
        token = os.getenv("ADMIN_TOKEN", "")
        if token:
            self.headers["X-Admin-Token"] = token

    @task(2)
    def health(self):
        with self.client.get("/api/healthz", name="healthz", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure("unhealthy")

    @task(3)
    def companies_page(self):
        self.client.get("/api/v1/admin/companies/page?limit=20", name="companies_page", headers=self.headers)

    @task(1)
    def export_demo(self):
        slug = os.getenv("SLUG", "demo")
        year = os.getenv("YEAR", "2025")
        month = os.getenv("MONTH", "7")
        self.client.get(f"/api/portal/{slug}/export/{year}/{month}", name="export", headers=self.headers)

