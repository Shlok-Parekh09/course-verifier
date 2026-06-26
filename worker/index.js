/**
 * Cloudflare Worker - Course Verifier API
 * Connects to MongoDB Atlas via the Data API (HTTP REST).
 *
 * Environment Variables (set in Cloudflare Dashboard):
 *   MONGO_DATA_API_KEY  - Your MongoDB Atlas Data API key
 *   MONGO_APP_ID        - Your MongoDB Atlas App ID (e.g. "data-abcde")
 */

const MONGO_BASE = (APP_ID) => `https://data.mongodb-api.com/app/${APP_ID}/endpoint/data/v1`;
const DB   = 'course_verifier';
const COLL = 'courses';

async function mongoRequest(env, action, body) {
    const url = `${MONGO_BASE(env.MONGO_APP_ID)}/action/${action}`;
    const res = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'api-key': env.MONGO_DATA_API_KEY,
        },
        body: JSON.stringify({
            dataSource: 'Cluster0',
            database: DB,
            collection: COLL,
            ...body,
        }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'MongoDB error');
    return data;
}

function corsHeaders() {
    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json',
    };
}

function json(body, status = 200) {
    return new Response(JSON.stringify(body), { status, headers: corsHeaders() });
}

export default {
    async fetch(request, env, ctx) {
        const url = new URL(request.url);
        const path = url.pathname;

        if (request.method === 'OPTIONS') {
            return new Response(null, { headers: corsHeaders() });
        }

        try {
            // Serve the cached courses list from KV (incredibly fast)
            if (path === '/api/get_courses' && request.method === 'GET') {
                const cachedData = await env.COURSE_CACHE.get('courses.json');
                if (cachedData) {
                    const parsed = JSON.parse(cachedData);
                    const pendingStr = await env.COURSE_CACHE.get('pending_solves.json');
                    let pending = [];
                    if (pendingStr) {
                        try { pending = JSON.parse(pendingStr); } catch (e) { }
                    }
                    // The dashboard pushes {"status": "success", "courses": [...]}
                    // We must return { documents: [...], pending_solves: [...] } for the frontend
                    return json({ documents: parsed.courses || [], pending_solves: pending });
                } else {
                    // Fallback to MongoDB if KV is empty, and automatically cache it
                    const data = await mongoRequest(env, 'find', {
                        projection: {
                            _id: 0, id: 1, name: 1, university: 1, country: 1,
                            status: 1, issue_category: 1, issue_sub_type: 1,
                            disc_reason: 1, has_qs_badge: 1, has_nirf_badge: 1, skills: 1, domain: 1,
                        },
                        sort: { id: 1 },
                        limit: 5000,
                    });
                    
                    // Cache the fresh data in KV for 1 hour (3600 seconds)
                    const payloadToCache = JSON.stringify({ status: "success", courses: data.documents });
                    ctx.waitUntil(env.COURSE_CACHE.put('courses.json', payloadToCache, { expirationTtl: 3600 }));
                    
                    return json({ documents: data.documents });
                }
            }

            // KV push endpoint used by dashboard.py to sync data from Mongo
            if (path === '/api/kv-push' && request.method === 'POST') {
                const auth = request.headers.get('Authorization') || '';
                const expectedKey = env.CF_KV_PUSH_KEY || 'courseverify_secure_push_key_2026';
                if (auth !== `Bearer ${expectedKey}`) {
                    return json({ error: 'Unauthorized' }, 401);
                }
                const endpoint = request.headers.get('X-Endpoint') || 'courses.json';
                const bodyText = await request.text();
                // Store in KV
                await env.COURSE_CACHE.put(endpoint, bodyText);
                return json({ status: 'success', message: `Saved ${endpoint} to KV cache` });
            }

            // Detailed course view (deprecated, handled by frontend now)
            if (path === '/api/get_course_details' && request.method === 'GET') {
                return json({ error: 'Endpoint deprecated. Details are returned by /api/get_courses' }, 410);
            }

            // Sync solves queue directly to MongoDB (from local python dashboard)
            if (path === '/api/pending_solves' && request.method === 'GET') {
                const pendingStr = await env.COURSE_CACHE.get('pending_solves.json');
                return new Response(`{"status":"success","pending_solves":${pendingStr || '[]'}}`, {
                    headers: { ...corsHeaders, 'Content-Type': 'application/json' }
                });
            }

            // Clear pending solves after successful MongoDB sync
            if (path === '/api/clear_pending_solves' && request.method === 'POST') {
                await env.COURSE_CACHE.put('pending_solves.json', '[]');
                return json({ status: 'success', message: 'Cleared pending solves queue' });
            }

            // Updates append to KV pending_solves queue (bypassing MongoDB Data API)
            if (path === '/api/solve_course' && request.method === 'POST') {
                const body = await request.json();
                const courseId = body.id;
                const update   = body.update || {};
                
                // Get existing pending solves
                const pendingStr = await env.COURSE_CACHE.get('pending_solves.json');
                let pending = [];
                if (pendingStr) {
                    try { pending = JSON.parse(pendingStr); } catch (e) { }
                }

                // Add to queue
                pending.push({
                    id: courseId,
                    update: update,
                    timestamp: Date.now()
                });

                // Write back to KV
                await env.COURSE_CACHE.put('pending_solves.json', JSON.stringify(pending));

                return json({ status: 'success', message: 'Buffered to Cloudflare KV queue' });
            }

            // Fallback for unknown routes
            return json({ error: 'Not found' }, 404);
        } catch (err) {
            return json({ error: err.message }, 500);
        }
    },
};
