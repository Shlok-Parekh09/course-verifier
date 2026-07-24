var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// src/index.js
var CORS_HEADERS = {
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
  "Access-Control-Max-Age": "86400"
};
var SOLVED_COURSES_KEY = "solved_courses.json";
var CACHE_TTL = 60;
function corsHeaders(request, env) {
  const origin = request.headers.get("Origin") || "*";
  const allowed = (env.ALLOWED_ORIGINS || "*").split(",").map((s) => s.trim());
  const allowOrigin = allowed.includes(origin) || allowed.includes("*") ? origin : allowed[0];
  return { ...CORS_HEADERS, "Access-Control-Allow-Origin": allowOrigin };
}
__name(corsHeaders, "corsHeaders");
function jsonResponse(data, status, request, env, ttl = 0) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
      ...corsHeaders(request, env),
      "Cache-Control": ttl > 0 ? `public, max-age=${ttl}, s-maxage=${ttl}` : "no-store"
    }
  });
}
__name(jsonResponse, "jsonResponse");
async function fromCache(request) {
  try {
    const cache = caches.default;
    const cached = await cache.match(request);
    return cached || null;
  } catch (e) {
    return null;
  }
}
__name(fromCache, "fromCache");
async function putCache(request, response) {
  try {
    const cache = caches.default;
    await cache.put(request, response.clone());
  } catch (e) {
  }
}
__name(putCache, "putCache");
async function readSolvedCourses(env) {
  try {
    const data = await env.COURSE_DATA.get(SOLVED_COURSES_KEY, { type: "json" });
    if (!data || typeof data !== "object" || Array.isArray(data)) return {};
    return data;
  } catch (e) {
    return {};
  }
}
__name(readSolvedCourses, "readSolvedCourses");
function toSolvesList(solvedMap) {
  return Object.entries(solvedMap).filter(([, val]) => val != null).map(([id, val]) => ({
    id,
    update: val.update,
    ts: val.ts || 0
  })).sort((a, b) => b.ts - a.ts);
}
__name(toSolvesList, "toSolvesList");
var index_default = {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(request, env) });
    }
    if (path === "/api/data.json" || path === "/api/data") {
      const hit = await fromCache(request);
      if (hit) return hit;
      try {
        const cached = await env.COURSE_DATA.get("data.json", { type: "json" });
        if (cached) {
          const resp = jsonResponse(cached, 200, request, env, CACHE_TTL);
          await putCache(request, resp);
          return resp;
        }
        return jsonResponse({ status: "error", message: "No data available yet." }, 404, request, env);
      } catch (e) {
        return jsonResponse({ status: "error", message: "KV read error: " + e.message }, 500, request, env);
      }
    }
    if (path === "/api/courses.json" || path === "/api/courses") {
      const hit = await fromCache(request);
      if (hit) return hit;
      try {
        const [cached, solvedMap] = await Promise.all([
          env.COURSE_DATA.get("courses.json", { type: "json" }),
          readSolvedCourses(env)
        ]);
        if (!cached) {
          return jsonResponse({ status: "error", message: "No course data available yet." }, 404, request, env);
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
        return jsonResponse({ status: "error", message: "KV read error: " + e.message }, 500, request, env);
      }
    }
    if (path === "/api/solves.json" || path === "/api/solves") {
      const hit = await fromCache(request);
      if (hit) return hit;
      try {
        const solvedMap = await readSolvedCourses(env);
        const pending = toSolvesList(solvedMap);
        const resp = jsonResponse({ pending_solves: pending }, 200, request, env, CACHE_TTL);
        await putCache(request, resp);
        return resp;
      } catch (e) {
        return jsonResponse({ status: "error", message: "KV read error: " + e.message }, 500, request, env);
      }
    }
    if (path === "/api/analytics.json" || path === "/api/analytics") {
      const hit = await fromCache(request);
      if (hit) return hit;
      try {
        const cached = await env.COURSE_DATA.get("analytics.json", { type: "json" });
        if (cached) {
          const resp = jsonResponse(cached, 200, request, env, CACHE_TTL);
          await putCache(request, resp);
          return resp;
        }
        return jsonResponse({ status: "error", message: "No analytics data available." }, 404, request, env);
      } catch (e) {
        return jsonResponse({ status: "error", message: "KV read error: " + e.message }, 500, request, env);
      }
    }
    if (path === "/api/kv-push" && request.method === "POST") {
      const auth = request.headers.get("Authorization");
      if (auth !== `Bearer ${env.KV_PUSH_KEY}`) {
        return jsonResponse({ status: "error", message: "Unauthorized" }, 401, request, env);
      }
      try {
        const endpoint = request.headers.get("X-Endpoint");
        if (!endpoint) {
          return jsonResponse({ status: "error", message: "Missing X-Endpoint header" }, 400, request, env);
        }
        const rawBody = await request.text();
        await env.COURSE_DATA.put(endpoint, rawBody);
        return jsonResponse({ status: "success", message: `Pushed ${endpoint} to KV` }, 200, request, env);
      } catch (e) {
        return jsonResponse({ status: "error", message: "Failed to push: " + e.message }, 500, request, env);
      }
    }
    if (path === "/api/solve_course" && request.method === "POST") {
      try {
        const body = await request.json();
        if (!body.id) {
          return jsonResponse({ status: "error", message: "Missing course id" }, 400, request, env);
        }
        const solvedMap = await readSolvedCourses(env);
        solvedMap[String(body.id)] = {
          update: body.update,
          ts: Date.now()
        };
        await env.COURSE_DATA.put(SOLVED_COURSES_KEY, JSON.stringify(solvedMap));
        return jsonResponse({ status: "success", message: "Solve recorded" }, 200, request, env);
      } catch (e) {
        return jsonResponse({ status: "error", message: "Failed to record solve: " + e.message }, 500, request, env);
      }
    }
    if (path === "/api/solve-audit") {
      const auth = request.headers.get("Authorization");
      if (auth !== `Bearer ${env.KV_PUSH_KEY}`) {
        return jsonResponse({ status: "error", message: "Unauthorized" }, 401, request, env);
      }
      try {
        const solvedMap = await readSolvedCourses(env);
        const entries = Object.entries(solvedMap).filter(([, val]) => val != null).map(([id, val]) => {
          const tsMs = val.ts || 0;
          return {
            id,
            ts: tsMs,
            solved_at_utc: new Date(tsMs).toISOString(),
            solved_at_ist: new Date(tsMs + 5.5 * 3600 * 1e3).toISOString().replace("T", " ").substring(0, 19) + " IST"
          };
        }).sort((a, b) => b.ts - a.ts);
        return jsonResponse({ total: entries.length, solves: entries }, 200, request, env);
      } catch (e) {
        return jsonResponse({ status: "error", message: "Audit failed: " + e.message }, 500, request, env);
      }
    }
    if (path === "/api/unsolve-after" && request.method === "POST") {
      const auth = request.headers.get("Authorization");
      if (auth !== `Bearer ${env.KV_PUSH_KEY}`) {
        return jsonResponse({ status: "error", message: "Unauthorized" }, 401, request, env);
      }
      try {
        const body = await request.json();
        const solvedMap = await readSolvedCourses(env);
        const removed = [];
        const kept = {};
        if (body.remove_ids && Array.isArray(body.remove_ids)) {
          const idsToRemove = new Set(body.remove_ids.map((id) => String(id)));
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
            status: "success",
            removed_count: removed.length,
            remaining_count: Object.keys(kept).length,
            removed_courses: removed
          }, 200, request, env);
        }
        let cutoffMs;
        if (body.after_ts) {
          cutoffMs = Number(body.after_ts);
        } else if (body.after_ist) {
          cutoffMs = (/* @__PURE__ */ new Date(body.after_ist.replace(" ", "T") + "+05:30")).getTime();
        } else {
          return jsonResponse({ status: "error", message: "Provide after_ts (unix ms) or after_ist (YYYY-MM-DD HH:MM:SS)" }, 400, request, env);
        }
        if (isNaN(cutoffMs)) {
          return jsonResponse({ status: "error", message: "Invalid timestamp" }, 400, request, env);
        }
        for (const [id, val] of Object.entries(solvedMap)) {
          if (val == null) continue;
          if ((val.ts || 0) > cutoffMs) {
            removed.push({
              id,
              ts: val.ts,
              solved_at_ist: new Date((val.ts || 0) + 5.5 * 3600 * 1e3).toISOString().replace("T", " ").substring(0, 19) + " IST"
            });
          } else {
            kept[id] = val;
          }
        }
        await env.COURSE_DATA.put(SOLVED_COURSES_KEY, JSON.stringify(kept));
        return jsonResponse({
          status: "success",
          cutoff_utc: new Date(cutoffMs).toISOString(),
          cutoff_ist: new Date(cutoffMs + 5.5 * 3600 * 1e3).toISOString().replace("T", " ").substring(0, 19) + " IST",
          removed_count: removed.length,
          remaining_count: Object.keys(kept).length,
          removed_courses: removed
        }, 200, request, env);
      } catch (e) {
        return jsonResponse({ status: "error", message: "Unsolve failed: " + e.message }, 500, request, env);
      }
    }
    if (path === "/api/migrate-solves" && request.method === "POST") {
      const auth = request.headers.get("Authorization");
      if (auth !== `Bearer ${env.KV_PUSH_KEY}`) {
        return jsonResponse({ status: "error", message: "Unauthorized" }, 401, request, env);
      }
      try {
        const solvedMap = await readSolvedCourses(env);
        let migrated = 0;
        try {
          const legacy = await env.COURSE_DATA.get("pending_solves.json", { type: "json" });
          if (legacy && Array.isArray(legacy)) {
            for (const item of legacy) {
              if (item && item.id && !solvedMap[String(item.id)]) {
                solvedMap[String(item.id)] = { update: item.update, ts: item.ts || 0 };
                migrated++;
              }
            }
          }
        } catch (e) {
        }
        try {
          const list = await env.COURSE_DATA.list({ prefix: "solve_" });
          if (list && list.keys && list.keys.length > 0) {
            for (const key of list.keys) {
              const id = key.name.split("_")[1];
              if (!id || solvedMap[id]) continue;
              try {
                const val = key.metadata || await env.COURSE_DATA.get(key.name, { type: "json" });
                if (val) {
                  solvedMap[id] = {
                    update: Array.isArray(val) ? val : val.update || val,
                    ts: val.ts || 0
                  };
                  migrated++;
                }
              } catch (e) {
              }
            }
          }
        } catch (e) {
        }
        await env.COURSE_DATA.put(SOLVED_COURSES_KEY, JSON.stringify(solvedMap));
        return jsonResponse({
          status: "success",
          message: `Migration complete. Migrated ${migrated} new entries. Total: ${Object.keys(solvedMap).length}.`
        }, 200, request, env);
      } catch (e) {
        return jsonResponse({ status: "error", message: "Migration failed: " + e.message }, 500, request, env);
      }
    }
    return jsonResponse({
      status: "error",
      message: "Not found."
    }, 404, request, env);
  }
};
export {
  index_default as default
};
//# sourceMappingURL=index.js.map
