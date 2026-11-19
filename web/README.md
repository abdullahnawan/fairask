# FairAsk web

The Next.js form and report. It calls the FastAPI app through `/api/*`, which
`next.config.ts` forwards to `API_URL` (default `http://localhost:8000`).

```sh
# terminal 1, repo root
uvicorn main:app --app-dir api

# terminal 2
cd web
npm install
npm run dev      # http://localhost:3000
npm test         # Vitest
```
