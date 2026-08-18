const API_ROOT = "/api/manage/products/";
const PRICES_API = "/api/manage/products/prices/";
const FAMILY_API = "/api/manage/families/";
const SUPPLIER_API = "/api/manage/suppliers/";
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
    familyHistoryId: null,
    familyHistoryEntries: [],
    supplierHistoryId: null,
    supplierHistoryEntries: [],
    priceRows: [],
};

let familyHistoryRequestId = 0;
let supplierHistoryRequestId = 0;

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
    renderFamilyTable();
    renderSupplierTable();
    refreshDrawerLabels();
    refreshEntityHistoryLabels();
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
    const familySelect = document.getElementById("field-family");
    const selected = familySelect.value;
    const familyOptions = state.families
        .filter((family) => family.is_active || String(family.id) === selected)
        .map((family) => ({
            value: String(family.id),
            label: family.is_active ? family.name : `${family.name} (${t("inactive")})`,
        }));
    fillSelect(
        familySelect,
        familyOptions,
        familyOptions.length ? null : t("noFamilies")
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
    state.suppliers
        .filter((supplier) => supplier.is_active || selectedIds.has(supplier.id))
        .forEach((supplier) => {
            const label = document.createElement("label");
            const input = document.createElement("input");
            input.type = "checkbox";
            input.value = String(supplier.id);
            input.checked = selectedIds.has(supplier.id);
            const text = document.createElement("span");
            text.textContent = supplier.is_active
                ? supplier.name
                : `${supplier.name} (${t("inactive")})`;
            label.append(input, text);
            box.appendChild(label);
        });
}

function closeDrawer() {
    document.getElementById("drawer").hidden = true;
    document.getElementById("drawer-backdrop").hidden = true;
    state.editingId = null;
}

function firstActiveFamilyId() {
    const family = state.families.find((item) => item.is_active);
    return family ? family.id : null;
}

function sortFamilies() {
    state.families.sort((left, right) =>
        left.name.localeCompare(right.name, currentLang(), { sensitivity: "base" })
    );
}

function replaceFamily(family) {
    const index = state.families.findIndex((item) => item.id === family.id);
    if (index === -1) {
        state.families.push(family);
    } else {
        state.families[index] = family;
    }
    sortFamilies();
    state.products.forEach((product) => {
        if (product.family.id === family.id) {
            product.family = {
                id: family.id,
                name: family.name,
                is_active: family.is_active,
            };
        }
    });
    fillFilterOptions();
    fillFormLookups();
    renderTable();
    renderFamilyTable();
}

function closeFamilyDrawer() {
    document.getElementById("family-drawer").hidden = true;
    document.getElementById("family-drawer-backdrop").hidden = true;
    resetFamilyHistory();
}

function closePricesDrawer() {
    document.getElementById("prices-drawer").hidden = true;
    document.getElementById("prices-drawer-backdrop").hidden = true;
    state.priceRows = [];
}

async function openPricesDrawer() {
    closeDrawer();
    closeFamilyDrawer();
    closeSupplierDrawer();
    document.getElementById("prices-drawer").hidden = false;
    document.getElementById("prices-drawer-backdrop").hidden = false;
    try {
        const data = await api(PRICES_API);
        state.priceRows = data.products.map((row) => ({ ...row }));
        renderPricesTable();
    } catch (error) {
        showBanner(error.message, true);
    }
}

function renderPricesTable() {
    const body = document.getElementById("prices-table-body");
    if (!body) {
        return;
    }
    body.replaceChildren();
    state.priceRows.forEach((row) => {
        const tr = document.createElement("tr");
        if (!row.is_active) {
            tr.classList.add("is-inactive");
        }
        const code = document.createElement("td");
        code.textContent = row.internal_code || "—";
        const desc = document.createElement("td");
        desc.textContent = row.description;
        const costCell = document.createElement("td");
        const costInput = document.createElement("input");
        costInput.type = "number";
        costInput.step = "0.01";
        costInput.className = "prices-input";
        costInput.value = row.cost;
        costInput.dataset.field = "cost";
        costInput.dataset.id = String(row.id);
        costCell.appendChild(costInput);
        const sellCell = document.createElement("td");
        const sellInput = document.createElement("input");
        sellInput.type = "number";
        sellInput.step = "0.01";
        sellInput.className = "prices-input";
        sellInput.value = row.price;
        sellInput.dataset.field = "price";
        sellInput.dataset.id = String(row.id);
        sellCell.appendChild(sellInput);
        const wholesaleCell = document.createElement("td");
        const wholesaleInput = document.createElement("input");
        wholesaleInput.type = "number";
        wholesaleInput.step = "0.01";
        wholesaleInput.className = "prices-input";
        wholesaleInput.value = row.wholesale;
        wholesaleInput.dataset.field = "wholesale";
        wholesaleInput.dataset.id = String(row.id);
        wholesaleCell.appendChild(wholesaleInput);
        tr.append(code, desc, costCell, sellCell, wholesaleCell);
        body.appendChild(tr);
    });
}

async function savePrices() {
    clearBanner();
    const inputs = document.querySelectorAll("#prices-table-body .prices-input");
    const byId = {};
    inputs.forEach((input) => {
        const id = Number(input.dataset.id);
        const field = input.dataset.field;
        if (!byId[id]) {
            byId[id] = { id };
        }
        byId[id][field] = input.value;
    });
    const updates = Object.values(byId);
    try {
        const data = await api(PRICES_API, {
            method: "PATCH",
            body: JSON.stringify({ updates }),
        });
        data.products.forEach((row) => {
            const index = state.products.findIndex((p) => p.id === row.id);
            if (index !== -1) {
                state.products[index].cost = row.cost;
                state.products[index].price = row.price;
                state.products[index].wholesale = row.wholesale;
            }
        });
        renderTable();
        showBanner(t("pricesSaved"));
        closePricesDrawer();
    } catch (error) {
        showBanner(error.message, true);
    }
}

async function openFamilyDrawer() {
    closeDrawer();
    closeSupplierDrawer();
    document.getElementById("family-drawer").hidden = false;
    document.getElementById("family-drawer-backdrop").hidden = false;
    try {
        const data = await api(FAMILY_API);
        state.families = data.families;
        sortFamilies();
        fillFilterOptions();
        fillFormLookups();
        renderFamilyTable();
        resetFamilyHistory();
    } catch (error) {
        showBanner(error.message, true);
        renderFamilyTable();
    }
}

function renderFamilyTable() {
    const body = document.getElementById("family-table-body");
    if (!body) {
        return;
    }
    body.replaceChildren();
    if (!state.families.length) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 4;
        cell.className = "empty-row";
        cell.textContent = t("emptyFamilies");
        row.appendChild(cell);
        body.appendChild(row);
        return;
    }
    state.families.forEach((family) => {
        const row = document.createElement("tr");
        if (!family.is_active) {
            row.classList.add("is-inactive");
        }

        const name = document.createElement("td");
        name.textContent = family.name;

        const count = document.createElement("td");
        count.textContent = String(family.product_count ?? 0);

        const status = document.createElement("td");
        const pill = document.createElement("span");
        pill.className = family.is_active ? "pill pill-ok" : "pill pill-muted";
        pill.textContent = family.is_active ? t("active") : t("inactive");
        status.appendChild(pill);

        const actions = document.createElement("td");
        actions.className = "row-actions";
        const lifecycle = document.createElement("button");
        lifecycle.type = "button";
        lifecycle.className = family.is_active ? "btn btn-danger" : "btn";
        lifecycle.textContent = family.is_active ? t("deactivate") : t("reactivate");
        lifecycle.addEventListener("click", () => toggleFamilyActive(family));
        const history = document.createElement("button");
        history.type = "button";
        history.className = "btn";
        history.textContent = t("history");
        history.addEventListener("click", () => loadFamilyHistory(family));
        actions.append(lifecycle, history);

        row.append(name, count, status, actions);
        body.appendChild(row);
    });
}

function askFamilyName(options) {
    return new Promise((resolve) => {
        const backdrop = document.getElementById("family-name-dialog-backdrop");
        const dialog = document.getElementById("family-name-dialog");
        const title = document.getElementById("family-name-dialog-title");
        const help = document.getElementById("family-name-dialog-help");
        const input = document.getElementById("family-name-input");
        const error = document.getElementById("family-name-error");
        const confirmButton = document.getElementById("family-name-confirm");
        const cancelButton = document.getElementById("family-name-cancel");

        title.textContent = t(options.titleKey);
        if (options.helpKey) {
            help.textContent = t(options.helpKey);
            help.hidden = false;
        } else {
            help.hidden = true;
        }
        confirmButton.textContent = t(options.confirmKey || "save");
        input.value = options.initial || "";
        error.hidden = true;
        backdrop.hidden = false;
        dialog.hidden = false;
        input.focus();
        input.select();

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
            const name = input.value.trim();
            if (!name) {
                error.textContent = t("family_name_required");
                error.hidden = false;
                input.focus();
                return;
            }
            finish(name);
        }

        function onCancel() {
            finish(null);
        }

        function onKey(event) {
            if (event.key === "Enter") {
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

async function promptCreateFamily(showHelp) {
    const name = await askFamilyName({
        titleKey: "familyCreateTitle",
        confirmKey: "save",
        helpKey: showHelp ? "familyCreateHelp" : null,
    });
    if (name === null) {
        return null;
    }
    try {
        const data = await api(FAMILY_API, {
            method: "POST",
            body: JSON.stringify({ name }),
        });
        replaceFamily(data.family);
        showBanner(t("familyCreated"));
        if (!document.getElementById("family-drawer").hidden) {
            loadFamilyHistory(data.family);
        }
        return data.family;
    } catch (error) {
        showBanner(error.message, true);
        return null;
    }
}

async function toggleFamilyActive(family) {
    if (family.is_active && !window.confirm(t("confirmDeactivateFamily"))) {
        return;
    }
    try {
        const data = await api(`${FAMILY_API}${family.id}/`, {
            method: "PATCH",
            body: JSON.stringify({ is_active: !family.is_active }),
        });
        replaceFamily(data.family);
        showBanner(t("familySaved"));
        if (state.familyHistoryId === family.id) {
            loadFamilyHistory(data.family);
        }
    } catch (error) {
        showBanner(error.message, true);
    }
}

async function startNewProduct() {
    const activeId = firstActiveFamilyId();
    if (activeId) {
        await openDrawer(null, activeId);
        return;
    }
    const family = await promptCreateFamily(true);
    if (!family) {
        return;
    }
    await openDrawer(null, family.id);
}

async function createFamilyFromProductForm() {
    const family = await promptCreateFamily(false);
    if (!family) {
        return;
    }
    document.getElementById("field-family").value = String(family.id);
}

function selectedSupplierIdsFromForm() {
    return new Set(
        [...document.querySelectorAll("#supplier-options input:checked")].map((input) =>
            Number(input.value)
        )
    );
}

function supplierContactLabel(supplier) {
    return supplier.contact_name || supplier.email || supplier.phone || t("none");
}

function sortSuppliers() {
    state.suppliers.sort((left, right) =>
        left.name.localeCompare(right.name, currentLang(), { sensitivity: "base" })
    );
}

function replaceSupplier(supplier) {
    const index = state.suppliers.findIndex((item) => item.id === supplier.id);
    if (index === -1) {
        state.suppliers.push(supplier);
    } else {
        state.suppliers[index] = supplier;
    }
    sortSuppliers();
    state.products.forEach((product) => {
        product.suppliers = product.suppliers.map((item) =>
            item.id === supplier.id
                ? {
                      id: supplier.id,
                      name: supplier.name,
                      contact_name: supplier.contact_name,
                      email: supplier.email,
                      phone: supplier.phone,
                      notes: supplier.notes,
                      is_active: supplier.is_active,
                  }
                : item
        );
    });
    const productDrawerOpen = !document.getElementById("drawer").hidden;
    if (productDrawerOpen) {
        fillSupplierOptions(selectedSupplierIdsFromForm());
    }
    renderTable();
    renderSupplierTable();
}

function closeSupplierDrawer() {
    document.getElementById("supplier-drawer").hidden = true;
    document.getElementById("supplier-drawer-backdrop").hidden = true;
    resetSupplierHistory();
}

async function openSupplierDrawer() {
    closeDrawer();
    closeFamilyDrawer();
    document.getElementById("supplier-drawer").hidden = false;
    document.getElementById("supplier-drawer-backdrop").hidden = false;
    try {
        const data = await api(SUPPLIER_API);
        state.suppliers = data.suppliers;
        sortSuppliers();
        renderSupplierTable();
        resetSupplierHistory();
        if (!document.getElementById("drawer").hidden) {
            fillSupplierOptions(selectedSupplierIdsFromForm());
        }
    } catch (error) {
        showBanner(error.message, true);
        renderSupplierTable();
    }
}

function renderSupplierTable() {
    const body = document.getElementById("supplier-table-body");
    if (!body) {
        return;
    }
    body.replaceChildren();
    if (!state.suppliers.length) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 5;
        cell.className = "empty-row";
        cell.textContent = t("emptySuppliers");
        row.appendChild(cell);
        body.appendChild(row);
        return;
    }
    state.suppliers.forEach((supplier) => {
        const row = document.createElement("tr");
        if (!supplier.is_active) {
            row.classList.add("is-inactive");
        }

        const name = document.createElement("td");
        name.textContent = supplier.name;

        const contact = document.createElement("td");
        contact.textContent = supplierContactLabel(supplier);

        const count = document.createElement("td");
        count.textContent = String(supplier.product_count ?? 0);

        const status = document.createElement("td");
        const pill = document.createElement("span");
        pill.className = supplier.is_active ? "pill pill-ok" : "pill pill-muted";
        pill.textContent = supplier.is_active ? t("active") : t("inactive");
        status.appendChild(pill);

        const actions = document.createElement("td");
        actions.className = "row-actions";
        const edit = document.createElement("button");
        edit.type = "button";
        edit.className = "btn";
        edit.textContent = t("edit");
        edit.addEventListener("click", () => editSupplier(supplier));
        const lifecycle = document.createElement("button");
        lifecycle.type = "button";
        lifecycle.className = supplier.is_active ? "btn btn-danger" : "btn";
        lifecycle.textContent = supplier.is_active ? t("deactivate") : t("reactivate");
        lifecycle.addEventListener("click", () => toggleSupplierActive(supplier));
        const history = document.createElement("button");
        history.type = "button";
        history.className = "btn";
        history.textContent = t("history");
        history.addEventListener("click", () => loadSupplierHistory(supplier));
        actions.append(edit, lifecycle, history);

        row.append(name, contact, count, status, actions);
        body.appendChild(row);
    });
}

function supplierFormPayload() {
    return {
        name: document.getElementById("supplier-field-name").value.trim(),
        contact_name: document.getElementById("supplier-field-contact").value.trim(),
        email: document.getElementById("supplier-field-email").value.trim(),
        phone: document.getElementById("supplier-field-phone").value.trim(),
        notes: document.getElementById("supplier-field-notes").value.trim(),
    };
}

function askSupplierForm(supplier) {
    return new Promise((resolve) => {
        const backdrop = document.getElementById("supplier-form-dialog-backdrop");
        const dialog = document.getElementById("supplier-form-dialog");
        const title = document.getElementById("supplier-form-title");
        const help = document.getElementById("supplier-form-help");
        const nameInput = document.getElementById("supplier-field-name");
        const error = document.getElementById("supplier-form-error");
        const confirmButton = document.getElementById("supplier-form-confirm");
        const cancelButton = document.getElementById("supplier-form-cancel");
        const isEdit = Boolean(supplier);

        title.textContent = t(isEdit ? "supplierEditTitle" : "supplierCreateTitle");
        help.hidden = isEdit;
        nameInput.value = supplier ? supplier.name : "";
        nameInput.disabled = isEdit;
        document.getElementById("supplier-field-contact").value = supplier ? supplier.contact_name || "" : "";
        document.getElementById("supplier-field-email").value = supplier ? supplier.email || "" : "";
        document.getElementById("supplier-field-phone").value = supplier ? supplier.phone || "" : "";
        document.getElementById("supplier-field-notes").value = supplier ? supplier.notes || "" : "";
        error.hidden = true;
        backdrop.hidden = false;
        dialog.hidden = false;
        if (isEdit) {
            document.getElementById("supplier-field-contact").focus();
        } else {
            nameInput.focus();
        }

        function finish(value) {
            backdrop.hidden = true;
            dialog.hidden = true;
            nameInput.disabled = false;
            confirmButton.removeEventListener("click", onConfirm);
            cancelButton.removeEventListener("click", onCancel);
            backdrop.removeEventListener("click", onCancel);
            nameInput.removeEventListener("keydown", onKey);
            resolve(value);
        }

        function onConfirm() {
            const payload = supplierFormPayload();
            if (!payload.name) {
                error.textContent = t("supplier_name_required");
                error.hidden = false;
                if (!isEdit) {
                    nameInput.focus();
                }
                return;
            }
            finish(payload);
        }

        function onCancel() {
            finish(null);
        }

        function onKey(event) {
            if (event.key === "Enter") {
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
        nameInput.addEventListener("keydown", onKey);
    });
}

async function promptCreateSupplier() {
    const payload = await askSupplierForm(null);
    if (payload === null) {
        return null;
    }
    try {
        const data = await api(SUPPLIER_API, {
            method: "POST",
            body: JSON.stringify(payload),
        });
        replaceSupplier(data.supplier);
        showBanner(t("supplierCreated"));
        if (!document.getElementById("supplier-drawer").hidden) {
            loadSupplierHistory(data.supplier);
        }
        return data.supplier;
    } catch (error) {
        showBanner(error.message, true);
        return null;
    }
}

async function editSupplier(supplier) {
    const payload = await askSupplierForm(supplier);
    if (payload === null) {
        return;
    }
    try {
        const data = await api(`${SUPPLIER_API}${supplier.id}/`, {
            method: "PATCH",
            body: JSON.stringify({
                contact_name: payload.contact_name,
                email: payload.email,
                phone: payload.phone,
                notes: payload.notes,
            }),
        });
        replaceSupplier(data.supplier);
        showBanner(t("supplierSaved"));
        if (state.supplierHistoryId === supplier.id) {
            loadSupplierHistory(data.supplier);
        }
    } catch (error) {
        showBanner(error.message, true);
    }
}

async function toggleSupplierActive(supplier) {
    if (supplier.is_active && !window.confirm(t("confirmDeactivateSupplier"))) {
        return;
    }
    try {
        const data = await api(`${SUPPLIER_API}${supplier.id}/`, {
            method: "PATCH",
            body: JSON.stringify({ is_active: !supplier.is_active }),
        });
        replaceSupplier(data.supplier);
        showBanner(t("supplierSaved"));
        if (state.supplierHistoryId === supplier.id) {
            loadSupplierHistory(data.supplier);
        }
    } catch (error) {
        showBanner(error.message, true);
    }
}

async function createSupplierFromProductForm() {
    const supplier = await promptCreateSupplier();
    if (!supplier) {
        return;
    }
    const selected = selectedSupplierIdsFromForm();
    selected.add(supplier.id);
    fillSupplierOptions(selected);
}

function formPayload() {
    const supplierIds = [...document.querySelectorAll("#supplier-options input:checked")].map(
        (input) => Number(input.value)
    );
    return {
        family_id: Number(document.getElementById("field-family").value),
        internal_code: document.getElementById("field-internal-code").value,
        description: document.getElementById("field-description").value,
        price: document.getElementById("field-price").value,
        unit_of_measure: document.getElementById("field-unit").value,
        reorder_level: document.getElementById("field-reorder").value,
        reason: document.getElementById("field-reason").value,
        supplier_ids: supplierIds,
    };
}

function fillHistoryList(list, entries) {
    list.replaceChildren();
    if (!entries.length) {
        const item = document.createElement("li");
        item.textContent = t("noHistory");
        list.appendChild(item);
        return;
    }
    entries.forEach((entry) => {
        const item = document.createElement("li");
        const actionKey = `action${entry.action.charAt(0).toUpperCase()}${entry.action.slice(1)}`;
        const when = new Date(entry.created_at).toLocaleString();
        const who = entry.user_email || "—";
        const reason = entry.reason ? ` — ${entry.reason}` : "";
        item.textContent = `${t(actionKey)} · ${who} · ${when}${reason}`;
        list.appendChild(item);
    });
}

async function loadHistory(productId) {
    const list = document.getElementById("history-list");
    const data = await api(`${API_ROOT}${productId}/history/`);
    fillHistoryList(list, data.history);
}

function resetFamilyHistory() {
    familyHistoryRequestId += 1;
    state.familyHistoryId = null;
    state.familyHistoryEntries = [];
    const title = document.getElementById("family-history-title");
    const hint = document.getElementById("family-history-hint");
    const list = document.getElementById("family-history-list");
    if (!title || !hint || !list) {
        return;
    }
    title.textContent = t("history");
    hint.hidden = false;
    list.replaceChildren();
}

function resetSupplierHistory() {
    supplierHistoryRequestId += 1;
    state.supplierHistoryId = null;
    state.supplierHistoryEntries = [];
    const title = document.getElementById("supplier-history-title");
    const hint = document.getElementById("supplier-history-hint");
    const list = document.getElementById("supplier-history-list");
    if (!title || !hint || !list) {
        return;
    }
    title.textContent = t("history");
    hint.hidden = false;
    list.replaceChildren();
}

function showFamilyHistory(family) {
    const title = document.getElementById("family-history-title");
    const hint = document.getElementById("family-history-hint");
    const list = document.getElementById("family-history-list");
    if (!title || !hint || !list) {
        return;
    }
    title.textContent = t("historyFor", { name: family.name });
    hint.hidden = true;
    fillHistoryList(list, state.familyHistoryEntries);
}

function showSupplierHistory(supplier) {
    const title = document.getElementById("supplier-history-title");
    const hint = document.getElementById("supplier-history-hint");
    const list = document.getElementById("supplier-history-list");
    if (!title || !hint || !list) {
        return;
    }
    title.textContent = t("historyFor", { name: supplier.name });
    hint.hidden = true;
    fillHistoryList(list, state.supplierHistoryEntries);
}

async function loadFamilyHistory(family) {
    const requestId = ++familyHistoryRequestId;
    if (state.familyHistoryId !== family.id) {
        state.familyHistoryEntries = [];
    }
    state.familyHistoryId = family.id;
    showFamilyHistory(family);
    try {
        const data = await api(`${FAMILY_API}${family.id}/history/`);
        if (requestId !== familyHistoryRequestId) {
            return;
        }
        state.familyHistoryEntries = data.history;
        showFamilyHistory(family);
    } catch (error) {
        if (requestId !== familyHistoryRequestId) {
            return;
        }
        showBanner(error.message, true);
    }
}

async function loadSupplierHistory(supplier) {
    const requestId = ++supplierHistoryRequestId;
    if (state.supplierHistoryId !== supplier.id) {
        state.supplierHistoryEntries = [];
    }
    state.supplierHistoryId = supplier.id;
    showSupplierHistory(supplier);
    try {
        const data = await api(`${SUPPLIER_API}${supplier.id}/history/`);
        if (requestId !== supplierHistoryRequestId) {
            return;
        }
        state.supplierHistoryEntries = data.history;
        showSupplierHistory(supplier);
    } catch (error) {
        if (requestId !== supplierHistoryRequestId) {
            return;
        }
        showBanner(error.message, true);
    }
}

function refreshEntityHistoryLabels() {
    if (state.familyHistoryId) {
        const family = state.families.find((item) => item.id === state.familyHistoryId);
        if (family) {
            showFamilyHistory(family);
        } else {
            resetFamilyHistory();
        }
    } else {
        const title = document.getElementById("family-history-title");
        if (title) {
            title.textContent = t("history");
        }
    }
    if (state.supplierHistoryId) {
        const supplier = state.suppliers.find((item) => item.id === state.supplierHistoryId);
        if (supplier) {
            showSupplierHistory(supplier);
        } else {
            resetSupplierHistory();
        }
    } else {
        const title = document.getElementById("supplier-history-title");
        if (title) {
            title.textContent = t("history");
        }
    }
}

async function openDrawer(product, selectFamilyId) {
    closeFamilyDrawer();
    closeSupplierDrawer();
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
        const familyId = selectFamilyId || firstActiveFamilyId();
        if (familyId) {
            document.getElementById("field-family").value = String(familyId);
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
    renderFamilyTable();
    renderSupplierTable();
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
    document.getElementById("manage-families").addEventListener("click", () => {
        openFamilyDrawer();
    });
    document.getElementById("manage-suppliers").addEventListener("click", () => {
        openSupplierDrawer();
    });
    document.getElementById("manage-prices").addEventListener("click", () => {
        openPricesDrawer();
    });
    document.getElementById("prices-drawer-close").addEventListener("click", closePricesDrawer);
    document.getElementById("prices-drawer-backdrop").addEventListener("click", closePricesDrawer);
    document.getElementById("prices-save").addEventListener("click", savePrices);
    document.getElementById("new-product").addEventListener("click", () => startNewProduct());
    document.getElementById("new-family").addEventListener("click", () => promptCreateFamily(false));
    document.getElementById("new-family-inline").addEventListener("click", () => createFamilyFromProductForm());
    document.getElementById("new-supplier").addEventListener("click", () => promptCreateSupplier());
    document.getElementById("new-supplier-inline").addEventListener("click", () => createSupplierFromProductForm());
    document.getElementById("family-drawer-close").addEventListener("click", closeFamilyDrawer);
    document.getElementById("family-drawer-backdrop").addEventListener("click", closeFamilyDrawer);
    document.getElementById("supplier-drawer-close").addEventListener("click", closeSupplierDrawer);
    document.getElementById("supplier-drawer-backdrop").addEventListener("click", closeSupplierDrawer);
    document.getElementById("drawer-close").addEventListener("click", closeDrawer);
    document.getElementById("drawer-backdrop").addEventListener("click", closeDrawer);
    document.getElementById("product-form").addEventListener("submit", saveProduct);
    document.getElementById("drawer-lifecycle").addEventListener("click", () => {
        const product = state.products.find((item) => item.id === state.editingId);
        if (product) {
            toggleLifecycle(product);
        }
    });
    const sortableHead = document.querySelector(".page .grid thead");
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
    refreshEntityHistoryLabels();
    bindEvents();
    try {
        await loadCatalog();
    } catch (error) {
        showBanner(t("loadFailed"), true);
    }
}

init();
