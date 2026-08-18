const API_ROOT = "/api/manage/products/";
const THEME_KEY = "cc-theme";
const LANG_KEY = "cc-lang";

const state = {
    products: [],
    families: [],
    suppliers: [],
    units: [],
    selectedIds: new Set(),
    editingId: null,
};

function currentLang() {
    return localStorage.getItem(LANG_KEY) || "en";
}

function currentTheme() {
    return localStorage.getItem(THEME_KEY) || "light";
}

function t(key, vars) {
    const dict = CONSOLE_I18N[currentLang()] || CONSOLE_I18N.en;
    let text = dict[key] || CONSOLE_I18N.en[key] || key;
    if (vars) {
        Object.entries(vars).forEach(([name, value]) => {
            text = text.replaceAll(`{${name}}`, String(value));
        });
    }
    return text;
}

function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
}

function applyStaticI18n() {
    document.documentElement.lang = currentLang();
    document.title = `${t("title")} — CentCompras`;
    document.querySelectorAll("[data-i18n]").forEach((node) => {
        node.textContent = t(node.getAttribute("data-i18n"));
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
        node.setAttribute("placeholder", t(node.getAttribute("data-i18n-placeholder")));
    });
    const themeButton = document.getElementById("theme-toggle");
    themeButton.textContent = currentTheme() === "dark" ? t("themeLight") : t("themeDark");
}

function setTheme(theme) {
    localStorage.setItem(THEME_KEY, theme);
    document.documentElement.setAttribute("data-theme", theme);
    applyStaticI18n();
}

function setLanguage(lang) {
    localStorage.setItem(LANG_KEY, lang);
    applyStaticI18n();
    fillFilterOptions();
    fillFormLookups();
    renderTable();
    refreshDrawerLabels();
}

let bannerTimer = null;

function showBanner(message, isError) {
    const banner = document.getElementById("banner");
    banner.hidden = false;
    banner.textContent = message;
    banner.classList.toggle("is-error", Boolean(isError));
    if (bannerTimer) {
        window.clearTimeout(bannerTimer);
    }
    bannerTimer = window.setTimeout(clearBanner, 5000);
}

function clearBanner() {
    if (bannerTimer) {
        window.clearTimeout(bannerTimer);
        bannerTimer = null;
    }
    const banner = document.getElementById("banner");
    banner.hidden = true;
    banner.textContent = "";
}

async function api(path, options) {
    const response = await fetch(path, {
        credentials: "same-origin",
        ...options,
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken(),
            ...(options && options.headers),
        },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
        const mapped = payload.code ? t(payload.code) : "";
        const message = mapped && mapped !== payload.code
            ? mapped
            : (payload.error || t("errorGeneric"));
        throw new Error(message);
    }
    return payload;
}

function isLowStock(product) {
    const stock = Number(product.stock);
    const reorder = Number(product.reorder_level);
    return reorder > 0 && stock <= reorder;
}

function filteredProducts() {
    const query = document.getElementById("search-input").value.trim().toLowerCase();
    const familyId = document.getElementById("family-filter").value;
    const status = document.getElementById("status-filter").value;
    const unit = document.getElementById("unit-filter").value;
    const lowOnly = document.getElementById("low-stock-filter").checked;

    return state.products.filter((product) => {
        if (familyId && String(product.family.id) !== familyId) {
            return false;
        }
        if (status === "active" && !product.is_active) {
            return false;
        }
        if (status === "inactive" && product.is_active) {
            return false;
        }
        if (unit && product.unit_of_measure !== unit) {
            return false;
        }
        if (lowOnly && !isLowStock(product)) {
            return false;
        }
        if (!query) {
            return true;
        }
        const haystack = `${product.internal_code} ${product.description} ${product.family.name}`.toLowerCase();
        return haystack.includes(query);
    });
}

function unitLabel(value) {
    return t(`unit.${value}`);
}

function fillSelect(select, options, placeholder) {
    const current = select.value;
    select.replaceChildren();
    if (placeholder) {
        const empty = document.createElement("option");
        empty.value = "";
        empty.textContent = placeholder;
        select.appendChild(empty);
    }
    options.forEach((option) => {
        const node = document.createElement("option");
        node.value = option.value;
        node.textContent = option.label;
        select.appendChild(node);
    });
    if ([...select.options].some((option) => option.value === current)) {
        select.value = current;
    }
}

function fillFilterOptions() {
    fillSelect(
        document.getElementById("family-filter"),
        state.families.map((family) => ({
            value: String(family.id),
            label: family.is_active ? family.name : `${family.name} (${t("inactive")})`,
        })),
        t("allFamilies")
    );
    fillSelect(
        document.getElementById("unit-filter"),
        state.units.map((unit) => ({
            value: unit.value,
            label: unitLabel(unit.value),
        })),
        t("allUnits")
    );
}

function fillFormLookups() {
    fillSelect(
        document.getElementById("field-family"),
        state.families.map((family) => ({
            value: String(family.id),
            label: family.is_active ? family.name : `${family.name} (${t("inactive")})`,
        }))
    );
    fillSelect(
        document.getElementById("field-unit"),
        state.units.map((unit) => ({
            value: unit.value,
            label: unitLabel(unit.value),
        }))
    );
}

function renderTable() {
    const body = document.getElementById("product-table-body");
    const rows = filteredProducts();
    body.replaceChildren();

    document.getElementById("result-count").textContent = t("showingCount", {
        shown: rows.length,
        total: state.products.length,
    });

    if (rows.length === 0) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 11;
        cell.className = "empty-row";
        cell.textContent = state.products.length === 0 ? t("empty") : t("noMatch");
        row.appendChild(cell);
        body.appendChild(row);
        return;
    }

    rows.forEach((product) => {
        const row = document.createElement("tr");
        if (state.selectedIds.has(product.id)) {
            row.classList.add("is-selected");
        }
        if (!product.is_active) {
            row.classList.add("is-inactive");
        }

        const checkCell = document.createElement("td");
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = state.selectedIds.has(product.id);
        checkbox.addEventListener("click", (event) => event.stopPropagation());
        checkbox.addEventListener("change", () => {
            if (checkbox.checked) {
                state.selectedIds.add(product.id);
            } else {
                state.selectedIds.delete(product.id);
            }
            renderTable();
        });
        checkCell.appendChild(checkbox);

        const code = document.createElement("td");
        code.textContent = product.internal_code || "—";

        const description = document.createElement("td");
        description.textContent = product.description;

        const family = document.createElement("td");
        family.textContent = product.family.name;

        const stock = document.createElement("td");
        stock.textContent = product.stock;
        if (isLowStock(product)) {
            const pill = document.createElement("span");
            pill.className = "pill pill-warn";
            pill.textContent = t("belowReorder");
            stock.append(" ", pill);
        }

        const unit = document.createElement("td");
        unit.textContent = unitLabel(product.unit_of_measure);

        const reorder = document.createElement("td");
        reorder.textContent = product.reorder_level;

        const price = document.createElement("td");
        price.textContent = product.price;

        const suppliers = document.createElement("td");
        suppliers.textContent = product.suppliers.length
            ? product.suppliers.map((item) => item.name).join(", ")
            : t("none");

        const status = document.createElement("td");
        const statusPill = document.createElement("span");
        statusPill.className = product.is_active ? "pill pill-ok" : "pill pill-muted";
        statusPill.textContent = product.is_active ? t("active") : t("inactive");
        status.appendChild(statusPill);

        const actions = document.createElement("td");
        actions.className = "row-actions";
        const editButton = document.createElement("button");
        editButton.type = "button";
        editButton.className = "btn";
        editButton.textContent = t("edit");
        editButton.addEventListener("click", (event) => {
            event.stopPropagation();
            openDrawer(product);
        });
        const lifeButton = document.createElement("button");
        lifeButton.type = "button";
        lifeButton.className = product.is_active ? "btn btn-danger" : "btn";
        lifeButton.textContent = product.is_active ? t("deactivate") : t("reactivate");
        lifeButton.addEventListener("click", (event) => {
            event.stopPropagation();
            toggleLifecycle(product);
        });
        actions.append(editButton, lifeButton);

        row.append(
            checkCell,
            code,
            description,
            family,
            stock,
            unit,
            reorder,
            price,
            suppliers,
            status,
            actions
        );
        row.addEventListener("click", () => openDrawer(product));
        body.appendChild(row);
    });

    const visibleIds = rows.map((product) => product.id);
    const selectAll = document.getElementById("select-all");
    selectAll.checked = visibleIds.length > 0 && visibleIds.every((id) => state.selectedIds.has(id));
}

function replaceProduct(product) {
    const index = state.products.findIndex((item) => item.id === product.id);
    if (index === -1) {
        state.products.push(product);
        state.products.sort((left, right) => left.id - right.id);
        return;
    }
    state.products[index] = product;
}

function refreshDrawerLabels() {
    const drawer = document.getElementById("drawer");
    if (drawer.hidden) {
        return;
    }
    const isNew = !document.getElementById("field-id").value;
    document.getElementById("drawer-title").textContent = isNew ? t("drawerNew") : t("drawerEdit");
    const lifeButton = document.getElementById("drawer-lifecycle");
    if (isNew) {
        lifeButton.hidden = true;
        return;
    }
    const product = state.products.find((item) => String(item.id) === document.getElementById("field-id").value);
    if (!product) {
        return;
    }
    lifeButton.hidden = false;
    lifeButton.textContent = product.is_active ? t("deactivate") : t("reactivate");
    lifeButton.className = product.is_active ? "btn btn-danger" : "btn";
}

function fillSupplierOptions(selectedIds) {
    const box = document.getElementById("supplier-options");
    box.replaceChildren();
    state.suppliers.forEach((supplier) => {
        const label = document.createElement("label");
        const input = document.createElement("input");
        input.type = "checkbox";
        input.value = String(supplier.id);
        input.checked = selectedIds.has(supplier.id);
        const text = document.createElement("span");
        text.textContent = supplier.is_active ? supplier.name : `${supplier.name} (${t("inactive")})`;
        label.append(input, text);
        box.appendChild(label);
    });
}

function closeDrawer() {
    document.getElementById("drawer").hidden = true;
    document.getElementById("drawer-backdrop").hidden = true;
    state.editingId = null;
}

function formPayload() {
    const supplierIds = [...document.querySelectorAll("#supplier-options input:checked")].map(
        (input) => Number(input.value)
    );
    return {
        family_id: Number(document.getElementById("field-family").value),
        internal_code: document.getElementById("field-internal-code").value,
        description: document.getElementById("field-description").value,
        stock: document.getElementById("field-stock").value,
        price: document.getElementById("field-price").value,
        unit_of_measure: document.getElementById("field-unit").value,
        reorder_level: document.getElementById("field-reorder").value,
        reason: document.getElementById("field-reason").value,
        supplier_ids: supplierIds,
    };
}

async function loadHistory(productId) {
    const list = document.getElementById("history-list");
    list.replaceChildren();
    const data = await api(`${API_ROOT}${productId}/history/`);
    if (!data.history.length) {
        const item = document.createElement("li");
        item.textContent = t("noHistory");
        list.appendChild(item);
        return;
    }
    data.history.forEach((entry) => {
        const item = document.createElement("li");
        const actionKey = `action${entry.action.charAt(0).toUpperCase()}${entry.action.slice(1)}`;
        const when = new Date(entry.created_at).toLocaleString();
        const who = entry.user_email || "—";
        const reason = entry.reason ? ` — ${entry.reason}` : "";
        item.textContent = `${t(actionKey)} · ${who} · ${when}${reason}`;
        list.appendChild(item);
    });
}

async function openDrawer(product) {
    fillFormLookups();
    document.getElementById("drawer").hidden = false;
    document.getElementById("drawer-backdrop").hidden = false;
    document.getElementById("field-reason").value = "";
    const historyList = document.getElementById("history-list");
    historyList.replaceChildren();

    if (!product) {
        state.editingId = null;
        document.getElementById("field-id").value = "";
        document.getElementById("field-internal-code").value = "";
        document.getElementById("field-description").value = "";
        document.getElementById("field-stock").value = "0";
        document.getElementById("field-price").value = "0.00";
        document.getElementById("field-reorder").value = "0";
        if (state.families.length) {
            document.getElementById("field-family").value = String(state.families[0].id);
        }
        if (state.units.length) {
            document.getElementById("field-unit").value = state.units[0].value;
        }
        fillSupplierOptions(new Set());
        refreshDrawerLabels();
        return;
    }

    state.editingId = product.id;
    document.getElementById("field-id").value = String(product.id);
    document.getElementById("field-internal-code").value = product.internal_code;
    document.getElementById("field-description").value = product.description;
    document.getElementById("field-family").value = String(product.family.id);
    document.getElementById("field-stock").value = product.stock;
    document.getElementById("field-price").value = product.price;
    document.getElementById("field-reorder").value = product.reorder_level;
    document.getElementById("field-unit").value = product.unit_of_measure;
    fillSupplierOptions(new Set(product.suppliers.map((item) => item.id)));
    refreshDrawerLabels();
    try {
        await loadHistory(product.id);
    } catch (error) {
        showBanner(error.message, true);
    }
}

async function saveProduct(event) {
    event.preventDefault();
    clearBanner();
    const payload = formPayload();
    const productId = document.getElementById("field-id").value;
    try {
        let data;
        if (productId) {
            data = await api(`${API_ROOT}${productId}/`, {
                method: "PATCH",
                body: JSON.stringify(payload),
            });
            replaceProduct(data.product);
            showBanner(t("saved"));
            await loadHistory(data.product.id);
        } else {
            data = await api(API_ROOT, {
                method: "POST",
                body: JSON.stringify(payload),
            });
            replaceProduct(data.product);
            showBanner(t("created"));
            closeDrawer();
        }
        renderTable();
        refreshDrawerLabels();
    } catch (error) {
        showBanner(error.message, true);
    }
}

async function askDeactivateReason() {
    return new Promise((resolve) => {
        const backdrop = document.getElementById("reason-dialog-backdrop");
        const dialog = document.getElementById("reason-dialog");
        const input = document.getElementById("deactivate-reason-input");
        const error = document.getElementById("deactivate-reason-error");
        const confirmButton = document.getElementById("deactivate-reason-confirm");
        const cancelButton = document.getElementById("deactivate-reason-cancel");

        input.value = "";
        error.hidden = true;
        backdrop.hidden = false;
        dialog.hidden = false;
        input.focus();

        function finish(value) {
            backdrop.hidden = true;
            dialog.hidden = true;
            confirmButton.removeEventListener("click", onConfirm);
            cancelButton.removeEventListener("click", onCancel);
            backdrop.removeEventListener("click", onCancel);
            input.removeEventListener("keydown", onKey);
            resolve(value);
        }

        function onConfirm() {
            const reason = input.value.trim();
            if (!reason) {
                error.textContent = t("deactivate_reason_required");
                error.hidden = false;
                input.focus();
                return;
            }
            finish(reason);
        }

        function onCancel() {
            finish(null);
        }

        function onKey(event) {
            if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                onConfirm();
            }
            if (event.key === "Escape") {
                onCancel();
            }
        }

        confirmButton.addEventListener("click", onConfirm);
        cancelButton.addEventListener("click", onCancel);
        backdrop.addEventListener("click", onCancel);
        input.addEventListener("keydown", onKey);
    });
}

function reasonFromOpenDrawer(product) {
    const drawerOpen = !document.getElementById("drawer").hidden;
    const editingThis = Boolean(product) && drawerOpen && state.editingId === product.id;
    if (!editingThis) {
        return "";
    }
    return document.getElementById("field-reason").value.trim();
}

async function resolveDeactivateReason(product) {
    const fromField = reasonFromOpenDrawer(product);
    if (fromField) {
        return fromField;
    }
    return askDeactivateReason();
}

async function toggleLifecycle(product) {
    clearBanner();
    let reason = reasonFromOpenDrawer(product);
    if (product.is_active) {
        reason = await resolveDeactivateReason(product);
        if (reason === null) {
            return;
        }
    }
    const path = product.is_active
        ? `${API_ROOT}${product.id}/deactivate/`
        : `${API_ROOT}${product.id}/reactivate/`;
    try {
        const data = await api(path, {
            method: "POST",
            body: JSON.stringify({ reason }),
        });
        replaceProduct(data.product);
        showBanner(product.is_active ? t("deactivated") : t("reactivated"));
        renderTable();
        if (!document.getElementById("drawer").hidden && state.editingId === product.id) {
            await openDrawer(data.product);
        }
    } catch (error) {
        showBanner(error.message, true);
    }
}

async function applyBulk() {
    clearBanner();
    const action = document.getElementById("bulk-action").value;
    const ids = filteredProducts()
        .map((product) => product.id)
        .filter((id) => state.selectedIds.has(id));
    if (!action) {
        showBanner(t("chooseAction"), true);
        return;
    }
    if (!ids.length) {
        showBanner(t("selectRows"), true);
        return;
    }
    let reason = document.getElementById("field-reason").value;
    if (action === "deactivate") {
        reason = await askDeactivateReason();
        if (reason === null) {
            return;
        }
    }
    try {
        const data = await api(`${API_ROOT}bulk/`, {
            method: "POST",
            body: JSON.stringify({
                action,
                ids,
                reason,
            }),
        });
        data.products.forEach(replaceProduct);
        state.selectedIds.clear();
        document.getElementById("bulk-action").value = "";
        showBanner(t("bulkDone"));
        renderTable();
    } catch (error) {
        showBanner(error.message, true);
    }
}

async function loadCatalog() {
    const data = await api(API_ROOT);
    state.products = data.products;
    state.families = data.families;
    state.suppliers = data.suppliers;
    state.units = data.units;
    fillFilterOptions();
    fillFormLookups();
    renderTable();
}

function bindEvents() {
    document.getElementById("language-select").value = currentLang();
    document.getElementById("language-select").addEventListener("change", (event) => {
        setLanguage(event.target.value);
    });
    document.getElementById("theme-toggle").addEventListener("click", () => {
        setTheme(currentTheme() === "dark" ? "light" : "dark");
    });
    ["search-input", "family-filter", "status-filter", "unit-filter", "low-stock-filter"].forEach((id) => {
        document.getElementById(id).addEventListener("input", renderTable);
        document.getElementById(id).addEventListener("change", renderTable);
    });
    document.getElementById("select-all").addEventListener("change", (event) => {
        const rows = filteredProducts();
        if (event.target.checked) {
            rows.forEach((product) => state.selectedIds.add(product.id));
        } else {
            rows.forEach((product) => state.selectedIds.delete(product.id));
        }
        renderTable();
    });
    document.getElementById("bulk-apply").addEventListener("click", applyBulk);
    document.getElementById("new-product").addEventListener("click", () => openDrawer(null));
    document.getElementById("drawer-close").addEventListener("click", closeDrawer);
    document.getElementById("drawer-backdrop").addEventListener("click", closeDrawer);
    document.getElementById("product-form").addEventListener("submit", saveProduct);
    document.getElementById("drawer-lifecycle").addEventListener("click", () => {
        const product = state.products.find((item) => item.id === state.editingId);
        if (product) {
            toggleLifecycle(product);
        }
    });
}

async function init() {
    applyStaticI18n();
    bindEvents();
    try {
        await loadCatalog();
    } catch (error) {
        showBanner(t("loadFailed"), true);
    }
}

init();
