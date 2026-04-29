/**
 * Redireciona para o login quando fetch devolve 401 (sessão expirada).
 * Em localhost, SRA_LOG regista pedidos (verbose).
 * Carregado no head de base.html após sra_log.js.
 */
(function () {
  "use strict";
  var nativeFetch = window.fetch;
  window.fetch = async function (input, init) {
    var log = window.SRA_LOG;
    var verbose = log && typeof log.isVerbose === "function" && log.isVerbose();
    var url = "";
    var method = "GET";
    var t0 = 0;
    if (verbose) {
      url =
        typeof input === "string"
          ? input
          : input && typeof input.url === "string"
            ? input.url
            : "";
      method =
        (init && init.method) ||
        (typeof input === "object" && input && input.method) ||
        "GET";
      t0 =
        typeof performance !== "undefined" && performance.now
          ? performance.now()
          : 0;
      log.debug("fetch →", method, url || "(request)");
    }
    var resp = await nativeFetch.apply(this, arguments);
    if (verbose && log) {
      var ms =
        t0 && typeof performance !== "undefined" && performance.now
          ? Math.round(performance.now() - t0)
          : null;
      log.debug("fetch ←", resp.status, method, url || "", ms != null ? ms + "ms" : "");
    }
    if (resp.status === 401) {
      window.location.href = "/login";
    }
    return resp;
  };
})();
