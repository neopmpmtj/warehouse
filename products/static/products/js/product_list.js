async function getProducts() {
    const response = await fetch("/api/products/");

    if (!response.ok) {
        throw new Error("Server unavailable");
    }

    return response.json();
}


function formatCatalogTimestamp(isoTimestamp) {
    if (!isoTimestamp) {
        return "unknown time";
    }

    return new Date(isoTimestamp).toLocaleString();
}


function displayCatalogStatus(catalogUpdatedAt, fromCache) {
    const statusElement = document.getElementById("catalog-status");

    if (!statusElement) {
        return;
    }

    const timestampText = formatCatalogTimestamp(catalogUpdatedAt);

    if (fromCache) {
        statusElement.textContent =
            `Catalogue cached at ${timestampText}. Stock may be outdated until you reconnect.`;
        return;
    }

    statusElement.textContent = `Catalogue updated at ${timestampText}.`;
}


function displayProducts(products) {
    const tableBody = document.getElementById("product-table-body");

    tableBody.replaceChildren();

    for (const product of products) {
        const row = document.createElement("tr");

        const idCell = document.createElement("td");
        idCell.textContent = product.id;

        const descriptionCell = document.createElement("td");
        descriptionCell.textContent = product.description;

        const stockCell = document.createElement("td");
        stockCell.textContent = product.stock;

        const priceCell = document.createElement("td");
        priceCell.textContent = product.price;

        row.append(
            idCell,
            descriptionCell,
            stockCell,
            priceCell
        );

        tableBody.appendChild(row);
    }
}


async function loadProducts() {
    try {
        const data = await getProducts();

        await saveProducts(data.products, data.catalog_updated_at);

        displayProducts(data.products);
        displayCatalogStatus(data.catalog_updated_at, false);

        console.log("Products loaded from server");

    } catch (error) {
        const cachedProducts = await getCachedProducts();
        const catalogUpdatedAt = await getSyncMetadata("catalog_updated_at");

        displayProducts(cachedProducts);

        if (cachedProducts.length === 0) {
            const statusElement = document.getElementById("catalog-status");
            if (statusElement) {
                statusElement.textContent = "No cached products available offline.";
            }
        } else {
            displayCatalogStatus(catalogUpdatedAt, true);
        }

        console.log("Products loaded from IndexedDB");
    }
}


loadProducts();


window.addEventListener("online", () => {
    console.log("Connection restored. Refreshing products...");
    loadProducts();
});


setInterval(() => {
    if (navigator.onLine) {
        loadProducts();
    }
}, 30000);
