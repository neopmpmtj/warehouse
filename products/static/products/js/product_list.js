async function getProducts() {
    const response = await fetch("/api/products/");

    if (!response.ok) {
        throw new Error("Server unavailable");
    }
    
    const data = await response.json();

    return data.products;
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
        const products = await getProducts();

        await saveProducts(products);

        displayProducts(products);

        console.log("Products loaded from server");

    } catch (error) {
        const cachedProducts = await getCachedProducts();

        displayProducts(cachedProducts);

        console.log("Products loaded from IndexedDB");
    }
}


loadProducts();


// When internet access returns, immediately try to refresh products.
window.addEventListener("online", () => {
    console.log("Connection restored. Refreshing products...");
    loadProducts();
});


// Backup: retry every 30 seconds while the app is open.
setInterval(() => {
    if (navigator.onLine) {
        loadProducts();
    }
}, 30000);