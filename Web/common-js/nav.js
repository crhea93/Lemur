(function () {
  const mount = document.getElementById("site-nav");
  if (!mount) {
    return;
  }

  const active = (document.body.dataset.navActive || "").toLowerCase();
  const items = [
    { key: "home", label: "Home", href: "/" },
    { key: "table", label: "Cluster Table", href: "/Table/index_table.html" },
    { key: "reduction", label: "Data Reduction", href: "/reduction.html" },
    { key: "stamps", label: "Stamps", href: "/stamps" },
    {
      key: "github",
      label: "GitHub",
      href: "https://github.com/crhea93/Lemur",
      external: true,
    },
  ];

  const links = items
    .map((item) => {
      const activeClass = item.key === active ? " is-active" : "";
      const ariaCurrent = item.key === active ? ' aria-current="page"' : "";
      const targetAttrs = item.external
        ? ' target="_blank" rel="noopener noreferrer"'
        : "";
      return `<a href="${item.href}" class="w3-bar-item w3-button w3-hover-teal${activeClass}"${ariaCurrent}${targetAttrs}>${item.label}</a>`;
    })
    .join("");

  mount.innerHTML = `<div class="w3-bar" id="nav">${links}</div>`;
})();
