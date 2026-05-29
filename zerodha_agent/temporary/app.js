const state = { threadId: null };

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

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (character) => {
    switch (character) {
      case "&": return "&amp;";
      case "<": return "&lt;";
      case ">": return "&gt;";
      case '"': return "&quot;";
      case "'": return "&#39;";
      default: return character;
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
      html.push(`<h${level} class="md-heading">${formatInlineMarkdown(heading[2])}</h${level}>`);
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
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function renderList(target, items, renderItem) {
  const node = el(target);
  if (!node) return;
  node.innerHTML = "";
  if (!Array.isArray(items) || items.length === 0) {
    node.innerHTML = '<div class="empty">No records</div>';
    return;
  }
  items.forEach((item) => node.insertAdjacentHTML("beforeend", renderItem(item)));
}

async function loadStatus() {
  const button = el("refreshStatus");
  if (button) button.disabled = true;
  try {
    const status = await fetchJson("/api/account/status");
    if (status.error) {
      setHTML(
        "profile",
        `<span style="color:var(--red)">Failed to load: ${status.error}</span>`,
      );
      return;
    }
    renderStatus(status);
  } catch (err) {
    setHTML(
      "profile",
      `<span style="color:var(--red)">Failed to load: ${err.message}</span>`,
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
  renderList("holdings", holdings, (item) => `
    <div class="row">
      <div class="row-top">
        <strong>${item.tradingsymbol || "-"}</strong>
        <span>${item.quantity ?? "-"} qty</span>
      </div>
      <small>Avg ${formatCurrency(item.average_price)} · LTP ${formatCurrency(item.last_price)}</small>
    </div>
  `);

  setText("positionCount", String(positions.length));
  renderList("positions", positions, (item) => `
    <div class="row">
      <div class="row-top">
        <strong>${item.tradingsymbol || "-"}</strong>
        <span>${item.quantity ?? "-"} qty</span>
      </div>
      <small>PNL ${formatCurrency(item.pnl)}</small>
    </div>
  `);
}

function addMessage(role, text = "", options = {}) {
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
  const input = el("messageInput");
  if (!input) return;

  const message = input.value.trim();
  if (!message) return;

  input.value = "";
  addMessage("user", message);

  const sendBtn = el("sendBtn");
  if (sendBtn) sendBtn.disabled = true;

  const agentBubble = addMessage("agent", "", { markdown: true, streaming: true });
  let streamedText = "";

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

        let eventData;
        try {
          eventData = JSON.parse(raw);
        } catch {
          continue;
        }

        if (eventData.type === "token") {
          streamedText += eventData.data;
          rerenderAgentBubble(streamedText, true);
        } else if (eventData.type === "pending_action") {
          if (eventData.data?.thread_id) {
            state.threadId = eventData.data.thread_id;
            setText("threadId", state.threadId.slice(0, 8));
          }
          rerenderAgentBubble(
            "⏳ Action prepared - review the Approvals panel to confirm.",
            false,
          );
          await loadApprovals();
        } else if (eventData.type === "done") {
          if (eventData.thread_id) {
            state.threadId = eventData.thread_id;
            setText("threadId", state.threadId.slice(0, 8));
          }
          rerenderAgentBubble(streamedText, false);
        } else if (eventData.type === "error") {
          rerenderAgentBubble(`Error: ${eventData.data}`, false);
        }
      }
    }
  } catch (err) {
    if (agentBubble) {
      agentBubble.innerHTML = `<div class="message-content">Error: ${escapeHtml(err.message)}</div>`;
    }
  } finally {
    if (sendBtn) sendBtn.disabled = false;
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
      const argRows = Object.entries(action.arguments)
        .filter(([k]) => k !== "raw_instruction")
        .map(
          ([k, v]) => `
          <tr>
            <td class="arg-key">${k}</td>
            <td class="arg-val">${v}</td>
          </tr>`,
        )
        .join("");

      container.insertAdjacentHTML(
        "beforeend",
        `
        <div class="approval-card" id="approval-${action.id}">
          <div class="approval-header">
            <div>
              <strong>${action.summary}</strong>
              <div class="muted">
                ${action.name} ·
                <span class="risk-${action.risk}">${action.risk} risk</span>
              </div>
            </div>
          </div>
          <table class="arg-table">
            <tbody>${argRows}</tbody>
          </table>
          ${
            action.arguments.raw_instruction
              ? `
            <div class="raw-instruction muted">
              "${action.arguments.raw_instruction}"
            </div>`
              : ""
          }
          <div class="approval-actions">
            <button class="secondary" data-action="reject" data-id="${action.id}">
              Reject
            </button>
            <button class="danger" data-action="approve" data-id="${action.id}">
              Approve
            </button>
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
  const card = el(`approval-${button.dataset.id}`);
  if (!card) return;

  card.querySelectorAll("button").forEach((b) => (b.disabled = true));

  try {
    const result = await fetchJson(`/api/actions/${button.dataset.id}`, {
      method: "POST",
      body: JSON.stringify({ approved }),
    });

    addMessage(approved ? "agent success" : "agent", result.message);

    if (approved) {
      await loadStatus();
    }
    await loadApprovals();
  } catch (err) {
    addMessage("agent", `Approval error: ${err.message}`);
    card.querySelectorAll("button").forEach((b) => (b.disabled = false));
  }
}

el("refreshStatus")?.addEventListener("click", loadStatus);
el("chatForm")?.addEventListener("submit", sendMessage);
el("approvals")?.addEventListener("click", decideApproval);

addMessage(
  "agent",
  'Connected. Ask me about your account or say something like "buy 10 INFY" to prepare an order.',
);
loadStatus().catch((err) => console.warn("Initial status load failed:", err));
loadApprovals().catch((err) =>
  console.warn("Initial approvals load failed:", err),
);
