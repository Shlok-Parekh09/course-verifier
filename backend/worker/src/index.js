/**
 * Course Verifier API — Cloudflare Worker
 * 
 * Serves pre-computed /api/data.json and /api/courses.json from KV store.
 * The local dashboard pushes updated payloads to KV after each upload,
 * so the public website always has instant access to the latest data.
 */

const CORS_HEADERS = {
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Max-Age': '86400',
};

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
      // Allow caching for 10 seconds at the edge, but revalidate after
      'Cache-Control': 'public, max-age=10, s-maxage=10',
    },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders(request, env) });
    }

    // Route: /api/data.json or /api/data
    if (path === '/api/data.json' || path === '/api/data') {
      try {
        const cached = await env.COURSE_DATA.get('data.json', { type: 'json' });
        if (cached) {
          return jsonResponse(cached, 200, request, env);
        }
        return jsonResponse({ status: 'error', message: 'No data available yet. Upload a PDF from the local dashboard first.' }, 404, request, env);
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'KV read error: ' + e.message }, 500, request, env);
      }
    }

    // Route: /api/courses.json or /api/courses
    if (path === '/api/courses.json' || path === '/api/courses') {
      try {
        const cached = await env.COURSE_DATA.get('courses.json', { type: 'json' });
        if (cached) {
          // Fetch individual pending solves to prevent race conditions
          let pending = [];
          const list = await env.COURSE_DATA.list({ prefix: 'solve_' });
          
          if (list && list.keys && list.keys.length > 0) {
            const fetchPromises = list.keys.map(async key => {
              try {
                const update = await env.COURSE_DATA.get(key.name, { type: 'json' });
                const id = key.name.split('_')[1];
                if (update) pending.push({ id, update });
              } catch (e) {
                // ignore individual key read error
              }
            });
            await Promise.all(fetchPromises);
          }

          // Merge legacy pending solves to restore previously solved data
          try {
            const legacy = await env.COURSE_DATA.get('pending_solves.json', { type: 'json' });
            if (legacy && Array.isArray(legacy)) {
              for (const item of legacy) {
                if (!pending.find(p => p.id == item.id)) {
                  pending.push({ id: item.id, update: item.update });
                }
              }
            }
          } catch(e) {}

          if (Array.isArray(cached)) {
            return jsonResponse({ documents: cached, pending_solves: pending }, 200, request, env);
          } else {
            cached.pending_solves = pending;
            return jsonResponse(cached, 200, request, env);
          }
        }
        return jsonResponse({ status: 'error', message: 'No course data available yet.' }, 404, request, env);
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'KV read error: ' + e.message }, 500, request, env);
      }
    }

    
    // Route: /api/solves.json
    if (path === '/api/solves.json' || path === '/api/solves') {
      try {
        let pending = [];
        const list = await env.COURSE_DATA.list({ prefix: 'solve_' });
        
        if (list && list.keys && list.keys.length > 0) {
          const fetchPromises = list.keys.map(async key => {
            try {
              const val = await env.COURSE_DATA.get(key.name, { type: 'json' });
              const id = key.name.split('_')[1];
              if (val) {
                if (Array.isArray(val)) pending.push({ id, update: val, ts: 0 });
                else pending.push({ id, update: val.update, ts: val.ts || 0 });
              }
            } catch (e) {}
          });
          await Promise.all(fetchPromises);
        }

        try {
          const legacy = await env.COURSE_DATA.get('pending_solves.json', { type: 'json' });
          if (legacy && Array.isArray(legacy)) {
            for (const item of legacy) {
              if (!pending.find(p => p.id == item.id)) {
                pending.push({ id: item.id, update: item.update, ts: 0 });
              }
            }
          }
        } catch(e) {}
        
        pending.sort((a, b) => b.ts - a.ts);

        return jsonResponse({ pending_solves: pending }, 200, request, env);
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'KV read error: ' + e.message }, 500, request, env);
      }
    }

    // Route: /api/analytics.json
    if (path === '/api/analytics.json' || path === '/api/analytics') {
      try {
        const cached = await env.COURSE_DATA.get('analytics.json', { type: 'json' });
        if (cached) {
          return jsonResponse(cached, 200, request, env);
        }
        return jsonResponse({ status: 'error', message: 'No analytics data available.' }, 404, request, env);
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'KV read error: ' + e.message }, 500, request, env);
      }
    }

    // Route: /api/kv-push
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
        
        // Read raw text to avoid CPU limits on massive JSON parsing
        const rawBody = await request.text();
        await env.COURSE_DATA.put(endpoint, rawBody);
        
        return jsonResponse({ status: 'success', message: `Pushed ${endpoint} to KV` }, 200, request, env);
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'Failed to push: ' + e.message }, 500, request, env);
      }
    }

    // Route: /api/solve_course
    if (path === '/api/solve_course' && request.method === 'POST') {
      try {
        const body = await request.json();
        // Use individual keys to prevent read-modify-write race conditions
        const payload = {
          update: body.update,
          ts: Date.now()
        };
        await env.COURSE_DATA.put(`solve_${body.id}`, JSON.stringify(payload));
        return jsonResponse({ status: 'success', message: 'Solve recorded' }, 200, request, env);
      } catch (e) {
        return jsonResponse({ status: 'error', message: 'Failed to record solve: ' + e.message }, 500, request, env);
      }
    }

    // Default: 404
    return jsonResponse({
      status: 'error',
      message: 'Not found. Available endpoints: /api/data.json, /api/courses.json',
    }, 404, request, env);
  },
};
