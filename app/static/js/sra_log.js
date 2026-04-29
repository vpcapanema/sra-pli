/**
 * Logs no console do browser (DevTools → Consola).
 * - `debug` / `info`: ativos com hostname loopback OU com
 *   `window.__SRA_CONSOLE_VERBOSE__ === true` (servidor injeta em development).
 * - `warn` / `error`: sempre.
 * API: SRA_LOG.debug / .info / .warn / .error
 */
(function () {
  "use strict";

  function isLocalHost() {
    var h = "";
    if (typeof location !== "undefined" && location.hostname) {
      h = String(location.hostname).toLowerCase();
    }
    return (
      h === "localhost" ||
      h === "127.0.0.1" ||
      h === "::1" ||
      h === "[::1]"
    );
  }

  function isVerboseEnabled() {
    if (typeof window !== "undefined" && window.__SRA_CONSOLE_VERBOSE__ === true) {
      return true;
    }
    return isLocalHost();
  }

  var verbose = isVerboseEnabled();

  function emit(fn, args) {
    if (typeof console !== "undefined" && typeof console[fn] === "function") {
      console[fn].apply(console, args);
    }
  }

  window.SRA_LOG = {
    isVerbose: function () {
      return verbose;
    },
    debug: function () {
      if (!verbose) {
        return;
      }
      var a = ["[SRA]",].concat([].slice.call(arguments));
      emit("debug", a);
    },
    info: function () {
      if (!verbose) {
        return;
      }
      var a = ["[SRA]",].concat([].slice.call(arguments));
      emit("info", a);
    },
    warn: function () {
      var a = ["[SRA]",].concat([].slice.call(arguments));
      emit("warn", a);
    },
    error: function () {
      var a = ["[SRA]",].concat([].slice.call(arguments));
      emit("error", a);
    },
  };
})();
