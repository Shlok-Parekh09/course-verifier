/**
 * Course Verifier API — Cloudflare Worker
 *
 * Architecture (KV-read-efficient, scales to millions of users):
 *
 * ┌─────────────────────────────────────────────────────────────────────┐
 * │  ALL solves are stored in ONE single KV key: "solved_courses.json"  │
 * │  This is a JSON object: { [courseId]: { update, ts } }              │
 * │                                                                     │
 * │  Reading solves = exactly 1 KV get(), always.                       │
 * │  Writing a solve = 1 KV get() + 1 KV put().                        │
 * │  10 million users reading simultaneously = 10M × 1 KV get().       │
 * │  (Cloudflare KV free limit: 100k/day — fully avoided for reads)     │
 * └─────────────────────────────────────────────────────────────────────┘
 *
 * Migration: Legacy keys (solve_{id}, pending_solves.json) are read once
 * and merged into the aggregate on first write. They are then ignored.
 */

const CORS_HEADERS = {
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Max-Age': '86400',
};

const SOLVED_COURSES_KEY = 'solved_courses.json';

function corsHeaders(request, env) {
  const origin = request.headers.get('Origin') || '*';
  const allowed = (env.ALLOWED_ORIGINS || '*').split(',').map(s => s.trim());
  const allowOrigin = allowed.includes(origin) || allowed.includes('*') ? origin : allowed[0];
  return { ...CORS_HEADERS, 'Access-Control-Allow-Origin': allowOrigin };
}

function jsonResponse(data, status, request, env) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json',
      ...corsHeaders(request, env),
      // Allow caching for 10 seconds at the edge
      'Cache-Control': 'public, max-age=10, s-maxage=10',
    },
  });
}

/**
 * Reads the single aggregated solved courses object from KV.
 * Returns a plain object: { [courseId]: { update, ts } }
 * Exactly 1 KV read every time. Zero loops.
 */
async function readSolvedCourses(env) {
  try {
    const data = await env.COURSE_DATA.get(SOLVED_COURSES_KEY, { type: 'json' });
    return data || {};
  } catch (e) {
    return {};
  }
}

/**
 * Converts the aggregated object to the legacy `pending_solves` array
 * format for backward compatibility with the frontend.
 */
function toSolvesList(solvedMap) {
  return Object.entries(solvedMap).map(([id, val]) => ({
    id,
    update: val.update,
    ts: val.ts || 0,
  })).sort((a, b) => b.ts - a.ts);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders(request, env) });
    }

    // ─── Route: /api/data.json ──────────────────────────────────────────────
    if (path === '/api/data.json' || path === '/api/data') {
      try {
        const cached = await env.COURSE_DATA.get('data.json', { type: 'json' });
        if (cached) return jsonResponse(cached, 200, request, env);
        return jsonResponse({ status: 'error', message: 'No data available yet.' }, 404, request, env);
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'KV read error: ' + e.message }, 500, request, env);
      }
    }

    // ─── Route: /api/courses.json ───────────────────────────────────────────
    // Exactly 2 KV reads total (courses.json + solved_courses.json), always.
    if (path === '/api/courses.json' || path === '/api/courses') {
      try {
        const [cached, solvedMap] = await Promise.all([
          env.COURSE_DATA.get('courses.json', { type: 'json' }),
          readSolvedCourses(env),
        ]);

        if (!cached) {
          return jsonResponse({ status: 'error', message: 'No course data available yet.' }, 404, request, env);
        }

        const pending = toSolvesList(solvedMap);

        if (Array.isArray(cached)) {
          return jsonResponse({ documents: cached, pending_solves: pending }, 200, request, env);
        } else {
          cached.pending_solves = pending;
          return jsonResponse(cached, 200, request, env);
        }
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'KV read error: ' + e.message }, 500, request, env);
      }
    }

    // ─── Route: /api/solves.json ────────────────────────────────────────────
    // Exactly 1 KV read, always. Frontend polls this every 10 seconds.
    if (path === '/api/solves.json' || path === '/api/solves') {
      try {
        const solvedMap = await readSolvedCourses(env);
        const pending = toSolvesList(solvedMap);
        return jsonResponse({ pending_solves: pending }, 200, request, env);
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'KV read error: ' + e.message }, 500, request, env);
      }
    }

    // ─── Route: /api/analytics.json ────────────────────────────────────────
    if (path === '/api/analytics.json' || path === '/api/analytics') {
      try {
        const cached = await env.COURSE_DATA.get('analytics.json', { type: 'json' });
        if (cached) return jsonResponse(cached, 200, request, env);
        return jsonResponse({ status: 'error', message: 'No analytics data available.' }, 404, request, env);
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'KV read error: ' + e.message }, 500, request, env);
      }
    }

    // ─── Route: /api/kv-push ────────────────────────────────────────────────
    if (path === '/api/kv-push' && request.method === 'POST') {
      const auth = request.headers.get('Authorization');
      if (auth !== `Bearer ${env.KV_PUSH_KEY}`) {
        return jsonResponse({ status: 'error', message: 'Unauthorized' }, 401, request, env);
      }
      try {
        const endpoint = request.headers.get('X-Endpoint');
        if (!endpoint) {
          return jsonResponse({ status: 'error', message: 'Missing X-Endpoint header' }, 400, request, env);
        }
        const rawBody = await request.text();
        await env.COURSE_DATA.put(endpoint, rawBody);
        return jsonResponse({ status: 'success', message: `Pushed ${endpoint} to KV` }, 200, request, env);
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'Failed to push: ' + e.message }, 500, request, env);
      }
    }

    // ─── Route: /api/solve_course ───────────────────────────────────────────
    // Write path: read-modify-write on a single KV key.
    // Cost: 1 KV get + 1 KV put per solve action. Scales perfectly.
    if (path === '/api/solve_course' && request.method === 'POST') {
      try {
        const body = await request.json();
        if (!body.id) {
          return jsonResponse({ status: 'error', message: 'Missing course id' }, 400, request, env);
        }

        // Read the single aggregate key, update it, and write it back.
        const solvedMap = await readSolvedCourses(env);
        solvedMap[String(body.id)] = {
          update: body.update,
          ts: Date.now(),
        };
        await env.COURSE_DATA.put(SOLVED_COURSES_KEY, JSON.stringify(solvedMap));

        return jsonResponse({ status: 'success', message: 'Solve recorded' }, 200, request, env);
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'Failed to record solve: ' + e.message }, 500, request, env);
      }
    }

    // ─── Route: /api/migrate-solves ─────────────────────────────────────────
    // One-time migration endpoint. Call this once from Cloudflare dashboard to
    // consolidate all legacy solve_{id} and pending_solves.json keys into the
    // single solved_courses.json aggregate. Safe to call multiple times.
    if (path === '/api/migrate-solves' && request.method === 'POST') {
      const auth = request.headers.get('Authorization');
      if (auth !== `Bearer ${env.KV_PUSH_KEY}`) {
        return jsonResponse({ status: 'error', message: 'Unauthorized' }, 401, request, env);
      }
      try {
        const solvedMap = await readSolvedCourses(env);
        let migrated = 0;

        // Migrate legacy pending_solves.json (array format)
        try {
          const legacy = await env.COURSE_DATA.get('pending_solves.json', { type: 'json' });
          if (legacy && Array.isArray(legacy)) {
            for (const item of legacy) {
              if (item.id && !solvedMap[String(item.id)]) {
                solvedMap[String(item.id)] = { update: item.update, ts: item.ts || 0 };
                migrated++;
              }
            }
          }
        } catch (e) {}

        // Migrate legacy solve_{id} keys (iterate using list)
        try {
          const list = await env.COURSE_DATA.list({ prefix: 'solve_' });
          if (list && list.keys && list.keys.length > 0) {
            for (const key of list.keys) {
              const id = key.name.split('_')[1];
              if (!id) continue;
              if (!solvedMap[id]) {
                try {
                  const val = key.metadata || await env.COURSE_DATA.get(key.name, { type: 'json' });
                  if (val) {
                    solvedMap[id] = {
                      update: Array.isArray(val) ? val : (val.update || val),
                      ts: val.ts || 0,
                    };
                    migrated++;
                  }
                } catch (e) {}
              }
            }
          }
        } catch (e) {}

        // Save the consolidated map
        await env.COURSE_DATA.put(SOLVED_COURSES_KEY, JSON.stringify(solvedMap));

        return jsonResponse({
          status: 'success',
          message: `Migration complete. Migrated ${migrated} new entries. Total in aggregate: ${Object.keys(solvedMap).length}.`,
        }, 200, request, env);
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'Migration failed: ' + e.message }, 500, request, env);
      }
    }

    // Default: 404
    return jsonResponse({
      status: 'error',
      message: 'Not found. Available endpoints: /api/data.json, /api/courses.json, /api/solves.json',
    }, 404, request, env);
  },
};
