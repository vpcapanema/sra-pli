(function () {
  var PARTICULAS = ['do','da','de','dos','das','du','e','di','del','la','von','van'];
  function formatarNome(raw) {
    if (!raw) return '';
    var palavras = raw.replace(/\s+/g, ' ').trim().split(' ');
    return palavras.map(function (p, i) {
      var baixa = p.toLocaleLowerCase('pt-BR');
      if (i > 0 && PARTICULAS.indexOf(baixa) !== -1) return baixa;
      return baixa.charAt(0).toLocaleUpperCase('pt-BR') + baixa.slice(1);
    }).join(' ');
  }
  var inp = document.getElementById('inp-nome');
  if (inp) {
    inp.addEventListener('blur', function () { inp.value = formatarNome(inp.value); });
    var form = document.getElementById('form-novo-usuario');
    if (form) form.addEventListener('submit', function () { inp.value = formatarNome(inp.value); });
  }
  var senha = document.getElementById('inp-senha-usuario');
  var btnSenha = document.getElementById('btn-toggle-senha-usuario');
  if (senha && btnSenha) {
    btnSenha.addEventListener('click', function () {
      var mostrar = senha.type === 'password';
      senha.type = mostrar ? 'text' : 'password';
      btnSenha.textContent = mostrar ? 'Ocultar' : 'Mostrar';
      btnSenha.setAttribute('aria-pressed', mostrar ? 'true' : 'false');
    });
  }
})();
