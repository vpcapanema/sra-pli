(function () {
  const inp = document.getElementById("login-password");
  const btn = document.getElementById("login-toggle-pw");
  if (!inp || !btn) return;
  btn.addEventListener("click", function () {
    const show = inp.type === "password";
    inp.type = show ? "text" : "password";
    btn.setAttribute("aria-pressed", show ? "true" : "false");
    btn.textContent = show ? "Ocultar" : "Mostrar";
    btn.title = show ? "Ocultar senha" : "Mostrar senha";
  });
})();
