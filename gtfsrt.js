// 15-Minute Guelph. © 2026 Randy Harris. All rights reserved.
/* Minimal GTFS-realtime decoder (protobuf wire format), no dependencies.
   Decodes the fields 15-Minute Guelph uses from FeedMessage:
   vehicles, trip updates and alerts. */
(function (root) {
  "use strict";
  function Reader(buf) { this.b = buf; this.p = 0; }
  Reader.prototype.varint = function () {
    let r = 0, s = 0, b;
    do { b = this.b[this.p++]; if (s < 28) r |= (b & 0x7f) << s; else r += (b & 0x7f) * Math.pow(2, s); s += 7; } while (b & 0x80);
    return r >>> 0 === r ? r : r; };
  Reader.prototype.svarint = function () { const v = this.varint64(); return v; };
  Reader.prototype.varint64 = function () {   // returns a JS number (safe for timestamps / int32 delays)
    let lo = 0, hi = 0, s = 0, b;
    for (let i = 0; i < 10; i++) { b = this.b[this.p++]; if (s < 32) lo += (b & 0x7f) * Math.pow(2, s); else hi += (b & 0x7f) * Math.pow(2, s - 32); s += 7; if (!(b & 0x80)) break; }
    let n = lo + hi * 4294967296;
    if (n >= 9223372036854775808) n -= 18446744073709551616;   // negative int64 / int32 (two's complement)
    return n; };
  Reader.prototype.bytes = function () { const n = this.varint(); const v = this.b.subarray(this.p, this.p + n); this.p += n; return v; };
  Reader.prototype.float = function () { const v = new DataView(this.b.buffer, this.b.byteOffset + this.p, 4).getFloat32(0, true); this.p += 4; return v; };
  Reader.prototype.skip = function (wt) {
    if (wt === 0) this.varint64(); else if (wt === 1) this.p += 8; else if (wt === 2) { const n = this.varint(); this.p += n; } else if (wt === 5) this.p += 4;
    else throw new Error("unsupported wire type " + wt); };
  const td = typeof TextDecoder !== "undefined" ? new TextDecoder() : null;
  const str = u8 => td ? td.decode(u8) : Buffer.from(u8).toString("utf8");

  // generic message walker: spec maps field number -> handler(reader, wireType, out)
  function msg(u8, spec, out) {
    const r = new Reader(u8);
    while (r.p < u8.length) {
      const key = r.varint(), f = key >>> 3, wt = key & 7, h = spec[f];
      if (h) h(r, wt, out); else r.skip(wt);
    }
    return out;
  }
  const S = (k) => (r, wt, o) => { o[k] = str(r.bytes()); };
  const V = (k) => (r, wt, o) => { o[k] = r.varint64(); };
  const F = (k) => (r, wt, o) => { o[k] = r.float(); };
  const M = (k, spec, many) => (r, wt, o) => { const v = msg(r.bytes(), spec, {}); if (many) (o[k] = o[k] || []).push(v); else o[k] = v; };

  const TripDescriptor = { 1: S("trip_id"), 2: S("start_time"), 3: S("start_date"), 4: V("schedule_relationship"), 5: S("route_id"), 6: V("direction_id") };
  const VehicleDescriptor = { 1: S("id"), 2: S("label"), 3: S("license_plate") };
  const Position = { 1: F("latitude"), 2: F("longitude"), 3: F("bearing"), 4: (r, wt, o) => { r.p += 8; }, 5: F("speed") };
  const StopTimeEvent = { 1: V("delay"), 2: V("time"), 3: V("uncertainty") };
  const StopTimeUpdate = { 1: V("stop_sequence"), 4: S("stop_id"), 2: M("arrival", StopTimeEvent), 3: M("departure", StopTimeEvent), 5: V("schedule_relationship") };
  const TripUpdate = { 1: M("trip", TripDescriptor), 3: M("vehicle", VehicleDescriptor), 2: M("stop_time_update", StopTimeUpdate, true), 4: V("timestamp"), 5: V("delay") };
  const VehiclePosition = { 1: M("trip", TripDescriptor), 8: M("vehicle", VehicleDescriptor), 2: M("position", Position), 3: V("current_stop_sequence"), 7: S("stop_id"), 4: V("current_status"), 5: V("timestamp"), 6: V("congestion_level"), 9: V("occupancy_status") };
  const Translation = { 1: S("text"), 2: S("language") };
  const TranslatedString = { 1: M("translation", Translation, true) };
  const TimeRange = { 1: V("start"), 2: V("end") };
  const EntitySelector = { 1: S("agency_id"), 2: S("route_id"), 3: V("route_type"), 4: M("trip", TripDescriptor), 5: S("stop_id") };
  const Alert = { 1: M("active_period", TimeRange, true), 5: M("informed_entity", EntitySelector, true), 6: V("cause"), 7: V("effect"), 8: M("url", TranslatedString), 10: M("header_text", TranslatedString), 11: M("description_text", TranslatedString) };
  const FeedEntity = { 1: S("id"), 2: V("is_deleted"), 3: M("trip_update", TripUpdate), 4: M("vehicle", VehiclePosition), 5: M("alert", Alert) };
  const FeedHeader = { 1: S("gtfs_realtime_version"), 2: V("incrementality"), 3: V("timestamp") };
  const FeedMessage = { 1: M("header", FeedHeader), 2: M("entity", FeedEntity, true) };

  function decode(buf) { const u8 = buf instanceof Uint8Array ? buf : new Uint8Array(buf); const m = msg(u8, FeedMessage, {}); m.entity = m.entity || []; return m; }
  function text(ts) { if (!ts || !ts.translation) return ""; const en = ts.translation.find(t => !t.language || /^en/i.test(t.language)); return (en || ts.translation[0]).text || ""; }
  const api = { decode, text };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.GTFSRT = api;
})(typeof self !== "undefined" ? self : this);
