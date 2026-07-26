/* ================================================================
   COURSEVERIFY CATALOG  ·  APP.JS  v9  (static JSON edition)
   Loads courses directly from courses.json in the same folder.
   Dashboard uses a local COBE WebGL globe.
   No backend server required.
   ================================================================ */

'use strict';

const COURSES_JSON = 'courses.json';

// ── State ────────────────────────────────────────────────────────
let globalData = null;
let currentFilter = { type: null, value: null };
let countryDataList = [];
let allCoursesData = [];
let currentPage = 1;
const PAGE_SIZE = 100;
let lastStatsHash = '';
let lastCountryHash = '';
let lastBarHash = '';
let firstDataFetch = true;

// ── Tab filter state ─────────────────────────────────────────────
let courseFilter = { search: '', country: 'all', domain: 'all', qs: 'any', nirf: 'any', courseType: 'all' };

// ── edX All Courses filter state ────────────────────────────────────
let edxFilterState = {
    typePill: 'all',   // course type from #course-type-pills
    domainChip: 'all'  // domain category from #domain-chips-scroll
};

// ── Domain category by course idx (ID number) ───────────────────
const DOMAIN_RANGES = [
    { label: 'Free',                  min: 1,    max: 25   },
    { label: 'Free to Audit',         min: 26,   max: 48   },
    { label: 'High Value Low Cost',   min: 49,   max: 100  },
    { label: 'Foundational',          min: 101,  max: 601  },
    { label: 'Network Infrastructure',min: 602,  max: 1585 },
    { label: 'System & Endpoint',     min: 1586, max: 1890 },
    { label: 'Cyber Forensics',       min: 1891, max: 2634 },
    { label: 'Data & Application',    min: 2635, max: 2965 },
    { label: 'Legal & Ethical',       min: 2966, max: 3727 },
];

function getDomainCategory(idxRaw) {
    const idx = parseInt(idxRaw, 10);
    if (isNaN(idx)) return 'Uncategorised';
    for (const r of DOMAIN_RANGES) {
        if (idx >= r.min && idx <= r.max) return r.label;
    }
    return 'Uncategorised';
}

const ALL_DOMAIN_LABELS = DOMAIN_RANGES.map(r => r.label);

// ── Academic-domain normalizer ──────────────────────────────────
const _CANON_DOMAIN_FRAGMENTS = [
    ['post graduate diploma', "Post Graduate Diploma"],
    ['post grad diploma',     "Post Graduate Diploma"],
    ['graduate diploma',      "Post Graduate Diploma"],
    ['post graduate certificate', "Post Graduate Certificate"],
    ['post grad certificate', "Post Graduate Certificate"],
    ['post grad cert',        "Post Graduate Certificate"],
    ['bachelor',              "Bachelor's Degree"],
    ['master',                "Master's Degree"],
    ['pg',                    "Master's Degree"],
    ['diploma',               "Diploma"],
    ['certificate',           "Certificate"],
    ['cert',                  "Certificate"],
    ['free to audit',         "Free to Audit"],
    ['high value low cost',   "High Value Low Cost"],
    ['free',                  "Free"],
];
function normalizeDomain(raw) {
    if (!raw) return 'Other';
    const k = String(raw).toLowerCase().replace('gradiuate', 'graduate').trim();
    if (!k || ['unknown', 'unknown domain', 'none', 'null'].includes(k)) return 'Other';
    for (const [frag, label] of _CANON_DOMAIN_FRAGMENTS) {
        if (k.includes(frag)) return label;
    }
    return 'Other';
}

let barChart, mapChart, lineChart, quantityBarChartInstance;
let barMode = 'domain'; // 'domain' | 'country'

// ── Country flag emoji helper ─────────────────────────────────────
const FLAG_MAP = {
    'India': '🇮🇳', 'United States': '🇺🇸', 'Australia': '🇦🇺',
    'United Kingdom': '🇬🇧', 'Canada': '🇨🇦', 'Germany': '🇩🇪',
    'France': '🇫🇷', 'Singapore': '🇸🇬', 'South Africa': '🇿🇦',
    'New Zealand': '🇳🇿', 'UAE': '🇦🇪', 'China': '🇨🇳',
    'Japan': '🇯🇵', 'Netherlands': '🇳🇱', 'Switzerland': '🇨🇭',
    'Brazil': '🇧🇷', 'Italy': '🇮🇹', 'Spain': '🇪🇸',
    'Ireland': '🇮🇪', 'Sweden': '🇸🇪', 'Denmark': '🇩🇰',
};
function getFlag(name) {
    if (!name) return '🌐';
    for (const [key, flag] of Object.entries(FLAG_MAP)) {
        if (name.toLowerCase().includes(key.toLowerCase()) || key.toLowerCase().includes(name.toLowerCase())) return flag;
    }
    return '🌐';
}

// ================================================================
//  THEME
// ================================================================
function initTheme() {
    const toggle = document.getElementById('theme-toggle');
    const label = document.getElementById('theme-label');
    const saved = localStorage.getItem('cvTheme') || 'dark';
    if (saved === 'light') {
        document.body.classList.add('light-mode');
        if (label) label.textContent = 'Light';
    }
    if (toggle) {
        toggle.addEventListener('click', () => {
            document.body.classList.toggle('light-mode');
            const isLight = document.body.classList.contains('light-mode');
            localStorage.setItem('cvTheme', isLight ? 'light' : 'dark');
            if (label) label.textContent = isLight ? 'Light' : 'Dark';
            updateChartThemeColors();
            applyGlobeTheme(isLight ? 'light' : 'dark');
        });
    }

    // Sync the initial globe palette with the loaded theme.
    applyGlobeTheme(getCurrentGlobeTheme());
}

function updateChartThemeColors() {
    const isLight = document.body.classList.contains('light-mode');
    const tickColor = isLight ? 'rgba(13, 19, 33, 0.7)' : 'rgba(255,255,255,0.7)';
    if (quantityBarChartInstance) {
        quantityBarChartInstance.options.plugins.legend.labels.color = tickColor;
        quantityBarChartInstance.options.scales.x.ticks.color = tickColor;
        quantityBarChartInstance.update();
    }
}

// ================================================================
//  TABS
// ================================================================
function switchTab(targetId) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('#nav-tabs a').forEach(a => a.classList.remove('active'));
    const content = document.getElementById(targetId);
    if (content) content.classList.add('active');
    const link = document.querySelector(`#nav-tabs a[data-target="${targetId}"]`);
    if (link) link.classList.add('active');
    if (targetId === 'tab-courses') loadAllCourses();
    if (targetId === 'tab-analytics') {
        if (allCoursesData.length === 0) loadAllCourses(true);
        renderAnalytics({});
    }
}

function initTabs() {
    document.querySelectorAll('#nav-tabs a').forEach(a => {
        a.addEventListener('click', e => {
            e.preventDefault();
            switchTab(a.getAttribute('data-target'));
        });
    });
}

// ================================================================
//  INTERACTIVE 3D GLOBE (COBE)
// ================================================================
let globeInstance = null;   // { isCobe, pointOfView(), controls() }
let selectedCountry = null;
let cobeMarkers = [];

const COUNTRY_COORDS = {
    'India': [20.5937, 78.9629], 'United States': [37.0902, -95.7129], 'United States of America': [37.0902, -95.7129],
    'United Kingdom': [55.3781, -3.4360], 'Australia': [-25.2744, 133.7751], 'Canada': [56.1304, -106.3468],
    'Germany': [51.1657, 10.4515], 'France': [46.2276, 2.2137], 'Singapore': [1.3521, 103.8198],
    'South Africa': [-30.5595, 22.9375], 'New Zealand': [-40.9006, 174.886], 'UAE': [23.4241, 53.8478],
    'United Arab Emirates': [23.4241, 53.8478], 'China': [35.8617, 104.1954], 'Japan': [36.2048, 138.2529],
    'Netherlands': [52.1326, 5.2913], 'Switzerland': [46.8182, 8.2275], 'Brazil': [-14.235, -51.9253],
    'Italy': [41.8719, 12.5674], 'Spain': [40.4637, -3.7492], 'Ireland': [53.1424, -7.6921],
    'Sweden': [60.1282, 18.6435], 'Denmark': [56.2639, 9.5018], 'South Korea': [35.9078, 127.7669],
    'Malaysia': [4.2105, 101.9758], 'Hong Kong': [22.3193, 114.1694], 'Saudi Arabia': [23.8859, 45.0792],
    'Luxembourg': [49.8153, 6.1296], 'Russia': [61.524, 105.3188], 'Mexico': [23.6345, -102.5528],
    'Israel': [31.0461, 34.8516], 'Turkey': [38.9637, 35.2433], 'Thailand': [15.87, 100.9925],
    'Indonesia': [-0.7893, 113.9213], 'Philippines': [12.8797, 121.774], 'Colombia': [4.5709, -74.2973],
    'Chile': [-35.6751, -71.543], 'Nigeria': [9.082, 8.6753], 'Kenya': [-0.0236, 37.9062],
    'Egypt': [26.8206, 30.8025], 'Pakistan': [30.3753, 69.3451], 'Bangladesh': [23.685, 90.3563],
    'Sri Lanka': [7.8731, 80.7718], 'Nepal': [28.3949, 84.124], 'Taiwan': [23.6978, 120.9605],
    'Finland': [61.9241, 25.7482], 'Norway': [60.472, 8.4689], 'Poland': [51.9194, 19.1451],
    'Austria': [47.5162, 14.5501], 'Belgium': [50.5039, 4.4699], 'Portugal': [39.3999, -8.2245],
    'Greece': [39.0742, 21.8243], 'Czech Republic': [49.8175, 15.473]
};

const GLOBAL_HUBS = [
    { name: "India", lat: 20.5937, lng: 78.9629 },
    { name: "United States", lat: 37.0902, lng: -95.7129 },
    { name: "United Kingdom", lat: 55.3781, lng: -3.4360 },
    { name: "Australia", lat: -25.2744, lng: 133.7751 },
    { name: "Germany", lat: 51.1657, lng: 10.4515 },
    { name: "Canada", lat: 56.1304, lng: -106.3468 },
    { name: "Singapore", lat: 1.3521, lng: 103.8198 },
    { name: "France", lat: 46.2276, lng: 2.2137 },
    { name: "Japan", lat: 36.2048, lng: 138.2529 }
];

function generateDenseArcData() {
    const arcs = [];
    for (let i = 0; i < GLOBAL_HUBS.length; i++) {
        for (let j = i + 1; j < GLOBAL_HUBS.length; j++) {
            arcs.push({
                startLat: GLOBAL_HUBS[i].lat,
                startLng: GLOBAL_HUBS[i].lng,
                endLat: GLOBAL_HUBS[j].lat,
                endLng: GLOBAL_HUBS[j].lng
            });
        }
    }
    return arcs;
}

// Convert hex (#rrggbb) to COBE RGB triple [0..1]
function hexToRgb01(hex) {
    const clean = hex.replace('#', '');
    const bigint = parseInt(clean, 16);
    const r = (bigint >> 16) & 255;
    const g = (bigint >> 8) & 255;
    const b = bigint & 255;
    return [r / 255, g / 255, b / 255];
}

const GLOBE_THEMES = {
    dark: {
        base: '#111827',      // slate-900 sphere base (visible but still dark)
        bg: '#0b0f19',        // canvas background
        halo: '#6366f1',      // brighter indigo atmosphere
        marker: '#d8b4fe',    // brighter violet markers
        arc: '#22d3ee'        // neon cyan arcs
    },
    light: {
        base: '#e2e8f0',      // slate-200 sphere base (clear against light bg)
        bg: '#f8fafc',        // bright off-white canvas
        halo: '#4f46e5',      // deeper indigo bloom
        marker: '#7e22ce',    // deep purple markers for contrast on light sphere
        arc: '#0891b2'        // darker cyan arcs for contrast on light sphere
    }
};

function getCurrentGlobeTheme() {
    return document.body.classList.contains('light-mode') ? 'light' : 'dark';
}

function applyGlobeTheme(theme) {
    const t = GLOBE_THEMES[theme] || GLOBE_THEMES.dark;
    const base = hexToRgb01(t.base);
    const glow = hexToRgb01(t.halo);
    const marker = hexToRgb01(t.marker);
    const arc = hexToRgb01(t.arc);

    if (cobeGlobe) {
        // Re-generate dense N×N hub arcs with the current theme color
        const denseArcs = generateDenseArcData().map(a => ({
            from: [a.startLat, a.startLng],
            to: [a.endLat, a.endLng],
            color: arc
        }));

        cobeGlobe.update({
            baseColor: base,
            glowColor: glow,
            markerColor: marker,
            arcColor: arc,
            arcWidth: 0.8,   // visible precision lines
            arcHeight: 0.28, // gentle orbital curve
            markers: cobeMarkers,
            arcs: denseArcs
        });
    }
}

function initGlobe() {
    const container = document.getElementById('globe-container');
    if (!container) {
        console.warn('[Globe] container #globe-container not found');
        return;
    }
    if (typeof window.createGlobe !== 'function') {
        container.innerHTML = '<div class="globe-fallback">Globe library not loaded. Please wait or refresh.</div>';
        console.error('[Globe] COBE (window.createGlobe) is not available.');
        return;
    }
    initCobeGlobe(container);
}

// COBE render state
let cobeGlobe = null;
let cobeState = { phi: 0, theta: 0.3, scale: 0.85 };
let cobeAutoRotate = true;
let cobeIsDragging = false;
let cobeAnimationId = null;

function initCobeGlobe(container) {
    container.innerHTML = '';
    const width = container.clientWidth || 800;
    const height = container.clientHeight || 600;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    const canvas = document.createElement('canvas');
    canvas.id = 'cobe-canvas';
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    canvas.style.display = 'block';
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    container.appendChild(canvas);

    // COBE wraps the canvas in its own div; make sure that wrapper is sized and interactive
    setTimeout(() => {
        const wrapper = canvas.parentElement;
        if (wrapper && wrapper !== container) {
            wrapper.style.pointerEvents = 'auto';
            wrapper.style.width = '100%';
            wrapper.style.height = '100%';
        }
    }, 0);

    const markerEntries = Object.entries(COUNTRY_COORDS);
    cobeMarkers = markerEntries.map(([name, [lat, lng]], i) => ({
        id: 'cobe-' + i,
        location: [lat, lng],
        size: 0.022,
        color: [0.847, 0.706, 0.996]  // #d8b4fe bright violet hub marker
    }));

    const arcs = generateDenseArcData().map((arc, i) => ({
        id: 'arc-' + i,
        from: [arc.startLat, arc.startLng],
        to: [arc.endLat, arc.endLng],
        color: [0.133, 0.827, 0.933]   // default neon cyan, overridden by theme
    }));

    const initialTheme = getCurrentGlobeTheme();

    try {
        cobeGlobe = window.createGlobe(canvas, {
            devicePixelRatio: dpr,
            width: width,
            height: height,
            phi: cobeState.phi,
            theta: cobeState.theta,
            dark: 0.72,
            diffuse: 1.2,
            scale: cobeState.scale,
            mapSamples: 22000,
            mapBrightness: 14,
            mapBaseBrightness: 0.18,
            baseColor: hexToRgb01(GLOBE_THEMES[initialTheme].base),
            markerColor: hexToRgb01(GLOBE_THEMES[initialTheme].marker),
            glowColor: hexToRgb01(GLOBE_THEMES[initialTheme].halo),
            arcColor: hexToRgb01(GLOBE_THEMES[initialTheme].arc),
            arcWidth: 0.4,
            arcHeight: 0.22,
            markerElevation: 0.025,
            offset: [0, 0],
            markers: cobeMarkers,
            arcs: arcs,
            onRender: (state) => {
                // Sync our tracked state into COBE before every frame
                state.phi = cobeState.phi;
                state.theta = cobeState.theta;
                state.scale = cobeState.scale;
            }
        });
    } catch (err) {
        console.error('[Globe] COBE init failed:', err);
        container.innerHTML = '<div class="globe-fallback">Unable to create 3D globe.</div>';
        return;
    }

    // Public API used by handleCountryClick / resetCountrySelection
    globeInstance = {
        isCobe: true,
        controls: () => ({ autoRotate: cobeAutoRotate, enableZoom: true }),
        pointOfView: ({ lat = 20, lng = 0, altitude = 2.5 }, duration = 1000) => {
            // Match COBE's rotation convention used in cobeProject() so the clicked
            // country ends up centered and facing the viewer (north up).
            const targetPhi = -lng * (Math.PI / 180) - Math.PI / 2;
            const targetTheta = lat * (Math.PI / 180);
            // COBE uses a unit sphere scale rather than a camera distance; lower scale
            // pulls the globe back so it occupies ~55–60 % of the viewport height.
            const targetScale = Math.max(0.72, Math.min(1.18, 2.15 / altitude));
            const startPhi = cobeState.phi;
            const startTheta = cobeState.theta;
            const startScale = cobeState.scale;
            const startTime = performance.now();

            let deltaPhi = targetPhi - startPhi;
            while (deltaPhi > Math.PI) deltaPhi -= 2 * Math.PI;
            while (deltaPhi < -Math.PI) deltaPhi += 2 * Math.PI;

            cobeAutoRotate = false;
            function animateView(now) {
                const p = Math.min(1, (now - startTime) / duration);
                const ease = 1 - Math.pow(1 - p, 3);
                cobeState.phi = startPhi + deltaPhi * ease;
                cobeState.theta = startTheta + (targetTheta - startTheta) * ease;
                cobeState.scale = startScale + (targetScale - startScale) * ease;
                cobeGlobe.update(cobeState);
                if (p < 1) {
                    requestAnimationFrame(animateView);
                } else {
                    cobeAutoRotate = true;
                }
            }
            requestAnimationFrame(animateView);
        }
    };

    // Projection that mirrors COBE's internal rotation matrix so we can hit-test countries
    function latLonTo3D([lat, lon]) {
        const latRad = (lat * Math.PI) / 180;
        const lonRad = (lon * Math.PI) / 180 - Math.PI;
        const cosLat = Math.cos(latRad);
        return [-cosLat * Math.cos(lonRad), Math.sin(latRad), cosLat * Math.sin(lonRad)];
    }

    function cobeProject(lat, lng) {
        const p = latLonTo3D([lat, lng]);
        const r = 1.0;
        const pos = [p[0] * r, p[1] * r, p[2] * r];

        const cx = Math.cos(cobeState.theta);
        const cy = Math.cos(cobeState.phi);
        const sx = Math.sin(cobeState.theta);
        const sy = Math.sin(cobeState.phi);
        const aspect = canvas.width / canvas.height;

        const rx = cy * pos[0] + sy * pos[2];
        const ry = sy * sx * pos[0] + cx * pos[1] - cy * sx * pos[2];
        const rz = -sy * cx * pos[0] + sx * pos[1] + cy * cx * pos[2];

        return {
            x: ((rx / aspect) * cobeState.scale + 1) / 2,
            y: (-ry * cobeState.scale + 1) / 2,
            visible: rz > 0.05
        };
    }

    function getHoveredCountry(clientX, clientY) {
        const rect = canvas.getBoundingClientRect();
        const clickX = (clientX - rect.left) / rect.width;
        const clickY = (clientY - rect.top) / rect.height;

        let best = null;
        let bestDist = Infinity;
        markerEntries.forEach(([name, [lat, lng]]) => {
            const proj = cobeProject(lat, lng);
            if (!proj.visible) return;
            const dx = proj.x - clickX;
            const dy = proj.y - clickY;
            const dist = Math.hypot(dx, dy);
            if (dist < bestDist) {
                bestDist = dist;
                best = { name, dist };
            }
        });
        return bestDist < 0.25 ? best?.name : null;
    }

    // Tooltip
    let tooltipEl = document.getElementById('cobe-tooltip');
    if (!tooltipEl) {
        tooltipEl = document.createElement('div');
        tooltipEl.id = 'cobe-tooltip';
        tooltipEl.className = 'globe-tooltip';
        tooltipEl.style.cssText = 'position:fixed; display:none; pointer-events:none; z-index:100;';
        document.body.appendChild(tooltipEl);
    }

    function showTooltip(e, name, count) {
        tooltipEl.innerHTML = `<b>${escHtml(name)}</b>${count ? `<br/>${count} course${count === 1 ? '' : 's'}` : '<br/>Click to view'}`;
        tooltipEl.style.display = 'block';
        tooltipEl.style.left = (e.clientX + 12) + 'px';
        tooltipEl.style.top = (e.clientY + 12) + 'px';
    }
    function hideTooltip() {
        tooltipEl.style.display = 'none';
    }

    // Mouse / touch interaction
    let dragStartX = 0, dragStartY = 0, hasDragged = false, isDown = false;
    let lastHoverCountry = null;
    let mouseDownCountry = null;

    function updateHover(clientX, clientY) {
        if (isDown) { hideTooltip(); return; }
        const country = getHoveredCountry(clientX, clientY);
        if (country) {
            const count = (globalData?.country_counts && Object.entries(globalData.country_counts)
                .filter(([k]) => isSameCountry(k, country)).reduce((s, [, v]) => s + v, 0)) || 0;
            showTooltip({ clientX, clientY }, country, count);
            canvas.style.cursor = 'pointer';
            lastHoverCountry = country;
        } else {
            hideTooltip();
            canvas.style.cursor = 'grab';
            lastHoverCountry = null;
        }
    }

    canvas.addEventListener('mousemove', e => updateHover(e.clientX, e.clientY));

    canvas.addEventListener('mousedown', e => {
        isDown = true;
        cobeIsDragging = true;
        hasDragged = false;
        dragStartX = e.clientX;
        dragStartY = e.clientY;
        cobeAutoRotate = false;
        canvas.style.cursor = 'grabbing';
        mouseDownCountry = getHoveredCountry(e.clientX, e.clientY);
    });

    window.addEventListener('mouseup', e => {
        if (!isDown) return;
        isDown = false;
        cobeIsDragging = false;
        canvas.style.cursor = 'grab';
        const clickCountry = !hasDragged ? (mouseDownCountry || lastHoverCountry) : null;
        if (clickCountry) handleCountryClick(clickCountry);
        mouseDownCountry = null;
        setTimeout(() => { cobeAutoRotate = true; }, 2500);
    });

    window.addEventListener('mousemove', e => {
        if (!isDown) return;
        const dx = e.clientX - dragStartX;
        const dy = e.clientY - dragStartY;
        if (Math.hypot(dx, dy) > 4) hasDragged = true;

        const sens = 0.005;
        cobeState.phi += dx * sens;
        cobeState.theta = Math.max(-Math.PI / 2 + 0.1, Math.min(Math.PI / 2 - 0.1, cobeState.theta + dy * sens));
        dragStartX = e.clientX;
        dragStartY = e.clientY;
        cobeGlobe.update(cobeState);
    });

    // Touch support
    canvas.addEventListener('touchstart', e => {
        if (e.touches.length === 1) {
            const t = e.touches[0];
            isDown = true;
            cobeIsDragging = true;
            hasDragged = false;
            dragStartX = t.clientX;
            dragStartY = t.clientY;
            cobeAutoRotate = false;
            mouseDownCountry = getHoveredCountry(t.clientX, t.clientY);
        }
    }, { passive: true });

    window.addEventListener('touchend', e => {
        if (!isDown) return;
        isDown = false;
        cobeIsDragging = false;
        const clickCountry = !hasDragged ? (mouseDownCountry || lastHoverCountry) : null;
        if (clickCountry) handleCountryClick(clickCountry);
        mouseDownCountry = null;
        setTimeout(() => { cobeAutoRotate = true; }, 2000);
    });

    window.addEventListener('touchmove', e => {
        if (!isDown || e.touches.length !== 1) return;
        const t = e.touches[0];
        const dx = t.clientX - dragStartX;
        const dy = t.clientY - dragStartY;
        if (Math.hypot(dx, dy) > 4) hasDragged = true;
        const sens = 0.006;
        cobeState.phi += dx * sens;
        cobeState.theta = Math.max(-Math.PI / 2 + 0.1, Math.min(Math.PI / 2 - 0.1, cobeState.theta + dy * sens));
        dragStartX = t.clientX;
        dragStartY = t.clientY;
        cobeGlobe.update(cobeState);
    }, { passive: true });

    // Zoom with wheel
    canvas.addEventListener('wheel', e => {
        e.preventDefault();
        cobeState.scale += e.deltaY * -0.0008;
        cobeState.scale = Math.max(0.55, Math.min(1.35, cobeState.scale));
        cobeGlobe.update(cobeState);
    }, { passive: false });

    // Resize handling
    const ro = new ResizeObserver(() => {
        const w = container.clientWidth || 800;
        const h = container.clientHeight || 600;
        canvas.width = Math.floor(w * dpr);
        canvas.height = Math.floor(h * dpr);
        cobeGlobe.update({ width: w, height: h });
    });
    ro.observe(container);

    // Dedicated animation loop so rotation/drag/zoom are applied every frame
    function animate() {
        if (cobeAutoRotate && !cobeIsDragging) {
            cobeState.phi += 0.005;
        }
        cobeGlobe.update(cobeState);
        cobeAnimationId = requestAnimationFrame(animate);
    }
    cobeAnimationId = requestAnimationFrame(animate);

    // Apply the dynamic theme once the globe is alive (also wires arc/marker colors)
    applyGlobeTheme(initialTheme);

    console.log('[Globe] COBE active. Markers:', cobeMarkers.length, 'Arcs:', arcs.length);
    updateGlobeHighlight(globalData?.country_counts || {});
}

function getCountryCoords(countryName) {
    for (const [name, [lat, lng]] of Object.entries(COUNTRY_COORDS)) {
        if (isSameCountry(name, countryName)) return { lat, lng };
    }
    return null;
}

function handleCountryClick(countryName) {
    selectedCountry = countryName;
    currentFilter = { type: 'country', value: countryName };

    if (globeInstance) {
        const coords = getCountryCoords(countryName);
        if (coords) {
            globeInstance.pointOfView({ lat: coords.lat, lng: coords.lng, altitude: 1.6 }, 1000);
        }
        globeInstance.controls().autoRotate = false;
    }

    const matches = allCoursesData.filter(c => isSameCountry(c.country, countryName));

    // Update dashboard widgets to reflect only this country
    const countryCounts = {};
    const domainCounts = {};
    matches.forEach(c => {
        if (c.country && isValidCountry(c.country)) {
            countryCounts[c.country] = (countryCounts[c.country] || 0) + 1;
        }
        const cat = getDomainCategory(c.id);
        if (cat && cat !== 'Uncategorised') domainCounts[cat] = (domainCounts[cat] || 0) + 1;
    });
    const scopedData = {
        status: 'success',
        documents: matches,
        stats: { total: matches.length },
        country_counts: countryCounts,
        domain_counts: domainCounts
    };
    updateDashboardExtras(scopedData);
    updateCards(scopedData.stats);

    renderCountryDetailPanel(countryName, matches);
}

function renderCountryDetailPanel(countryName, courses) {
    const panel = document.getElementById('course-details-panel');
    const tbody = document.getElementById('course-details-body');
    const nameEl = document.getElementById('country-detail-name');
    const flagEl = document.getElementById('country-detail-flag');
    const countEl = document.getElementById('country-detail-count');
    const btnName = document.getElementById('country-btn-name');
    if (!panel || !tbody) return;

    if (nameEl) nameEl.textContent = countryName;
    if (flagEl) flagEl.textContent = getFlag(countryName);
    if (countEl) countEl.textContent = `${courses.length} course${courses.length === 1 ? '' : 's'}`;
    if (btnName) btnName.textContent = countryName;

    // Sync every "total courses" counter in the UI with the filtered set.
    const totalValFallback = document.getElementById('total-courses-val');
    if (totalValFallback) totalValFallback.textContent = courses.length.toLocaleString();

    // Quick stats
    const qsCount = courses.filter(c => c.has_qs_badge).length;
    const domainMap = {};
    courses.forEach(c => {
        const dom = getDomainCategory(c.id) || 'Other';
        domainMap[dom] = (domainMap[dom] || 0) + 1;
    });
    const topDomains = Object.entries(domainMap).sort((a, b) => b[1] - a[1]).slice(0, 3);
    const topDomain = topDomains[0]?.[0] || '—';

    const cdsTotal = document.getElementById('cds-total');
    const cdsQs = document.getElementById('cds-qs');
    const cdsDomain = document.getElementById('cds-domain');
    if (cdsTotal) cdsTotal.textContent = courses.length.toLocaleString();
    if (cdsQs) cdsQs.textContent = qsCount.toLocaleString();
    if (cdsDomain) cdsDomain.textContent = topDomain;

    const topicList = document.getElementById('country-detail-topic-list');
    if (topicList) {
        topicList.innerHTML = topDomains.length
            ? topDomains.map(([dom, cnt]) => `<span class="country-detail-topic" title="${cnt} courses">${escHtml(dom)} <span style="opacity:.7;">(${cnt})</span></span>`).join('')
            : '<span class="country-detail-topic">No domain data</span>';
    }

    // Wire the View All Courses button
    const viewBtn = document.getElementById('country-view-table');
    if (viewBtn) {
        viewBtn.onclick = () => viewCountryInTable(countryName);
    }

    const qsRank = c => c.qs ? String(c.qs) : (c.has_qs_badge ? 'Yes' : 'No');
    const nirfRank = c => c.nirf ? String(c.nirf) : (c.has_nirf_badge ? 'Yes' : 'No');

    tbody.innerHTML = courses.length === 0
        ? '<tr><td colspan="4" class="empty-state">No courses found for this country.</td></tr>'
        : courses.slice(0, 20).map(c => `
            <tr>
                <td class="course-name-cell" title="${escHtml(c.name)}"><strong>${escHtml(c.name)}</strong></td>
                <td>${escHtml(c.university || '—')}</td>
                <td>${escHtml(qsRank(c))}</td>
                <td>${escHtml(nirfRank(c))}</td>
            </tr>`).join('');

    panel.style.display = 'flex';

    // Dim the right-sidebar chart so it never visually collides with the open panel.
    const dashRight = document.querySelector('.dash-right');
    if (dashRight) dashRight.classList.add('has-active-selection');
}

function viewCountryInTable(countryName) {
    jumpToCourses({ country: countryName });
}

function resetCountrySelection() {
    selectedCountry = null;
    currentFilter = { type: null, value: null };
    const panel = document.getElementById('course-details-panel');
    if (panel) panel.style.display = 'none';
    const dashRight = document.querySelector('.dash-right');
    if (dashRight) dashRight.classList.remove('has-active-selection');
    if (globeInstance) {
        globeInstance.pointOfView({ lat: 20, lng: 0, altitude: 2.5 }, 1200);
        globeInstance.controls().autoRotate = true;
    }
    // Restore global dashboard data
    if (globalData) {
        updateDashboardExtras(globalData);
        updateCards(globalData.stats);
    }
}

function updateGlobeHighlight(countryCounts) {
    if (!globeInstance?.isCobe || !cobeGlobe) return;
    const counts = countryCounts || {};
    const max = Math.max(...Object.values(counts), 1);
    const markerEntries = Object.entries(COUNTRY_COORDS);
    const theme = GLOBE_THEMES[getCurrentGlobeTheme()];
    const baseMarker = hexToRgb01(theme.marker);
    const selectedMarker = hexToRgb01('#00f2fe');   // bright cyan for active selection
    cobeMarkers = markerEntries.map(([name, [lat, lng]], i) => {
        const count = Object.entries(counts)
            .filter(([k]) => isSameCountry(k, name))
            .reduce((s, [, v]) => s + v, 0);
        const isSelected = selectedCountry && isSameCountry(selectedCountry, name);
        // Square-root scale with a hard max so India doesn't swallow smaller dots.
        const maxSize = 0.055;
        const minSize = 0.018;
        const size = isSelected ? 0.065 : (count ? Math.min(maxSize, minSize + (Math.sqrt(count) / Math.sqrt(max)) * (maxSize - minSize)) : minSize);
        return {
            id: 'cobe-' + i,
            location: [lat, lng],
            size,
            color: isSelected ? selectedMarker : (count ? baseMarker : [baseMarker[0] * 0.55, baseMarker[1] * 0.55, baseMarker[2] * 0.55])
        };
    });
    cobeGlobe.update({ markers: cobeMarkers });
}
// ================================================================
//  DASHBOARD EXTRAS (IIT/IIIT/NIT, Free/FTA/HVLC, Top 5 Countries)
// ================================================================
function renderCountryBarChart(intlCountries, total) {
    const qCtx = document.getElementById('quantityBarChart');
    if (!qCtx) return;
    if (quantityBarChartInstance) quantityBarChartInstance.destroy();
    const labels = intlCountries.map(c => c[0]);
    const dVals = intlCountries.map(c => (c[1] / total) * 100);

    const isLight = document.body.classList.contains('light-mode');
    const tickColor = isLight ? 'rgba(13, 19, 33, 0.7)' : 'rgba(255,255,255,0.7)';
    const fillColor = isLight ? '#378ADD' : '#60a5fa';
    quantityBarChartInstance = new Chart(qCtx.getContext('2d'), {
        type: 'bar',
        data: { labels, datasets: [{ data: dVals, backgroundColor: fillColor, borderRadius: 4, barThickness: 18 }] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: (ctx) => intlCountries[ctx[0].dataIndex][0],
                        label: (ctx) => {
                            const raw = intlCountries[ctx[0].dataIndex][1];
                            return `${raw.toLocaleString()} courses (${ctx.raw.toFixed(1)}%)`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false, drawBorder: false },
                    ticks: { color: tickColor, font: { size: 10 } }
                },
                y: {
                    display: true,
                    beginAtZero: true,
                    max: 20,
                    grid: { color: isLight ? 'rgba(0,0,0,0.04)' : 'rgba(255,255,255,0.04)', drawBorder: false },
                    ticks: { color: tickColor, font: { size: 10 }, callback: v => v + '%' }
                }
            },
            layout: { padding: { top: 10, bottom: 0 } }
        }
    });
}

function updateDashboardExtras(data) {
    if (!data) return;
    const docs = data.documents || [];
    const total = docs.length || data.stats?.total || 1;
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    const setPct = (id, v) => { const el = document.getElementById(id); if (el) el.style.width = v; };

    let iitCount = 0, iiitCount = 0, nitCount = 0;
    const seen = { iit: new Set(), iiit: new Set(), nit: new Set() };
    docs.forEach(c => {
        const uni = (c.university || '').toUpperCase();
        const name = (c.name || '').toLowerCase();
        const key = name;
        if (/\bIIIT\b/.test(uni) || /\bIIIT\b/.test(c.university || '')) {
            if (!seen.iiit.has(key)) { iiitCount++; seen.iiit.add(key); }
        } else if (/\bIIT\b/.test(uni) && !/\bIIIT\b/.test(uni) && !/\bNIT\b/.test(uni)) {
            if (!seen.iit.has(key)) { iitCount++; seen.iit.add(key); }
        }
        if (/\bNIT\b/.test(uni)) {
            if (!seen.nit.has(key)) { nitCount++; seen.nit.add(key); }
        }
    });
    set('dash-iit-count', iitCount.toLocaleString());
    set('dash-iiit-count', iiitCount.toLocaleString());
    set('dash-nit-count', nitCount.toLocaleString());
    const instMax = Math.max(iitCount, iiitCount, nitCount, 1);
    setPct('dash-iit-bar', (iitCount / instMax * 100) + '%');
    setPct('dash-iiit-bar', (iiitCount / instMax * 100) + '%');
    setPct('dash-nit-bar', (nitCount / instMax * 100) + '%');

    const domainCounts = data.domain_counts || {};
    const freeCount = domainCounts['Free'] || 0;
    const ftaCount = domainCounts['Free to Audit'] || 0;
    const hvlcCount = domainCounts['High Value Low Cost'] || 0;
    set('dash-free-count', freeCount.toLocaleString());
    set('dash-fta-count', ftaCount.toLocaleString());
    set('dash-hvlc-count', hvlcCount.toLocaleString());

    const countryCounts = data.country_counts || {};
    const sortedCountries = Object.entries(countryCounts)
        .filter(([k]) => isValidCountry(k))
        .sort((a, b) => b[1] - a[1]);

    const indiaEntry = sortedCountries.find(([k]) => isSameCountry(k, 'India'));
    if (indiaEntry) {
        const [name, count] = indiaEntry;
        set('india-stat-count', count.toLocaleString());
        set('india-stat-pct', `${Math.round(count / total * 100)}% of catalog`);
    } else {
        set('india-stat-count', '—');
        set('india-stat-pct', 'No data');
    }

    const intlCountries = sortedCountries.filter(([k]) => !isSameCountry(k, 'India')).slice(0, 4);
    renderCountryBarChart(intlCountries, total);

    updateGlobeHighlight(countryCounts);
}

// ================================================================
//  CHARTS INIT
// ================================================================
function initCharts() {
    Chart.defaults.color = '#9499b0';
    Chart.defaults.borderColor = 'rgba(255,255,255,0.06)';
    Chart.defaults.font.family = "'Inter', sans-serif";

    const lCtx = document.getElementById('countryLineChart')?.getContext('2d');
    if (lCtx) {
        lineChart = new Chart(lCtx, {
            type: 'line',
            data: { labels: [], datasets: [{ label: 'Courses', data: [], borderColor: '#14b8a6', backgroundColor: 'rgba(20,184,166,0.10)', tension: 0.45, fill: true, pointBackgroundColor: '#14b8a6', pointRadius: 4, pointHoverRadius: 6 }] },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.04)' } },
                    x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { maxRotation: 45 } }
                }
            }
        });
    }

    const bCtx = document.getElementById('coursesBarChart')?.getContext('2d');
    if (bCtx) {
        barChart = new Chart(bCtx, {
            type: 'bar',
            data: { labels: [], datasets: [{ label: 'Courses', data: [], backgroundColor: 'rgba(20,184,166,0.75)', hoverBackgroundColor: '#14b8a6', borderRadius: 5 }] },
            options: {
                indexAxis: 'y',
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: 'rgba(255,255,255,0.04)' } },
                    y: { ticks: { autoSkip: false }, grid: { display: false } }
                },
                plugins: { legend: { display: false } },
                onClick: (_, els) => {
                    if (els.length) applyFilter(barMode, barChart.data.labels[els[0].index]);
                }
            }
        });
    }

    const mCtx = document.getElementById('countryMapChart')?.getContext('2d');
    if (mCtx) {
        fetch('https://unpkg.com/world-atlas/countries-110m.json').then(r => r.json()).then(topo => {
            let countries = ChartGeo.topojson.feature(topo, topo.objects.countries).features;
            countries = countries.filter(d => d.properties.name !== 'Antarctica');
            mapChart = new Chart(mCtx, {
                type: 'choropleth',
                data: {
                    labels: countries.map(d => d.properties.name),
                    datasets: [{
                        label: 'Courses',
                        data: countries.map(d => ({ feature: d, value: 0 })),
                        borderColor: 'rgba(148,163,184,0.35)',
                        borderWidth: 1.2
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    showOutline: false, showGraticule: false,
                    layout: { padding: 0 },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: ctx => {
                                    const name = ctx.raw?.feature?.properties?.name || ctx.label || 'Unknown';
                                    const count = ctx.raw?.feature?._realCount ?? 0;
                                    return `${name}: ${Math.round(count)} courses`;
                                }
                            }
                        }
                    },
                    scales: {
                        projection: { axis: 'x', projection: 'equirectangular' },
                        color: {
                            axis: 'x',
                            interpolate: (v) => {
                                if (v <= 0) return 'rgba(251, 251, 251, 0.7)';
                                const t = Math.pow(v, 0.5);
                                const r = Math.round(147 - t * (147 - 67));
                                const g = Math.round(197 - t * (197 - 56));
                                const b = Math.round(253 - t * (253 - 202));
                                const a = (0.45 + t * 0.55).toFixed(2);
                                return `rgba(${r},${g},${b},${a})`;
                            },
                            missing: 'rgba(254, 2, 2, 0.7)'
                        }
                    }
                }
            });
            if (globalData) updateMapChart(globalData.country_counts);
        }).catch(() => { });
    }

    document.querySelectorAll('#bar-toggle-pills button').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#bar-toggle-pills button').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            barMode = btn.dataset.val;
            updateBarChart();
        });
    });

    document.getElementById('clear-filter')?.addEventListener('click', () => resetCountrySelection());
}

// ================================================================
//  DATA UPDATES
// ================================================================
function updateCards(stats) {
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set('total-count', stats.total || 0);
}

function updateBarChart(animate = true) {
    if (!barChart || !globalData) return;
    const src = barMode === 'domain' ? globalData.domain_counts : globalData.country_counts;
    let entries = Object.entries(src || {}).sort((a, b) => b[1] - a[1]);
    if (barMode === 'country') entries = entries.slice(0, 12);
    barChart.data.labels = entries.map(e => e[0]);
    barChart.data.datasets[0].data = entries.map(e => e[1]);
    if (animate) barChart.update(); else barChart.update('none');
}

function isValidCountry(k) {
    if (!k) return false;
    const s = String(k).trim().toLowerCase();
    return s !== '' && s !== 'undefined' && s !== 'unknown' && s !== 'null' && !s.startsWith('not found');
}

function updateLineChart(countryCounts, animate = true) {
    if (!lineChart) return;
    const sorted = Object.entries(countryCounts || {})
        .filter(([k]) => isValidCountry(k))
        .sort((a, b) => b[1] - a[1])
        .slice(0, 20);
    countryDataList = sorted;
    lineChart.data.labels = sorted.map(x => x[0]);
    lineChart.data.datasets[0].data = sorted.map(x => x[1]);
    if (animate) lineChart.update(); else lineChart.update('none');
}

function updateMapChart(countryCounts, animate = true) {
    if (!mapChart || !mapChart.data?.datasets?.[0]?.data?.length) return;
    mapChart.data.datasets[0].data.forEach(d => {
        const name = d.feature.properties.name;
        let val = 0;
        for (const [c, cnt] of Object.entries(countryCounts || {})) {
            if (c.toLowerCase().includes(name.toLowerCase()) || name.toLowerCase().includes(c.toLowerCase())) val += cnt;
        }
        d.feature._realCount = val;
        d.value = val;
    });

    const vals = mapChart.data.datasets[0].data.map(d => d.value).filter(v => v > 0);
    const commit = () => { if (animate) mapChart.update(); else mapChart.update('none'); };
    if (vals.length === 0) { commit(); return; }
    const maxSqrt = Math.sqrt(Math.max(...vals));
    mapChart.data.datasets[0].data.forEach(d => {
        d.value = d.value > 0 ? (Math.sqrt(d.value) / maxSqrt) * 100 : 0;
    });
    commit();
}

function updateCountryLeaderboard(countryCounts, containerId = 'country-list') {
    const el = document.getElementById(containerId);
    if (!el) return;
    const entries = Object.entries(countryCounts || {})
        .filter(([k]) => isValidCountry(k))
        .sort((a, b) => b[1] - a[1])
        .slice(0, 15);
    const max = entries[0]?.[1] || 1;
    el.innerHTML = entries.map(([name, cnt]) => `
        <div class="country-row" onclick="applyFilter('country','${name.replace(/'/g, "\\'")}')">
            <span class="c-flag">${getFlag(name)}</span>
            <span class="c-name">${name}</span>
            <div class="c-bar-wrap"><div class="c-bar" style="width:${Math.round(cnt / max * 100)}%"></div></div>
            <span class="c-count">${cnt}</span>
        </div>
    `).join('');
}

// ================================================================
//  DASHBOARD BAR-CHART FILTER (filtered detail panel)
// ================================================================
function applyFilter(type, value) {
    currentFilter = { type, value };
    if (type === 'country' && value) {
        handleCountryClick(value);
        return;
    }
    if (!value || !type) {
        resetCountrySelection();
        return;
    }
    // Domain filtering kept for legacy chart interactions
    const panel = document.getElementById('course-details-panel');
    const tbody = document.getElementById('course-details-body');
    if (!tbody || !globalData?.documents) return;
    const filtered = globalData.documents.filter(c => normalizeDomain(c.domain) === value);
    if (panel) panel.style.display = 'flex';
    if (document.getElementById('country-detail-name')) document.getElementById('country-detail-name').textContent = value;
    if (document.getElementById('country-detail-count')) document.getElementById('country-detail-count').textContent = `${filtered.length} course${filtered.length === 1 ? '' : 's'}`;
    if (document.getElementById('country-detail-flag')) document.getElementById('country-detail-flag').textContent = '🔬';

    const qsRank = c => c.qs ? String(c.qs) : (c.has_qs_badge ? 'Yes' : 'No');
    const nirfRank = c => c.nirf ? String(c.nirf) : (c.has_nirf_badge ? 'Yes' : 'No');

    tbody.innerHTML = filtered.length === 0
        ? '<tr><td colspan="4" class="empty-state">No courses found</td></tr>'
        : filtered.map(c => `
            <tr>
                <td class="course-name-cell" title="${escHtml(c.name)}"><strong>${escHtml(c.name)}</strong></td>
                <td>${escHtml(c.university || '—')}</td>
                <td>${escHtml(qsRank(c))}</td>
                <td>${escHtml(nirfRank(c))}</td>
            </tr>`).join('');
}

// ================================================================
//  TAB FILTERS
// ================================================================
function populateSelect(selectId, values) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    const current = sel.value;
    const first = sel.querySelector('option');
    sel.innerHTML = '';
    if (first) sel.appendChild(first);
    [...values].filter(Boolean).sort().forEach(v => {
        const o = document.createElement('option');
        o.value = v; o.textContent = v;
        sel.appendChild(o);
    });
    sel.value = [...sel.options].some(o => o.value === current) ? current : (first ? first.value : 'all');
}

function refreshFilterOptions() {
    const cCountries = new Set();
    allCoursesData.forEach(c => { if (c.country) cCountries.add(c.country); });
    populateSelect('cf-country', cCountries);
    populateSelect('cf-domain', ALL_DOMAIN_LABELS);
}

function getFilteredCourseData() {
    const f = courseFilter;
    const q = f.search.trim().toLowerCase();
    return allCoursesData.filter(c => {
        if (f.country !== 'all' && c.country !== f.country) return false;
        if (f.domain !== 'all' && getDomainCategory(c.id) !== f.domain) return false;
        if (f.courseType !== 'all' && normalizeDomain(c.domain) !== f.courseType) return false;
        if (f.qs === 'yes' && !c.has_qs_badge) return false;
        if (f.qs === 'no' && c.has_qs_badge) return false;
        if (f.nirf === 'yes' && !c.has_nirf_badge) return false;
        if (f.nirf === 'no' && c.has_nirf_badge) return false;
        if (q && !`${c.name} ${c.university || ''} ${c.country || ''} ${c.domain || ''} ${getDomainCategory(c.id)} ${normalizeDomain(c.domain)}`.toLowerCase().includes(q)) return false;
        return true;
    });
}

function syncCourseFilters() {
    const f = courseFilter;
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
    set('cf-search', f.search); set('cf-course-type', f.courseType); set('cf-country', f.country); set('cf-domain', f.domain);
    set('cf-qs', f.qs); set('cf-nirf', f.nirf);
}

function applyCourseFilter() { currentPage = 1; renderCoursesPage(); }

function jumpToCourses(partial) {
    courseFilter = { search: '', country: 'all', domain: 'all', qs: 'any', nirf: 'any', courseType: 'all', ...partial };
    syncCourseFilters();
    switchTab('tab-courses');
    applyCourseFilter();
}

function initFilters() {
    // Legacy course-filters are no longer in the DOM; edX tabs/chips handle filtering.
    // Keep this function as a no-op so existing callers don't break.
}

// ================================================================
//  ALL COURSES — edX-style tabbed carousel
// ================================================================
const ALL_TYPE_PILLS = [
    "All", "Bachelor's Degree", "Master's Degree", "Post Graduate Diploma",
    "Post Graduate Certificate", "Diploma", "Certificate", "Free",
    "Free to Audit", "High Value Low Cost"
];

const ALL_DOMAIN_CHIPS = [
    "Featured", "Foundational", "Network Infrastructure", "System & Endpoint",
    "Cyber Forensics", "Data & Application", "Legal & Ethical",
    "Free", "Free to Audit", "High Value Low Cost"
];

function matchTypePill(course, pill) {
    if (pill === 'all' || pill === 'All') return true;
    const norm = normalizeDomain(course.domain);
    return norm === pill;
}

function matchDomainChip(course, chip) {
    if (chip === 'all' || chip === 'Featured') return true;
    return getDomainCategory(course.id) === chip;
}

function getEdxFilteredCourses() {
    const base = getFilteredCourseData();
    return base.filter(c => matchTypePill(c, edxFilterState.typePill) && matchDomainChip(c, edxFilterState.domainChip));
}

function getEdxCardBannerClass(course) {
    const cat = getDomainCategory(course.id).toLowerCase();
    if (cat.includes('cyber forensics') || cat.includes('network infrastructure') || cat.includes('system & endpoint')) return 'cyber';
    if (cat.includes('data & application')) return 'data';
    if (cat.includes('legal & ethical')) return 'business';
    if (cat.includes('foundational')) return 'ai';
    if (['Post Graduate Diploma', 'Post Graduate Certificate'].includes(normalizeDomain(course.domain))) return 'exec';
    return 'default';
}

function getEdxCardTag(course) {
    const norm = normalizeDomain(course.domain);
    if (['Post Graduate Diploma', 'Post Graduate Certificate'].includes(norm)) return 'Executive Education';
    if (norm === "Master's Degree") return "Master's";
    if (norm === "Bachelor's Degree") return "Bachelor's";
    if (norm === 'Certificate' || norm === 'Diploma') return 'Certificate';
    if (norm === 'Free to Audit') return 'Free to Audit';
    if (norm === 'High Value Low Cost') return 'High Value';
    if (norm === 'Free') return 'Free';
    return 'Trending';
}

function getProviderLogoInitials(name) {
    if (!name) return '?';
    const words = String(name).trim().split(/\s+/).filter(w => w.length > 1 && !/^(the|of|and|&|for|in)$/i.test(w));
    const firstLetters = words.slice(0, 2).map(w => w[0].toUpperCase());
    return firstLetters.join('') || name[0].toUpperCase();
}

function formatDuration(course) {
    if (course.duration) return String(course.duration).trim();
    const weeks = (course.id % 12) + 2; // stable synthetic fallback when no duration field
    return `${weeks} weeks to complete`;
}

function getEdxRelevanceTag(course) {
    if (course.has_qs_badge && course.has_nirf_badge) return { label: 'Dual Ranked', icon: '🏆' };
    if (course.has_qs_badge) return { label: 'QS Ranked', icon: '🌟' };
    if (course.has_nirf_badge) return { label: 'NIRF Ranked', icon: '🇮🇳' };
    if (course.country && ['India', 'United States', 'United Kingdom', 'Australia', 'Canada'].some(c => isSameCountry(c, course.country))) {
        return { label: 'Top Hub', icon: '🌐' };
    }
    return { label: 'Relevant', icon: '✨' };
}

function renderEdxCards() {
    const row = document.getElementById('edx-cards-row');
    const countEl = document.getElementById('edx-result-count');
    if (!row) return;

    const courses = getEdxFilteredCourses();
    if (countEl) countEl.textContent = `${courses.length.toLocaleString()} course${courses.length === 1 ? '' : 's'}`;

    if (courses.length === 0) {
        row.innerHTML = `<div class="edx-empty">
            <div style="font-size:2rem;margin-bottom:10px;">🔍</div>
            No courses match the selected filters.
        </div>`;
        return;
    }

    row.innerHTML = courses.map(c => {
        const bannerClass = getEdxCardBannerClass(c);
        const tag = getEdxCardTag(c);
        const provider = getProviderLogoInitials(c.university);
        const duration = formatDuration(c);
        const relevance = getEdxRelevanceTag(c);
        return `
        <article class="edx-card" onclick="showCourseModal('${c.id}')">
            <div class="edx-card-banner ${bannerClass}">
                <div class="edx-card-logo">
                    <span class="logo-initial">${escHtml(provider)}</span>
                    <span>${escHtml(c.university || '—')}</span>
                </div>
                <div class="edx-card-tag">${escHtml(tag)}</div>
            </div>
            <div class="edx-card-body">
                <h3 class="edx-card-title">${escHtml(c.name)}</h3>
                <div class="edx-card-meta">
                    <span class="edx-card-duration">⏱ ${escHtml(duration)}</span>
                    <span class="edx-card-relevance">${relevance.icon} ${escHtml(relevance.label)}</span>
                </div>
            </div>
            <div class="edx-card-footer">
                <button class="edx-card-btn" onclick="event.stopPropagation(); showCourseModal('${c.id}')">View Details</button>
            </div>
        </article>`;
    }).join('');
}

function setEdxTypePill(pill) {
    edxFilterState.typePill = pill;
    document.querySelectorAll('#course-type-pills .type-pill').forEach(b => {
        b.classList.toggle('active', b.dataset.type === pill);
    });
    renderEdxCards();
}

function setEdxDomainChip(chip) {
    edxFilterState.domainChip = chip;
    document.querySelectorAll('#domain-chips-scroll .domain-chip').forEach(b => {
        b.classList.toggle('active', b.dataset.domain === chip);
    });
    renderEdxCards();
}

function syncEdxFiltersFromLegacy() {
    // If legacy courseFilter has values, reflect them in the new pill bars.
    const f = courseFilter;
    if (f.courseType && f.courseType !== 'all' && ALL_TYPE_PILLS.includes(f.courseType)) {
        edxFilterState.typePill = f.courseType;
    }
    if (f.domain && f.domain !== 'all' && ALL_DOMAIN_CHIPS.includes(f.domain)) {
        edxFilterState.domainChip = f.domain;
    }
}

function initEdxControls() {
    const typePills = document.getElementById('course-type-pills');
    if (typePills) {
        typePills.addEventListener('click', e => {
            const btn = e.target.closest('.type-pill');
            if (btn) setEdxTypePill(btn.dataset.type || 'all');
        });
    }

    const domainChips = document.getElementById('domain-chips-scroll');
    if (domainChips) {
        domainChips.addEventListener('click', e => {
            const btn = e.target.closest('.domain-chip');
            if (btn) setEdxDomainChip(btn.dataset.domain || 'all');
        });
    }

    document.getElementById('edx-reset-filters')?.addEventListener('click', () => {
        edxFilterState = { typePill: 'all', domainChip: 'all' };
        courseFilter = { search: '', country: 'all', domain: 'all', qs: 'any', nirf: 'any', courseType: 'all' };
        setEdxTypePill('all');
        setEdxDomainChip('all');
    });
}

function scrollDomains(dx) {
    const el = document.getElementById('domain-chips-scroll');
    if (el) el.scrollBy({ left: dx, behavior: 'smooth' });
}

async function loadAllCourses(force = false) {
    const row = document.getElementById('edx-cards-row');
    if (allCoursesData.length > 0 && !force) { renderEdxCards(); return; }
    if (row) row.innerHTML = `<div class="edx-empty">Loading trending courses…</div>`;
    try {
        const res = await fetch(COURSES_JSON);
        const data = await res.json();
        allCoursesData = (Array.isArray(data) ? data : data.courses || []).sort((a, b) => parseInt(a.id || '9') - parseInt(b.id || '9'));
        refreshFilterOptions();
        syncEdxFiltersFromLegacy();
        setEdxTypePill(edxFilterState.typePill);
        setEdxDomainChip(edxFilterState.domainChip);
        renderEdxCards();
    } catch (e) {
        if (row) row.innerHTML = `<div class="edx-empty" style="color:var(--red);">Error loading courses.</div>`;
        console.error('loadAllCourses error:', e);
    }
}

function renderCoursesPage() {
    // Kept for compatibility with legacy callers; the edX grid is the live view.
    renderEdxCards();
}

function applyCourseFilter() {
    currentPage = 1;
    syncEdxFiltersFromLegacy();
    setEdxTypePill(edxFilterState.typePill);
    setEdxDomainChip(edxFilterState.domainChip);
    renderEdxCards();
}

function jumpToCourses(partial) {
    courseFilter = { search: '', country: 'all', domain: 'all', qs: 'any', nirf: 'any', courseType: 'all', ...partial };
    edxFilterState = { typePill: 'all', domainChip: 'all' };
    if (partial && partial.domain && ALL_DOMAIN_CHIPS.includes(partial.domain)) {
        edxFilterState.domainChip = partial.domain;
    }
    if (partial && partial.courseType && ALL_TYPE_PILLS.includes(partial.courseType)) {
        edxFilterState.typePill = partial.courseType;
    }
    setEdxTypePill(edxFilterState.typePill);
    setEdxDomainChip(edxFilterState.domainChip);
    switchTab('tab-courses');
}

// ================================================================
//  MODAL
// ================================================================
function buildCourseDetails(c) {
    const langRow = (c.pdf_table || []).find(r => r.attribute === 'Language');
    const rows = [
        { label: 'University', value: c.university },
        { label: 'Domain', value: c.domain },
        { label: 'Domain Category', value: getDomainCategory(c.id) },
        { label: 'Country', value: c.country },
        { label: 'Cost', value: c.cost },
        { label: 'Duration', value: c.duration },
        { label: 'Mode', value: c.mode },
        { label: 'Skills', value: c.skills },
        { label: 'QS Ranked', value: c.has_qs_badge ? 'Yes' : 'No' },
        { label: 'NIRF Ranked', value: c.has_nirf_badge ? 'Yes' : 'No' },
    ];
    if (langRow && langRow.original) rows.push({ label: 'Language', value: langRow.original });

    return `<div style="display:grid; grid-template-columns:minmax(120px, 30%) 1fr; gap:12px 16px;">
        ${rows.map(r => `
            <div style="color:var(--text-3); font-size:0.75rem; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; padding-top:4px;">${escHtml(r.label)}</div>
            <div style="color:var(--text-1); font-size:0.9rem; line-height:1.4;">${escHtml(r.value) || '—'}</div>
        `).join('')}
    </div>`;
}

async function showCourseModal(courseId, fallbackName, fallbackUni) {
    if (allCoursesData.length === 0) {
        try {
            const res = await fetch(COURSES_JSON);
            const data = await res.json();
            allCoursesData = Array.isArray(data) ? data : data.courses || [];
            refreshFilterOptions();
        } catch (e) { return; }
    }
    let c = allCoursesData.find(x => String(x.id) === String(courseId));
    if (!c && fallbackName) c = allCoursesData.find(x => x.name === fallbackName && (x.university || '') === (fallbackUni || ''));
    if (!c) { alert('Course not found.'); return; }

    document.getElementById('modal-course-title').textContent = c.name;
    document.getElementById('modal-body').innerHTML = buildCourseDetails(c);

    document.getElementById('course-modal').classList.add('open');
}

function recomputeAndRender() {
    const stats = computeStats(allCoursesData);
    const countryCounts = computeCountryCounts(allCoursesData);
    const domainCounts = computeDomainCounts(allCoursesData);
    globalData = { status: 'success', documents: allCoursesData, stats, country_counts: countryCounts, domain_counts: domainCounts };
    updateCards(stats);
    updateBarChart(false);
    updateLineChart(countryCounts, false);
    updateMapChart(countryCounts, false);
    updateCountryLeaderboard(countryCounts, 'country-list');
    updateDashboardExtras(globalData);
    applyCourseFilter();
    if (currentFilter.type) applyFilter(currentFilter.type, currentFilter.value);
}

function initModal() {
    document.getElementById('close-modal')?.addEventListener('click', () =>
        document.getElementById('course-modal').classList.remove('open'));
    document.getElementById('course-modal')?.addEventListener('click', e => {
        if (e.target === document.getElementById('course-modal'))
            document.getElementById('course-modal').classList.remove('open');
    });
}

// ================================================================
//  DATA FETCH FROM LOCAL JSON
// ================================================================
function computeStats(courses) {
    return { total: courses.length };
}

function computeCountryCounts(courses) {
    const counts = {};
    courses.forEach(c => {
        if (c.country && isValidCountry(c.country)) {
            counts[c.country] = (counts[c.country] || 0) + 1;
        }
    });
    return counts;
}

function computeDomainCounts(courses) {
    const counts = {};
    courses.forEach(c => {
        const cat = getDomainCategory(c.id);
        if (cat && cat !== 'Uncategorised') counts[cat] = (counts[cat] || 0) + 1;
    });
    return counts;
}

async function fetchData() {
    if (!globalData) document.body.dataset.loading = 'true';
    try {
        const res = await fetch(COURSES_JSON + '?v=' + Date.now());
        const data = await res.json();
        
        const lastMod = res.headers.get('Last-Modified');
        if (lastMod) {
            const dateObj = new Date(lastMod);
            const el = document.getElementById('last-updated-label');
            if (el) el.textContent = 'Last Updated: ' + dateObj.toLocaleString();
        }

        allCoursesData = (Array.isArray(data) ? data : data.courses || []).sort((a, b) => parseInt(a.id || '9') - parseInt(b.id || '9'));

        const stats = computeStats(allCoursesData);
        const countryCounts = computeCountryCounts(allCoursesData);
        const domainCounts = computeDomainCounts(allCoursesData);
        globalData = { status: 'success', documents: allCoursesData, stats, country_counts: countryCounts, domain_counts: domainCounts };

        const animate = firstDataFetch;
        firstDataFetch = false;
        _applyData(globalData, animate);
    } catch (e) {
        console.error('Data fetch error:', e);
    }
}

function _applyData(data, animate) {
    if (!data || data.status !== 'success') return;

    const statsHash    = JSON.stringify(data.stats);
    const countryHash  = JSON.stringify(data.country_counts);
    const barSrc       = barMode === 'domain' ? data.domain_counts : data.country_counts;
    const barHash      = JSON.stringify(barSrc);

    if (statsHash !== lastStatsHash) {
        updateCards(data.stats);
        lastStatsHash = statsHash;
    }
    if (barHash !== lastBarHash) {
        updateBarChart(animate);
        lastBarHash = barHash;
    }
    if (countryHash !== lastCountryHash) {
        updateLineChart(data.country_counts, animate);
        updateMapChart(data.country_counts, animate);
        updateCountryLeaderboard(data.country_counts, 'country-list');
        lastCountryHash = countryHash;
    }
    updateDashboardExtras(data);
    if (currentFilter.type) applyFilter(currentFilter.type, currentFilter.value);
    document.body.dataset.loading = 'false';
}

// ================================================================
//  ANALYTICS TAB
// ================================================================
let anCredentialChart = null;
let anPricingChart = null;
let anDomainChart = null;
let geoTableData = [];

const PALETTE = ['#6366f1', '#818cf8', '#f43f5e', '#1dda9f', '#f59e0b', '#06b6d4', '#ec4899', '#8b5cf6'];

function initAnalyticsSubTabs() {
    document.querySelectorAll('.asubtab').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.asubtab').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.atab-content').forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            const t = document.getElementById(btn.dataset.atab);
            if (t) t.classList.add('active');
        });
    });
    document.getElementById('an-country-search')?.addEventListener('input', e =>
        renderGeoTable(e.target.value.toLowerCase()));
}

function closeDrilldown(id) {
    const el = document.getElementById(id);
    if (el) { el.style.animation = 'slideDown 0.2s ease'; setTimeout(() => el.style.display = 'none', 180); }
}

function openDrilldown(panelId, titleId, tbodyId, title, rows) {
    const panel = document.getElementById(panelId);
    const titleEl = document.getElementById(titleId);
    const tbody = document.getElementById(tbodyId);
    if (!panel || !titleEl || !tbody) return;
    titleEl.textContent = title;
    tbody.innerHTML = rows;
    panel.style.display = 'block';
    panel.style.animation = 'slideUp 0.25s ease';
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function populateAnalyticsKPIs(d, stats, countryCounts) {
    const el = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
    const tot = stats?.total || 0;
    const indiaCount = Object.entries(countryCounts || {})
        .filter(([k]) => k.toLowerCase().includes('india'))
        .reduce((s, [, v]) => s + (Number(v) || 0), 0);
    const intlCount = Math.max(0, tot - indiaCount);
    const countryCnt = Object.keys(countryCounts || {}).filter(k => isValidCountry(k)).length;

    el('an-total', tot);
    el('an-indian', indiaCount);
    el('an-intl', intlCount);
    el('an-variants-sub', `${Object.values(d.variant_category || {}).reduce((s, v) => s + (Number(v) || 0), 0)} delivery variants`);
    el('an-indian-pct', `${tot ? ((indiaCount / tot) * 100).toFixed(1) : '—'}% of total catalog`);
    el('an-countries-count', `${countryCnt} countries represented`);
}

function populateInsightCards(d, globalData) {
    const container = document.getElementById('insight-cards-row');
    if (!container) return;

    const docs = globalData?.documents || [];
    const countryPivot = d.country_pivot || {};
    const domainPivot = d.domain_pivot || {};

    const topCountry = Object.entries(countryPivot).filter(([k]) => isValidCountry(k))
        .sort((a, b) => b[1] - a[1])[0];
    const topDomain = Object.entries(domainPivot).filter(([k]) => k && k !== 'Total')
        .sort((a, b) => (b[1].Total || 0) - (a[1].Total || 0))[0];

    const uniCounts = {};
    docs.forEach(r => { if (r.university) uniCounts[r.university] = (uniCounts[r.university] || 0) + 1; });
    const topUni = Object.entries(uniCounts).sort((a, b) => b[1] - a[1])[0];

    const insights = [
        { icon: '🌍', color: 'var(--blue)', label: 'Top Country', value: topCountry ? getFlag(topCountry[0]) + ' ' + topCountry[0] : '—', sub: topCountry ? `${topCountry[1]} courses` : '' },
        { icon: '🔬', color: 'var(--purple)', label: 'Top Domain', value: topDomain?.[0] || '—', sub: topDomain ? `${topDomain[1].Total || 0} courses` : '' },
        { icon: '🏛️', color: 'var(--blue)', label: 'Top University', value: topUni?.[0] || '—', sub: topUni ? `${topUni[1]} courses` : '' },
    ];

    container.innerHTML = insights.map(ins => `
        <div class="insight-card" style="border-top:3px solid ${ins.color};">
            <div class="insight-icon">${ins.icon}</div>
            <div class="insight-body">
                <div class="insight-label">${ins.label}</div>
                <div class="insight-value" style="color:${ins.color};">${ins.value}</div>
                <div class="insight-sub">${ins.sub}</div>
            </div>
        </div>`).join('');
}

function populateSplitVisual(indianPct) {
    const el = document.getElementById('an-split-visual');
    if (!el) return;
    const intlPct = 100 - indianPct;
    el.innerHTML = `
        <div style="margin-bottom:8px;display:flex;justify-content:space-between;">
            <span style="font-size:0.78rem;font-weight:700;color:var(--green);">🇮🇳 India ${indianPct.toFixed(1)}%</span>
            <span style="font-size:0.78rem;font-weight:700;color:var(--blue);">🌐 International ${intlPct.toFixed(1)}%</span>
        </div>
        <div style="height:16px;border-radius:20px;overflow:hidden;display:flex;">
            <div style="flex:${Math.round(indianPct)};background:var(--green);border-radius:20px 0 0 20px;"></div>
            <div style="flex:${Math.round(intlPct)};background:var(--blue);border-radius:0 20px 20px 0;"></div>
        </div>
        <div style="margin-top:12px;display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <div style="background:var(--green-bg);border-radius:10px;padding:12px;text-align:center;">
                <div style="font-size:1.4rem;font-weight:900;color:var(--green);">${indianPct.toFixed(1)}%</div>
                <div style="font-size:0.7rem;color:var(--text-3);font-weight:700;text-transform:uppercase;">Indian Catalog</div>
            </div>
            <div style="background:var(--blue-bg);border-radius:10px;padding:12px;text-align:center;">
                <div style="font-size:1.4rem;font-weight:900;color:var(--blue);">${intlPct.toFixed(1)}%</div>
                <div style="font-size:0.7rem;color:var(--text-3);font-weight:700;text-transform:uppercase;">International</div>
            </div>
        </div>`;
}

function populateCredentialChart(courseCategory) {
    const ctx = document.getElementById('an-credential-chart');
    if (!ctx) return;
    const entries = Object.entries(courseCategory || {}).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
    if (anCredentialChart) anCredentialChart.destroy();
    anCredentialChart = new Chart(ctx, {
        type: 'doughnut',
        data: { labels: entries.map(e => e[0]), datasets: [{ data: entries.map(e => e[1]), backgroundColor: PALETTE, borderColor: 'transparent', borderWidth: 0, hoverOffset: 10 }] },
        options: {
            responsive: true, maintainAspectRatio: false, cutout: '70%',
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: c => `${c.label}: ${c.raw} programs` } }
            },
            onClick: (e, els) => {
                if (!els.length) return;
                openAnalyticsDrilldownByCategory(entries[els[0].index][0]);
            }
        }
    });
    const legend = document.getElementById('an-credential-legend');
    if (legend) legend.innerHTML = entries.map(([label, val], i) => `
        <div class="an-legend-item" onclick="openAnalyticsDrilldownByCategory('${label.replace(/'/g, "\\'")}')">
            <div class="an-legend-dot" style="background:${PALETTE[i % PALETTE.length]}"></div>
            <div>
                <div class="an-legend-name">${escHtml(label)}</div>
                <div class="an-legend-val">${val} Courses</div>
            </div>
        </div>`).join('');
}

function populatePricingChart(pricingCategory) {
    const ctx = document.getElementById('an-pricing-chart');
    if (!ctx) return;
    const entries = Object.entries(pricingCategory || {}).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
    if (anPricingChart) anPricingChart.destroy();
    anPricingChart = new Chart(ctx, {
        type: 'bar',
        data: { labels: entries.map(e => e[0]), datasets: [{ label: 'Courses', data: entries.map(e => e[1]), backgroundColor: 'rgba(241,107,107,0.8)', hoverBackgroundColor: '#f16b6b', borderRadius: 8, borderSkipped: false }] },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { display: false }, ticks: { font: { size: 12, weight: '600' }, maxRotation: 30 } },
                y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { precision: 0 } }
            },
            animation: { duration: 900, easing: 'easeOutQuart' },
            onClick: (e, els) => {
                if (!els.length) return;
                const label = entries[els[0].index][0];
                const kw = label.split(' ')[0].toLowerCase();
                jumpToCourses({ search: kw });
            }
        }
    });
}

function populateAnTopCountries(countryPivot) {
    const el = document.getElementById('an-top-countries');
    if (!el) return;
    const entries = Object.entries(countryPivot || {}).filter(([k]) => isValidCountry(k))
        .sort((a, b) => b[1] - a[1]).slice(0, 5);
    const max = entries[0]?.[1] || 1;
    el.innerHTML = entries.map(([name, cnt], i) => `
        <div class="an-hub-row" onclick="geoRowDrilldown('${name.replace(/'/g, "\\'")}', ${cnt})" title="Click to see courses">
            <div class="an-hub-rank">${i + 1}</div>
            <div class="an-hub-name">${getFlag(name)} ${escHtml(name)}</div>
            <div class="an-hub-bar-wrap"><div class="an-hub-bar" style="width:${Math.round(cnt / max * 100)}%"></div></div>
            <div class="an-hub-count">${cnt}</div>
        </div>`).join('');
}

function renderGeoTable(search = '') {
    const tbody = document.getElementById('an-country-tbody');
    if (!tbody) return;
    const total = geoTableData.reduce((s, [, v]) => s + v, 0) || 1;
    const max = geoTableData[0]?.[1] || 1;
    const rows = search ? geoTableData.filter(([k]) => k.toLowerCase().includes(search)) : geoTableData;

    tbody.innerHTML = rows.length === 0
        ? `<tr><td colspan="5" style="text-align:center;color:var(--text-3);padding:24px;">No results</td></tr>`
        : rows.map(([name, cnt], i) => `
            <tr class="clickable-row" onclick="geoRowDrilldown('${name.replace(/'/g, "\\'")}', ${cnt})" title="Click to see courses">
                <td><span class="geo-rank">${(i + 1).toString().padStart(2, '0')}</span></td>
                <td><span style="font-size:1.1rem;margin-right:8px;">${getFlag(name)}</span><strong>${escHtml(name)}</strong></td>
                <td style="text-align:center;"><span class="geo-volume-badge">${cnt}</span></td>
                <td style="text-align:right;"><span class="geo-share">${((cnt / total) * 100).toFixed(1)}%</span></td>
                <td><div class="geo-prog-wrap"><div class="geo-prog-bar" style="width:${Math.round(cnt / max * 100)}%"></div></div></td>
            </tr>`).join('');
}

function isSameCountry(a, b) {
    if (!a || !b) return false;
    const al = String(a).trim().toLowerCase();
    const bl = String(b).trim().toLowerCase();
    if (!al || !bl) return false;
    return al === bl || al.includes(bl) || bl.includes(al);
}

function geoRowDrilldown(countryName, cnt) {
    const sourceData = allCoursesData.length > 0 ? allCoursesData : (globalData?.documents || []);
    const matches = sourceData.filter(r => isSameCountry(r.country, countryName));
    const rows = matches.length ? matches.map((r, i) => `<tr>
        <td style="color:var(--text-3);">${i + 1}</td>
        <td class="course-name-cell" style="font-weight:600;" title="${escHtml(r.name || r.course_name || '')}">${escHtml(r.name || r.course_name || '—')}</td>
        <td style="color:var(--text-2);">${escHtml(r.university || '—')}</td>
        <td>${escHtml(r.domain || '—')}</td>
    </tr>`).join('')
        : `<tr><td colspan="4" style="text-align:center;color:var(--text-3);padding:20px;">No course-level data yet</td></tr>`;

    openDrilldown('geo-drilldown', 'geo-drilldown-title', 'geo-drilldown-tbody',
        `${getFlag(countryName)} ${countryName} — ${cnt} Courses`, rows);
}

function populateDomainTab(domainPivot) {
    const ctx = document.getElementById('an-domain-chart');
    const entries = Object.entries(domainPivot || {}).filter(([k]) => k && k !== 'Total')
        .sort((a, b) => (b[1].Total || 0) - (a[1].Total || 0));

    if (ctx) {
        if (anDomainChart) anDomainChart.destroy();
        anDomainChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: entries.map(([k]) => k),
                datasets: [{
                    label: 'Total Courses', data: entries.map(([, v]) => v.Total || 0),
                    backgroundColor: 'rgba(99,102,241,0.75)', hoverBackgroundColor: '#6366f1',
                    borderRadius: 8, borderSkipped: false
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { display: false }, ticks: { font: { size: 11, weight: '600' }, maxRotation: 30 } },
                    y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { precision: 0 } }
                },
                animation: { duration: 900, easing: 'easeOutQuart' },
                onClick: (e, els) => {
                    if (els.length) domainRowDrilldown(entries[els[0].index][0]);
                }
            }
        });
    }

    const tbody = document.getElementById('an-domain-tbody');
    if (tbody) tbody.innerHTML = entries.map(([name, v]) => {
        const total = v.Total || 0, indian = v.Indian || 0, intl = v.International || 0;
        const ip = total ? Math.round(indian / total * 100) : 50;
        return `<tr class="clickable-row" onclick="domainRowDrilldown('${name.replace(/'/g, "\\'")}')">
            <td><div style="font-weight:800;color:var(--text-1);">${escHtml(name)}</div>
                <div style="font-size:0.68rem;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin-top:2px;">Click to explore</div></td>
            <td style="text-align:center;"><span class="dom-total">${total}</span></td>
            <td style="text-align:center;"><span class="dom-indian">${indian}</span></td>
            <td style="text-align:center;"><span class="dom-intl">${intl}</span></td>
            <td><div class="dom-mix-bar"><div class="dom-mix-in" style="flex:${ip}"></div><div class="dom-mix-out" style="flex:${100 - ip}"></div></div></td>
        </tr>`;
    }).join('');
}

function domainRowDrilldown(domainName) {
    const sourceData = allCoursesData.length > 0 ? allCoursesData : (globalData?.documents || []);
    const matches = sourceData.filter(r => normalizeDomain(r.domain || '') === domainName);
    const rows = matches.length ? matches.map((r, i) => `<tr>
        <td style="color:var(--text-3);">${i + 1}</td>
        <td class="course-name-cell" style="font-weight:600;" title="${escHtml(r.name || r.course_name || '')}">${escHtml(r.name || r.course_name || '—')}</td>
        <td>${escHtml(r.university || '—')}</td>
        <td>${escHtml(r.country || '—')}</td>
    </tr>`).join('')
        : `<tr><td colspan="4" style="text-align:center;color:var(--text-3);padding:20px;">No course-level data yet</td></tr>`;

    openDrilldown('dom-drilldown', 'dom-drilldown-title', 'dom-drilldown-tbody',
        `🔬 ${domainName} — Domain Deep-Dive`, rows);
}

function openAnalyticsDrilldownByCategory(catLabel) {
    jumpToCourses({ domain: catLabel });
}

function renderAnalytics(d) {
    const docs = globalData?.documents || [];
    const stats = globalData?.stats || {};
    const countryCounts = globalData?.country_counts || {};

    const effectiveCountryPivot = Object.keys(d.country_pivot || {}).length > 0
        ? d.country_pivot
        : Object.fromEntries(Object.entries(countryCounts).filter(([k]) => isValidCountry(k)));

    let effectiveDomainPivot = d.domain_pivot || {};
    if (Object.keys(effectiveDomainPivot).length === 0) {
        effectiveDomainPivot = {};
        allCoursesData.forEach(c => {
            const dom = normalizeDomain(c.domain || '');
            if (!dom || dom === 'Other') return;
            if (!effectiveDomainPivot[dom]) effectiveDomainPivot[dom] = { Total: 0, Indian: 0, International: 0 };
            effectiveDomainPivot[dom].Total++;
            if ((c.country || '').toLowerCase().includes('india')) effectiveDomainPivot[dom].Indian++;
            else effectiveDomainPivot[dom].International++;
        });
    }

    const effectiveCourseCategory = Object.keys(d.course_category || {}).length > 0
        ? d.course_category
        : (() => {
            const cc = {};
            allCoursesData.forEach(c => {
                const lvl = normalizeDomain(c.domain || '');
                if (lvl && lvl !== 'Other') cc[lvl] = (cc[lvl] || 0) + 1;
            });
            return cc;
        })();

    const effectivePricingCategory = Object.keys(d.pricing_category || {}).length > 0
        ? d.pricing_category
        : (() => {
            const pc = {};
            allCoursesData.forEach(c => {
                const cost = String(c.cost || '').toLowerCase();
                let bucket = 'Paid';
                if (cost === 'free') bucket = 'Free Courses';
                else if (cost.includes('audit')) bucket = 'Free to Audit';
                else if (cost.includes('low cost') || cost.includes('value')) bucket = 'High Value Low Cost';
                pc[bucket] = (pc[bucket] || 0) + 1;
            });
            return pc;
        })();

    populateAnalyticsKPIs(d, stats, countryCounts);
    populateInsightCards({ ...d, country_pivot: effectiveCountryPivot, domain_pivot: effectiveDomainPivot }, globalData);
    populateCredentialChart(effectiveCourseCategory);
    populatePricingChart(effectivePricingCategory);

    const realTotal = stats.total || Object.values(countryCounts).reduce((s, v) => s + v, 0) || 1;
    const indiaTotal = Object.entries(countryCounts)
        .filter(([k]) => k.toLowerCase().includes('india'))
        .reduce((s, [, v]) => s + (Number(v) || 0), 0);
    populateSplitVisual((indiaTotal / realTotal) * 100);

    populateAnTopCountries(effectiveCountryPivot);

    geoTableData = Object.entries(effectiveCountryPivot)
        .filter(([k]) => isValidCountry(k)).sort((a, b) => b[1] - a[1]);
    renderGeoTable();

    populateDomainTab(effectiveDomainPivot);

    console.log('[Analytics] OK - total:', realTotal, '| countries:', geoTableData.length, '| india:', indiaTotal);
}

// ================================================================
//  HELPERS
// ================================================================
function escHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function escJs(str) {
    if (!str) return '';
    return String(str).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

// ================================================================
//  INIT
// ================================================================
// app.js is loaded with `defer`, so the DOM is already ready here.
initTheme();
initTabs();
initGlobe();
initCharts();
initFilters();
initModal();
initAnalyticsSubTabs();
initEdxControls();

fetchData().then(() => renderAnalytics({}));

