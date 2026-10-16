const apiEndpoint = document.querySelector("meta[name='matrix-api-url']").content;
const csrfToken = document.querySelector("meta[name='csrf-token']").content;

const state = {
  sessionId: localStorage.getItem("matrix_ai_session_id") || "",
  user: null,
  lastWorkflowRunId: null,
  apiCatalogFilter: "enabled",
};

const sessionPanel = document.querySelector("#session-panel");
const resultOutput = document.querySelector("#result-output");
const approveAllButton = document.querySelector("#approve-all-button");
const permissionsOutput = document.querySelector("#permissions-output");
const historyOutput = document.querySelector("#history-output");
const apiCatalogOutput = document.querySelector("#api-catalog-output");
const matrixConnectionOutput = document.querySelector("#matrix-connection-output");

function setStatus(id, text, stateName = "idle") {
  const badge = document.querySelector(id);
  badge.textContent = text;
  badge.dataset.state = stateName;
}

async function api(action, payload = {}) {
  const response = await fetch(apiEndpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken,
    },
    body: JSON.stringify({
      action,
      session_id: state.sessionId || undefined,
      payload,
    }),
  });
  const body = await response.json();
  if (body.ok && action === "auth.login") {
    state.sessionId = body.data.session_id;
    state.user = body.data.user;
    localStorage.setItem("matrix_ai_session_id", state.sessionId);
  }
  if (action === "auth.logout") {
    state.sessionId = "";
    state.user = null;
    localStorage.removeItem("matrix_ai_session_id");
  }
  return body;
}

function formPayload(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function renderSession() {
  if (!state.user) {
    sessionPanel.innerHTML = `
      <select id="mock-user">
        <option value="engineer">Erin Engineer</option>
        <option value="approver">Priya Approver</option>
        <option value="admin">Avery Admin</option>
      </select>
      <button type="button" id="login-button">Login</button>
    `;
    sessionPanel.querySelector("#login-button").addEventListener("click", login);
    updateAdminVisibility();
    return;
  }

  sessionPanel.innerHTML = `
    <div class="user-chip">
      <strong>${escapeHtml(state.user.display_name)}</strong>
      <span>${escapeHtml(state.user.role)}</span>
    </div>
    <button type="button" class="secondary" id="logout-button">Logout</button>
  `;
  sessionPanel.querySelector("#logout-button").addEventListener("click", logout);
  updateAdminVisibility();
}

function renderResult(data) {
  state.lastWorkflowRunId = data.workflow_run?.id || null;
  approveAllButton.hidden = !state.lastWorkflowRunId || !["Approver", "Admin"].includes(state.user?.role);

  resultOutput.innerHTML = `
    <section class="summary-band">
      <h3>${escapeHtml(data.workflow_run?.title || "Workflow")}</h3>
      <p>${escapeHtml(data.ai_summary?.summary || "")}</p>
    </section>
    ${data.part_number_plan ? renderPartNumberPlan(data.part_number_plan) : ""}
    <section>
      <h3>Findings</h3>
      ${renderFindings(data.findings || [])}
    </section>
    <section>
      <h3>Proposed Actions</h3>
      ${renderActions(data.proposed_actions || [])}
    </section>
  `;
  bindActionButtons();
}

function renderPartNumberPlan(plan) {
  const family = plan.family || {};
  const sapStatus = plan.sap_status || {};
  const alternatives = (plan.alternative_part_numbers || []).join(", ") || "None";
  return `
    <section>
      <h3>Creation Summary</h3>
      <div class="plan-grid">
        <article class="plan-card">
          <span>Selected family</span>
          <strong>${escapeHtml(family.prefix)} · ${escapeHtml(family.name)}</strong>
          <span>${family.verified ? "Verified family mapping" : "Provisional mapping; verify REF0178"}</span>
        </article>
        <article class="plan-card">
          <span>Proposed part number</span>
          <strong>${escapeHtml(plan.candidate_part_number || "Unavailable")}</strong>
          <span>Sequence ${escapeHtml(plan.sequence)} · suffix ${escapeHtml(plan.suffix)}</span>
        </article>
        <article class="plan-card">
          <span>Availability evidence</span>
          <strong>${escapeHtml(plan.combined_sequence_count)} occupied sequence(s)</strong>
          <span>${escapeHtml(plan.matrix_sequence_count)} Matrix · ${escapeHtml(plan.sap_sequence_count)} SAP/legacy</span>
        </article>
        <article class="plan-card">
          <span>SAP source</span>
          <strong>${escapeHtml(sapStatus.mode || "unknown")}</strong>
          <span>${escapeHtml(sapStatus.message || "")}</span>
        </article>
      </div>
      <p class="field-help">Next alternatives: ${escapeHtml(alternatives)}</p>
    </section>
  `;
}

function renderPartSearchResult(data) {
  state.lastWorkflowRunId = null;
  approveAllButton.hidden = true;
  const source = data.source === "matrix"
    ? "Matrix server"
    : data.source === "sap" ? `SAP / legacy (${data.source_status?.mode || "unknown"})` : "Mock data";
  resultOutput.innerHTML = `
    <section class="summary-band">
      <h3>Part Search</h3>
      <p>${escapeHtml(data.count)} match(es) for ${escapeHtml(data.query)} from ${escapeHtml(source)}.</p>
    </section>
    ${renderPartMatches(data.matches || [])}
  `;
}

function renderPartMatches(matches) {
  if (!matches.length) {
    return `<p class="empty">No matching parts.</p>`;
  }

  return `
    <section>
      <h3>Matches</h3>
      <div class="permission-table">
        <table class="part-match-table">
          <thead>
            <tr>
              <th>Part</th>
              <th>Name</th>
              <th>Rev</th>
              <th>State</th>
              <th>Class</th>
              <th>Owner</th>
            </tr>
          </thead>
          <tbody>
            ${matches.map((part) => `
              <tr>
                <td><strong>${escapeHtml(part.part_number || part.material_number)}</strong></td>
                <td>${escapeHtml(part.name || part.description)}</td>
                <td>${escapeHtml(part.revision || "")}</td>
                <td>${escapeHtml(part.lifecycle_state || "")}</td>
                <td>${escapeHtml(part.classification || part.source || "")}</td>
                <td>${escapeHtml(part.owner || "")}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    </section>
  `;
}

function renderFindings(findings) {
  if (!findings.length) {
    return `<p class="empty">No findings.</p>`;
  }
  return `<div class="stacked-list">${findings.map((finding) => `
    <article class="list-item severity-${escapeHtml(finding.severity)}">
      <div>
        <strong>${escapeHtml(finding.message)}</strong>
        <span>${escapeHtml(finding.code)}</span>
      </div>
      <span class="pill">${escapeHtml(finding.severity)}</span>
    </article>
  `).join("")}</div>`;
}

function renderActions(actions) {
  if (!actions.length) {
    return `<p class="empty">No proposed actions.</p>`;
  }

  return `<div class="stacked-list">${actions.map((action) => {
    const canDecide = ["Approver", "Admin"].includes(state.user?.role)
      && ["approval_required", "ready"].includes(action.status);
    return `
      <article class="list-item">
        <div>
          <strong>${escapeHtml(action.payload_preview)}</strong>
          <span>${escapeHtml(action.label)} | ${escapeHtml(action.action_key)}</span>
          ${action.blocked_reason ? `<p>${escapeHtml(action.blocked_reason)}</p>` : ""}
        </div>
        <div class="action-column">
          <span class="pill status-${escapeHtml(action.status)}">${escapeHtml(action.status)}</span>
          ${canDecide ? `
            <button type="button" data-approve="${action.id}">Approve</button>
            <button type="button" class="secondary" data-reject="${action.id}">Reject</button>
          ` : ""}
        </div>
      </article>
    `;
  }).join("")}</div>`;
}

function renderPermissions(actions) {
  if (state.user?.role !== "Admin") {
    permissionsOutput.innerHTML = `<p class="empty">Admin role required.</p>`;
    return;
  }

  permissionsOutput.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Action</th>
          <th>Category</th>
          <th>Risk</th>
          <th>Enabled</th>
          <th>Approval</th>
        </tr>
      </thead>
      <tbody>
        ${actions.map((action) => `
          <tr>
            <td>
              <strong>${escapeHtml(action.label)}</strong>
              <span>${escapeHtml(action.key)}</span>
            </td>
            <td>${escapeHtml(action.category)}</td>
            <td>${escapeHtml(action.risk_level)}</td>
            <td><input type="checkbox" data-permission="${escapeHtml(action.key)}" data-field="enabled" ${action.enabled ? "checked" : ""}></td>
            <td><input type="checkbox" data-permission="${escapeHtml(action.key)}" data-field="requires_approval" ${action.requires_approval ? "checked" : ""}></td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;

  permissionsOutput.querySelectorAll("input[type='checkbox']").forEach((checkbox) => {
    checkbox.addEventListener("change", updatePermission);
  });
}

function renderConnectionStatus(data) {
  const ready = data.ready_for_rest_read ? "Live reads ready" : "Live reads not ready";
  const profile = data.profile_name || "No profile";
  const endpoint = data.execute_mql_matrix_enabled === null
    ? "Unknown"
    : data.execute_mql_matrix_enabled ? "Enabled" : "Disabled";
  const defaultMode = data.rest_read_default_enabled ? "REST read" : "Mock";
  matrixConnectionOutput.innerHTML = `
    <article class="connection-card">
      <strong>${escapeHtml(ready)}</strong>
      <span>Default mode: ${escapeHtml(defaultMode)} | Profile: ${escapeHtml(profile)} | executeMQL: ${escapeHtml(endpoint)}</span>
      ${data.profile_error ? `<p>${escapeHtml(data.profile_error)}</p>` : ""}
      ${data.template_error ? `<p>${escapeHtml(data.template_error)}</p>` : ""}
      ${data.template_names?.length ? `<p>Templates: ${data.template_names.map(escapeHtml).join(", ")}</p>` : ""}
    </article>
  `;
}

function renderApiCatalog(endpoints) {
  if (state.user?.role !== "Admin") {
    apiCatalogOutput.innerHTML = `<p class="empty">Admin role required.</p>`;
    return;
  }
  if (!endpoints.length) {
    apiCatalogOutput.innerHTML = `<p class="empty">No endpoints loaded. Sync the API spec to import available calls.</p>`;
    return;
  }

  apiCatalogOutput.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Matrix</th>
          <th>Endpoint</th>
          <th>Service</th>
          <th>Auth</th>
          <th>Local Mapping</th>
        </tr>
      </thead>
      <tbody>
        ${endpoints.map((endpoint) => `
          <tr>
            <td>
              <input type="checkbox"
                data-api-method="${escapeHtml(endpoint.method)}"
                data-api-path="${escapeHtml(endpoint.path)}"
                ${endpoint.matrix_enabled ? "checked" : ""}>
            </td>
            <td>
              <strong>${escapeHtml(endpoint.method)} ${escapeHtml(endpoint.path)}</strong>
              <span>${escapeHtml(endpoint.summary || "No summary")}</span>
              <span>${escapeHtml(parameterNames(endpoint.query_params, "Query"))}</span>
            </td>
            <td>${escapeHtml(endpoint.service_group)}</td>
            <td>${escapeHtml(authSummary(endpoint))}</td>
            <td>${escapeHtml((endpoint.local_action_keys || []).join(", ") || "None")}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;

  apiCatalogOutput.querySelectorAll("input[type='checkbox']").forEach((checkbox) => {
    checkbox.addEventListener("change", updateApiEndpointStatus);
  });
}

function renderHistory(data) {
  const workflows = data.workflows || [];
  if (!workflows.length) {
    historyOutput.innerHTML = `<p class="empty">No workflow history yet.</p>`;
    return;
  }

  historyOutput.innerHTML = workflows.map((workflow) => `
    <article class="list-item">
      <div>
        <strong>${escapeHtml(workflow.title)}</strong>
        <span>${escapeHtml(workflow.workflow_type)} | ${escapeHtml(workflow.created_by_user.display_name)}</span>
        <p>${escapeHtml(workflow.ai_summary?.summary || "")}</p>
      </div>
      <span class="pill">${workflow.proposed_actions.length} action(s)</span>
    </article>
  `).join("");
}

async function login() {
  const selectedUser = document.querySelector("#mock-user").value;
  const response = await api("auth.login", { username: selectedUser });
  if (!response.ok) {
    showErrors(response.errors);
    return;
  }
  renderSession();
  await Promise.all([loadPermissions(), loadHistory(), loadApiAdmin()]);
}

async function logout() {
  await api("auth.logout", {});
  renderSession();
  resultOutput.innerHTML = "";
  permissionsOutput.innerHTML = "";
  historyOutput.innerHTML = "";
  apiCatalogOutput.innerHTML = "";
  matrixConnectionOutput.innerHTML = "";
}

async function submitWorkflow(event, action, statusId) {
  event.preventDefault();
  if (!state.user) {
    showErrors(["Login is required."]);
    return;
  }

  setStatus(statusId, "Running", "busy");
  const response = await api(action, formPayload(event.currentTarget));
  if (response.ok) {
    renderResult(response.data);
    setStatus(statusId, "Complete", "success");
    await loadHistory();
  } else {
    showErrors(response.errors);
    setStatus(statusId, "Failed", "error");
  }
}

async function submitPartSearch(event) {
  event.preventDefault();
  if (!state.user) {
    showErrors(["Login is required."]);
    return;
  }

  setStatus("#part-search-status", "Searching", "busy");
  const form = document.querySelector("#part-search-form");
  const source = form.querySelector("[name='source']").value;
  const payload = {
    query: form.querySelector("[name='query']").value,
    use_matrix_server: source === "matrix",
  };
  const action = source === "sap" ? "sap.material.search" : "matrix.part.search";
  const response = await api(action, payload);
  if (response.ok) {
    renderPartSearchResult(response.data);
    setStatus("#part-search-status", "Complete", "success");
  } else {
    showErrors(response.errors);
    setStatus("#part-search-status", "Failed", "error");
  }
}

async function submitPartNumberPlan(event) {
  event.preventDefault();
  if (!state.user) {
    showErrors(["Login is required."]);
    return;
  }

  setStatus("#part-number-status", "Checking", "busy");
  const form = event.currentTarget;
  let bomItems;
  try {
    bomItems = parseBomItems(form.querySelector("[name='bom_items_text']").value);
  } catch (error) {
    showErrors([error.message]);
    setStatus("#part-number-status", "Failed", "error");
    return;
  }
  const payload = formPayload(form);
  delete payload.bom_items_text;
  payload.bom_items = bomItems;
  const response = await api("workflow.part_number.plan", payload);
  if (response.ok) {
    renderResult(response.data);
    setStatus("#part-number-status", "Summary ready", "success");
    await loadHistory();
  } else {
    showErrors(response.errors);
    setStatus("#part-number-status", "Failed", "error");
  }
}

function parseBomItems(value) {
  return value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).map((line, index) => {
    const [childPart, quantity = "1", findNumber = String((index + 1) * 10)] = line.split(",").map((item) => item.trim());
    const parsedQuantity = Number(quantity);
    if (!childPart || !Number.isFinite(parsedQuantity) || parsedQuantity <= 0) {
      throw new Error(`Invalid BOM line ${index + 1}. Use CHILD-PART, quantity, find number.`);
    }
    return { child_part: childPart, quantity: parsedQuantity, find_number: findNumber };
  });
}

async function loadPermissions() {
  if (!state.user) {
    return;
  }
  const response = await api("permissions.list", {});
  if (response.ok) {
    renderPermissions(response.data.actions);
    setStatus("#permission-status", "Loaded", "success");
  }
}

async function loadApiAdmin() {
  if (state.user?.role !== "Admin") {
    return;
  }
  await Promise.all([loadApiCatalog(), loadConnectionStatus()]);
}

async function loadApiCatalog() {
  if (state.user?.role !== "Admin") {
    return;
  }
  setStatus("#api-catalog-status", "Loading", "busy");
  const payload = state.apiCatalogFilter === "enabled" ? { matrix_enabled: true } : {};
  const response = await api("matrix.api.catalog.list", payload);
  if (response.ok) {
    renderApiCatalog(response.data.endpoints || []);
    setStatus("#api-catalog-status", "Loaded", "success");
  } else {
    showErrors(response.errors);
    setStatus("#api-catalog-status", "Failed", "error");
  }
}

async function syncApiCatalog() {
  if (state.user?.role !== "Admin") {
    return;
  }
  setStatus("#api-catalog-status", "Syncing", "busy");
  const response = await api("matrix.api.catalog.sync", {});
  if (response.ok) {
    renderApiCatalog(filteredCatalog(response.data.endpoints || []));
    setStatus("#api-catalog-status", `Synced ${response.data.total}`, "success");
    await loadConnectionStatus();
  } else {
    showErrors(response.errors);
    setStatus("#api-catalog-status", "Failed", "error");
  }
}

async function updateApiEndpointStatus(event) {
  const checkbox = event.currentTarget;
  setStatus("#api-catalog-status", "Saving", "busy");
  const response = await api("matrix.api.catalog.update_status", {
    method: checkbox.dataset.apiMethod,
    path: checkbox.dataset.apiPath,
    matrix_enabled: checkbox.checked,
  });

  if (response.ok) {
    setStatus("#api-catalog-status", "Saved", "success");
    await Promise.all([loadApiCatalog(), loadConnectionStatus()]);
  } else {
    checkbox.checked = !checkbox.checked;
    showErrors(response.errors);
    setStatus("#api-catalog-status", "Failed", "error");
  }
}

async function loadConnectionStatus() {
  if (state.user?.role !== "Admin") {
    return;
  }
  const response = await api("matrix.connection.status", {});
  if (response.ok) {
    renderConnectionStatus(response.data);
  }
}

async function updatePermission(event) {
  const checkbox = event.currentTarget;
  setStatus("#permission-status", "Saving", "busy");
  const response = await api("permissions.update", {
    action_key: checkbox.dataset.permission,
    [checkbox.dataset.field]: checkbox.checked,
  });

  if (response.ok) {
    setStatus("#permission-status", "Saved", "success");
  } else {
    checkbox.checked = !checkbox.checked;
    showErrors(response.errors);
    setStatus("#permission-status", "Failed", "error");
  }
}

async function approveAction(id) {
  const response = await api("approval.action.approve", {
    proposed_action_id: Number(id),
  });
  if (!response.ok) {
    showErrors(response.errors);
  }
  await loadHistory();
}

async function rejectAction(id) {
  const response = await api("approval.action.reject", {
    proposed_action_id: Number(id),
  });
  if (!response.ok) {
    showErrors(response.errors);
  }
  await loadHistory();
}

async function approveAllEligible() {
  if (!state.lastWorkflowRunId) {
    return;
  }
  const response = await api("approval.actions.approve_all_eligible", {
    workflow_run_id: state.lastWorkflowRunId,
  });
  if (response.ok) {
    showNotice(`Approved ${response.data.approved.length}; skipped ${response.data.skipped.length}.`);
    await loadHistory();
  } else {
    showErrors(response.errors);
  }
}

async function loadHistory() {
  if (!state.user) {
    return;
  }
  const response = await api("audit.workflow.history", { limit: 15 });
  if (response.ok) {
    renderHistory(response.data);
  }
}

function bindActionButtons() {
  resultOutput.querySelectorAll("[data-approve]").forEach((button) => {
    button.addEventListener("click", () => approveAction(button.dataset.approve));
  });
  resultOutput.querySelectorAll("[data-reject]").forEach((button) => {
    button.addEventListener("click", () => rejectAction(button.dataset.reject));
  });
}

function showErrors(errors) {
  resultOutput.innerHTML = `<div class="message error">${errors.map(escapeHtml).join("<br>")}</div>`;
}

function showNotice(message) {
  resultOutput.insertAdjacentHTML("afterbegin", `<div class="message">${escapeHtml(message)}</div>`);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function bindTabs() {
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".tab-button").forEach((tab) => tab.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.remove("active"));
      button.classList.add("active");
      document.querySelector(`#${button.dataset.tab}`).classList.add("active");
      if (button.dataset.tab === "permissions-panel") {
        loadPermissions();
      }
      if (button.dataset.tab === "approval-panel") {
        loadHistory();
      }
      if (button.dataset.tab === "api-catalog-panel") {
        loadApiAdmin();
      }
    });
  });
}

function bindApiCatalogControls() {
  document.querySelectorAll("[data-api-catalog-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-api-catalog-filter]").forEach((tab) => tab.classList.remove("active"));
      button.classList.add("active");
      state.apiCatalogFilter = button.dataset.apiCatalogFilter;
      loadApiCatalog();
    });
  });
  document.querySelector("#refresh-api-catalog").addEventListener("click", loadApiAdmin);
  document.querySelector("#sync-api-catalog").addEventListener("click", syncApiCatalog);
}

function updateAdminVisibility() {
  const isAdmin = state.user?.role === "Admin";
  document.querySelectorAll("[data-admin-only]").forEach((element) => {
    element.hidden = !isAdmin;
  });
  const apiPanelActive = document.querySelector("#api-catalog-panel")?.classList.contains("active");
  if (!isAdmin && apiPanelActive) {
    document.querySelector("[data-tab='eco-panel']").click();
  }
}

function filteredCatalog(endpoints) {
  if (state.apiCatalogFilter === "enabled") {
    return endpoints.filter((endpoint) => endpoint.matrix_enabled);
  }
  return endpoints;
}

function parameterNames(params, label) {
  const names = (params || []).map((param) => param.name).filter(Boolean);
  return names.length ? `${label}: ${names.join(", ")}` : `${label}: none`;
}

function authSummary(endpoint) {
  const headers = (endpoint.header_params || []).map((param) => param.name).filter(Boolean);
  if (!endpoint.auth_required && !headers.length) {
    return "None";
  }
  if (headers.length) {
    return headers.join(", ");
  }
  return "Ticket";
}

async function bootstrap() {
  bindTabs();
  bindApiCatalogControls();
  document.querySelector("#part-number-form").addEventListener("submit", submitPartNumberPlan);
  document.querySelector("#eco-form").addEventListener("submit", (event) => {
    submitWorkflow(event, "workflow.eco.analyze", "#eco-status");
  });
  document.querySelector("#part-search-button").addEventListener("click", submitPartSearch);
  document.querySelector("#part-search-query").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      submitPartSearch(event);
    }
  });
  document.querySelector("#part-form").addEventListener("submit", (event) => {
    submitWorkflow(event, "workflow.part.analyze", "#part-status");
  });
  document.querySelector("#refresh-history").addEventListener("click", loadHistory);
  approveAllButton.addEventListener("click", approveAllEligible);

  if (state.sessionId) {
    const response = await api("auth.me", {});
    if (response.ok) {
      state.user = response.data.user;
    } else {
      state.sessionId = "";
      localStorage.removeItem("matrix_ai_session_id");
    }
  }
  renderSession();
  if (state.user) {
    await Promise.all([loadPermissions(), loadHistory(), loadApiAdmin()]);
  }
}

bootstrap();
