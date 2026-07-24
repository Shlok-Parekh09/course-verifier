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

    // ─── Route: /api/solve-audit (GET, admin) ──────────────────────────────
    // Returns all solved courses with human-readable timestamps.
    // Protected by KV_PUSH_KEY. Use this to investigate who solved what and when.
    if (path === '/api/solve-audit') {
      const auth = request.headers.get('Authorization');
      if (auth !== `Bearer ${env.KV_PUSH_KEY}`) {
        return jsonResponse({ status: 'error', message: 'Unauthorized' }, 401, request, env);
      }
      try {
        const solvedMap = await readSolvedCourses(env);
        const entries = Object.entries(solvedMap).map(([id, val]) => {
          const tsMs = val.ts || 0;
          const dt = new Date(tsMs);
          return {
            id,
            ts: tsMs,
            solved_at_utc: dt.toISOString(),
            solved_at_ist: new Date(tsMs + 5.5 * 3600 * 1000).toISOString().replace('T', ' ').substring(0, 19) + ' IST',
          };
        }).sort((a, b) => b.ts - a.ts); // Newest first

        return jsonResponse({
          total: entries.length,
          solves: entries,
        }, 200, request, env);
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'Audit failed: ' + e.message }, 500, request, env);
      }
    }

    // ─── Route: /api/unsolve-after (POST, admin) ───────────────────────────
    // Removes all solves recorded AFTER a given timestamp.
    // Body: { "after_ts": <unix ms> }  OR  { "after_ist": "2026-07-24 20:00:00" }
    // Protected by KV_PUSH_KEY.
    if (path === '/api/unsolve-after' && request.method === 'POST') {
      const auth = request.headers.get('Authorization');
      if (auth !== `Bearer ${env.KV_PUSH_KEY}`) {
        return jsonResponse({ status: 'error', message: 'Unauthorized' }, 401, request, env);
      }
      try {
        const body = await request.json();
        let cutoffMs;

        if (body.after_ts) {
          // Raw unix ms timestamp
          cutoffMs = Number(body.after_ts);
        } else if (body.after_ist) {
          // Parse IST time string like "2026-07-24 20:00:00"
          // IST = UTC+5:30, so subtract 5.5 hours to get UTC ms
          const parsed = new Date(body.after_ist.replace(' ', 'T') + '+05:30');
          cutoffMs = parsed.getTime();
        } else {
          return jsonResponse({ status: 'error', message: 'Provide after_ts (unix ms) or after_ist (YYYY-MM-DD HH:MM:SS)' }, 400, request, env);
        }

        if (isNaN(cutoffMs)) {
          return jsonResponse({ status: 'error', message: 'Invalid timestamp' }, 400, request, env);
        }

        const solvedMap = await readSolvedCourses(env);
        const removed = [];
        const kept = [];

        for (const [id, val] of Object.entries(solvedMap)) {
          if ((val.ts || 0) > cutoffMs) {
            removed.push({ id, ts: val.ts, solved_at_ist: new Date((val.ts || 0) + 5.5 * 3600 * 1000).toISOString().replace('T', ' ').substring(0, 19) + ' IST' });
          } else {
            kept[id] = val;
          }
        }

        // Write back only the kept solves
        await env.COURSE_DATA.put(SOLVED_COURSES_KEY, JSON.stringify(kept));

        return jsonResponse({
          status: 'success',
          cutoff_utc: new Date(cutoffMs).toISOString(),
          cutoff_ist: new Date(cutoffMs + 5.5 * 3600 * 1000).toISOString().replace('T', ' ').substring(0, 19) + ' IST',
          removed_count: removed.length,
          remaining_count: Object.keys(kept).length,
          removed_courses: removed,
        }, 200, request, env);
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'Unsolve failed: ' + e.message }, 500, request, env);
      }
    }

    // Default: 404
    return jsonResponse({
      status: 'error',
      message: 'Not found. Available endpoints: /api/data.json, /api/courses.json, /api/solves.json',
    }, 404, request, env);
  },
};

