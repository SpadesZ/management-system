# Screenshot source

`admin-approvals.png` was captured on 2026-10-02 from this checkout's real Vue
review-confirmation dialog. A DEMO_ONLY/SAMPLE_RECORD was created through the
isolated FastAPI backend, then approved through the UI; the response confirmed
PENDING -> APPROVED. This records a decision and creates no actual model-access
grant, key or usage. Login used the repository seed admin. Original labels are unchanged.

For isolation, the frontend ran on port 18704. Browser requests for the built-in backend URL `localhost:18001` were forwarded to the real isolated backend on port 18703. No API response was fabricated. This image is a local demo, not evidence of a current deployment or cost savings.
