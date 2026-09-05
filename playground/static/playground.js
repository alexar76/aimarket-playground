(() => {
  "use strict";
  const $ = (selector) => document.querySelector(selector);
  const i18n = globalThis.PlaygroundI18n;
  const t = (key, fallback) => i18n?.t(key, fallback) ?? fallback;
  const format = (key, fallback, values = {}) => Object.entries(values).reduce(
    (text, [name, value]) => text.replace(`{${name}}`, String(value)), t(key, fallback)
  );
  const visitorKey = "aimarket-playground-visitor";
  function newVisitor() {
    if (globalThis.crypto?.randomUUID) return crypto.randomUUID();
    return `visitor-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }
  function loadVisitor() {
    try {
      const saved = localStorage.getItem(visitorKey);
      if (saved) return saved;
      const created = newVisitor();
      localStorage.setItem(visitorKey, created);
      return created;
    } catch (_) {
      return newVisitor();
    }
  }
  const visitor = loadVisitor();

  const runButton = $("#run");
  const deviceInput = $("#device");
  const statusDot = $("#status-dot");
  const statusLabel = $("#status-label");
  const steps = [...document.querySelectorAll(".trace-step")];
  let lastResult = null;
  let lastElapsed = 0;
  let lastError = null;
  let running = false;

  const messages = {
    "upstream_timeout": ["error.timeout", "The live services took too long to answer. No charge was made."],
    "upstream_unavailable": ["error.unavailable", "A live dependency is temporarily unavailable. Please retry in a moment."],
    "hub_returned_no_output": ["error.noOutput", "The Hub answered without a capability result."],
    "local_rate_limited": ["error.localRateLimited", "This browser has used its Playground hourly allowance. Continue locally with the CLI below."],
    "hub_rate_limited": ["error.hubRateLimited", "The live Hub/GAIA sandbox has reached its trial rate limit. Try later or continue locally with the CLI below."],
    "invalid_request": ["error.invalidRequest", "The request was rejected before reaching the network."],
    "invalid_device": ["error.invalidDevice", "Device ID may contain only letters, digits, dots, dashes, and underscores."],
  };

  function setState(state, label) {
    statusDot.className = state;
    statusLabel.textContent = label;
  }

  function resetTrace() {
    const waiting = {
      gaia: t("step.gaia.waiting", "Waiting for a device reading"),
      metis: t("step.metis.waiting", "Verification gate has not started"),
      receipt: t("step.receipt.waiting", "No receipt received yet"),
    };
    steps.forEach((step) => {
      step.className = "trace-step";
      step.querySelector("b").textContent = t("step.wait", "WAIT");
      step.querySelector("small").textContent = waiting[step.dataset.step];
    });
  }

  function markStep(name, state, detail) {
    const step = document.querySelector(`[data-step="${name}"]`);
    step.className = `trace-step ${state}`;
    step.querySelector("b").textContent = state === "done"
      ? t("step.done", "DONE")
      : state === "failed"
        ? t("step.fail", "FAIL")
        : state === "not-performed"
          ? t("step.notPerformed", "NOT CHECKED")
          : state === "rejected" ? t("step.rejected", "NOT VERIFIED") : t("step.live", "LIVE");
    if (detail) step.querySelector("small").textContent = detail;
  }

  function showError(code) {
    const displayCode = code === "hub_refused:429" ? "hub_rate_limited" : code;
    lastError = displayCode;
    $("#empty-state").hidden = true;
    $("#result-panel").hidden = true;
    $("#error-panel").hidden = false;
    const message = messages[displayCode];
    $("#error-message").textContent = message
      ? t(message[0], message[1])
      : displayCode?.startsWith("hub_refused:")
        ? t("error.hubRefused", "The Hub refused this trial invoke.")
        : t("error.generic", "The run could not be completed.");
    setState("error", t("status.failed", "FAILED"));
  }

  function renderResultPanel(body, elapsed) {
    lastResult = body;
    lastElapsed = elapsed;
    lastError = null;
    $("#empty-state").hidden = true;
    $("#error-panel").hidden = true;
    $("#result-panel").hidden = false;
    $("#result").textContent = JSON.stringify(body, null, 2);
    $("#metric-capability").textContent = body.capability_id || "—";
    $("#metric-score").textContent = body.verification?.verify_performed === false
      ? t("metric.notPerformed", "NOT RUN")
      : body.verification?.verify_score ?? t("metric.unavailable", "UNAVAILABLE");
    $("#metric-receipt").textContent = body.receipt_nonce ? `${body.receipt_nonce.slice(0, 14)}…` : t("metric.missing", "MISSING");
    const assessment = body.verification?.assessment?.trim();
    $("#assessment-card").hidden = !assessment;
    $("#assessment").textContent = assessment || "";
    $("#elapsed").textContent = `${elapsed} MS`;
    $("#run-id").textContent = `run ${body.run_id.slice(0, 12)}`;
    const monitor = $("#monitor-link");
    monitor.href = body.monitor_url || "https://monitor.modelmarket.dev/";
  }

  function showVerifying(body, elapsed) {
    renderResultPanel(body, elapsed);
    markStep("gaia", "done", t("step.gaia.done", "Live capability returned output"));
    markStep("metis", "running", format(
      "step.metis.running",
      "Metis is verifying in the background · {seconds}s",
      {seconds: Math.max(0, Math.round(elapsed / 1000))},
    ));
    markStep("receipt", body.receipt_verification?.verified === true ? "done" : "failed", body.receipt_verification?.verified === true
      ? t("step.receipt.done", "Ed25519 verified against origin key")
      : format("step.receipt.failed", "Receipt not verified · {reason}", {reason: body.receipt_verification?.reason || "unknown"}));
    $("#metric-score").textContent = t("metric.pending", "PENDING");
    runButton.querySelector("span").textContent = t("console.verifying", "Metis is verifying…");
    setState("running", t("status.verifying", "METIS · VERIFYING"));
  }

  function showResult(body, elapsed) {
    renderResultPanel(body, elapsed);
    markStep("gaia", "done", t("step.gaia.done", "Live capability returned output"));
    const metisStatus = body.verification?.status;
    const metisScore = body.verification?.verify_score ?? "—";
    let metisDetail;
    if (body.verification?.verified === true) {
      metisDetail = format("step.metis.done", "Plausible and verified · score {score}", {score: metisScore});
    } else if (body.verification?.assessment_verdict === "implausible") {
      metisDetail = format("step.metis.implausible", "Metis assessed the reading as implausible · score {score}", {score: metisScore});
    } else if (body.verification?.assessment_verdict === "unknown" && body.verification?.assessment_verified === true) {
      metisDetail = t("step.metis.unstructured", "Metis answer passed its verifier but did not contain a structured verdict");
    } else if (metisStatus === "timeout" && body.verification?.timeout_source === "metis") {
      metisDetail = t("step.metis.timeout.metis", "Metis ended its own run at the server time limit");
    } else if (metisStatus === "timeout") {
      metisDetail = t("step.metis.timeout.playground", "Playground stopped waiting at its outer time limit");
    } else if (metisStatus === "unavailable") {
      metisDetail = t("step.metis.unavailable", "Metis was unavailable over the network or HTTP");
    } else if (metisStatus === "error") {
      metisDetail = t("step.metis.error", "Metis ended the run with an internal error");
    } else if (metisStatus === "not_performed") {
      metisDetail = t("step.metis.notPerformed", "Metis answered, but the verifier did not run");
    } else if (metisStatus === "needs_clarification") {
      metisDetail = format("step.metis.clarification", "Metis requested clarification · score {score}", {score: metisScore});
    } else {
      metisDetail = format("step.metis.rejected", "Verification completed · score {score} below threshold", {score: metisScore});
    }
    const metisState = body.verification?.verified === true
      ? "done"
      : metisStatus === "not_performed"
        ? "not-performed"
        : ["timeout", "unavailable", "error"].includes(metisStatus) ? "failed" : "rejected";
    markStep("metis", metisState, metisDetail);
    markStep("receipt", body.receipt_verification?.verified === true ? "done" : "failed", body.receipt_verification?.verified === true
      ? t("step.receipt.done", "Ed25519 verified against origin key")
      : format("step.receipt.failed", "Receipt not verified · {reason}", {reason: body.receipt_verification?.reason || "unknown"}));
    const fullyVerified = body.receipt_verification?.verified === true && body.verification?.verified === true;
    setState(fullyVerified ? "success" : "warning", fullyVerified
      ? t("status.verified", "VERIFIED") : t("status.partial", "PARTIAL"));
  }

  async function runGoldenPath() {
    const deviceId = deviceInput.value.trim();
    if (!/^[A-Za-z0-9._-]{1,64}$/.test(deviceId)) {
      showError("invalid_device");
      deviceInput.focus();
      return;
    }
    running = true;
    lastResult = null;
    lastError = null;
    runButton.disabled = true;
    $("#playground").setAttribute("aria-busy", "true");
    runButton.querySelector("span").textContent = t("console.contacting", "Contacting network…");
    $("#empty-state").hidden = false;
    $("#result-panel").hidden = true;
    $("#error-panel").hidden = true;
    resetTrace(); markStep("gaia", "running", t("step.gaia.running", "Calling GAIA through AIMarket Hub"));
    setState("running", t("status.running", "RUNNING"));
    const started = performance.now();
    try {
      const response = await fetchWithTimeout("/api/playground/runs", {
        method: "POST",
        headers: {"content-type": "application/json", "X-Playground-Visitor": visitor},
        body: JSON.stringify({device_id: deviceId}),
      }, 15000);
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        showError(response.status === 429 ? "local_rate_limited" : "invalid_request");
        markStep("gaia", "failed", t("step.gaia.rejected", "Request was rejected safely"));
        return;
      }
      if (body.status === "failed") { showError(body.error_code); markStep("gaia", "failed", t("step.gaia.failed", "Live invoke did not complete")); return; }
      if (body.status === "verifying") showVerifying(body, Math.round(performance.now() - started));
      if (body.status === "completed") showResult(body, Math.round(performance.now() - started));
      else await pollRun(body.run_id, started);
    } catch (error) {
      showError("upstream_unavailable");
      markStep("gaia", "failed", t("step.gaia.failed", "Live invoke did not complete"));
    } finally {
      running = false;
      runButton.disabled = false;
      $("#playground").setAttribute("aria-busy", "false");
      runButton.querySelector("span").textContent = t("console.run", "Run real invoke");
    }
  }

  const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

  async function fetchWithTimeout(url, options, timeoutMs) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await fetch(url, {...options, signal: controller.signal});
    } finally {
      clearTimeout(timer);
    }
  }

  async function pollRun(runId, started) {
    const deadlineMs = 650000;
    while (performance.now() - started < deadlineMs) {
      await sleep(1000);
      const response = await fetchWithTimeout(`/api/playground/runs/${encodeURIComponent(runId)}`, {
        headers: {"X-Playground-Visitor": visitor},
      }, 15000);
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error("run_status_unavailable");
      const elapsed = Math.round(performance.now() - started);
      if (body.status === "running") continue;
      if (body.status === "verifying") {
        showVerifying(body, elapsed);
        continue;
      }
      if (body.status === "completed") {
        showResult(body, elapsed);
        return;
      }
      if (body.status === "failed") {
        showError(body.error_code);
        return;
      }
      throw new Error("unknown_run_status");
    }
    showError("upstream_timeout");
  }

  deviceInput.addEventListener("input", () => {
    document.querySelectorAll(".dynamic-device").forEach((node) => { node.textContent = `"${deviceInput.value}"`; });
  });
  deviceInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !runButton.disabled) runGoldenPath();
  });
  runButton.addEventListener("click", runGoldenPath);
  $("#retry").addEventListener("click", runGoldenPath);
  async function copyText(text, button) {
    const original = button.textContent;
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = t("copy.copied", "Copied");
    } catch (_) {
      button.textContent = t("copy.failed", "Copy failed");
    }
    setTimeout(() => { button.textContent = original; }, 1600);
  }
  $("#copy-result").addEventListener("click", async () => {
    if (lastResult) await copyText(JSON.stringify(lastResult, null, 2), $("#copy-result"));
  });
  $("#copy-command").addEventListener("click", async (event) => {
    await copyText("uvx create-aimarket-agent my-agent --kind data-provider --metis", event.currentTarget);
  });
  i18n?.onChange(() => {
    if (running && lastResult?.status === "verifying") {
      showVerifying(lastResult, lastElapsed);
    } else if (running) {
      runButton.querySelector("span").textContent = t("console.contacting", "Contacting network…");
      setState("running", t("status.running", "RUNNING"));
      resetTrace();
      markStep("gaia", "running", t("step.gaia.running", "Calling GAIA through AIMarket Hub"));
    } else if (lastResult?.status === "verifying") {
      showVerifying(lastResult, lastElapsed);
    } else if (lastResult) {
      showResult(lastResult, lastElapsed);
    } else if (lastError) {
      showError(lastError);
    } else {
      resetTrace();
      setState("", t("status.ready", "READY"));
      $("#run-id").textContent = t("status.noRun", "No run yet");
    }
  });
})();
