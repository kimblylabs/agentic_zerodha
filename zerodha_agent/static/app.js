const state = {
  threadId: null,
  isProcessing: false,
  voice: {
    enabled: false,
    armed: false,
    recognition: null,
    queryBuffer: "",
    finalizeTimer: null,
  },
};

const WAKE_PHRASE = "hey kimbly";
const WAKE_WORD_PATTERN =
  /\b(?:hey|hi|hello|ok|okay)\s+(?:kimbly|kimbly|kimbli|kimberly|kimberley)\b/;
const VOICE_QUERY_SILENCE_MS = 1800;

const formatCurrency = (value) => {
  if (typeof value !== "number") return "-";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
};

const el = (id) => document.getElementById(id);

const setText = (id, value) => {
  const node = el(id);
  if (!node) return;
  node.textContent = value;
};

const setHTML = (id, value) => {
  const node = el(id);
  if (!node) return;
  node.innerHTML = value;
};

const setInputValue = (value) => {
  const input = el("messageInput");
  if (!input) return;
  input.value = value;
};

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (character) => {
    switch (character) {
      case "&":
        return "&amp;";
      case "<":
        return "&lt;";
      case ">":
        return "&gt;";
      case '"':
        return "&quot;";
      case "'":
        return "&#39;";
      default:
        return character;
    }
  });
}

function formatInlineMarkdown(text) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
}

function renderMarkdown(rawText) {
  const lines = String(rawText).replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let listType = null;

  const closeList = () => {
    if (listType) {
      html.push(`</${listType}>`);
      listType = null;
    }
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      closeList();
      html.push('<div class="md-spacer"></div>');
      continue;
    }

    const heading = trimmed.match(/^(#{1,3})\s+(.*)$/);
    if (heading) {
      closeList();
      const level = Math.min(heading[1].length + 2, 5);
      html.push(
        `<h${level} class="md-heading">${formatInlineMarkdown(heading[2])}</h${level}>`,
      );
      continue;
    }

    const bullet = trimmed.match(/^[-*]\s+(.*)$/);
    if (bullet) {
      if (listType !== "ul") {
        closeList();
        html.push('<ul class="md-list">');
        listType = "ul";
      }
      html.push(`<li>${formatInlineMarkdown(bullet[1])}</li>`);
      continue;
    }

    const ordered = trimmed.match(/^\d+\.\s+(.*)$/);
    if (ordered) {
      if (listType !== "ol") {
        closeList();
        html.push('<ol class="md-list">');
        listType = "ol";
      }
      html.push(`<li>${formatInlineMarkdown(ordered[1])}</li>`);
      continue;
    }

    closeList();
    html.push(`<p class="md-paragraph">${formatInlineMarkdown(trimmed)}</p>`);
  }

  closeList();
  return html.join("");
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

function normalizeSpeechText(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function findWakePhrase(normalizedText) {
  const match = normalizedText.match(WAKE_WORD_PATTERN);
  if (!match || typeof match.index !== "number") {
    return null;
  }
  return {
    start: match.index,
    end: match.index + match[0].length,
    phrase: match[0],
  };
}

function updateVoiceStatus(mode, hintOverride = "") {
  const indicator = el("voiceIndicator");
  const title = el("voiceStateTitle");
  const hint = el("voiceStateHint");
  if (!indicator || !title || !hint) return;

  const states = {
    off: {
      title: "Voice Off",
      hint: "Click Enable Voice",
      className: "state-off",
    },
    unsupported: {
      title: "Voice Unavailable",
      hint: "Browser speech recognition not supported",
      className: "state-error",
    },
    idle: {
      title: "Ready",
      hint: `Say \"${WAKE_PHRASE}\"`,
      className: "state-idle",
    },
    wake: {
      title: "Wake Detected",
      hint: "Speak your query now",
      className: "state-wake",
    },
    capturing: {
      title: "Listening",
      hint: "Capturing your query",
      className: "state-capturing",
    },
    error: {
      title: "Mic Error",
      hint: "Retrying voice input",
      className: "state-error",
    },
  };

  const selected = states[mode] || states.off;
  title.textContent = selected.title;
  hint.textContent = hintOverride || selected.hint;
  indicator.classList.remove(
    "state-off",
    "state-idle",
    "state-wake",
    "state-capturing",
    "state-error",
  );
  indicator.classList.add(selected.className);
}

function clearVoiceFinalizeTimer() {
  if (state.voice.finalizeTimer) {
    clearTimeout(state.voice.finalizeTimer);
    state.voice.finalizeTimer = null;
  }
}

function setVoiceDraft(text) {
  const draft = String(text || "").trim();
  state.voice.queryBuffer = draft;
  setInputValue(draft);
}

function setProcessingState(isProcessing, source = "text") {
  state.isProcessing = isProcessing;

  const sendBtn = el("sendBtn");
  if (sendBtn) {
    sendBtn.disabled = isProcessing;
    sendBtn.classList.toggle("is-loading", isProcessing);
    sendBtn.textContent = isProcessing ? "Processing" : "Send";
  }

  const input = el("messageInput");
  if (input) {
    input.disabled = isProcessing;
    input.classList.toggle("is-disabled", isProcessing);
  }

  if (!state.voice.enabled) return;
  if (isProcessing) {
    updateVoiceStatus("capturing", "Processing your request...");
  } else if (source === "voice") {
    updateVoiceStatus("idle");
  }
}

function finalizeVoiceQuery() {
  clearVoiceFinalizeTimer();
  const query = state.voice.queryBuffer.trim();
  setVoiceDraft("");
  state.voice.armed = false;
  updateVoiceStatus(state.voice.enabled ? "idle" : "off");
  if (query) {
    setInputValue(query);
    updateVoiceStatus("capturing", "Sending your query...");
    void submitQuery(query, { source: "voice" });
  }
}

function handleVoiceFinalTranscript(transcript) {
  const normalized = normalizeSpeechText(transcript);
  if (!normalized) return;

  const wake = findWakePhrase(normalized);
  if (wake) {
    state.voice.armed = true;
    setVoiceDraft("");
    updateVoiceStatus("wake");

    const remaining = normalized.slice(wake.end).trim();
    if (remaining) {
      setVoiceDraft(remaining);
      updateVoiceStatus("capturing", "Keep speaking...");
      clearVoiceFinalizeTimer();
      state.voice.finalizeTimer = setTimeout(finalizeVoiceQuery, 400);
    }
    return;
  }

  if (!state.voice.armed) return;

  const combined = `${state.voice.queryBuffer} ${normalized}`.trim();
  setVoiceDraft(combined);
  updateVoiceStatus("capturing", "Keep speaking...");
  clearVoiceFinalizeTimer();
  state.voice.finalizeTimer = setTimeout(
    finalizeVoiceQuery,
    VOICE_QUERY_SILENCE_MS,
  );
}

function startVoiceRecognition() {
  const recognition = state.voice.recognition;
  if (!recognition) return;
  try {
    recognition.start();
    updateVoiceStatus("idle");
  } catch {
    // Ignore repeated starts while recognition is active.
  }
}

function stopVoiceRecognition() {
  const recognition = state.voice.recognition;
  if (!recognition) return;
  clearVoiceFinalizeTimer();
  setVoiceDraft("");
  state.voice.armed = false;
  try {
    recognition.stop();
  } catch {
    // Ignore stop races.
  }
  updateVoiceStatus("off");
}

function initVoiceControls() {
  const toggle = el("voiceToggle");
  const SpeechRecognition =
    window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!toggle || !SpeechRecognition) {
    updateVoiceStatus("unsupported");
    if (toggle) toggle.disabled = true;
    return;
  }

  const recognition = new SpeechRecognition();
  recognition.lang = "en-IN";
  recognition.continuous = true;
  recognition.interimResults = true;

  recognition.onresult = (event) => {
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const result = event.results[i];
      const transcript = result[0].transcript || "";
      const normalized = normalizeSpeechText(transcript);
      if (!result.isFinal) {
        if (!state.voice.armed) {
          const wake = findWakePhrase(normalized);
          if (wake) {
            state.voice.armed = true;
            setVoiceDraft("");
            updateVoiceStatus("wake", `Detected: ${wake.phrase}`);

            const remaining = normalized.slice(wake.end).trim();
            if (remaining) {
              setVoiceDraft(remaining);
              updateVoiceStatus("capturing", "Keep speaking...");
              clearVoiceFinalizeTimer();
              state.voice.finalizeTimer = setTimeout(
                finalizeVoiceQuery,
                VOICE_QUERY_SILENCE_MS,
              );
            }
            continue;
          }
        }

        if (state.voice.armed) {
          const interimWake = findWakePhrase(normalized);
          const draftText = interimWake
            ? normalized.slice(interimWake.end).trim()
            : normalized;
          setVoiceDraft(draftText);
          updateVoiceStatus(
            "capturing",
            `Heard: ${transcript.trim() || "..."}`,
          );
          clearVoiceFinalizeTimer();
          state.voice.finalizeTimer = setTimeout(
            finalizeVoiceQuery,
            VOICE_QUERY_SILENCE_MS,
          );
        } else if (state.voice.enabled) {
          updateVoiceStatus("idle", `Heard: ${transcript.trim() || "..."}`);
        }
        continue;
      }
      handleVoiceFinalTranscript(transcript);
    }
  };

  recognition.onend = () => {
    if (state.voice.enabled) {
      startVoiceRecognition();
    }
  };

  recognition.onerror = (event) => {
    if (state.voice.enabled) {
      updateVoiceStatus("error", `Mic error: ${event?.error || "retrying"}`);
    }
  };

  state.voice.recognition = recognition;
  updateVoiceStatus("off");

  toggle.addEventListener("click", () => {
    state.voice.enabled = !state.voice.enabled;
    toggle.textContent = state.voice.enabled ? "Disable Voice" : "Enable Voice";
    if (state.voice.enabled) {
      startVoiceRecognition();
    } else {
      stopVoiceRecognition();
    }
  });
}

function renderList(target, items, renderItem) {
  const node = el(target);
  if (!node) return;
  node.innerHTML = "";
  if (!Array.isArray(items) || items.length === 0) {
    node.innerHTML = '<div class="empty">No records</div>';
    return;
  }
  items.forEach((item) =>
    node.insertAdjacentHTML("beforeend", renderItem(item)),
  );
}

async function loadStatus() {
  const button = el("refreshStatus");
  if (button) button.disabled = true;
  try {
    const status = await fetchJson("/api/account/status");
    if (status.error) {
      console.error("Account status error:", status.error);
      setHTML(
        "profile",
        `<span style='color:var(--red)'>Failed to load account: ${status.error}</span>`,
      );
      return;
    }
    renderStatus(status);
  } catch (err) {
    console.warn("loadStatus failed:", err.message);
    setHTML(
      "profile",
      `<span style='color:var(--red)'>Failed to load: ${err.message}</span>`,
    );
  } finally {
    if (button) button.disabled = false;
  }
}

function renderStatus(status) {
  const profile = status.profile || {};
  const margins = status.margins || {};
  const available = margins.available || {};
  const utilised = margins.utilised || {};
  const holdings = status.holdings || [];
  const positions = Array.isArray(status.positions)
    ? status.positions
    : status.positions?.net || [];

  setHTML(
    "profile",
    `
    <strong>${profile.user_name || "Unknown Account"}</strong>
    <span>${profile.email || "No email available"}</span>
    <span>${profile.broker || "ZERODHA"}</span>
  `,
  );
  setText("availableCash", formatCurrency(available.cash));
  setText(
    "utilisedMargin",
    formatCurrency(
      Object.values(utilised).reduce((sum, v) => sum + (Number(v) || 0), 0),
    ),
  );

  setText("holdingCount", String(holdings.length));
  renderList(
    "holdings",
    holdings,
    (item) => `
    <div class="row">
      <div class="row-top">
        <strong>${item.tradingsymbol || "-"}</strong>
        <span>${item.quantity ?? "-"} qty</span>
      </div>
      <small>Avg ${formatCurrency(item.average_price)} · LTP ${formatCurrency(item.last_price)}</small>
    </div>
  `,
  );

  setText("positionCount", String(positions.length));
  renderList(
    "positions",
    positions,
    (item) => `
    <div class="row">
      <div class="row-top">
        <strong>${item.tradingsymbol || "-"}</strong>
        <span>${item.quantity ?? "-"} qty</span>
      </div>
      <small>PNL ${formatCurrency(item.pnl)}</small>
    </div>
  `,
  );
}

function addMessage(role, text, options = {}) {
  const messages = el("messages");
  if (!messages) return null;
  const div = document.createElement("div");
  div.className = `message ${role}`;
  if (options.markdown) {
    div.innerHTML = `
      <div class="message-content markdown">${renderMarkdown(text)}</div>
      ${options.streaming ? '<span class="cursor"></span>' : ""}
    `;
  } else {
    div.textContent = text;
  }
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
  return div;
}

async function sendMessage(event) {
  event.preventDefault();
  if (state.isProcessing) return;
  const input = el("messageInput");
  if (!input) return;
  const message = input.value.trim();
  if (!message) return;

  input.value = "";
  await submitQuery(message, { source: "text" });
}

async function submitQuery(message, { source = "text" } = {}) {
  if (state.isProcessing) return;
  addMessage("user", message);
  setProcessingState(true, source);

  const agentBubble = addMessage("agent", "", {
    markdown: true,
    streaming: true,
  });
  let streamedText = "";
  let rafId = null;
  let needsFrame = false;

  if (agentBubble) {
    agentBubble.innerHTML = `
      <div class="message-content thinking">
        <span class="thinking-label">Thinking</span>
        <span class="thinking-loader" aria-hidden="true"></span>
      </div>
    `;
  }

  try {
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, thread_id: state.threadId }),
    });

    if (!response.ok) {
      if (agentBubble) {
        agentBubble.innerHTML = `<div class="message-content">Error: ${escapeHtml(await response.text())}</div>`;
      }
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const rerenderAgentBubble = (rawText, streaming = true) => {
      if (!agentBubble) return;
      agentBubble.innerHTML = `
        <div class="message-content markdown">${renderMarkdown(rawText)}</div>
        ${streaming ? '<span class="cursor"></span>' : ""}
      `;
      const messages = el("messages");
      if (messages) messages.scrollTop = messages.scrollHeight;
    };

    const rerenderStreamingBubble = () => {
      if (!agentBubble) return;
      agentBubble.innerHTML = `
        <div class="message-content">${escapeHtml(streamedText).replace(/\n/g, "<br>")}</div>
        <span class="cursor"></span>
      `;
      const messages = el("messages");
      if (messages) messages.scrollTop = messages.scrollHeight;
    };

    const scheduleStreamingRender = () => {
      if (rafId) {
        needsFrame = true;
        return;
      }
      rafId = window.requestAnimationFrame(() => {
        rafId = null;
        rerenderStreamingBubble();
        if (needsFrame) {
          needsFrame = false;
          scheduleStreamingRender();
        }
      });
    };

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (!raw) continue;

        let event;
        try {
          event = JSON.parse(raw);
        } catch {
          continue;
        }

        if (event.type === "token") {
          streamedText += event.data;
          scheduleStreamingRender();
        } else if (event.type === "pending_action") {
          if (event.data?.thread_id) {
            state.threadId = event.data.thread_id;
            setText("threadId", state.threadId.slice(0, 8));
          }
          rerenderAgentBubble(
            "⏳ Action prepared - review the Approvals panel to confirm.",
            false,
          );
          await loadApprovals();
        } else if (event.type === "done") {
          if (rafId) {
            window.cancelAnimationFrame(rafId);
            rafId = null;
          }
          if (event.thread_id) {
            state.threadId = event.thread_id;
            setText("threadId", state.threadId.slice(0, 8));
          }
          rerenderAgentBubble(streamedText, false);
        } else if (event.type === "error") {
          rerenderAgentBubble(`Error: ${event.data}`, false);
        }
      }
    }
  } catch (err) {
    if (agentBubble) {
      agentBubble.innerHTML = `<div class="message-content">Error: ${escapeHtml(err.message)}</div>`;
    }
  } finally {
    setProcessingState(false, source);
    await loadApprovals();
  }
}

async function loadApprovals() {
  try {
    const approvals = await fetchJson("/api/actions");
    setText("approvalCount", `${approvals.length} pending`);
    const container = el("approvals");
    if (!container) return;
    container.innerHTML = "";

    if (!approvals.length) {
      container.innerHTML = '<div class="empty">No approvals waiting</div>';
      return;
    }

    approvals.forEach((action) => {
      container.insertAdjacentHTML(
        "beforeend",
        `
        <div class="approval-card">
          <div>
            <strong>${action.summary}</strong>
            <div class="muted">${action.name} · <span class="risk-${action.risk}">${action.risk} risk</span></div>
          </div>
          <pre>${JSON.stringify(action.arguments, null, 2)}</pre>
          <div class="approval-actions">
            <button class="secondary" data-action="reject" data-id="${action.id}">Reject</button>
            <button class="danger" data-action="approve" data-id="${action.id}">Approve</button>
          </div>
        </div>
      `,
      );
    });
  } catch (err) {
    console.warn("loadApprovals failed:", err.message);
  }
}

async function decideApproval(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) return;

  const approved = button.dataset.action === "approve";
  button.disabled = true;
  try {
    const result = await fetchJson(`/api/actions/${button.dataset.id}`, {
      method: "POST",
      body: JSON.stringify({ approved }),
    });
    addMessage("agent", result.message);
    await loadApprovals();
    await loadStatus();
  } catch (err) {
    addMessage("agent", `Approval error: ${err.message}`);
    button.disabled = false;
  }
}

// Event listeners
el("refreshStatus")?.addEventListener("click", loadStatus);
el("chatForm")?.addEventListener("submit", sendMessage);
el("approvals")?.addEventListener("click", decideApproval);

// Init
addMessage(
  "agent",
  "Connected. Ask me about your Zerodha account or prepare an order for approval.",
);
initVoiceControls();
loadStatus().catch((err) => console.warn("Initial status load failed:", err));
loadApprovals().catch((err) =>
  console.warn("Initial approvals load failed:", err),
);
