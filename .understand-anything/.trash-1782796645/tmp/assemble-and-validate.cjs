#!/usr/bin/env node
const fs = require('fs');
const root = 'C:/Users/meena shah/Desktop/course-verifier';
const inter = root + '/.understand-anything/intermediate';

const assembled = JSON.parse(fs.readFileSync(inter + '/assembled-graph.json', 'utf8'));
const layers = JSON.parse(fs.readFileSync(inter + '/layers.json', 'utf8'));
const tour = JSON.parse(fs.readFileSync(inter + '/tour.json', 'utf8'));
const scan = JSON.parse(fs.readFileSync(inter + '/scan-result.json', 'utf8'));

// Clean language list: drop wrangler-cache noise that was filtered from files.
const dropLang = new Set(['sqlite-shm', 'sqlite-wal', 'unknown']);
let languages = (scan.languages || []).filter(l => !dropLang.has(l));
// Normalize db/sqlite -> keep both but unique
languages = Array.from(new Set(languages));

const graph = {
  version: '1.0.0',
  project: {
    name: scan.name,
    languages,
    frameworks: scan.frameworks || [],
    description: scan.description,
    analyzedAt: '2026-06-30T05:15:54Z',
    gitCommitHash: 'c8963589363580960926a3e3143a247c2180cf73'
  },
  nodes: assembled.nodes,
  edges: assembled.edges,
  layers,
  tour
};

fs.writeFileSync(inter + '/assembled-graph.json', JSON.stringify(graph, null, 2));
console.log('Assembled full graph: nodes=' + graph.nodes.length + ' edges=' + graph.edges.length +
  ' layers=' + graph.layers.length + ' tour=' + graph.tour.length);

// ---- inline deterministic validation ----
const issues = [], warnings = [];
if (!Array.isArray(graph.nodes)) { issues.push('graph.nodes missing'); graph.nodes = []; }
if (!Array.isArray(graph.edges)) { issues.push('graph.edges missing'); graph.edges = []; }
const nodeIds = new Set();
const seen = new Map();
graph.nodes.forEach((n, i) => {
  if (!n.id) { issues.push('Node[' + i + '] missing id'); return; }
  if (!n.type) issues.push("Node[" + i + "] '" + n.id + "' missing type");
  if (!n.name) issues.push("Node[" + i + "] '" + n.id + "' missing name");
  if (!n.summary) issues.push("Node[" + i + "] '" + n.id + "' missing summary");
  if (!n.tags || !n.tags.length) issues.push("Node[" + i + "] '" + n.id + "' missing tags");
  if (seen.has(n.id)) issues.push("Duplicate node ID '" + n.id + "'");
  else seen.set(n.id, i);
  nodeIds.add(n.id);
});
graph.edges.forEach((e, i) => {
  if (!nodeIds.has(e.source)) issues.push("Edge[" + i + "] source '" + e.source + "' not found");
  if (!nodeIds.has(e.target)) issues.push("Edge[" + i + "] target '" + e.target + "' not found");
});
const fileLevelTypes = new Set(['file','config','document','service','pipeline','table','schema','resource','endpoint']);
const fileNodes = graph.nodes.filter(n => fileLevelTypes.has(n.type)).map(n => n.id);
const assigned = new Map();
if (!Array.isArray(graph.layers)) { graph.layers = []; }
if (!Array.isArray(graph.tour)) { graph.tour = []; }
graph.layers.forEach(layer => {
  (layer.nodeIds || []).forEach(id => {
    if (!nodeIds.has(id)) issues.push("Layer '" + layer.id + "' refs missing node '" + id + "'");
    if (assigned.has(id)) issues.push("Node '" + id + "' appears in multiple layers");
    assigned.set(id, layer.id);
  });
});
fileNodes.forEach(id => { if (!assigned.has(id)) issues.push("File node '" + id + "' not in any layer"); });
graph.tour.forEach((step, i) => {
  (step.nodeIds || []).forEach(id => {
    if (!nodeIds.has(id)) issues.push("Tour step[" + i + "] refs missing node '" + id + "'");
  });
});
const withEdges = new Set([...graph.edges.map(e => e.source), ...graph.edges.map(e => e.target)]);
graph.nodes.forEach(n => { if (!withEdges.has(n.id)) warnings.push("Node '" + n.id + "' has no edges (orphan)"); });
const stats = {
  totalNodes: graph.nodes.length,
  totalEdges: graph.edges.length,
  totalLayers: graph.layers.length,
  tourSteps: graph.tour.length,
  nodeTypes: graph.nodes.reduce((a, n) => { a[n.type] = (a[n.type]||0)+1; return a; }, {}),
  edgeTypes: graph.edges.reduce((a, e) => { a[e.type] = (a[e.type]||0)+1; return a; }, {})
};
fs.writeFileSync(inter + '/review.json', JSON.stringify({ issues, warnings, stats }, null, 2));
console.log('Validation: issues=' + issues.length + ' warnings=' + warnings.length);
if (issues.length) { console.log('ISSUES:\n' + issues.join('\n')); }
if (warnings.length) { console.log('WARNINGS (' + warnings.length + '):\n' + warnings.slice(0,15).join('\n') + (warnings.length>15?'\n...':'')); }
console.log('STATS:', JSON.stringify(stats, null, 2));