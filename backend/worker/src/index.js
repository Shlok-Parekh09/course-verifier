/**
 * Course Verifier API — Cloudflare Worker
 *
 * Architecture (KV-read-efficient, scales to millions of users):
 *
 * ┌─────────────────────────────────────────────────────────────────────┐
 * │  ALL solves are stored in ONE single KV key: "solved_courses.json"  │
 * │  This is a JSON object: { [courseId]: { update, ts } }              │
 * │                                                                     │
 * │  Reading solves  = 1 KV get() ... but CACHED for 60s at CDN edge.  │
 * │  So real KV reads ≈ 1 per 60 seconds globally, not 1 per request.  │
 * │  Writing a solve = 1 KV get() + 1 KV put() + cache purge.          │
 * └─────────────────────────────────────────────────────────────────────┘
 */

const CORS_HEADERS = {
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
  'Access-Control-Max-Age': '86400',
};

const SOLVED_COURSES_KEY = 'solved_courses.json';

// Cache TTL in seconds. GET endpoints are cached at the Cloudflare edge.
// This means even with 10,000 users polling every 10s, only 1 KV read
// happens per 60 seconds instead of 10,000.
const CACHE_TTL = 60;

function corsHeaders(request, env) {
  const origin = request.headers.get('Origin') || '*';
  const allowed = (env.ALLOWED_ORIGINS || '*').split(',').map(s => s.trim());
  const allowOrigin = allowed.includes(origin) || allowed.includes('*') ? origin : allowed[0];
  return { ...CORS_HEADERS, 'Access-Control-Allow-Origin': allowOrigin };
}

function jsonResponse(data, status, request, env, ttl = 0) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json',
      ...corsHeaders(request, env),
      'Cache-Control': ttl > 0 ? `public, max-age=${ttl}, s-maxage=${ttl}` : 'no-store',
    },
  });
}

/**
 * Try to serve from Cloudflare's edge cache first.
 * Returns the cached Response, or null if not cached.
 */
async function fromCache(request) {
  try {
    const cache = caches.default;
    const cached = await cache.match(request);
    return cached || null;
  } catch (e) {
    return null;
  }
}

/**
 * Save a response to Cloudflare's edge cache.
 * The response must have a Cache-Control header with max-age set.
 */
async function putCache(request, response) {
  try {
    const cache = caches.default;
    // Clone before putting — the response body can only be consumed once
    await cache.put(request, response.clone());
  } catch (e) {}
}

/**
 * Reads the single aggregated solved courses object from KV.
 * Returns a plain object: { [courseId]: { update, ts } }
 * Exactly 1 KV read. Zero loops.
 */
async function readSolvedCourses(env) {
  try {
    const data = await env.COURSE_DATA.get(SOLVED_COURSES_KEY, { type: 'json' });
    if (!data || typeof data !== 'object' || Array.isArray(data)) return {};
    return data;
  } catch (e) {
    return {};
  }
}

/**
 * Converts the aggregated object to the legacy `pending_solves` array
 * format for backward compatibility with the frontend.
 * Skips any entries where val is null/undefined (legacy corruption guard).
 */
function toSolvesList(solvedMap) {
  return Object.entries(solvedMap)
    .filter(([, val]) => val != null)
    .map(([id, val]) => ({
      id,
      update: val.update,
      ts: val.ts || 0,
      by: val.by || 'unknown'
    }))
    .sort((a, b) => b.ts - a.ts);
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
      // Try edge cache first
      const hit = await fromCache(request);
      if (hit) return hit;

      try {
        const cached = await env.COURSE_DATA.get('data.json', { type: 'json' });
        if (cached) {
          const resp = jsonResponse(cached, 200, request, env, CACHE_TTL);
          await putCache(request, resp);
          return resp;
        }
        return jsonResponse({ status: 'error', message: 'No data available yet.' }, 404, request, env);
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'KV read error: ' + e.message }, 500, request, env);
      }
    }

    // ─── Route: /api/courses.json ───────────────────────────────────────────
    // Exactly 2 KV reads total, but cached at CDN edge for CACHE_TTL seconds.
    // Means KV is only read once per CACHE_TTL seconds regardless of user count.
    if (path === '/api/courses.json' || path === '/api/courses') {
      const hit = await fromCache(request);
      if (hit) return hit;

      try {
        const [cached, solvedMap] = await Promise.all([
          env.COURSE_DATA.get('courses.json', { type: 'json' }),
          readSolvedCourses(env),
        ]);

        if (!cached) {
          return jsonResponse({ status: 'error', message: 'No course data available yet.' }, 404, request, env);
        }

        const pending = toSolvesList(solvedMap);

        let body;
        if (Array.isArray(cached)) {
          body = { documents: cached, pending_solves: pending };
        } else {
          cached.pending_solves = pending;
          body = cached;
        }

        const resp = jsonResponse(body, 200, request, env, CACHE_TTL);
        await putCache(request, resp);
        return resp;
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'KV read error: ' + e.message }, 500, request, env);
      }
    }

    // ─── Route: /api/solves.json ────────────────────────────────────────────
    // Frontend polls this every 30s. Cached at CDN edge for CACHE_TTL seconds.
    // Real KV reads = 1 per 60 seconds GLOBALLY, regardless of how many users poll.
    if (path === '/api/solves.json' || path === '/api/solves') {
      const hit = await fromCache(request);
      if (hit) return hit;

      try {
        const solvedMap = await readSolvedCourses(env);
        const pending = toSolvesList(solvedMap);
        const resp = jsonResponse({ pending_solves: pending }, 200, request, env, CACHE_TTL);
        await putCache(request, resp);
        return resp;
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'KV read error: ' + e.message }, 500, request, env);
      }
    }

    // ─── Route: /api/analytics.json ────────────────────────────────────────
    if (path === '/api/analytics.json' || path === '/api/analytics') {
      const hit = await fromCache(request);
      if (hit) return hit;

      try {
        const cached = await env.COURSE_DATA.get('analytics.json', { type: 'json' });
        if (cached) {
          const resp = jsonResponse(cached, 200, request, env, CACHE_TTL);
          await putCache(request, resp);
          return resp;
        }
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

    // ─── Route: /api/cleanup_solve_keys ─────────────────────────────────────
    if (path === '/api/cleanup_solve_keys' && request.method === 'POST') {
      const auth = request.headers.get('Authorization');
      if (auth !== `Bearer ${env.KV_PUSH_KEY}`) {
        return jsonResponse({ status: 'error', message: 'Unauthorized' }, 401, request, env);
      }
      try {
        const list = await env.COURSE_DATA.list({ prefix: 'solve_' });
        let deleted = 0;
        if (list && list.keys && list.keys.length > 0) {
          for (const key of list.keys) {
            await env.COURSE_DATA.delete(key.name);
            deleted++;
          }
        }
        return jsonResponse({ status: 'success', message: `Deleted ${deleted} solve_ keys` }, 200, request, env);
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'Failed to delete: ' + e.message }, 500, request, env);
      }
    }


    // ─── Route: /api/solve_course ───────────────────────────────────────────
    // Write path: read-modify-write on a single KV key.
    // Now supports batching to drastically reduce KV writes and request counts.
    if (path === '/api/solve_course' && request.method === 'POST') {
      try {
        const body = await request.json();
        const solvesToProcess = body.solves ? body.solves : (body.id ? [body] : []);
        
        if (solvesToProcess.length === 0) {
          return jsonResponse({ status: 'error', message: 'No solves provided' }, 400, request, env);
        }

        const solvedMap = await readSolvedCourses(env);
        const now = Date.now();
        
        for (const solve of solvesToProcess) {
          if (solve.id) {
            solvedMap[String(solve.id)] = {
              update: solve.update,
              ts: now,
              by: solve.by || 'unknown'
            };
          }
        }
        
        await env.COURSE_DATA.put(SOLVED_COURSES_KEY, JSON.stringify(solvedMap));

        return jsonResponse({ status: 'success', message: `Recorded ${solvesToProcess.length} solves` }, 200, request, env);
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'Failed to record solve: ' + e.message }, 500, request, env);
      }
    }

    // ─── Route: /api/solve-audit (admin) ───────────────────────────────────
    if (path === '/api/solve-audit') {
      const auth = request.headers.get('Authorization');
      if (auth !== `Bearer ${env.KV_PUSH_KEY}`) {
        return jsonResponse({ status: 'error', message: 'Unauthorized' }, 401, request, env);
      }
      try {
        const solvedMap = await readSolvedCourses(env);
        const entries = Object.entries(solvedMap)
          .filter(([, val]) => val != null)
          .map(([id, val]) => {
            const tsMs = val.ts || 0;
            return {
              id,
              ts: tsMs,
              by: val.by || 'unknown',
              solved_at_utc: new Date(tsMs).toISOString(),
              solved_at_ist: new Date(tsMs + 5.5 * 3600 * 1000).toISOString().replace('T', ' ').substring(0, 19) + ' IST',
            };
          })
          .sort((a, b) => b.ts - a.ts);

        return jsonResponse({ total: entries.length, solves: entries }, 200, request, env);
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'Audit failed: ' + e.message }, 500, request, env);
      }
    }

    // ─── Route: /api/unsolve-after (admin) ─────────────────────────────────
    // Body: { "after_ist": "YYYY-MM-DD HH:MM:SS" } OR { "after_ts": <unix ms> } OR { "remove_ids": [123, 456] }
    if (path === '/api/unsolve-after' && request.method === 'POST') {
      const auth = request.headers.get('Authorization');
      if (auth !== `Bearer ${env.KV_PUSH_KEY}`) {
        return jsonResponse({ status: 'error', message: 'Unauthorized' }, 401, request, env);
      }
      try {
        const body = await request.json();
        const solvedMap = await readSolvedCourses(env);
        const removed = [];
        const kept = {};
        
        // Mode 1: Remove specific IDs
        if (body.remove_ids && Array.isArray(body.remove_ids)) {
          const idsToRemove = new Set(body.remove_ids.map(id => String(id)));
          for (const [id, val] of Object.entries(solvedMap)) {
            if (val == null) continue;
            if (idsToRemove.has(id)) {
              removed.push({ id, ts: val.ts });
            } else {
              kept[id] = val;
            }
          }
          await env.COURSE_DATA.put(SOLVED_COURSES_KEY, JSON.stringify(kept));
          return jsonResponse({
            status: 'success',
            removed_count: removed.length,
            remaining_count: Object.keys(kept).length,
            removed_courses: removed,
          }, 200, request, env);
        }

        // Mode 2: Remove by timestamp
        let cutoffMs;

        if (body.after_ts) {
          cutoffMs = Number(body.after_ts);
        } else if (body.after_ist) {
          cutoffMs = new Date(body.after_ist.replace(' ', 'T') + '+05:30').getTime();
        } else {
          return jsonResponse({ status: 'error', message: 'Provide after_ts (unix ms) or after_ist (YYYY-MM-DD HH:MM:SS)' }, 400, request, env);
        }

        if (isNaN(cutoffMs)) {
          return jsonResponse({ status: 'error', message: 'Invalid timestamp' }, 400, request, env);
        }

        for (const [id, val] of Object.entries(solvedMap)) {
          // Guard: skip null/undefined entries from legacy migration
          if (val == null) continue;
          if ((val.ts || 0) > cutoffMs) {
            removed.push({
              id,
              ts: val.ts,
              solved_at_ist: new Date((val.ts || 0) + 5.5 * 3600 * 1000).toISOString().replace('T', ' ').substring(0, 19) + ' IST',
            });
          } else {
            kept[id] = val;
          }
        }

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

    // ─── Route: /api/migrate-solves (admin) ────────────────────────────────
    if (path === '/api/migrate-solves' && request.method === 'POST') {
      const auth = request.headers.get('Authorization');
      if (auth !== `Bearer ${env.KV_PUSH_KEY}`) {
        return jsonResponse({ status: 'error', message: 'Unauthorized' }, 401, request, env);
      }
      try {
        const solvedMap = await readSolvedCourses(env);
        let migrated = 0;

        try {
          const legacy = await env.COURSE_DATA.get('pending_solves.json', { type: 'json' });
          if (legacy && Array.isArray(legacy)) {
            for (const item of legacy) {
              if (item && item.id && !solvedMap[String(item.id)]) {
                solvedMap[String(item.id)] = { update: item.update, ts: item.ts || 0 };
                migrated++;
              }
            }
          }
        } catch (e) {}

        try {
          const list = await env.COURSE_DATA.list({ prefix: 'solve_' });
          if (list && list.keys && list.keys.length > 0) {
            for (const key of list.keys) {
              const id = key.name.split('_')[1];
              if (!id || solvedMap[id]) continue;
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
        } catch (e) {}

        await env.COURSE_DATA.put(SOLVED_COURSES_KEY, JSON.stringify(solvedMap));

        return jsonResponse({
          status: 'success',
          message: `Migration complete. Migrated ${migrated} new entries. Total: ${Object.keys(solvedMap).length}.`,
        }, 200, request, env);
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'Migration failed: ' + e.message }, 500, request, env);
      }
    }


    // ─── Route: /api/update_domain (admin) ─────────────────────────────────
    // Patches the domain field for specific course IDs in courses.json KV.
    // Body: { "domain_updates": [ { "id": 337, "domain": "Master's Degree" }, ... ] }
    if (path === '/api/update_domain' && request.method === 'POST') {
      const auth = request.headers.get('Authorization');
      if (auth !== `Bearer ${env.KV_PUSH_KEY}`) {
        return jsonResponse({ status: 'error', message: 'Unauthorized' }, 401, request, env);
      }
      try {
        const body = await request.json();
        const updates = body.domain_updates;
        if (!Array.isArray(updates) || updates.length === 0) {
          return jsonResponse({ status: 'error', message: 'Provide domain_updates array' }, 400, request, env);
        }

        // Build a fast lookup: id -> new domain
        const domainMap = {};
        for (const u of updates) {
          if (u.id != null && u.domain) domainMap[String(u.id)] = u.domain;
        }

        // Read existing courses.json from KV
        const courses = await env.COURSE_DATA.get('courses.json', { type: 'json' });
        if (!courses || !Array.isArray(courses)) {
          return jsonResponse({ status: 'error', message: 'courses.json not found or not an array in KV' }, 404, request, env);
        }

        let patched = 0;
        for (const c of courses) {
          const idStr = String(c.id ?? '');
          if (domainMap[idStr] !== undefined && c.domain !== domainMap[idStr]) {
            c.domain = domainMap[idStr];
            patched++;
          }
        }

        await env.COURSE_DATA.put('courses.json', JSON.stringify(courses));

        // Purge edge cache for courses.json endpoint
        try {
          const cache = caches.default;
          const cacheUrl = new URL('/api/courses.json', request.url);
          await cache.delete(new Request(cacheUrl.toString()));
        } catch (e) {}

        return jsonResponse({
          status: 'success',
          message: `Patched domain for ${patched} of ${updates.length} requested courses`,
          patched,
        }, 200, request, env);
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'Domain update failed: ' + e.message }, 500, request, env);
      }
    }

    // Default: 404

    return jsonResponse({
      status: 'error',
      message: 'Not found.',
    }, 404, request, env);
  },
};
