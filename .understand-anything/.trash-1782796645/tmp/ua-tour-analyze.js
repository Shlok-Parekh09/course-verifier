#!/usr/bin/env node
'use strict';

const fs = require('fs');

function main() {
  const inPath = process.argv[2];
  const outPath = process.argv[3];
  if (!inPath || !outPath) {
    console.error('Usage: node ua-tour-analyze.js <input.json> <output.json>');
    process.exit(1);
  }
  const raw = JSON.parse(fs.readFileSync(inPath, 'utf8'));
  const nodes = raw.nodes || [];
  const edges = raw.edges || [];
  const layers = raw.layers || [];

  const nodeById = new Map();
  nodes.forEach(n => nodeById.set(n.id, n));

  // Fan-in / fan-out
  const fanIn = new Map();
  const fanOut = new Map();
  nodes.forEach(n => { fanIn.set(n.id, 0); fanOut.set(n.id, 0); });
  edges.forEach(e => {
    if (fanIn.has(e.target)) fanIn.set(e.target, fanIn.get(e.target) + 1);
    if (fanOut.has(e.source)) fanOut.set(e.source, fanOut.get(e.source) + 1);
  });

  const fanInRanking = nodes
    .map(n => ({ id: n.id, fanIn: fanIn.get(n.id), name: n.name, summary: n.summary }))
    .sort((a, b) => b.fanIn - a.fanIn)
    .slice(0, 20);

  const fanOutRanking = nodes
    .map(n => ({ id: n.id, fanOut: fanOut.get(n.id), name: n.name, summary: n.summary }))
    .sort((a, b) => b.fanOut - a.fanOut)
    .slice(0, 20);

  // Entry point candidates
  const fanOutVals = nodes.map(n => fanOut.get(n.id)).sort((a, b) => b - a);
  const fanInVals = nodes.map(n => fanIn.get(n.id)).sort((a, b) => a - b);
  const top10pctFanOutThreshold = fanOutVals[Math.max(0, Math.floor(fanOutVals.length * 0.1))] || 0;
  const bottom25pctFanInThreshold = fanInVals[Math.max(0, Math.floor(fanInVals.length * 0.25))] || 0;

  const entryFilenames = ['index.ts','index.js','main.ts','main.js','app.ts','app.js','server.ts','server.js','mod.rs','main.go','main.py','main.rs','manage.py','app.py','wsgi.py','asgi.py','run.py','__main__.py','Application.java','Main.java','Program.cs','config.ru','index.php','App.swift','Application.kt','main.cpp','main.c'];

  const entryScores = nodes.map(n => {
    let score = 0;
    const isDoc = n.type === 'document';
    const depth = n.filePath ? n.filePath.split('/').length - 1 : 99;
    if (isDoc) {
      if (n.name === 'README.md' && depth === 0) score += 5;
      else if (n.filePath && n.filePath.endsWith('.md') && depth === 0) score += 2;
    } else {
      if (entryFilenames.includes(n.name)) score += 3;
      if (depth <= 1) score += 1;
      if (fanOut.get(n.id) >= top10pctFanOutThreshold && top10pctFanOutThreshold > 0) score += 1;
      if (fanIn.get(n.id) <= bottom25pctFanInThreshold) score += 1;
    }
    return { id: n.id, score, name: n.name, summary: n.summary, type: n.type };
  });
  const entryPointCandidates = entryScores
    .filter(e => e.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 5);

  // BFS from top code entry point (skip documents)
  const topCodeEntry = entryScores
    .filter(e => e.type !== 'document')
    .sort((a, b) => b.score - a.score)[0];

  const bfs = { startNode: null, order: [], depthMap: {}, byDepth: {} };
  if (topCodeEntry) {
    bfs.startNode = topCodeEntry.id;
    const adj = new Map();
    nodes.forEach(n => adj.set(n.id, []));
    edges.forEach(e => {
      if (e.type === 'imports' || e.type === 'calls') {
        if (adj.has(e.source)) adj.get(e.source).push(e.target);
      }
    });
    const visited = new Set();
    const queue = [{ id: topCodeEntry.id, depth: 0 }];
    visited.add(topCodeEntry.id);
    while (queue.length) {
      const { id, depth } = queue.shift();
      bfs.order.push(id);
      bfs.depthMap[id] = depth;
      if (!bfs.byDepth[depth]) bfs.byDepth[depth] = [];
      bfs.byDepth[depth].push(id);
      (adj.get(id) || []).forEach(next => {
        if (!visited.has(next) && nodeById.has(next)) {
          visited.add(next);
          queue.push({ id: next, depth: depth + 1 });
        }
      });
    }
  }

  // Non-code inventory
  const nonCodeFiles = { documentation: [], infrastructure: [], data: [], config: [] };
  nodes.forEach(n => {
    const entry = { id: n.id, name: n.name, type: n.type, summary: n.summary };
    if (n.type === 'document') nonCodeFiles.documentation.push(entry);
    else if (['service', 'pipeline', 'resource'].includes(n.type)) nonCodeFiles.infrastructure.push(entry);
    else if (['table', 'schema', 'endpoint'].includes(n.type)) nonCodeFiles.data.push(entry);
    else if (n.type === 'config') nonCodeFiles.config.push(entry);
  });

  // Tightly coupled clusters: bidirectional relationships
  const edgeSet = new Set(edges.map(e => `${e.source}|${e.target}`));
  const bidirPairs = [];
  edges.forEach(e => {
    const rev = `${e.target}|${e.source}`;
    if (edgeSet.has(rev) && e.source < e.target) {
      bidirPairs.push([e.source, e.target]);
    }
  });
  // Also treat "related" both ways as coupling (already bidir if both directions exist).
  // Build clusters by union-find over bidir pairs, then expand.
  const parent = new Map();
  function find(x) { if (!parent.has(x)) parent.set(x, x); while (parent.get(x) !== x) { parent.set(x, parent.get(parent.get(x))); x = parent.get(x); } return x; }
  function union(a, b) { const ra = find(a), rb = find(b); if (ra !== rb) parent.set(ra, rb); }
  bidirPairs.forEach(([a, b]) => { union(a, b); });

  // Expand: add nodes that connect (any edge) to 2+ members of a cluster
  const clusterMap = new Map();
  nodes.forEach(n => { if (parent.has(n.id)) { const r = find(n.id); if (!clusterMap.has(r)) clusterMap.set(r, new Set()); clusterMap.get(r).add(n.id); } });
  // For each candidate cluster, consider adding neighbors with >=2 connections
  const outNeighbors = new Map();
  const inNeighbors = new Map();
  nodes.forEach(n => { outNeighbors.set(n.id, new Set()); inNeighbors.set(n.id, new Set()); });
  edges.forEach(e => { if (outNeighbors.has(e.source)) outNeighbors.get(e.source).add(e.target); if (inNeighbors.has(e.target)) inNeighbors.get(e.target).add(e.source); });

  clusterMap.forEach((members, root) => {
    const memberArr = Array.from(members);
    nodes.forEach(n => {
      if (members.has(n.id)) return;
      let conn = 0;
      const outs = outNeighbors.get(n.id) || new Set();
      const ins = inNeighbors.get(n.id) || new Set();
      memberArr.forEach(m => { if (outs.has(m) || ins.has(m)) conn++; });
      if (conn >= 2) members.add(n.id);
    });
  });

  // Edge counts within clusters
  const clusters = [];
  clusterMap.forEach((members) => {
    const arr = Array.from(members);
    if (arr.length < 2) return;
    let cnt = 0;
    edges.forEach(e => { if (members.has(e.source) && members.has(e.target)) cnt++; });
    clusters.push({ nodes: arr, edgeCount: cnt });
  });
  clusters.sort((a, b) => b.edgeCount - a.edgeCount);
  const topClusters = clusters.slice(0, 10);

  // Node summary index
  const nodeSummaryIndex = {};
  nodes.forEach(n => { nodeSummaryIndex[n.id] = { name: n.name, type: n.type, summary: n.summary }; });

  const out = {
    scriptCompleted: true,
    entryPointCandidates,
    fanInRanking,
    fanOutRanking,
    bfsTraversal: bfs,
    nonCodeFiles,
    clusters: topClusters,
    layers: { count: layers.length, list: layers },
    nodeSummaryIndex,
    totalNodes: nodes.length,
    totalEdges: edges.length
  };
  fs.writeFileSync(outPath, JSON.stringify(out, null, 2));
  process.exit(0);
}

try { main(); } catch (e) { console.error(e); process.exit(1); }