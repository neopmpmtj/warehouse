const PO_API = "/api/manage/purchase-orders/";
const CATALOG_API = "/api/manage/purchase-orders/catalog/";

const state = {
    orders: [],
    suppliers: [],
    products: [],
    editingId: null,
    editingOrder: null,
    receiveOrderId: null,
};

function t(key, vars) {
    const lang = document.documentElement.getAttribute("lang") || "en";
    const base = CONSOLE_I18N[lang] || CONSOLE_I18N.en;
    const proc = PROCUREMENT_I18N[lang] || PROCUREMENT_I18N.en;
    let text = proc[key] || base[key] || key;
    if (vars) {
        Object.keys(vars).forEach((k) => {
            text = text.replace(`{${k}}`, vars[k]);
        });
    }
    return text;
}

function applyI18n() {
    document.querySelectorAll("[data-i18n]").forEach((el) => {
        const key = el.getAttribute("data-i18n");
        const text = t(key);
        if (el.tagName === "BUTTON" || el.tagName === "OPTION") {
            el.textContent = text;
        } else {
            el.textContent = text;
        }
    });
    const themeBtn = document.getElementById("theme-toggle");
    const theme = document.documentElement.getAttribute("data-theme");
    themeBtn.textContent = theme === "dark" ? t("themeLight") : t("themeDark");
}

function getCsrfToken() {
    const meta = document.querySelector("meta[name='csrf-token']");
    return meta ? meta.getAttribute("content") : "";
}

async function apiFetch(url, options = {}) {
    const headers = options.headers || {};
    if (options.body && !headers["Content-Type"]) {
        headers["Content-Type"] = "application/json";
    }
    headers["X-CSRFToken"] = getCsrfToken();
    const response = await fetch(url, { ...options, headers, credentials: "same-origin" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        const err = new Error(data.error || t("errorGeneric"));
        err.code = data.code || data.error;
        err.status = response.status;
        throw err;
    }
    return data;
}

function showBanner(message, isError) {
    const banner = document.getElementById("banner");
    banner.textContent = message;
    banner.classList.toggle("banner-error", isError);
    banner.hidden = false;
}

function statusLabel(status) {
    const map = {
        draft: t("statusDraft"),
        pending_approval: t("statusPending"),
        approved: t("statusApproved"),
        cancelled: t("statusCancelled"),
    };
    return map[status] || status;
}

function productLabel(product) {
    const code = product.internal_code ? `${product.internal_code} — ` : "";
    return `${code}${product.description}`;
}

function filteredOrders() {
    const filter = document.getElementById("status-filter").value;
    if (filter === "all") return state.orders;
    return state.orders.filter((o) => o.status === filter);
}

function renderOrderTable() {
    const tbody = document.getElementById("order-table-body");
    const rows = filteredOrders();
    if (!rows.length) {
        const msg = state.orders.length ? t("noMatch") : t("emptyOrders");
        tbody.innerHTML = `<tr><td colspan="5" class="empty-cell">${msg}</td></tr>`;
        return;
    }
    tbody.innerHTML = rows
        .map((order) => {
            const created = new Date(order.created_at).toLocaleString();
            return `
                <tr>
                    <td>#${order.id}</td>
                    <td>${order.supplier.name}</td>
                    <td><span class="status-pill status-${order.status}">${statusLabel(order.status)}</span></td>
                    <td>${created}</td>
                    <td class="actions-cell">
                        <button type="button" class="btn btn-ghost btn-open" data-id="${order.id}">${t("edit")}</button>
                    </td>
                </tr>`;
        })
        .join("");
    tbody.querySelectorAll(".btn-open").forEach((btn) => {
        btn.addEventListener("click", () => openOrderDrawer(Number(btn.dataset.id)));
    });
}

function fillSupplierSelect(selectedId) {
    const select = document.getElementById("field-supplier");
    select.innerHTML = state.suppliers
        .map((s) => `<option value="${s.id}">${s.name}</option>`)
        .join("");
    if (selectedId) select.value = String(selectedId);
}

function canEditLines(order) {
    return order && (order.status === "draft" || order.status === "pending_approval");
}

function renderLineRow(line, editable) {
    const productOptions = state.products
        .map((p) => {
            const selected = p.id === line.product_id ? " selected" : "";
            return `<option value="${p.id}"${selected}>${productLabel(p)}</option>`;
        })
        .join("");
    const cost = line.unit_cost || "0.00";
    const removeBtn = editable
        ? `<button type="button" class="btn btn-ghost btn-remove-line" data-line-id="${line.id || ""}">${t("remove")}</button>`
        : "";
    const productCell = editable
        ? `<select class="line-product" data-line-id="${line.id || ""}">${productOptions}</select>`
        : (line.product_label || productLabel(line.product || {}));
    const qtyCell = editable
        ? `<input type="number" class="line-qty" min="1" value="${line.quantity_ordered}" data-line-id="${line.id || ""}">`
        : String(line.quantity_ordered);
    return `
        <tr data-line-id="${line.id || "new"}">
            <td>${productCell}</td>
            <td>${qtyCell}</td>
            <td class="line-cost">${cost}</td>
            <td>${line.quantity_received || 0}</td>
            <td>${line.quantity_outstanding || 0}</td>
            <td>${removeBtn}</td>
        </tr>`;
}

function renderLines(order) {
    const tbody = document.getElementById("line-table-body");
    const editable = canEditLines(order);
    const lines = order.lines || [];
    if (!lines.length && editable) {
        tbody.innerHTML = renderLineRow({ product_id: state.products[0]?.id, quantity_ordered: 1, unit_cost: "0.00" }, true);
    } else {
        tbody.innerHTML = lines.map((line) => renderLineRow(line, editable)).join("");
    }
    bindLineEvents(editable);
}

function bindLineEvents(editable) {
    if (!editable) return;
    document.querySelectorAll(".line-product").forEach((sel) => {
        sel.addEventListener("change", () => {
            const productId = Number(sel.value);
            const product = state.products.find((p) => p.id === productId);
            const row = sel.closest("tr");
            if (product && row) {
                row.querySelector(".line-cost").textContent = product.cost;
            }
        });
    });
    document.querySelectorAll(".btn-remove-line").forEach((btn) => {
        btn.addEventListener("click", () => {
            const row = btn.closest("tr");
            row.remove();
        });
    });
}

function collectLinesFromForm() {
    const rows = document.querySelectorAll("#line-table-body tr");
    const lines = [];
    rows.forEach((row) => {
        const productSel = row.querySelector(".line-product");
        const qtyInput = row.querySelector(".line-qty");
        if (!productSel || !qtyInput) return;
        const product_id = Number(productSel.value);
        const quantity_ordered = Number(qtyInput.value);
        if (product_id && quantity_ordered > 0) {
            lines.push({ product_id, quantity_ordered });
        }
    });
    return lines;
}

function renderDrawerActions(order) {
    const top = document.getElementById("drawer-actions-top");
    const bottom = document.getElementById("drawer-actions-bottom");
    top.innerHTML = "";
    bottom.innerHTML = "";
    if (!order) {
        bottom.innerHTML = `<button type="button" id="btn-save" class="btn btn-primary">${t("save")}</button>`;
        return;
    }
    const status = order.status;
    if (status === "draft" || status === "pending_approval") {
        bottom.innerHTML = `
            <button type="button" id="btn-save" class="btn btn-primary">${t("save")}</button>
            ${status === "draft" ? `<button type="button" id="btn-submit" class="btn">${t("submit")}</button>` : ""}
            <button type="button" id="btn-cancel-order" class="btn btn-danger">${t("cancelOrder")}</button>
            <button type="button" id="btn-add-line" class="btn btn-ghost">${t("addLine")}</button>`;
    } else if (status === "approved") {
        bottom.innerHTML = `
            <button type="button" id="btn-receive" class="btn btn-primary">${t("receive")}</button>
            <button type="button" id="btn-cancel-order" class="btn btn-danger">${t("cancelOrder")}</button>`;
    }
    if (status === "pending_approval") {
        top.innerHTML = `<button type="button" id="btn-approve" class="btn btn-primary">${t("approve")}</button>`;
    }
}

function bindDrawerActionButtons(order) {
    const saveBtn = document.getElementById("btn-save");
    if (saveBtn) saveBtn.addEventListener("click", () => saveOrder(order));
    const submitBtn = document.getElementById("btn-submit");
    if (submitBtn) submitBtn.addEventListener("click", () => submitOrder(order.id));
    const approveBtn = document.getElementById("btn-approve");
    if (approveBtn) approveBtn.addEventListener("click", () => approveOrder(order.id));
    const cancelBtn = document.getElementById("btn-cancel-order");
    if (cancelBtn) cancelBtn.addEventListener("click", () => cancelOrder(order.id));
    const receiveBtn = document.getElementById("btn-receive");
    if (receiveBtn) receiveBtn.addEventListener("click", () => openReceiveDialog(order));
    const addLineBtn = document.getElementById("btn-add-line");
    if (addLineBtn) {
        addLineBtn.addEventListener("click", () => {
            const tbody = document.getElementById("line-table-body");
            const first = state.products[0];
            const html = renderLineRow({
                product_id: first?.id,
                quantity_ordered: 1,
                unit_cost: first?.cost || "0.00",
            }, true);
            tbody.insertAdjacentHTML("beforeend", html);
            bindLineEvents(true);
        });
    }
}

async function openOrderDrawer(orderId) {
    let order = null;
    if (orderId) {
        const data = await apiFetch(`${PO_API}${orderId}/`);
        order = data.order;
        state.editingId = orderId;
        state.editingOrder = order;
    } else {
        state.editingId = null;
        state.editingOrder = { status: "draft", lines: [], supplier: state.suppliers[0] };
    }
    document.getElementById("drawer-title").textContent = orderId ? t("drawerEdit") + " #" + orderId : t("drawerNew");
    fillSupplierSelect(order?.supplier?.id || state.suppliers[0]?.id);
    document.getElementById("field-supplier").disabled = order && order.status !== "draft" && order.status !== "pending_approval";
    document.getElementById("field-notes").value = order?.notes || "";
    document.getElementById("field-notes").readOnly = order && !canEditLines(order);
    renderLines(order || { lines: [], status: "draft" });
    renderDrawerActions(order);
    bindDrawerActionButtons(order);
    document.getElementById("drawer").hidden = false;
    document.getElementById("drawer-backdrop").hidden = false;
}

function closeDrawer() {
    document.getElementById("drawer").hidden = true;
    document.getElementById("drawer-backdrop").hidden = true;
    state.editingId = null;
    state.editingOrder = null;
}

async function saveOrder(existing) {
    const supplier_id = Number(document.getElementById("field-supplier").value);
    const notes = document.getElementById("field-notes").value;
    const lines = collectLinesFromForm();
    try {
        if (existing && existing.id) {
            await apiFetch(`${PO_API}${existing.id}/`, {
                method: "PATCH",
                body: JSON.stringify({ supplier_id, notes, lines }),
            });
        } else {
            const created = await apiFetch(PO_API, {
                method: "POST",
                body: JSON.stringify({ supplier_id, notes, lines }),
            });
            state.editingId = created.order.id;
        }
        showBanner(t("saved"), false);
        await loadOrders();
        if (state.editingId) await openOrderDrawer(state.editingId);
    } catch (err) {
        showBanner(err.message, true);
    }
}

async function submitOrder(id) {
    try {
        await apiFetch(`${PO_API}${id}/submit/`, { method: "POST", body: "{}" });
        showBanner(t("submitted"), false);
        await loadOrders();
        await openOrderDrawer(id);
    } catch (err) {
        showBanner(err.message, true);
    }
}

async function approveOrder(id) {
    try {
        await apiFetch(`${PO_API}${id}/approve/`, { method: "POST", body: "{}" });
        showBanner(t("approved"), false);
        await loadOrders();
        await openOrderDrawer(id);
    } catch (err) {
        const msg = err.code === "approval_forbidden" ? t("approval_forbidden") : err.message;
        showBanner(msg, true);
    }
}

async function cancelOrder(id) {
    try {
        await apiFetch(`${PO_API}${id}/cancel/`, { method: "POST", body: "{}" });
        showBanner(t("cancelled"), false);
        closeDrawer();
        await loadOrders();
    } catch (err) {
        showBanner(err.message, true);
    }
}

function openReceiveDialog(order) {
    state.receiveOrderId = order.id;
    const container = document.getElementById("receive-lines");
    const lines = order.lines.filter((l) => l.quantity_outstanding > 0);
    container.innerHTML = lines
        .map(
            (line) => `
            <label class="receive-line">
                <span>${line.product_label} (${t("colOutstanding")}: ${line.quantity_outstanding})</span>
                <input type="number" class="receive-qty" min="0" max="${line.quantity_outstanding}"
                    value="${line.quantity_outstanding}" data-line-id="${line.id}">
            </label>`
        )
        .join("");
    document.getElementById("receive-dialog").hidden = false;
    document.getElementById("receive-dialog-backdrop").hidden = false;
}

function closeReceiveDialog() {
    document.getElementById("receive-dialog").hidden = true;
    document.getElementById("receive-dialog-backdrop").hidden = true;
    state.receiveOrderId = null;
}

async function confirmReceive() {
    const inputs = document.querySelectorAll(".receive-qty");
    const lines = [];
    inputs.forEach((input) => {
        const qty = Number(input.value);
        const po_line_id = Number(input.dataset.lineId);
        if (qty > 0) lines.push({ po_line_id, quantity_received: qty });
    });
    if (!lines.length) {
        closeReceiveDialog();
        return;
    }
    try {
        await apiFetch(`${PO_API}${state.receiveOrderId}/receive/`, {
            method: "POST",
            body: JSON.stringify({ lines }),
        });
        showBanner(t("received"), false);
        closeReceiveDialog();
        await loadOrders();
        await openOrderDrawer(state.receiveOrderId);
    } catch (err) {
        showBanner(err.message, true);
    }
}

async function loadCatalog() {
    const data = await apiFetch(CATALOG_API);
    state.suppliers = data.suppliers || [];
    state.products = data.products || [];
}

async function loadOrders() {
    try {
        const data = await apiFetch(PO_API);
        state.orders = data.orders || data;
        renderOrderTable();
    } catch (err) {
        showBanner(t("loadFailed"), true);
    }
}

function initTheme() {
    const btn = document.getElementById("theme-toggle");
    btn.addEventListener("click", () => {
        const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", next);
        localStorage.setItem("cc-theme", next);
        applyI18n();
    });
}

function initLanguage() {
    const select = document.getElementById("language-select");
    const lang = document.documentElement.getAttribute("lang") || "en";
    select.value = lang;
    select.addEventListener("change", () => {
        const newLang = select.value;
        document.documentElement.setAttribute("lang", newLang);
        localStorage.setItem("cc-lang", newLang);
        applyI18n();
        renderOrderTable();
    });
}

document.getElementById("new-order").addEventListener("click", () => openOrderDrawer(null));
document.getElementById("drawer-close").addEventListener("click", closeDrawer);
document.getElementById("drawer-backdrop").addEventListener("click", closeDrawer);
document.getElementById("status-filter").addEventListener("change", renderOrderTable);
document.getElementById("receive-confirm").addEventListener("click", confirmReceive);
document.getElementById("receive-cancel").addEventListener("click", closeReceiveDialog);
document.getElementById("receive-dialog-backdrop").addEventListener("click", closeReceiveDialog);

initTheme();
initLanguage();
applyI18n();
loadCatalog().then(() => loadOrders());
