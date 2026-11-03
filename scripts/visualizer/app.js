"use strict";
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
    "Both variants send the same 1 MiB payload, with independent 10% loss draws.",
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
let ring = [],
  base = 0,
  route = "upper",
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
    total: 1048576,
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
let focusSequence;
function reset(event) {
  focusSequence = undefined;
  $("event-focus").textContent = "Awaiting first event";
  backendDone = false;
  queue = [];
  raw = [];
  origin = null;
  ring = [];
  base = 0;
  route = "upper";
  broken.clear();
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
  if (queue.length) present(queue.shift());
};
$("speed").onchange = () => {
  slow = $("speed").value === "slow";
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
    "base " +
    base +
    " … " +
    (base + 31) +
    " | DELIVERED IN ORDER < " +
    base +
    (scenario >= 5 ? " | event-derived recording" : " | sender state");
  $("ring").replaceChildren(
    ...Array.from({ length: 32 }, (_, i) => {
      const slot = ring[i],
        div = document.createElement("div");
      div.className = "slot " + (slot?.state || "");
      if (focusSequence === base + i) div.classList.add("current-slot");
      const num = document.createElement("b");
      num.textContent = slot?.sequence ?? base + i;
      div.append(num);
      div.append(
        document.createTextNode(
          slot
            ? {
                UNSENT: "UNSENT",
                IN_FLIGHT: "IN FLIGHT",
                SACKED_OO_BUFFERED: "BUFFERED",
                DROPPED_GAP: "MISSING",
                FAST_RETRANSMIT: "FAST RETRY",
                ACKED_CONTIGUOUS: "DELIVERED",
              }[slot.state] || slot.state
            : "—",
        ),
      );
      if (slot?.gap_reports)
        div.append(
          document.createElement("br"),
          document.createTextNode("gap " + slot.gap_reports + "/3"),
        );
      return div;
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
  if (keyEvent(e)) queue.push(e);
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
function mark(sequence, state) {
  const i = sequence - base;
  if (i >= 0 && i < 32)
    ring[i] = { sequence, state, gap_reports: ring[i]?.gap_reports || 0 };
}
function compare() {
  const a = results[2],
    b = results[3];
  if (!a || !b) return;
  $("bars").replaceChildren();
  for (const [key, label, unit] of [
    ["seconds", "Total time", "s"],
    ["goodput_mbps", "Payload goodput", "Mb/s"],
    ["retransmits", "Retransmissions", "DATA"],
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
  focusSequence = seq ?? (e.event === "gap_detected" ? e.base : undefined);
  const focus = [e.source, String(e.event || "record").replaceAll("_", " ")];
  if (focusSequence != null) focus.push("sequence #" + focusSequence);
  if (e.path) focus.push("path " + e.path);
  if (e.monotonic_ns && origin !== null)
    focus.push("trace time " + ((e.monotonic_ns - origin) / 1e9).toFixed(3) + " s");
  $("event-focus").textContent = focus.filter(Boolean).join("  ·  ");
  if (e.event === "variant_start") {
    ring = [];
    base = 0;
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
  if (
    e.source === "sender" &&
    e.base !== undefined &&
    e.event !== "ring_snapshot" &&
    e.base !== base
  ) {
    base = e.base;
    ring = Array.from(
      { length: 32 },
      (_, i) =>
        ring.find((s) => s?.sequence === base + i) || {
          sequence: base + i,
          state: "UNSENT",
          gap_reports: 0,
        },
    );
  }
  if (e.event === "ring_snapshot") {
    base = e.base;
    ring = e.slots.map((s) => ({ ...s }));
  }
  if (e.event === "send") {
    mark(seq, "IN_FLIGHT");
    packet("DATA #" + seq);
    say(
      "PIPELINED DATA #" +
        seq +
        ": The sender retains this chunk until ACK coverage frees the slot. Current contiguous base is " +
        base +
        ".",
    );
  }
  if (e.event === "dropped_gap") {
    mark(seq, "DROPPED_GAP");
    packet("DROP #" + seq, true);
    say(
      "OBSERVED PACKET DROP #" +
        seq +
        ": " +
        (e.reason === "operator_injection"
          ? "The operator dropped this DATA datagram."
          : "The sender’s configured random-loss simulation discarded this DATA attempt.") +
        " Later chunks may arrive while this gap holds the window.",
    );
  }
  if (e.event === "out_of_order") {
    mark(seq, "SACKED_OO_BUFFERED");
    say(
      "OUT-OF-ORDER #" +
        seq +
        ": The receiver buffered this chunk beyond its missing prefix. " +
        (scenario === 2
          ? "Plain ACK mode also retains buffered chunks."
          : "In SACK mode a bitmap reports buffered coverage to the sender."),
    );
  }
  if (e.event === "gap_detected") mark(e.base, "DROPPED_GAP");
  if (e.event === "retransmit") {
    const fast = e.reason === "fast_gap";
    mark(seq, fast ? "FAST_RETRANSMIT" : "IN_FLIGHT");
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
      (e.dpid === 1 && e.port === 3) || e.dpid === 3 ? "lower" : "upper";
    broken.add(path);
    $(path).setAttribute("stroke", "#f85149");
    $("route-status").textContent = "LINK DOWN " + path;
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
    say(
      "APPLICATION RECOVERED: First useful ACK after route readiness. Recorded link-down → useful ACK interval " +
        e.link_down_to_ack_ms.toFixed(3) +
        " ms. Playback pauses do not affect this measurement.",
    );
    $("route-status").textContent =
      "RECOVERED " + e.link_down_to_ack_ms.toFixed(3) + " ms";
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
  const e = queue.shift();
  present(e);
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
  nextAt = performance.now() + (hold ? 4000 : slow ? 1000 : 30);
}, 20);
setInterval(renderRaw, 500);
$("filter").oninput = renderRaw;
reset({});
