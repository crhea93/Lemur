function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

function decodeSegment(value) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function splitObsids(obsids) {
  if (!obsids) {
    return [];
  }
  return String(obsids)
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function fitsDownloadPath(name) {
  return `/api/fits/${encodeURIComponent(name)}/download`;
}

function fitsZipKeyCandidates(name) {
  const compact = String(name).replace(/\s+/g, "");
  return [
    `${name}.zip`,
    `${compact}.zip`,
    `${name}/fits.zip`,
    `${name}/${name}.zip`,
    `${compact}/fits.zip`,
    `${compact}/${compact}.zip`,
  ];
}

async function handleHealth() {
  return json({ status: "ok" });
}

async function handleResolveName(request) {
  const url = new URL(request.url);
  const q = (url.searchParams.get("q") || "").trim();
  if (!q) {
    return json({ query: "", names: [] });
  }

  const names = new Set([q]);
  try {
    const sesameUrl = `https://cds.unistra.fr/cgi-bin/nph-sesame/-oI/SNV?${encodeURIComponent(q)}`;
    const resp = await fetch(sesameUrl, {
      headers: { "user-agent": "LemurArchive/1.0" },
    });
    if (resp.ok) {
      const text = await resp.text();
      for (const line of text.split("\n")) {
        const match = line.match(/^%I\S*\s+(.+)$/);
        if (!match) {
          continue;
        }
        const candidate = String(match[1] || "").trim();
        if (candidate) {
          names.add(candidate);
        }
      }
    }
  } catch {
    // Best-effort resolver endpoint; fallback to raw query.
  }

  return json({ query: q, names: Array.from(names) });
}

async function handleListClusters(env) {
  const sql = `
        SELECT
            c.ID,
            c.Name,
            c.redshift,
            c.RightAsc,
            c.Declination,
            c.R_cool_3,
            c.R_cool_7,
            c.csb_ct,
            c.csb_pho,
            c.csb_flux,
            GROUP_CONCAT(o.Obsid) AS Obsids
        FROM Clusters c
        LEFT JOIN Obsids o ON o.ClusterNumber = c.ID
        GROUP BY c.ID
        ORDER BY c.Name COLLATE NOCASE
    `;

  const res = await env.DB.prepare(sql).all();
  const rows = res.results || [];

  const out = rows.map((row) => ({
    ID: row.ID,
    Name: row.Name,
    redshift: row.redshift,
    RightAsc: row.RightAsc,
    Declination: row.Declination,
    R_cool_3: row.R_cool_3,
    R_cool_7: row.R_cool_7,
    csb_ct: row.csb_ct,
    csb_pho: row.csb_pho,
    csb_flux: row.csb_flux,
    Obsids: splitObsids(row.Obsids),
    fits_download_url: fitsDownloadPath(row.Name),
  }));

  return json(out);
}

async function assetExists(env, origin, path) {
  const req = new Request(new URL(path, origin).toString(), {
    method: "GET",
  });
  const res = await env.ASSETS.fetch(req);
  return res.ok;
}

async function handleClusterDetail(env, request, name) {
  const cluster = await env.DB.prepare("SELECT * FROM Clusters WHERE Name = ?")
    .bind(name)
    .first();

  if (!cluster) {
    return json({ detail: "Cluster not found" }, 404);
  }

  const obsRes = await env.DB.prepare(
    "SELECT Obsid FROM Obsids WHERE ClusterNumber = ?",
  )
    .bind(cluster.ID)
    .all();
  const obsids = (obsRes.results || []).map((r) => r.Obsid);

  const regionRes = await env.DB.prepare(
    "SELECT * FROM Region WHERE idCluster = ? ORDER BY idRegion",
  )
    .bind(cluster.ID)
    .all();
  const regions = regionRes.results || [];

  const url = new URL(request.url);
  const baseUrl = `/Cluster_plots/${encodeURIComponent(name)}`;
  const maybeMain = `${baseUrl}/bkgsub_exp.png`;
  const files = (await assetExists(env, url.origin, maybeMain))
    ? ["bkgsub_exp.png"]
    : [];

  return json({
    cluster,
    obsids,
    regions,
    fits_download_url: fitsDownloadPath(name),
    plots: {
      base_url: baseUrl,
      files,
    },
  });
}

async function handleFitsDownload(env, _request, name) {
  if (!env.FITS || typeof env.FITS.get !== "function") {
    return json({ detail: "FITS storage binding is not configured" }, 500);
  }

  for (const key of fitsZipKeyCandidates(name)) {
    const object = await env.FITS.get(key);
    if (!object) {
      continue;
    }

    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set("etag", object.httpEtag);
    headers.set("content-type", "application/zip");
    headers.set(
      "content-disposition",
      `attachment; filename="${encodeURIComponent(name)}_fits.zip"`,
    );
    return new Response(object.body, { headers });
  }

  return json({ detail: "FITS archive not found for this cluster" }, 404);
}

async function handleApi(env, request, pathname) {
  if (request.method !== "GET") {
    return json({ detail: "Method not allowed" }, 405);
  }

  if (pathname === "/api/health") {
    return handleHealth();
  }
  if (pathname === "/api/clusters") {
    return handleListClusters(env);
  }
  if (pathname === "/api/resolve-name") {
    return handleResolveName(request);
  }

  const clusterMatch = pathname.match(/^\/api\/clusters\/(.+)$/);
  if (clusterMatch) {
    const name = decodeSegment(clusterMatch[1]);
    return handleClusterDetail(env, request, name);
  }

  const fitsMatch = pathname.match(/^\/api\/fits\/(.+)\/download$/);
  if (fitsMatch) {
    const name = decodeSegment(fitsMatch[1]);
    return handleFitsDownload(env, request, name);
  }

  return json({ detail: "Not found" }, 404);
}

function rewriteClusterPath(request) {
  const url = new URL(request.url);
  if (url.pathname === "/") {
    url.pathname = "/index.html";
    return new Request(url, request);
  }
  if (url.pathname === "/cluster.html") {
    return request;
  }
  if (url.pathname.startsWith("/cluster/")) {
    url.pathname = "/cluster.html";
    return new Request(url, request);
  }
  return request;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    try {
      if (url.pathname.startsWith("/api/")) {
        return await handleApi(env, request, url.pathname);
      }

      return env.ASSETS.fetch(rewriteClusterPath(request));
    } catch (err) {
      return json(
        {
          detail: "Internal server error",
          error: String(err && err.message ? err.message : err),
        },
        500,
      );
    }
  },
};
