(function () {
    const mount = document.getElementById("site-nav");
    if (!mount) {
        return;
    }

    const active = (document.body.dataset.navActive || "").toLowerCase();
    const items = [
        { key: "home", label: "Home", href: "/" },
        { key: "table", label: "Cluster Table", href: "/Table/index_table.html" },
        { key: "stamps", label: "Stamps", href: "/stamps" },
    ];

    const links = items
        .map((item) => {
            const activeClass = item.key === active ? " is-active" : "";
            const ariaCurrent = item.key === active ? ' aria-current="page"' : "";
            return `<a href="${item.href}" class="w3-bar-item w3-button w3-hover-teal${activeClass}"${ariaCurrent}>${item.label}</a>`;
        })
        .join("");

    mount.innerHTML = `<div class="w3-bar" id="nav">${links}</div>`;
})();
