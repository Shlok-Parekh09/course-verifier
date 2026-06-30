#!/usr/bin/env node
'use strict';

const fs = require('fs');

function main() {
  const inPath = process.argv[2];
  const outPath = process.argv[3];
  if (!inPath || !outPath) {
    console.error('Usage: node ua-arch-analyze.js <input.json> <output.json>');
    process.exit(1);
  }
  const data = JSON.parse(fs.readFileSync(inPath, 'utf8'));
  const fileNodes = data.fileNodes || [];
  const importEdges = data.importEdges || [];
  const allEdges = data.allEdges || [];

  // --- A. Directory Grouping ---
  // Common prefix
  const paths = fileNodes.map(n => n.filePath);
  function commonPrefixDir(ps) {
    if (ps.length === 0) return '';
    const split = ps.map(p => p.split('/').filter(Boolean));
    let prefix = [];
    const minLen = Math.min(...split.map(s => s.length));
    for (let i = 0; i < minLen; i++) {
      const seg = split[0][i];
      if (split.every(s => s[i] === seg)) prefix.push(seg);
      else break;
    }
    // Only treat as prefix if it ends at a directory boundary (i.e., last segment is a dir shared by all)
    // We want the common directory prefix. If all paths share the same first segment, that's the prefix.
    return prefix.length > 0 ? prefix.join('/') + '/' : '';
  }
  const prefix = commonPrefixDir(paths);

  function groupOf(filePath) {
    const segs = filePath.split('/').filter(Boolean);
    let rest = segs;
    if (prefix) {
      const prefSegs = prefix.split('/').filter(Boolean);
      // strip matching prefix segments
      let i = 0;
      while (i < prefSegs.length && i < rest.length && rest[i] === prefSegs[i]) i++;
      rest = rest.slice(i);
    }
    if (rest.length === 0) return 'root';
    if (rest.length === 1) return 'root';
    return rest[0];
  }

  const directoryGroups = {};
  fileNodes.forEach(n => {
    const g = groupOf(n.filePath);
    if (!directoryGroups[g]) directoryGroups[g] = [];
    directoryGroups[g].push(n.id);
  });

  // --- B. Node Type Grouping ---
  const nodeTypeGroups = {};
  fileNodes.forEach(n => {
    if (!nodeTypeGroups[n.type]) nodeTypeGroups[n.type] = [];
    nodeTypeGroups[n.type].push(n.id);
  });

  // --- C. Import Adjacency / fan-out fan-in ---
  const fileFanOut = {};
  const fileFanIn = {};
  fileNodes.forEach(n => { fileFanOut[n.id] = 0; fileFanIn[n.id] = 0; });
  importEdges.forEach(e => {
    if (fileFanOut[e.source] !== undefined) fileFanOut[e.source]++;
    if (fileFanIn[e.target] !== undefined) fileFanIn[e.target]++;
  });

  // --- D. Cross-Category Dependency Analysis ---
  const typeOf = {};
  fileNodes.forEach(n => { typeOf[n.id] = n.type; });
  const crossMap = {};
  allEdges.forEach(e => {
    const ft = typeOf[e.source] || 'unknown';
    const tt = typeOf[e.target] || 'unknown';
    const key = `${ft}->${tt}:${e.type}`;
    crossMap[key] = (crossMap[key] || 0) + 1;
  });
  const crossCategoryEdges = Object.entries(crossMap).map(([k, count]) => {
    const [fromType, rest] = k.split('->');
    const [toType, edgeType] = rest.split(':');
    return { fromType, toType, edgeType, count };
  });

  // --- E. Inter-Group Import Frequency ---
  const groupOfId = {};
  fileNodes.forEach(n => { groupOfId[n.id] = groupOf(n.filePath); });
  const interMap = {};
  importEdges.forEach(e => {
    const fg = groupOfId[e.source];
    const tg = groupOfId[e.target];
    if (!fg || !tg || fg === tg) return;
    const key = `${fg}->${tg}`;
    interMap[key] = (interMap[key] || 0) + 1;
  });
  const interGroupImports = Object.entries(interMap).map(([k, count]) => {
    const [from, to] = k.split('->');
    return { from, to, count };
  });

  // --- F. Intra-Group Import Density ---
  const intraGroupDensity = {};
  Object.keys(directoryGroups).forEach(g => {
    intraGroupDensity[g] = { internalEdges: 0, totalEdges: 0, density: 0 };
  });
  importEdges.forEach(e => {
    const fg = groupOfId[e.source];
    const tg = groupOfId[e.target];
    if (fg && intraGroupDensity[fg]) intraGroupDensity[fg].totalEdges++;
    if (tg && fg === tg && intraGroupDensity[fg]) intraGroupDensity[fg].internalEdges++;
  });
  Object.keys(intraGroupDensity).forEach(g => {
    const d = intraGroupDensity[g];
    d.density = d.totalEdges > 0 ? d.internalEdges / d.totalEdges : 0;
  });

  // --- G. Directory Pattern Matching ---
  const patterns = [
    [['routes','api','controllers','endpoints','handlers','routers','blueprints','controller','serializers'],'api'],
    [['services','core','lib','domain','logic','internal','composables','signals','mailers','jobs','channels'],'service'],
    [['models','db','data','persistence','repository','entities','migrations','entity','sql','database','schema'],'data'],
    [['components','views','pages','ui','layouts','screens'],'ui'],
    [['middleware','plugins','interceptors','guards'],'middleware'],
    [['utils','helpers','common','shared','tools','templatetags','pkg'],'utility'],
    [['config','constants','env','settings','management'],'config'],
    [['__tests__','test','tests','spec','specs'],'test'],
    [['types','interfaces','schemas','contracts','dtos','dto','request','response'],'types'],
    [['hooks'],'hooks'],
    [['store','state','reducers','actions','slices'],'state'],
    [['assets','static','public'],'assets'],
    [['cmd','bin'],'entry'],
    [['docs','documentation','wiki'],'documentation'],
    [['deploy','deployment','infra','infrastructure','docker','k8s','kubernetes','helm','charts','terraform','tf'],'infrastructure'],
    [['.github','.gitlab','.circleci'],'ci-cd'],
  ];
  // Build a flat lookup from segment -> label
  const segLookup = {};
  patterns.forEach(([segs, label]) => {
    segs.forEach(s => { segLookup[s] = label; });
  });
  // extra
  Object.assign(segLookup, {
    '.github': 'ci-cd', '.gitlab': 'ci-cd', '.circleci': 'ci-cd',
    'infinityfree': 'ui', 'worker': 'service', 'templates': 'ui',
    'scratch': 'utility', 'public': 'assets',
  });

  const patternMatches = {};
  Object.keys(directoryGroups).forEach(g => {
    patternMatches[g] = segLookup[g] || 'unknown';
  });

  // File-level pattern detection for individual files
  function filePattern(n) {
    const fp = n.filePath;
    const name = n.name;
    if (/\.test\./.test(name) || /\.spec\./.test(name) || /^test_.*\.py$/.test(name) || /_test\.go$/.test(name) || /Test\.java$/.test(name) || /_spec\.rb$/.test(name) || /Test\.php$/.test(name) || /Tests\.cs$/.test(name)) return 'test';
    if (/\.d\.ts$/.test(name)) return 'types';
    if (['index.ts','index.js','__init__.py'].includes(name)) return 'entry';
    if (name === 'manage.py') return 'entry';
    if (name === 'wsgi.py' || name === 'asgi.py') return 'config';
    if (/^cmd\/.+\/main\.go$/.test(fp)) return 'entry';
    if (name === 'main.rs' || name === 'lib.rs') return 'entry';
    if (name === 'Application.java' || name === 'Program.cs') return 'entry';
    if (name === 'config.ru') return 'entry';
    if (['Cargo.toml','go.mod','Gemfile','pom.xml','build.gradle','composer.json'].includes(name)) return 'config';
    if (name === 'Dockerfile' || /^docker-compose/.test(name)) return 'infrastructure';
    if (/\.tf$/.test(name) || /\.tfvars$/.test(name)) return 'infrastructure';
    if (/^\.github\/workflows\//.test(fp) || name === '.gitlab-ci.yml' || name === 'Jenkinsfile') return 'ci-cd';
    if (/\.sql$/.test(name)) return 'data';
    if (/\.graphql$/.test(name) || /\.gql$/.test(name) || /\.proto$/.test(name)) return 'types';
    if (/\.md$/.test(name) || /\.rst$/.test(name)) return 'documentation';
    if (name === 'Makefile') return 'infrastructure';
    return null;
  }
  const filePatternMatches = {};
  fileNodes.forEach(n => {
    const p = filePattern(n);
    if (p) filePatternMatches[n.id] = p;
  });

  // --- H. Deployment Topology ---
  const infraFiles = [];
  let hasDockerfile = false, hasCompose = false, hasK8s = false, hasTerraform = false, hasCI = false;
  fileNodes.forEach(n => {
    const fp = n.filePath; const name = n.name;
    if (name === 'Dockerfile' || /^docker-compose/.test(name)) {
      infraFiles.push(fp);
      if (name === 'Dockerfile') hasDockerfile = true;
      if (/^docker-compose/.test(name)) hasCompose = true;
    }
    if (/\.tf$/.test(name) || /\.tfvars$/.test(name)) { infraFiles.push(fp); hasTerraform = true; }
    if (/(^|\/)k8s\//.test(fp) || /\.ya?ml$/.test(name) && /k8s|kubernetes|helm|chart/.test(fp)) { infraFiles.push(fp); hasK8s = true; }
    if (/^\.github\/workflows\//.test(fp) || name === '.gitlab-ci.yml' || name === 'Jenkinsfile') { infraFiles.push(fp); hasCI = true; }
    if (n.type === 'service' || n.type === 'resource') infraFiles.push(fp);
  });
  const deploymentTopology = {
    hasDockerfile, hasCompose, hasK8s, hasTerraform, hasCI,
    infraFiles: [...new Set(infraFiles)],
  };

  // --- I. Data Pipeline ---
  const schemaFiles = [], migrationFiles = [], dataModelFiles = [], apiHandlerFiles = [];
  fileNodes.forEach(n => {
    const fp = n.filePath; const name = n.name; const tags = (n.tags || []).join(',');
    if (/\.sql$/.test(name) && /migrat/i.test(fp)) migrationFiles.push(fp);
    else if (/\.sql$/.test(name) || /\.graphql$/.test(name) || /\.gql$/.test(name) || /\.proto$/.test(name)) schemaFiles.push(fp);
    if (n.type === 'table' || n.type === 'schema' || /data-model|database|persistence/.test(tags)) dataModelFiles.push(fp);
    if (/api-handler|endpoint/.test(tags) || /routes|api|controllers/.test(fp)) apiHandlerFiles.push(fp);
  });

  // --- J. Documentation Coverage ---
  const docGroups = new Set();
  fileNodes.forEach(n => {
    if (n.type === 'document' || /\.md$/.test(n.name) || /\.rst$/.test(n.name)) {
      const g = groupOf(n.filePath);
      docGroups.add(g);
    }
  });
  const totalGroups = Object.keys(directoryGroups).length;
  const undocumentedGroups = Object.keys(directoryGroups).filter(g => !docGroups.has(g));
  const docCoverage = {
    groupsWithDocs: docGroups.size,
    totalGroups,
    coverageRatio: totalGroups > 0 ? docGroups.size / totalGroups : 0,
    undocumentedGroups,
  };

  // --- K. Dependency Direction ---
  const pairDir = {};
  interGroupImports.forEach(({ from, to, count }) => {
    const key = `${from}->${to}`;
    const rev = `${to}->${from}`;
    pairDir[key] = (pairDir[key] || 0) + count;
  });
  const seen = new Set();
  const dependencyDirection = [];
  Object.keys(pairDir).forEach(k => {
    const [a, b] = k.split('->');
    const rev = `${b}->${a}`;
    if (seen.has(k) || seen.has(rev)) return;
    seen.add(k); seen.add(rev);
    const fwd = pairDir[k] || 0;
    const back = pairDir[rev] || 0;
    if (fwd >= back && fwd > 0) dependencyDirection.push({ dependent: a, dependsOn: b });
    else if (back > 0) dependencyDirection.push({ dependent: b, dependsOn: a });
  });

  // --- File stats ---
  const filesPerGroup = {};
  Object.entries(directoryGroups).forEach(([g, ids]) => { filesPerGroup[g] = ids.length; });
  const nodeTypeCounts = {};
  Object.entries(nodeTypeGroups).forEach(([t, ids]) => { nodeTypeCounts[t] = ids.length; });

  const result = {
    scriptCompleted: true,
    commonPrefix: prefix,
    directoryGroups,
    nodeTypeGroups,
    crossCategoryEdges,
    interGroupImports,
    intraGroupDensity,
    patternMatches,
    filePatternMatches,
    deploymentTopology,
    dataPipeline: { schemaFiles, migrationFiles, dataModelFiles, apiHandlerFiles },
    docCoverage,
    dependencyDirection,
    fileStats: {
      totalFileNodes: fileNodes.length,
      filesPerGroup,
      nodeTypeCounts,
    },
    fileFanIn,
    fileFanOut,
  };

  fs.writeFileSync(outPath, JSON.stringify(result, null, 2));
  console.error('Analysis complete. Wrote ' + outPath);
  process.exit(0);
}

try { main(); } catch (e) { console.error('FATAL: ' + e.stack); process.exit(1); }