"use strict";
let focusSequence,
  sessionInfo = {},
  timeline = [],
  cursor = 0,
  board = [],
  cumulative = 0;
const $ = (id) => document.getElementById(id);
const names = [
  "",
  "Baseline UDP",
  "Loss without SACK",
  "Loss with SACK",
  "A/B comparison",
  "SDN failover",
  "Static route failure",
];
const talking = {
  1: [
    "START negotiates file metadata and the ACK format before DATA flows.",
    "Selective Repeat bounds the sender to 32 slots; contiguous ACKs advance the base.",
    "FIN and CRC32 establish completion. Independent SHA-256 verifies the reconstructed file.",
  ],
  2: [
    "This run disables SACK, adaptive RTO and congestion control.",
    "Missing DATA blocks the contiguous window until retransmission fills the hole.",
    "The receiver still buffers later packets. Plain ACK mode also supports gap-based retransmission.",
  ],
  3: [
    "The receiver buffers out-of-order DATA and reports a cumulative base plus a 32-bit bitmap.",
    "Three distinct later-ACK reports can trigger a selective fast retry. A timeout remains the fallback.",
    "Karn’s rule avoids ambiguous RTT samples; RTO and cwnd respond to measured feedback.",
  ],
  4: [
    "Both variants send identical bytes and lose the same first attempts at the relay.",
    "Compare measured duration, goodput and extra sends. A single pair does not establish statistical superiority.",
    "Duplicate DATA arrivals are distinct from duplicate deliveries. The finalized file must match.",
  ],
  5: [
    "The red marker is the recorded controller port-down event on the active branch.",
    "Green route readiness follows OpenFlow barriers. The next useful ACK demonstrates application progress.",
    "The displayed recovery interval comes from event timestamps in this selected recorded trial.",
  ],
  6: [
    "Static mode keeps host traffic on its original path after the link cut.",
    "Application retries cannot repair a permanently disconnected network route.",
    "An expected failure is a successful experiment expectation, while the file transfer remains unsuccessful.",
  ],
};
let backendDone = false;
let queue = [],
  raw = [],
  paused = false,
  slow = true,
  nextAt = 0,
  origin = null,
  scenario = 0;
let route = "upper",
  broken = new Set(),
  activeAnimation = null;
let seenMilestones = new Set(),
  sampled = {},
  firstRetry = null,
  retryCount = 0;
let producer = {},
  results = {},
  latest = {},
  series = [],
  changing = false;
function blank() {
  return {
    sent: 0,
    drops: 0,
    retries: 0,
    ooo: 0,
    bytes: 0,
    rto: null,
    cwnd: null,
    total: (sessionInfo.packets || 32) * 1024,
  };
}
let view = blank();
const say = (text) => {
  $("live-narration").textContent = text;
};
async function request(path, body = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw Error(data.error);
  return data;
}
function error(exc) {
  $("notice").textContent = exc.message;
}

let nextSeq = 0,
  receiverBase = null,
  duplicates = null;
function clearBoard() {
  cumulative = 0;
  nextSeq = 0;
  receiverBase = null;
  duplicates = null;
  board = Array.from(
    { length: Math.min(sessionInfo.packets || 32, 32) },
    () => ({ state: "WAITING", retries: 0 }),
  );
}
function seek(position) {
  if (!timeline.length) return;
  const events = timeline,
    start = sessionInfo,
    clock = origin,
    done = backendDone,
    records = raw,
    counters = producer;
  reset(start);
  timeline = events;
  origin = clock;
  backendDone = done;
  raw = records;
  producer = counters;
  while (cursor < position) present(events[cursor++]);
  queue = events.slice(position);
  paused = true;
  $("scrub").max = events.length;
  $("scrub").value = position;
}
function advance() {
  if (!queue.length) return;
  cursor++;
  present(queue.shift());
  $("scrub").value = cursor;
}
const pivotal = (e) =>
  ["dropped_gap", "retransmit", "link_down", "recovery"].includes(e.event);
$("prev").onclick = () => seek(Math.max(0, cursor - 1));
$("jump").onclick = () => {
  const i = timeline.findIndex((e, i) => i >= cursor && pivotal(e));
  if (i >= 0) seek(i + 1);
};
$("scrub").onchange = () => seek(Number($("scrub").value));
document.addEventListener("keydown", (e) => {
  if (
    e.code === "Space" &&
    !["INPUT", "SELECT", "BUTTON"].includes(e.target.tagName)
  ) {
    e.preventDefault();
    (paused ? $("play") : $("pause")).click();
  }
});
function reset(event) {
  sessionInfo = event;
  timeline = [];
  cursor = 0;
  clearBoard();
  $("story").replaceChildren();
  $("scrub").value = $("scrub").max = 0;
  focusSequence = undefined;
  $("event-focus").textContent = "Awaiting first event";
  backendDone = false;
  queue = [];
  raw = [];
  origin = null;

  failoverRecords = [];
  activeAnimation?.cancel();
  $("packet").style.visibility = "hidden";
  $("cut-marker").setAttribute("visibility", "hidden");
  $("outstanding").setAttribute("visibility", "hidden");
  route = "upper";
  broken.clear();
  for (const branch of ["upper", "lower"]) $(branch).removeAttribute("stroke-dasharray");
  seenMilestones.clear();
  sampled = {};
  firstRetry = null;
  retryCount = 0;
  producer = {};
  results = {};
  latest = {};
  series = [];
  view = blank();
  paused = false;
  nextAt = 0;
  scenario = event.scenario || 0;
  $("integrity").textContent = "PENDING";
  $("lane").textContent = "CLIENT ↔ UDP WIRE ↔ SERVER";
  $("client-state").textContent = "CLIENT";
  $("server-state").textContent = "SERVER";
  $("bars").replaceChildren();
  $("status").textContent = "RECEIVING REAL DATA";
  $("comparison").hidden = scenario !== 4;
  $("verify").textContent = "Verification pending";
  $("frame").textContent = "No captured wire header in this session.";
  $("header").replaceChildren();
  $("mask").textContent = "SACK register —";
  $("network-mode").textContent =
    scenario >= 5
      ? "Recorded Mininet / OpenFlow 1.3 trial"
      : "Localhost C transfer / observed UDP relay. Diamond is a schematic in this mode.";
  $("talking").replaceChildren(
    ...(talking[scenario] || talking[1]).map((text) => {
      const li = document.createElement("li");
      li.textContent = text;
      return li;
    }),
  );
  for (const button of document.querySelectorAll("[data-scenario]")) {
    button.classList.toggle(
      "active",
      Number(button.dataset.scenario) === scenario,
    );
    button.setAttribute(
      "aria-pressed",
      String(Number(button.dataset.scenario) === scenario),
    );
  }
  $("upper").setAttribute("stroke", scenario >= 5 ? "#3fb950" : "#586069");
  $("lower").setAttribute("stroke", "#586069");
  $("route-status").textContent =
    scenario >= 5
      ? "Waiting for recorded route state"
      : "Localhost observation";
  renderRing();
  renderCounters();
  draw();
}
for (const button of document.querySelectorAll("[data-scenario]"))
  button.onclick = async () => {
    if (changing) return;
    changing = true;
    try {
      $("notice").textContent =
        "Preparing the selected real run or recorded trace…";
      await request("/api/scenario", {
        scenario: Number(button.dataset.scenario),
        packets: Number($("packets").value),
      });
    } catch (exc) {
      error(exc);
    } finally {
      changing = false;
    }
  };
$("play").onclick = () => {
  paused = false;
  nextAt = 0;
  if (activeAnimation) activeAnimation.play();
};
$("pause").onclick = () => {
  paused = true;
  if (activeAnimation) activeAnimation.pause();
};
$("step").onclick = () => {
  paused = true;
  advance();
};
$("speed").onchange = () => {
  slow = $("speed").value !== "instant";
  nextAt = 0;
};
$("stop").onclick = async () => {
  queue = [];
  paused = true;
  try {
    if (!backendDone) await request("/api/stop");
  } catch (exc) {
    error(exc);
  }
  $("status").textContent = "STOPPED";
};
$("run").onclick = () =>
  request("/api/start", {
    packets: Number($("packets").value),
    sack: $("sack").checked,
    adaptive_rto: $("adaptive").checked,
    cc: $("cc").checked,
    drop_rate: Number($("loss").value),
  }).catch(error);
$("inject").onclick = () => request("/api/inject-loss").catch(error);
$("load").onclick = () =>
  request("/api/replay-trial", {
    trial: $("trialPath").value || $("trials").value,
    follow: $("follow").checked,
    speed: 1,
  }).catch(error);
fetch("/api/trials")
  .then((r) => r.json())
  .then((d) =>
    $("trials").replaceChildren(...d.trials.map((t) => new Option(t, t))),
  )
  .catch(error);
function renderRing() {
  $("window-label").textContent =
    "Permanent packet IDs · showing #0–" +
    (board.length - 1) +
    " · client ACK covers " +
    cumulative +
    " packets";
  $("ring").replaceChildren(
    ...board.map((slot, n) => {
      const card = document.createElement("div");
      card.className =
        "slot board-" +
        slot.state.split(" ")[0] +
        (n === focusSequence ? " current-slot" : "");
      for (const text of [
        "PKT #" + n,
        n * 1024 + "–" + (n * 1024 + 1023) + " B",
        slot.state,
        slot.retries ? "Retries: " + slot.retries : "",
      ]) {
        const line = document.createElement("div");
        line.textContent = text;
        card.append(line);
      }
      return card;
    }),
  );
}
function renderCounters() {
  $("progress").textContent =
    Math.min(100, (view.bytes / view.total) * 100).toFixed(1) + "%";
  $("sent").textContent = view.sent;
  $("retry").textContent = view.drops + " / " + view.retries;
  $("buffered").textContent = view.ooo;
  $("transport").textContent =
    (view.rto === null ? "—" : view.rto.toFixed(0) + " ms") +
    " / " +
    (view.cwnd === null ? "—" : view.cwnd.toFixed(1));
}
function keyEvent(e) {
  if (
    [
      "session_end",
      "variant_start",
      "trial_metadata",
      "verification",
      "recorded_metrics",
      "recovery",
      "link_down",
      "route_ready",
      "dropped_gap",
    ].includes(e.event)
  )
    return true;
  if (e.event === "retransmit") {
    firstRetry ??= e.sequence;
    retryCount++;
    return (
      e.sequence === firstRetry || retryCount < 25 || retryCount % 16 === 0
    );
  }
  if (e.event === "frame")
    return (
      (e.wire_type !== 3 && e.wire_type !== 4 && e.wire_type !== 10) ||
      e.sequence < 8 ||
      e.sequence % 64 === 0
    );
  if (["send", "out_of_order", "gap_detected", "hole_filled"].includes(e.event))
    return e.sequence < 8 || e.sequence % 64 === 0;
  if (
    [
      "ring_snapshot",
      "ack_progress",
      "path_health",
      "rto_update",
      "cwnd_change",
    ].includes(e.event)
  ) {
    const bucket = Math.floor((e.monotonic_ns || 0) / 200000000);
    if (sampled[e.event] === bucket) return false;
    sampled[e.event] = bucket;
    return true;
  }
  return false;
}
function ingest(e) {
  if (e.event === "session_start") {
    reset(e);
    say(
      "Preparing " +
        (names[scenario] || "manual telemetry") +
        ". Every displayed transition is backed by a recorded event.",
    );
    return;
  }
  if (e.event === "session_end") backendDone = true;
  raw.push(e);
  if (raw.length > 1000) raw.shift();
  if (e.monotonic_ns && origin === null) origin = e.monotonic_ns;
  if (e.event === "variant_start") {
    producer = blank();
    sampled = {};
    firstRetry = null;
    retryCount = 0;
  }
  producer = { ...blank(), ...producer };
  if (e.event === "send") producer.sent++;
  if (e.event === "retransmit") {
    producer.sent++;
    producer.retries++;
  }
  if (e.event === "dropped_gap") producer.drops++;
  if (e.event === "out_of_order") producer.ooo++;
  if (
    ["rto_update", "send", "retransmit"].includes(e.event) &&
    e.value !== undefined
  )
    producer.rto = e.value;
  if (e.event === "cwnd_change") producer.cwnd = e.value;
  if (e.event === "ack_progress") producer.bytes = e.bytes;
  if (e.event === "trial_metadata") producer.total = e.file_bytes;
  e.view = { ...producer };
  const local = sessionInfo.packets <= 32 && scenario < 5;
  if (scenario === 5) {
    collectFailover(e);
    return;
  }
  const keep = local
      ? [
          "send",
          "ack_progress",
          "out_of_order",
          "retransmit",
          "dropped_gap",
          "variant_start",
          "verification",
          "session_end",
        ].includes(e.event) ||
        (e.event === "frame" &&
          ([2, 9].includes(e.wire_type) || (e.wire_type === 10 && e.sack_mask)))
      : keyEvent(e);
  if (keep) {
    queue.push(e);
    timeline.push(e);
    $("scrub").max = timeline.length;
  }
}
// Show equally many real sends on each side of the cut, irrespective of the
// recorded file offset. The trace clock and byte counters retain their values.
let failoverRecords = [];
function collectFailover(e) {
  if (["trial_metadata", "send", "retransmit", "link_down", "route_ready",
       "recovery", "recorded_metrics", "session_end"].includes(e.event))
    failoverRecords.push(e);
  if (e.event !== "session_end") return;

  const cut = failoverRecords.find(r => r.event === "link_down");
  const alternate = cut && failoverRecords.find(r => r.event === "route_ready" &&
    r.monotonic_ns > cut.monotonic_ns && r.path === "lower");
  const sends = failoverRecords.filter(r => r.event === "send");
  if (cut) {
    const last = sends.filter(r => r.monotonic_ns <= cut.monotonic_ns).at(-1);
    const base = Math.floor(cut.view.bytes / 1024);
    if (last && last.sequence >= base) cut.windowAtCut = [base, last.sequence];
  }
  const selected = new Set(failoverRecords.filter(r =>
    !["send", "retransmit", "link_down"].includes(r.event)));
  if (cut) selected.add(cut);
  const sample = records => {
    const count = Math.min(8, records.length);
    for (let i = 0; i < count; i++)
      selected.add(records[Math.round(i * (records.length - 1) / Math.max(1, count - 1))]);
  };
  sample(sends.filter(r => !cut || r.monotonic_ns < cut.monotonic_ns));
  if (alternate) {
    sample(sends.filter(r => r.monotonic_ns >= alternate.monotonic_ns));
    const retry = failoverRecords.find(r => r.event === "retransmit" &&
      r.monotonic_ns >= alternate.monotonic_ns);
    if (retry) selected.add(retry);
  }
  for (const record of failoverRecords) {
    if (selected.has(record)) timeline.push(record);
  }
  queue = timeline.slice();
  $("scrub").max = timeline.length;
  failoverRecords = [];
}

const stream = new EventSource("/api/stream");
stream.onmessage = (m) => ingest(JSON.parse(m.data));
stream.onerror = () =>
  ($("notice").textContent =
    "Connection interrupted. Waiting for the local backend to reconnect.");
function packet(label, red = false, reverse = false) {
  if (activeAnimation) activeAnimation.cancel();
  const points =
    route === "lower"
      ? [
          [65, 110],
          [200, 110],
          [380, 175],
          [560, 110],
          [695, 110],
        ]
      : [
          [65, 110],
          [200, 110],
          [380, 45],
          [560, 110],
          [695, 110],
        ];
  if (reverse) points.reverse();
  if (red) points.splice(3);
  $("packet-label").textContent = label + (red ? " ×" : "");
  $("packet").style.visibility = "visible";
  $("packet").querySelector("rect").style.stroke = red ? "#f85149" : "#58a6ff";
  activeAnimation = $("packet").animate(
    points.map(([x, y]) => ({
      transform: "translate(" + x + "px," + y + "px)",
    })),
    { duration: slow ? 650 : 180, fill: "forwards" },
  );
}
function frame(e) {
  $("header").replaceChildren(
    ...Array.from({ length: 24 }, (_, i) => {
      const d = document.createElement("div");
      d.className = "byte";
      const s = document.createElement("small");
      s.textContent = i;
      d.append(
        s,
        document.createTextNode(e.header_hex.slice(i * 2, i * 2 + 2)),
      );
      return d;
    }),
  );
  $("frame").textContent = JSON.stringify(e, null, 2);
  if (e.sack_mask !== undefined)
    $("mask").textContent =
      "SACK 0x" +
      e.sack_mask.toString(16).padStart(8, "0") +
      " | base " +
      e.sack_base;
}
function compare() {
  const a = results[2],
    b = results[3];
  if (!a || !b) return;
  $("bars").replaceChildren();
  for (const [key, label, unit] of [
    ["seconds", "Total time", "s"],
    ["goodput_mbps", "Payload goodput", "Mb/s"],
    ["fast_retries", "Fast retries", "DATA"],
    ["timeout_retries", "Timeout retries", "DATA"],
    ["duplicates", "Duplicate DATA arrivals", "packets"],
  ]) {
    const row = document.createElement("div");
    row.className = "measure";
    const title = document.createElement("span");
    title.textContent = label;
    row.append(title);
    const max = Math.max(a[key], b[key], 1);
    for (const [data, cls, name] of [
      [a, "", "Basic"],
      [b, "sack", "SACK"],
    ]) {
      const cell = document.createElement("div");
      cell.textContent = name + " " + data[key] + " " + unit;
      const bar = document.createElement("div");
      bar.className = "bar " + cls;
      bar.style.width = (data[key] / max) * 100 + "%";
      cell.append(bar);
      row.append(cell);
    }
    $("bars").append(row);
  }
  const note = document.createElement("p");
  note.textContent =
    "Both files verified against identical source bytes. Matching file hashes confirm correct reconstruction; duplicate DATA arrivals are counted separately.";
  $("bars").append(note);
}
function present(e) {
  view = { ...blank(), ...(e.view || view) };
  const seq = e.sequence;
  if (scenario === 5 && view.bytes > 0) {
    cumulative = Math.ceil(view.bytes / 1024);
    board.slice(0, cumulative).forEach(slot => slot.state = "ACKED ✓ RECEIVED & ACKED");
  }
  focusSequence = seq ?? (e.event === "gap_detected" ? e.base : undefined);
  const focus = [e.source, String(e.event || "record").replaceAll("_", " ")];
  if (focusSequence != null) focus.push("sequence #" + focusSequence);
  if (e.path) focus.push("path " + e.path);
  if (e.monotonic_ns && origin !== null)
    focus.push(
      "trace time " + ((e.monotonic_ns - origin) / 1e9).toFixed(3) + " s",
    );
  $("event-focus").textContent = focus.filter(Boolean).join("  ·  ");
  if (e.event === "variant_start") {
    $("integrity").textContent = "PENDING";
    say(
      "A/B run " +
        (e.variant === 2
          ? "A — no SACK, fixed timer"
          : "B — SACK, adaptive RTO and CC") +
        ". The source file is identical in both runs.",
    );
  }
  if (e.event === "trial_metadata") {
    $("notice").textContent =
      "Recorded trial: " +
      e.trial +
      ". Measured times refer to backend monotonic timestamps.";
    view.total = e.file_bytes;
  }
  if (e.event === "frame") {
    frame(e);
    const kind = e.wire_type;
    if (kind === 1 || kind === 8) {
      say(
        "STEP 1 — HANDSHAKE: Client sent START with a 24-byte header and 12-byte file metadata" +
          (kind === 8 ? " and SACK_CAPABLE." : ".") +
          " Waiting for the server reply.",
      );
      packet("START");
    } else if (kind === 2 || kind === 9) {
      say(
        "HANDSHAKE COMPLETE: The receiver acknowledged START" +
          (kind === 9 ? " and accepted SACK." : ".") +
          " DATA can now be pipelined.",
      );
      packet("START_ACK", false, true);
    } else if (kind === 5 || kind === 6) {
      say(
        "COMPLETION HANDSHAKE: FIN confirms the advertised file is complete and CRC-checked before the receiver finalizes its output.",
      );
      packet(kind === 5 ? "FIN" : "FIN_ACK", false, e.direction === "ack");
    } else
      packet(
        kind === 10 ? "SACK" : kind === 4 ? "ACK" : "DATA #" + seq,
        false,
        e.direction === "ack",
      );
  }
  if (e.event === "send") {
    packet("DATA #" + seq);
    say(
      "PIPELINED DATA #" +
        seq +
        ": The sender retains this chunk until ACK coverage frees the slot. Current contiguous base is " +
        cumulative +
        ".",
    );
  }
  if (e.event === "dropped_gap") {
    packet("DROP #" + seq, true);
    say(
      "OBSERVED PACKET DROP #" +
        seq +
        ": " +
        (e.reason === "operator_injection"
          ? "The operator dropped this DATA datagram."
          : "The loss injector discarded this DATA attempt before delivery.") +
        " Later chunks may arrive while this gap holds the window.",
    );
  }
  if (e.event === "out_of_order") {
    say(
      "OUT-OF-ORDER #" +
        seq +
        ": The receiver buffered this chunk beyond its missing prefix. " +
        (scenario === 2
          ? "Plain ACK mode also retains buffered chunks."
          : "In SACK mode a bitmap reports buffered coverage to the sender."),
    );
  }
  if (e.event === "retransmit") {
    const fast = e.reason === "fast_gap";
    packet((fast ? "FAST RETRY #" : "TIMEOUT #") + seq, broken.has(route));
    say(
      (fast
        ? "FAST RETRANSMIT #" +
          seq +
          ": Three distinct later-ACK reports triggered a selective retry before the timer."
        : "TIMEOUT RETRY #" +
          seq +
          ": The ACK deadline expired, so the sender retries this missing chunk.") +
        (scenario === 6
          ? " The static route still points at the cut link."
          : ""),
    );
  }
  if (e.event === "link_down") {
    const path =
      (e.dpid === 1 && e.port === 3) || (e.dpid === 4 && e.port === 2) || e.dpid === 3 ? "lower" : "upper";
    broken.add(path);
    activeAnimation?.cancel();
    $("packet").style.visibility = "hidden";
    if (scenario === 5 && path === "upper") {
      $("cut-marker").setAttribute("visibility", "visible");
      $("cut-marker").setAttribute("transform", e.dpid === 4 || (e.dpid === 2 && e.port === 2)
        ? "translate(470 78)" : "translate(290 78)");
      if (e.windowAtCut) {
        const [first, last] = e.windowAtCut;
        $("outstanding").setAttribute("visibility", "visible");
        $("outstanding-label").textContent = "DATA #" + first + "–" + last + " · awaiting ACK progress";
      }
      $("lane").textContent = "Transfer active · waiting for an alternate route";
    }
    $(path).setAttribute("stroke-dasharray", "9 6");
    $(path).setAttribute("stroke", "#f85149");
    $("route-status").textContent = scenario === 5
      ? "LINK DOWN · transfer still open · waiting for lower-path rules"
      : "LINK DOWN " + path;
    say(
      "LINK FAILURE — " +
        path.toUpperCase() +
        ": Recorded OFPPortStatus reports a down port. " +
        (scenario === 6
          ? "Static routing keeps the original route."
          : "The controller must install a working alternate route."),
    );
  }
  if (e.event === "route_ready") {
    route = e.path;
    if (scenario === 5 && broken.size)
      $("lane").textContent = "Backup route installed · waiting for the first advancing ACK";
    $(route).setAttribute("stroke", broken.has(route) ? "#f85149" : "#3fb950");
    $("route-status").textContent =
      "ROUTE READY " + route + " — barrier confirmed";
    say(
      "ROUTE READY — " +
        route.toUpperCase() +
        ": OpenFlow barriers confirmed rule processing. Continued ACK progress will prove application recovery.",
    );
  }
  if (e.source === "controller") {
    latest[e.event] = e;
    $("sdn").textContent = JSON.stringify(latest, null, 2);
  }
  if (e.event === "recovery") {
    $("outstanding").setAttribute("visibility", "hidden");
    if (scenario === 5) $("lane").textContent = "Lower route carrying traffic · ACK prefix advancing";
    packet("USEFUL ACK", false, true);
    say(
      "APPLICATION RECOVERED: First useful ACK after route readiness. Recorded link-down → useful ACK interval " +
        e.link_down_to_ack_ms.toFixed(3) +
        " ms. Playback pauses do not affect this measurement.",
    );
    $("route-status").textContent =
      "ACK progress resumed via selected " + route + " branch · " + e.link_down_to_ack_ms.toFixed(3) + " ms";
  }
  if (e.event === "ack_progress" && scenario < 5 && scenario !== 2)
    say(
      "CONTIGUOUS PROGRESS: " +
        e.bytes.toLocaleString() +
        " bytes acknowledged. The sender advances past completed chunks and reuses its bounded ring.",
    );
  if (e.event === "verification") {
    $("verify").textContent = JSON.stringify(e, null, 2);
    view.bytes = e.file_bytes;
    view.total = e.file_bytes;
    view.sent = e.data_sends;
    view.retries = e.retransmits;
    view.ooo = e.out_of_order;
    $("integrity").textContent =
      e.sha256_match && e.crc32_match ? "MATCH" : "FAILED";
    say(
      "TRANSFER VERIFIED: " +
        e.file_bytes.toLocaleString() +
        " bytes reconstructed. Sender and receiver CRC32 " +
        (e.crc32_match ? "match" : "differ") +
        "; independent SHA-256 " +
        (e.sha256_match ? "matches." : "differs."),
    );
    e.fast_retries = timeline
      .slice(0, cursor)
      .filter(
        (r) =>
          r.variant === e.variant &&
          r.event === "retransmit" &&
          r.reason === "fast_gap",
      ).length;
    e.timeout_retries = e.retransmits - e.fast_retries;
    if (e.variant) {
      results[e.variant] = e;
      compare();
    }
  }
  if (e.event === "recorded_metrics") {
    const data = Array.isArray(e.metrics) ? e.metrics[0] : e.metrics;
    if (data) {
      $("verify").textContent = JSON.stringify(data, null, 2);
      view.sent = data.data_sends;
      view.retries = data.retransmits;
      view.ooo = data.out_of_order ?? view.ooo;
      if (data.success && data.sha256_match) {
        view.bytes = data.file_bytes;
        view.total = data.file_bytes;
        $("integrity").textContent = "MATCH";
        say(
          "RECORDED TRANSFER VERIFIED: " +
            data.file_bytes.toLocaleString() +
            " bytes completed with matching SHA-256 digests. The recorded latency is " +
            (data.link_down_to_progress_seconds * 1000).toFixed(3) +
            " ms.",
        );
      } else {
        $("integrity").textContent = "NO OUTPUT";
        say(
          "EXPECTED STATIC FAILURE: The transfer exhausted its bounded retries on a disconnected route. The file was not completed. The recorded experiment expectation was " +
            (data.expectation_met ? "met." : "not met."),
        );
      }
    }
  }
  if (e.event === "session_end") {
    $("status").textContent = e.ok
      ? "PLAYBACK COMPLETE"
      : e.cancelled
        ? "STOPPED"
        : "FAILED";
    if (e.error) {
      say("Run failed: " + e.error);
      $("notice").textContent = e.error;
    }
  }
  if (e.monotonic_ns && view.rto !== null) {
    series.push({
      time: (e.monotonic_ns - origin) / 1e9,
      rto: view.rto,
      cwnd: view.cwnd,
    });
    if (series.length > 2000) series.shift();
  }
  if (e.event === "variant_start") clearBoard();
  if (e.event === "send") nextSeq = Math.max(nextSeq, seq + 1);
  if (e.sack_base !== undefined) receiverBase = e.sack_base;
  if (e.event === "verification") duplicates = e.duplicates;
  const previousBase = cumulative;
  const slot = board[seq];
  let story = "";
  if (slot && seq >= cumulative) {
    if (e.event === "send") slot.state = "FLIGHT · IN FLIGHT";
    if (e.event === "dropped_gap") slot.state = "DROPPED ✕ IN TRANSIT";
    if (e.event === "out_of_order") slot.state = "BUFFERED · SERVER RECEIVED";
    if (e.event === "retransmit") {
      slot.retries++;
      slot.state = "RETRY · " + (e.reason === "fast_gap" ? "FAST" : "TIMEOUT");
    }
  }
  if (e.event === "frame" && e.wire_type === 10 && e.sack_mask) {
    const buffered = [];
    board.forEach((b, n) => {
      const bit = n - e.sack_base;
      if (
        n >= cumulative &&
        bit >= 0 &&
        bit < 32 &&
        (e.sack_mask >>> bit) & 1
      ) {
        b.state = "BUFFERED · SERVER GOT IT (SACK=1)";
        buffered.push("#" + n);
      }
    });
    story =
      "Server SACK: contiguous through #" +
      (e.sack_base - 1) +
      "; buffered " +
      buffered.join(", ") +
      " · mask 0x" +
      e.sack_mask.toString(16);
  }
  if (
    e.event === "ack_progress" ||
    (e.event === "verification" && e.sha256_match && e.crc32_match) ||
    (e.event === "recorded_metrics" && $("integrity").textContent === "MATCH")
  ) {
    cumulative = Math.max(
      cumulative,
      e.event === "ack_progress" ? e.base : Math.ceil(view.total / 1024),
    );
    board
      .slice(0, cumulative)
      .forEach((b) => (b.state = "ACKED ✓ RECEIVED & ACKED"));
    if (e.event === "ack_progress")
      story =
        "Client ACK coverage advanced through packet #" +
        (cumulative - 1) +
        ".";
  }
  if (
    e.event === "ack_progress" &&
    board.some((b, n) => b.retries && n >= previousBase && n < e.base)
  )
    story += " A retransmitted packet is now covered.";
  if ([2, 9].includes(e.wire_type))
    story =
      "START acknowledged. Session 0x" +
      e.transfer_id +
      (e.wire_type === 9 ? " negotiated SACK." : " uses plain ACKs.");
  if (story) say(story);
  if (
    pivotal(e) ||
    story ||
    ["verification", "route_ready", "recorded_metrics"].includes(e.event) ||
    [2, 9].includes(e.wire_type)
  ) {
    const item = document.createElement("li"),
      button = document.createElement("button"),
      at = cursor;
    button.textContent =
      (e.monotonic_ns && origin !== null
        ? ((e.monotonic_ns - origin) / 1e9).toFixed(3) + " s · "
        : "") + $("live-narration").textContent;
    item.className = "story-" + e.event;
    button.onclick = () => seek(at);
    item.append(button);
    $("story").append(item);
  }
  $("client-state").textContent =
    "Client · ACK base " +
    cumulative +
    " · next seq " +
    nextSeq +
    " · RTO " +
    (view.rto?.toFixed(0) ?? "—") +
    " ms · cwnd " +
    (view.cwnd ?? "—");
  $("server-state").textContent =
    "Server · last in order " +
    (receiverBase === null ? "—" : receiverBase - 1) +
    " · duplicates " +
    (duplicates ?? "—") +
    " · buffered cards " +
    board.filter((b) => b.state.startsWith("BUFFERED")).length +
    " · integrity " +
    $("integrity").textContent;
  const wire = $("lane");
  if (
    e.event === "send" ||
    e.event === "retransmit" ||
    e.event === "dropped_gap" ||
    e.event === "frame" ||
    e.event === "ack_progress"
  ) {
    const reverse = e.direction === "ack" || e.event === "ack_progress";
    const drop = e.event === "dropped_gap";
    const badge = document.createElement("span");
    badge.textContent = drop
      ? "✕ DROP #" + seq
      : story ||
        (e.event === "frame"
          ? "Wire frame " + e.wire_type + " · CRC32 0x" + e.crc32
          : e.event.toUpperCase() + " #" + seq);
    wire.replaceChildren(badge);
    badge.animate(
      [
        { transform: "translateX(" + (reverse ? "25%" : "-25%") + ")" },
        {
          transform:
            "translateX(" + (drop ? "0" : reverse ? "-25%" : "25%") + ")",
        },
      ],
      { duration: drop ? 450 : 120, fill: "forwards" },
    );
  }
  renderRing();
  renderCounters();
  draw();
}
function draw() {
  const c = $("chart"),
    g = c.getContext("2d");
  g.clearRect(0, 0, c.width, c.height);
  g.strokeStyle = "#30363d";
  for (let i = 0; i < 5; i++) {
    g.beginPath();
    g.moveTo(0, i * 35 + 10);
    g.lineTo(c.width, i * 35 + 10);
    g.stroke();
  }
  for (const [key, max, color] of [
    ["rto", 2000, "#58a6ff"],
    ["cwnd", 32, "#3fb950"],
  ]) {
    g.strokeStyle = color;
    g.beginPath();
    let started = false;
    const lo = series[0]?.time || 0,
      span = Math.max(1, (series.at(-1)?.time || 0) - lo);
    for (const p of series) {
      if (p[key] === null) continue;
      const x = ((p.time - lo) / span) * c.width,
        y = 150 - (p[key] / max) * 140;
      started ? g.lineTo(x, y) : g.moveTo(x, y);
      started = true;
    }
    g.stroke();
  }
}
function renderRaw() {
  if (!$("advanced").open) return;
  const filter = $("filter").value.toLowerCase();
  $("events").replaceChildren(
    ...raw
      .filter((e) => (e.event + " " + e.source).toLowerCase().includes(filter))
      .slice(-120)
      .reverse()
      .map((e) => {
        const tr = document.createElement("tr");
        for (const value of [
          e.monotonic_ns && origin !== null
            ? ((e.monotonic_ns - origin) / 1e9).toFixed(3)
            : "—",
          e.source,
          e.event,
          JSON.stringify(e),
        ]) {
          const td = document.createElement("td");
          td.textContent = value;
          tr.append(td);
        }
        return tr;
      }),
  );
}
setInterval(() => {
  $("position").textContent =
    (paused ? "PAUSED · " : "") + "Key events queued " + queue.length;
  if (paused || !queue.length || performance.now() < nextAt) return;
  const e = queue[0];
  advance();
  if ($("speed").value === "step" && pivotal(e)) paused = true;
  if ($("speed").value === "instant") {
    while (queue.length) advance();
    return;
  }
  const milestone =
    e.event === "retransmit" && e.reason === "fast_gap"
      ? "fast_retry"
      : e.event === "route_ready"
        ? e.event + e.path
        : e.event;
  const important = [
    "dropped_gap",
    "fast_retry",
    "out_of_order",
    "link_down",
    "route_readyupper",
    "route_readylower",
    "verification",
  ].includes(milestone);
  const hold = slow && important && !seenMilestones.has(milestone);
  if (hold) seenMilestones.add(milestone);
  const delay = scenario === 5
    ? ({link_down: 3400, route_ready: 1600, recovery: 1400, send: 760, retransmit: 850}[e.event] ?? 120)
    : hold || pivotal(e) ? 1200 : 120;
  nextAt = performance.now() + delay;
}, 20);
setInterval(renderRaw, 500);
$("filter").oninput = renderRaw;
reset({});
