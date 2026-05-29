const state = {
  threadId: null,
};

const formatCurrency = (value) => {
  if (typeof value !== "number") return "-";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
};

const el = (id) => document.getElementById(id);

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

function renderList(target, items, renderItem) {
  const node = el(target);
  node.innerHTML = "";
  if (!Array.isArray(items) || items.length === 0) {
    node.innerHTML = '<div class="empty">No records</div>';
    return;
  }
  items.forEach((item) => node.insertAdjacentHTML("beforeend", renderItem(item)));
}

async function loadStatus() {
  const button = el("refreshStatus");
  button.disabled = true;
  try {
    const status = await fetchJson("/api/account/status");
    renderStatus(status);
  } finally {
    button.disabled = false;
  }
}

function renderStatus(status) {
  const profile = status.profile || {};
  const margins = status.margins || {};
  const available = margins.available || {};
  const utilised = margins.utilised || {};
  const holdings = status.holdings || [];
  const positions = status.positions || [];
  const orders = status.orders || [];

  el("mcpState").textContent = status.mcp_enabled ? "Live MCP" : "Demo";
  el("mcpState").className = `badge ${status.mcp_enabled ? "live" : "demo"}`;
  el("profile").innerHTML = `
    <strong>${profile.user_name || "Unknown Account"}</strong>
    <span>${profile.email || "No email available"}</span>
    <span>${profile.broker || "ZERODHA"}</span>
  `;
  el("availableCash").textContent = formatCurrency(available.cash);
  el("utilisedMargin").textContent = formatCurrency(Object.values(utilised).reduce((sum, value) => sum + (Number(value) || 0), 0));

  el("holdingCount").textContent = String(holdings.length);
  renderList("holdings", holdings, (item) => `
    <div class="row">
      <div class="row-top"><strong>${item.tradingsymbol || "-"}</strong><span>${item.quantity ?? "-"} qty</span></div>
      <small>Avg ${formatCurrency(item.average_price)} · LTP ${formatCurrency(item.last_price)}</small>
    </div>
  `);

  el("positionCount").textContent = String(positions.length);
  renderList("positions", positions, (item) => `
    <div class="row">
      <div class="row-top"><strong>${item.tradingsymbol || "-"}</strong><span>${item.quantity ?? "-"} qty</span></div>
      <small>PNL ${formatCurrency(item.pnl)}</small>
    </div>
  `);

  el("orderCount").textContent = String(orders.length);
  renderList("orders", orders, (item) => `
    <div class="row">
      <div class="row-top"><strong>${item.tradingsymbol || item.order_id || "-"}</strong><span>${item.status || "-"}</span></div>
      <small>${item.order_id || ""} ${item.quantity ? `· ${item.quantity} qty` : ""}</small>
    </div>
  `);
}

function addMessage(role, text) {
  const messages = el("messages");
  const div = document.createElement("div");
  div.className = `message ${role}`;
  div.textContent = text;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

async function sendMessage(event) {
  event.preventDefault();
  const input = el("messageInput");
  const message = input.value.trim();
  if (!message) return;

  input.value = "";
  addMessage("user", message);
  const result = await fetchJson("/api/chat", {
    method: "POST",
    body: JSON.stringify({ message, thread_id: state.threadId }),
  });
  state.threadId = result.thread_id;
  el("threadId").textContent = state.threadId.slice(0, 8);
  addMessage("agent", result.message);
  await loadApprovals();
}

async function loadApprovals() {
  const approvals = await fetchJson("/api/actions");
  el("approvalCount").textContent = `${approvals.length} pending`;
  const container = el("approvals");
  container.innerHTML = "";

  if (!approvals.length) {
    container.innerHTML = '<div class="empty">No approvals waiting</div>';
    return;
  }

  approvals.forEach((action) => {
    container.insertAdjacentHTML("beforeend", `
      <div class="approval-card">
        <div>
          <strong>${action.summary}</strong>
          <div class="muted">${action.name} · ${action.risk} risk</div>
        </div>
        <pre>${JSON.stringify(action.arguments, null, 2)}</pre>
        <div class="approval-actions">
          <button class="secondary" data-action="reject" data-id="${action.id}">Reject</button>
          <button class="danger" data-action="approve" data-id="${action.id}">Approve</button>
        </div>
      </div>
    `);
  });
}

async function decideApproval(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) return;

  const approved = button.dataset.action === "approve";
  button.disabled = true;
  const result = await fetchJson(`/api/actions/${button.dataset.id}`, {
    method: "POST",
    body: JSON.stringify({ approved }),
  });
  addMessage("agent", result.message);
  await loadApprovals();
  await loadStatus();
}

el("refreshStatus").addEventListener("click", loadStatus);
el("chatForm").addEventListener("submit", sendMessage);
el("approvals").addEventListener("click", decideApproval);

addMessage("agent", "Connected. Ask me about your Zerodha account or prepare an order for approval.");
loadStatus();
loadApprovals();
