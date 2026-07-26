// ES module entry that imports the local COBE build and exposes it globally.
import createGlobe from './cobe/dist/index.esm.js';

window.createGlobe = createGlobe;
console.log('[Globe] COBE imported from local build.');
