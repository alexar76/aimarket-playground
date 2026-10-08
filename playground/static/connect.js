(() => {
  "use strict";
  const messages = {
    en: {demo:"Live demo",protocol:"Protocol",title:"Connect your provider",testMode:"Test mode · no Hub payment",contract:"Contract",ownership:"Endpoint control",report:"Test report",import:"Import JSON",manifestNote:"Public HTTPS endpoint · Ed25519 provider key",input:"Test input",consent:"I control this endpoint and authorize one real call with harmless test data. My service may incur its own costs.",prepare:"Prepare connection",verification:"Verification",ready:"Ready",manifestCheck:"Manifest & input",invokeCheck:"Invoke & output schema",signatureCheck:"Request-bound signature",proofTitle:"Endpoint ownership proof",proofNote:"Serve this JSON at the address below, then run the check. The proof expires after 15 minutes.",downloadProof:"Download proof",copyToken:"Copy token",generatorNote:"Generated Python / TypeScript provider: set AIMARKET_ONBOARDING_CHALLENGE to this token and restart.",run:"Verify & invoke",scope:"This report covers one provider invocation and its signature. Hub receipts, payments, discovery and federation are not tested.",evidence:"Signed evidence & report",downloadReport:"Download report",ciTitle:"Local & CI",ciNote:"Same invoke profile. Exit 0 on pass, 1 on failure. Use --allow-loopback for a local provider.",guide:"Profile & setup guide",footer:"Provider invoke profile · not protocol certification",working:"Checking…",passed:"Passed",failed:"Failed",proofReady:"Proof required",jsonError:"Enter valid JSON objects for manifest and input (maximum 64 KB).",networkError:"Connection lost. Retry with the same challenge to retrieve the result.",copied:"Copied",newCheck:"New connection",manifest:"Manifest & input",endpoint_control:"Endpoint control",invoke:"Provider invoke",output_schema:"Output schema",provider_signature:"Ed25519 signature"},
    ru: {demo:"Живое демо",protocol:"Протокол",title:"Подключить поставщика",testMode:"Тестовый режим · без оплаты Hub",contract:"Контракт",ownership:"Контроль эндпоинта",report:"Отчёт",import:"Импорт JSON",manifestNote:"Публичный HTTPS эндпоинт · ключ Ed25519",input:"Тестовые входные данные",consent:"Я контролирую этот эндпоинт и разрешаю один реальный вызов с безопасными тестовыми данными. Мой сервис может понести собственные расходы.",prepare:"Подготовить подключение",verification:"Верификация",ready:"Готово к запуску",manifestCheck:"Манифест и входные данные",invokeCheck:"Вызов и схема результата",signatureCheck:"Подпись, привязанная к запросу",proofTitle:"Подтверждение контроля эндпоинта",proofNote:"Разместите этот JSON по адресу ниже, затем запустите проверку. Подтверждение действует 15 минут.",downloadProof:"Скачать подтверждение",copyToken:"Копировать токен",generatorNote:"Поставщик из генератора Python / TypeScript: задайте AIMARKET_ONBOARDING_CHALLENGE равным этому токену и перезапустите сервис.",run:"Проверить и вызвать",scope:"Отчёт проверяет один вызов поставщика и его подпись. Квитанции Hub, платежи, обнаружение и федерация не проверяются.",evidence:"Подписанные данные и отчёт",downloadReport:"Скачать отчёт",ciTitle:"Локально и в CI",ciNote:"Тот же профиль вызова. Код выхода 0 при успехе, 1 при ошибке. Для локального поставщика: --allow-loopback.",guide:"Профиль и настройка",footer:"Профиль вызова поставщика · не сертификация протокола",working:"Проверка…",passed:"Пройдено",failed:"Ошибка",proofReady:"Нужно подтверждение",jsonError:"Введите JSON-объекты манифеста и входных данных (не более 64 КБ).",networkError:"Соединение прервано. Повторите запрос с тем же подтверждением, чтобы получить результат.",copied:"Скопировано",newCheck:"Новое подключение",manifest:"Манифест и входные данные",endpoint_control:"Контроль эндпоинта",invoke:"Вызов поставщика",output_schema:"Схема результата",provider_signature:"Подпись Ed25519"},
    es: {demo:"Demo en vivo",protocol:"Protocolo",title:"Conecta tu proveedor",testMode:"Modo de prueba · sin pago al Hub",contract:"Contrato",ownership:"Control del endpoint",report:"Informe",import:"Importar JSON",manifestNote:"Endpoint HTTPS público · clave Ed25519",input:"Entrada de prueba",consent:"Controlo este endpoint y autorizo una llamada real con datos de prueba inocuos. Mi servicio puede incurrir en costes propios.",prepare:"Preparar conexión",verification:"Verificación",ready:"Listo",manifestCheck:"Manifiesto y entrada",invokeCheck:"Invocación y esquema de salida",signatureCheck:"Firma vinculada a la solicitud",proofTitle:"Prueba de control del endpoint",proofNote:"Publica este JSON en la dirección indicada y ejecuta la prueba. Caduca en 15 minutos.",downloadProof:"Descargar prueba",copyToken:"Copiar token",generatorNote:"Proveedor generado Python / TypeScript: asigna este token a AIMARKET_ONBOARDING_CHALLENGE y reinicia.",run:"Verificar e invocar",scope:"El informe cubre una invocación y su firma. No prueba recibos Hub, pagos, descubrimiento ni federación.",evidence:"Evidencia firmada e informe",downloadReport:"Descargar informe",ciTitle:"Local y CI",ciNote:"Mismo perfil. Código 0 al pasar, 1 al fallar. Para un proveedor local: --allow-loopback.",guide:"Perfil y configuración",footer:"Perfil de invocación · no es certificación del protocolo",working:"Verificando…",passed:"Aprobado",failed:"Fallido",proofReady:"Prueba requerida",jsonError:"Introduce objetos JSON válidos para manifiesto y entrada (máximo 64 KB).",networkError:"Conexión interrumpida. Reintenta con el mismo desafío para recuperar el resultado.",copied:"Copiado",newCheck:"Nueva conexión",manifest:"Manifiesto y entrada",endpoint_control:"Control del endpoint",invoke:"Invocación",output_schema:"Esquema de salida",provider_signature:"Firma Ed25519"},
    fr: {demo:"Démo en direct",protocol:"Protocole",title:"Connecter votre fournisseur",testMode:"Mode test · sans paiement Hub",contract:"Contrat",ownership:"Contrôle du point de terminaison",report:"Rapport",import:"Importer JSON",manifestNote:"Point de terminaison (endpoint) HTTPS public · clé Ed25519",input:"Entrée de test",consent:"Je contrôle ce point de terminaison et autorise un appel réel avec des données de test sans danger. Mon service peut engendrer ses propres frais.",prepare:"Préparer la connexion",verification:"Vérification",ready:"Prêt",manifestCheck:"Manifeste et entrée",invokeCheck:"Invocation et schéma de sortie",signatureCheck:"Signature liée à la requête",proofTitle:"Preuve de contrôle du point de terminaison",proofNote:"Publiez ce JSON à l’adresse indiquée, puis lancez le test. La preuve expire après 15 minutes.",downloadProof:"Télécharger la preuve",copyToken:"Copier le jeton",generatorNote:"Fournisseur Python / TypeScript généré : définissez AIMARKET_ONBOARDING_CHALLENGE avec ce jeton et redémarrez.",run:"Vérifier et invoquer",scope:"Le rapport couvre un appel et sa signature. Les reçus Hub, paiements, découverte et fédération ne sont pas testés.",evidence:"Preuve signée et rapport",downloadReport:"Télécharger le rapport",ciTitle:"Local et CI",ciNote:"Même profil. Code 0 en cas de succès, 1 en cas d’échec. Pour un fournisseur local : --allow-loopback.",guide:"Profil et configuration",footer:"Profil d’invocation du fournisseur · sans certification du protocole",working:"Vérification…",passed:"Réussi",failed:"Échec",proofReady:"Preuve requise",jsonError:"Saisissez des objets JSON valides pour manifeste et entrée (64 Ko maximum).",networkError:"Connexion interrompue. Réessayez avec le même défi pour récupérer le résultat.",copied:"Copié",newCheck:"Nouvelle connexion",manifest:"Manifeste et entrée",endpoint_control:"Contrôle du point de terminaison",invoke:"Invocation du fournisseur",output_schema:"Schéma de sortie",provider_signature:"Signature Ed25519"},
    zh: {demo:"实时演示",protocol:"协议",title:"连接你的提供方",testMode:"测试模式 · 无 Hub 支付",contract:"契约",ownership:"端点控制",report:"测试报告",import:"导入 JSON",manifestNote:"公开 HTTPS 端点 · Ed25519 密钥",input:"测试输入",consent:"我控制此端点，并授权使用无害测试数据进行一次真实调用。我的服务可能产生自身费用。",prepare:"准备连接",verification:"验证",ready:"就绪",manifestCheck:"清单与输入",invokeCheck:"调用与输出模式",signatureCheck:"绑定请求的签名",proofTitle:"端点控制证明",proofNote:"在下方地址提供此 JSON，然后运行检查。证明将在 15 分钟后过期。",downloadProof:"下载证明",copyToken:"复制令牌",generatorNote:"生成的 Python / TypeScript 提供方：将 AIMARKET_ONBOARDING_CHALLENGE 设置为此令牌并重启。",run:"验证并调用",scope:"报告涵盖一次提供方调用及其签名。不测试 Hub 收据、支付、发现或联邦。",evidence:"签名证据与报告",downloadReport:"下载报告",ciTitle:"本地与 CI",ciNote:"相同调用配置。成功退出码 0，失败为 1。本地提供方使用 --allow-loopback。",guide:"配置与安装指南",footer:"提供方调用配置 · 非协议认证",working:"检查中…",passed:"通过",failed:"失败",proofReady:"需要证明",jsonError:"请输入有效的清单和输入 JSON 对象（最大 64 KB）。",networkError:"连接中断。使用同一挑战重试以获取结果。",copied:"已复制",newCheck:"新连接",manifest:"清单与输入",endpoint_control:"端点控制",invoke:"提供方调用",output_schema:"输出模式",provider_signature:"Ed25519 签名"}
  };
  const $ = (id) => document.getElementById(id);
  const i18n = globalThis.PlaygroundI18n;
  let lang = "en";
  let challenge = null, report = null, state = "ready", busy = false;
  let visitor;
  try { visitor = sessionStorage.getItem("aimarket-provider-visitor"); } catch (_) {}
  if (!visitor) visitor = crypto.randomUUID();
  try { sessionStorage.setItem("aimarket-provider-visitor", visitor); } catch (_) {}
  const t = (key) => messages[lang][key] || messages.en[key] || key;
  function language() {
    document.documentElement.lang = lang;
    document.title = `AIMarket | ${t("title")}`;
    $("guide-link").href = `/connect/guide?lang=${lang}`;
    document.querySelectorAll("[data-text]").forEach((node) => { node.textContent = t(node.dataset.text); });
    $("status").textContent = t(state);
    if (challenge) $("prepare").textContent = t("newCheck");
    if (report) renderReport();
  }
  function status(value) { state = value; $("status").textContent = t(value); $("status").dataset.state = value; }
  function setBusy(value) {
    busy = value;
    for (const id of ["prepare", "run-check", "manifest-file", "manifest", "invoke-input", "consent"]) $(id).disabled = value;
    document.querySelector(".verification").setAttribute("aria-busy", String(value));
  }
  function progress(step) {
    for (let i = 1; i <= 3; i++) {
      if (step === i) $(`step-${i}`).setAttribute("aria-current", "step");
      else $(`step-${i}`).removeAttribute("aria-current");
    }
  }
  function showError(message) { $("error").textContent = message; $("error").hidden = false; }
  async function api(path, payload) {
    let response;
    try {
      response = await fetch(`/api/provider-check/${path}`, {method:"POST", headers:{"Content-Type":"application/json", "X-Playground-Visitor":visitor}, body:JSON.stringify(payload || {})});
    } catch (_) { throw new Error(t("networkError")); }
    const body = await response.json();
    if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : `HTTP ${response.status}`);
    return body;
  }
  function download(value, name) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2) + "\n"], {type:"application/json"}));
    const a = document.createElement("a"); a.href = url; a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function invalidate() {
    if (busy) return;
    challenge = null; report = null;
    $("proof-panel").hidden = true; $("report-panel").hidden = true; $("empty").hidden = false;
    $("error").hidden = true; $("prepare").textContent = t("prepare");
    status("ready"); progress(1);
  }
  for (const id of ["manifest", "invoke-input", "consent"]) $(id).addEventListener("input", invalidate);
  $("manifest-file").addEventListener("change", async () => {
    const file = $("manifest-file").files[0]; if (!file) return;
    if (file.size > 65536) { showError(t("jsonError")); return; }
    $("manifest").value = await file.text(); invalidate();
  });
  $("connect-form").addEventListener("submit", async (event) => {
    event.preventDefault(); if (busy) return;
    invalidate();
    let payload;
    try {
      payload = {manifest:JSON.parse($("manifest").value), input:JSON.parse($("invoke-input").value), consent:$("consent").checked};
      if (!payload.manifest || !payload.input || typeof payload.manifest !== "object" || typeof payload.input !== "object" || Array.isArray(payload.manifest) || Array.isArray(payload.input) || new TextEncoder().encode(JSON.stringify(payload)).length > 65536) throw new Error();
      // Preserve duplicate keys and numeric spelling for the server's strict parser.
      payload.manifest = $("manifest").value;
      payload.input = $("invoke-input").value;
      if (new TextEncoder().encode(JSON.stringify(payload)).length > 65536) throw new Error();
    } catch (_) { showError(t("jsonError")); return; }
    setBusy(true); status("working");
    try {
      challenge = await api("challenges", payload);
      $("proof-url").textContent = challenge.proof_url;
      $("proof-json").textContent = JSON.stringify(challenge.proof, null, 2);
      $("empty").hidden = true; $("proof-panel").hidden = false;
      $("prepare").textContent = t("newCheck"); status("proofReady"); progress(2);
    } catch (error) { status("failed"); showError(error.message); }
    finally { setBusy(false); }
  });
  function renderReport() {
    $("checks").replaceChildren();
    for (const check of report.checks) {
      const row = document.createElement("li"); row.className = check.status;
      const label = document.createElement("span"); label.textContent = t(check.id);
      const result = document.createElement("strong"); result.textContent = t(check.status);
      row.append(label, result);
      if (check.detail) { const detail = document.createElement("small"); detail.textContent = check.detail; row.append(detail); }
      $("checks").append(row);
    }
    $("report-json").textContent = JSON.stringify(report, null, 2);
  }
  $("run-check").addEventListener("click", async () => {
    if (!challenge || busy) return;
    setBusy(true); status("working"); $("error").hidden = true;
    try {
      report = await api(`challenges/${challenge.challenge_id}/run`);
      renderReport(); $("proof-panel").hidden = true; $("report-panel").hidden = false;
      status(report.status); progress(3);
    } catch (error) { status("failed"); showError(error.message); }
    finally { setBusy(false); }
  });
  $("download-proof").addEventListener("click", () => challenge && download(challenge.proof, "aimarket-provider-check.json"));
  $("download-report").addEventListener("click", () => report && download(report, "aimarket-provider-report.json"));
  $("copy-token").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(challenge.proof.challenge); $("copy-token").textContent = t("copied"); }
    catch (_) { $("proof-json").focus(); }
  });
  function applyLanguage() {
    lang = i18n.currentLang();
    language();
  }
  i18n.onChange(applyLanguage);
  i18n.ready.then(applyLanguage);
})();
