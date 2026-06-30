# 🖥️ my-ai Frontend — Next.js Dashboard

This is the Next.js (React) web client dashboard interface for the `my-ai` autonomous personal agent system.

---

## 🎨 Design System & Technologies

*   **Framework**: Next.js 15+ (App Router)
*   **Styling**: Modern Vanilla CSS Modules with dynamic HSL CSS custom properties for rich dark mode support.
*   **Icons**: Lucide React
*   **Data Fetching**: TanStack React Query (for cache state, query invalidations, and optimistic mutations)
*   **State Management**: Zustand (for reactive client sidebar and layout state)

---

## 🚀 Local Development

1. Install package dependencies:
   ```bash
   npm install
   ```
2. Start the development server:
   ```bash
   npm run dev
   ```
3. Open **[http://localhost:3004](http://localhost:3004)** in your browser.

### 🌐 API Proxy configuration
The client proxies API requests locally to prevent CORS blocks. During development:
*   Auth endpoints (`/api/v1/auth/*`) map to `http://localhost:8001`
*   Goal endpoints (`/api/v1/goals/*`) map to `http://localhost:8002`
*   Agent endpoints (`/api/v1/agents/*`) map to `http://localhost:8003`

In production, these routes are dynamically mapped using environment variables configured in `.env` (e.g. `NEXT_PUBLIC_AUTH_URL`, `NEXT_PUBLIC_GOALS_URL`, `NEXT_PUBLIC_AGENT_URL`).
