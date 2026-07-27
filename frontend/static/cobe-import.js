// ES module entry that imports COBE from a CDN and exposes it globally.
import createGlobe from 'https://cdn.skypack.dev/cobe';

window.createGlobe = createGlobe;
console.log('[Globe] COBE imported from CDN.');
