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
    sortKey: null,
    sortDir: "asc",
};

const NUMERIC_SORT_KEYS = new Set(["stock", "reorder_level", "price"]);

const LIFECYCLE_REASON = {
    GENESIS: "Genesis",
    IN_STOCK: "In stock",
    RESTOCKED: "Restocked",
    TEMP_UNAVAILABLE: "Temporarily unavailable",
    DISCONTINUED: "No longer commercialized",
};

const LIFECYCLE_OTHER = "__other__";

const LIFECYCLE_PRESETS = {
    genesis: [{ value: LIFECYCLE_REASON.GENESIS, labelKey: "reasonGenesis" }],
    activate: [
        { value: LIFECYCLE_REASON.IN_STOCK, labelKey: "reasonInStock" },
        { value: LIFECYCLE_REASON.RESTOCKED, labelKey: "reasonRestocked" },
        { value: LIFECYCLE_OTHER, labelKey: "reasonOther" },
    ],
    deactivate: [
        { value: LIFECYCLE_REASON.TEMP_UNAVAILABLE, labelKey: "reasonTempUnavailable" },
        { value: LIFECYCLE_REASON.DISCONTINUED, labelKey: "reasonDiscontinued" },
        { value: LIFECYCLE_OTHER, labelKey: "reasonOther" },
    ],
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

function supplierSortKey(product) {
    if (!product.suppliers.length) {
        return "";
    }
    return product.suppliers.map((item) => item.name).join(", ");
}

function sortValue(product, key) {
    switch (key) {
        case "internal_code":
            return product.internal_code || "";
        case "description":
            return product.description;
        case "family":
            return product.family.name;
        case "stock":
            return Number(product.stock);
        case "unit_of_measure":
            return unitLabel(product.unit_of_measure);
        case "reorder_level":
            return Number(product.reorder_level);
        case "price":
            return Number(product.price);
        case "suppliers":
            return supplierSortKey(product);
        case "status":
            return product.is_active ? t("active") : t("inactive");
        default:
            return product.id;
    }
}

function compareProducts(left, right, key, dir) {
    const leftVal = sortValue(left, key);
    const rightVal = sortValue(right, key);
    let cmp = 0;
    if (NUMERIC_SORT_KEYS.has(key)) {
        cmp = leftVal - rightVal;
    } else {
        cmp = String(leftVal).localeCompare(String(rightVal), currentLang(), {
            sensitivity: "base",
        });
    }
    if (cmp === 0) {
        cmp = left.id - right.id;
    }
    return dir === "desc" ? -cmp : cmp;
}

function sortedProducts(rows) {
    if (!state.sortKey) {
        return [...rows].sort((left, right) => left.id - right.id);
    }
    return [...rows].sort((left, right) => compareProducts(left, right, state.sortKey, state.sortDir));
}

function updateSortHeaders() {
    document.querySelectorAll("th[data-sort]").forEach((header) => {
        const key = header.getAttribute("data-sort");
        const columnKey = header.getAttribute("data-i18n-col");
        const columnLabel = columnKey ? t(columnKey) : key;
        const button = header.querySelector(".sort-btn");
        const indicator = header.querySelector(".sort-indicator");
        if (!button || !indicator) {
            return;
        }
        if (state.sortKey === key) {
            header.setAttribute("aria-sort", state.sortDir === "asc" ? "ascending" : "descending");
            header.classList.add("is-sorted");
            indicator.textContent = state.sortDir === "asc" ? "▲" : "▼";
            button.setAttribute(
                "aria-label",
                t(state.sortDir === "asc" ? "sortActiveAsc" : "sortActiveDesc", {
                    column: columnLabel,
                })
            );
            return;
        }
        header.setAttribute("aria-sort", "none");
        header.classList.remove("is-sorted");
        indicator.textContent = "";
        button.setAttribute("aria-label", t("sortBy", { column: columnLabel }));
    });
}

function toggleSort(key) {
    if (state.sortKey === key) {
        state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
        return;
    }
    state.sortKey = key;
    state.sortDir = "asc";
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
    const rows = sortedProducts(filteredProducts());
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
        updateSortHeaders();
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
    updateSortHeaders();
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
            closeDrawer();
            renderTable();
            const reason = await askLifecycleReason("genesis");
            if (reason === null) {
                showBanner(t("createdInactive"));
                return;
            }
            const activated = await api(`${API_ROOT}${data.product.id}/reactivate/`, {
                method: "POST",
                body: JSON.stringify({ reason }),
            });
            replaceProduct(activated.product);
            showBanner(t("activated"));
        }
        renderTable();
        refreshDrawerLabels();
    } catch (error) {
        showBanner(error.message, true);
    }
}

function lifecycleDialogConfig(mode) {
    if (mode === "genesis") {
        return {
            titleKey: "lifecycleGenesisTitle",
            helpKey: "genesisHelp",
            confirmKey: "genesisConfirm",
            confirmClass: "btn btn-primary",
            errorKey: "reactivate_reason_required",
        };
    }
    if (mode === "activate") {
        return {
            titleKey: "lifecycleActivateTitle",
            helpKey: null,
            confirmKey: "activate",
            confirmClass: "btn btn-primary",
            errorKey: "reactivate_reason_required",
        };
    }
    return {
        titleKey: "lifecycleDeactivateTitle",
        helpKey: null,
        confirmKey: "deactivate",
        confirmClass: "btn btn-danger",
        errorKey: "deactivate_reason_required",
    };
}

function askLifecycleReason(mode) {
    return new Promise((resolve) => {
        const config = lifecycleDialogConfig(mode);
        const backdrop = document.getElementById("lifecycle-dialog-backdrop");
        const dialog = document.getElementById("lifecycle-dialog");
        const title = document.getElementById("lifecycle-dialog-title");
        const help = document.getElementById("lifecycle-dialog-help");
        const presetList = document.getElementById("lifecycle-preset-list");
        const customWrap = document.getElementById("lifecycle-custom-wrap");
        const customInput = document.getElementById("lifecycle-custom-input");
        const error = document.getElementById("lifecycle-reason-error");
        const confirmButton = document.getElementById("lifecycle-confirm");
        const cancelButton = document.getElementById("lifecycle-cancel");
        const presets = LIFECYCLE_PRESETS[mode];

        title.textContent = t(config.titleKey);
        if (config.helpKey) {
            help.textContent = t(config.helpKey);
            help.hidden = false;
        } else {
            help.hidden = true;
        }
        confirmButton.textContent = t(config.confirmKey);
        confirmButton.className = config.confirmClass;
        customInput.value = "";
        error.hidden = true;
        customWrap.hidden = true;

        presetList.replaceChildren();
        presets.forEach((preset, index) => {
            const label = document.createElement("label");
            const input = document.createElement("input");
            input.type = "radio";
            input.name = "lifecycle-preset";
            input.value = preset.value;
            input.checked = index === 0;
            const text = document.createElement("span");
            text.textContent = t(preset.labelKey);
            label.append(input, text);
            presetList.appendChild(label);
        });

        function selectedValue() {
            const selected = presetList.querySelector('input[name="lifecycle-preset"]:checked');
            return selected ? selected.value : "";
        }

        function syncCustomField() {
            customWrap.hidden = selectedValue() !== LIFECYCLE_OTHER;
            if (!customWrap.hidden) {
                customInput.focus();
            }
        }

        function finish(value) {
            backdrop.hidden = true;
            dialog.hidden = true;
            confirmButton.removeEventListener("click", onConfirm);
            cancelButton.removeEventListener("click", onCancel);
            backdrop.removeEventListener("click", onCancel);
            customInput.removeEventListener("keydown", onKey);
            presetList.removeEventListener("change", syncCustomField);
            resolve(value);
        }

        function onConfirm() {
            const value = selectedValue();
            if (!value) {
                error.textContent = t(config.errorKey);
                error.hidden = false;
                return;
            }
            if (value === LIFECYCLE_OTHER) {
                const custom = customInput.value.trim();
                if (!custom) {
                    error.textContent = t(config.errorKey);
                    error.hidden = false;
                    customInput.focus();
                    return;
                }
                finish(custom);
                return;
            }
            finish(value);
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

        presetList.addEventListener("change", syncCustomField);
        confirmButton.addEventListener("click", onConfirm);
        cancelButton.addEventListener("click", onCancel);
        backdrop.addEventListener("click", onCancel);
        customInput.addEventListener("keydown", onKey);
        backdrop.hidden = false;
        dialog.hidden = false;
        syncCustomField();
        if (customWrap.hidden) {
            confirmButton.focus();
        }
    });
}

async function toggleLifecycle(product) {
    clearBanner();
    const reason = product.is_active
        ? await askLifecycleReason("deactivate")
        : await askLifecycleReason("activate");
    if (reason === null) {
        return;
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
    let reason = "";
    if (action === "deactivate") {
        reason = await askLifecycleReason("deactivate");
    } else {
        reason = await askLifecycleReason("activate");
    }
    if (reason === null) {
        return;
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
    const sortableHead = document.querySelector(".grid thead");
    if (sortableHead) {
        sortableHead.addEventListener("click", (event) => {
            const button = event.target.closest("th[data-sort] .sort-btn");
            if (!button) {
                return;
            }
            event.preventDefault();
            const key = button.closest("th").getAttribute("data-sort");
            toggleSort(key);
            renderTable();
        });
    }
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
