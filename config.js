// 15-Minute Guelph. © 2026 Randy Harris. All rights reserved.
// 15-Minute Guelph settings
// relay: the Cloudflare Worker that passes Guelph Transit's live feeds to the browser.
// This is the same Worker the Guelph Trip Planner uses (endpoints /vehicles, /tripupdates, /alerts).
// It only answers pages on randyharris1999-cloud.github.io and http://localhost:8000.
window.GUELPH_LIVE = {
  relay: "https://guelph-trip-planner.randyharris1999.workers.dev"
};
