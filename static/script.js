let allTokens = [];
const $ = id => document.getElementById(id);

const checkAuth = () => {
  const t = localStorage.getItem("adminToken");
  return t || ((location.href = "/login"), null), t;
};

const apiRequest = async (url, opts = {}) => {
  const t = checkAuth();
  if (!t) return null;
  const r = await fetch(url, {
    ...opts,
    headers: {
      ...opts.headers,
      Authorization: `Bearer ${t}`,
      "Content-Type": "application/json"
    }
  });
  return r.status === 401
    ? (localStorage.removeItem("adminToken"), (location.href = "/login"), null)
    : r;
};

const loadStats = async () => {
  try {
    const r = await apiRequest("/api/stats");
    if (!r) return;
    const d = await r.json();
    $("statTotal").textContent = d.total_tokens || 0;
    $("statActive").textContent = d.active_tokens || 0;
    $("statImages").textContent = `${d.today_images || 0}/${d.total_images ||
      0}`;
    $("statVideos").textContent = `${d.today_videos || 0}/${d.total_videos ||
      0}`;
    $("statErrors").textContent = `${d.today_errors || 0}/${d.total_errors ||
      0}`;
  } catch (e) {
    console.error("Ошибка загрузки статистики:", e);
  }
};

const loadTokens = async () => {
  try {
    const r = await apiRequest("/api/tokens");
    if (!r) return;
    allTokens = await r.json();
    renderTokens();
  } catch (e) {
    console.error("Ошибка загрузки Token:", e);
  }
};

const formatExpiry = exp => {
  if (!exp) return "-";
  const d = new Date(exp),
    now = new Date(),
    diff = d - now;
  const dateStr = d
    .toLocaleDateString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit"
    })
    .replace(/\//g, "-");
  const timeStr = d.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  });
  if (diff < 0)
    return `<span class="text-red-600">${dateStr} ${timeStr}</span>`;
  const days = Math.floor(diff / 864e5);
  if (days < 7)
    return `<span class="text-orange-600">${dateStr} ${timeStr}</span>`;
  return `${dateStr} ${timeStr}`;
};

const formatPlanType = type => {
  if (!type) return "-";
  const typeMap = {
    chatgpt_team: "Team",
    chatgpt_plus: "Plus",
    chatgpt_pro: "Pro",
    chatgpt_free: "Free"
  };
  return typeMap[type] || type;
};

const formatSora2 = t => {
  if (t.sora2_supported === true) {
    const remaining = t.sora2_total_count - t.sora2_redeemed_count;
    const tooltipText = `Код приглашения: ${t.sora2_invite_code ||
      "Нет"}\nДоступно: ${remaining}/${t.sora2_total_count}\nИспользовано раз: ${t.sora2_redeemed_count}`;
    return `<div class="inline-flex items-center gap-1"><span class="inline-flex items-center rounded px-2 py-0.5 text-xs bg-green-50 text-green-700 cursor-pointer" title="${tooltipText}" onclick="copySora2Code('${t.sora2_invite_code ||
      ""}')"Поддерживается</span><span class="text-xs text-muted-foreground" title="${tooltipText}">${remaining}/${t.sora2_total_count}</span></div>`;
  } else if (t.sora2_supported === false) {
    return `<span class="inline-flex items-center rounded px-2 py-0.5 text-xs bg-gray-100 text-gray-700 cursor-pointer" title="Нажмите для активации с помощью кода приглашения" onclick="openSora2Modal(${t.id})">Не поддерживается</span>`;
  } else {
    return "-";
  }
};

const formatPlanTypeWithTooltip = ({
  subscription_end,
  plan_title,
  plan_type
}) => {
  const tooltipText = subscription_end
    ? `Срок действия пакета: ${new Date(subscription_end)
        .toLocaleDateString("ru-RU", {
          year: "numeric",
          month: "2-digit",
          day: "2-digit"
        })
        .replace(/\//g, "-")} ${new Date(
        subscription_end
      ).toLocaleTimeString("ru-RU", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false
      })}`
    : "";
  return `<span class="inline-flex items-center rounded px-2 py-0.5 text-xs bg-blue-50 text-blue-700 cursor-pointer" title="${tooltipText ||
    plan_title ||
    "-"}">${formatPlanType(plan_type)}</span>`;
};

const formatSora2Remaining = ({ sora2_supported, sora2_remaining_count }) => {
  if (sora2_supported === true) {
    const remaining = sora2_remaining_count || 0;
    return `<span class="text-xs">${remaining}</span>`;
  } else {
    return "-";
  }
};

const formatClientId = clientId => {
  if (!clientId) return "-";
  const short = `${clientId.substring(0, 8)}...`;
  return `<span class="text-xs font-mono cursor-pointer hover:text-primary" title="${clientId}" onclick="navigator.clipboard.writeText('${clientId}').then(()=>showToast('Скопировано','success'))">${short}</span>`;
};

const renderTokens = () => {
  const tb = $("tokenTableBody");
  tb.innerHTML = allTokens
    .map(t => {
      const imageDisplay = t.image_enabled ? `${t.image_count || 0}` : "-";
      const videoDisplay =
        t.video_enabled && t.sora2_supported ? `${t.video_count || 0}` : "-";
      return `<tr><td class="py-2.5 px-3">${t.email}</td><td class="py-2.5 px-3"><span class="inline-flex items-center rounded px-2 py-0.5 text-xs ${t.is_active
        ? "bg-green-50 text-green-700"
        : "bg-gray-100 text-gray-700"}">${t.is_active
        ? "Активен"
        : "Отключить"}</span></td><td class="py-2.5 px-3">${formatClientId(
        t.client_id
      )}</td><td class="py-2.5 px-3 text-xs">${formatExpiry(
        t.expiry_time
      )}</td><td class="py-2.5 px-3 text-xs">${formatPlanTypeWithTooltip(
        t
      )}</td><td class="py-2.5 px-3 text-xs">${formatSora2(
        t
      )}</td><td class="py-2.5 px-3">${formatSora2Remaining(
        t
      )}</td><td class="py-2.5 px-3">${imageDisplay}</td><td class="py-2.5 px-3">${videoDisplay}</td><td class="py-2.5 px-3">${t.error_count ||
        0}</td><td class="py-2.5 px-3 text-xs text-muted-foreground">${t.remark ||
        "-"}</td><td class="py-2.5 px-3 text-right"><button onclick="testToken(${t.id})" class="inline-flex items-center justify-center rounded-md hover:bg-blue-50 hover:text-blue-700 h-7 px-2 text-xs mr-1">Тест</button><button onclick="openEditModal(${t.id})" class="inline-flex items-center justify-center rounded-md hover:bg-green-50 hover:text-green-700 h-7 px-2 text-xs mr-1">Редактировать</button><button onclick="toggleToken(${t.id},${t.is_active})" class="inline-flex items-center justify-center rounded-md hover:bg-accent h-7 px-2 text-xs mr-1">${t.is_active
        ? "Отключить"
        : "Включить"}</button><button onclick="deleteToken(${t.id})" class="inline-flex items-center justify-center rounded-md hover:bg-destructive/10 hover:text-destructive h-7 px-2 text-xs">Удалить</button></td></tr>`;
    })
    .join("");
};

const refreshTokens = async () => {
  await loadTokens();
  await loadStats();
};

const openAddModal = () => $("addModal").classList.remove("hidden");

const closeAddModal = () => {
  $("addModal").classList.add("hidden");
  $("addTokenAT").value = "";
  $("addTokenST").value = "";
  $("addTokenRT").value = "";
  $("addTokenClientId").value = "";
  $("addTokenRemark").value = "";
  $("addTokenImageEnabled").checked = true;
  $("addTokenVideoEnabled").checked = true;
  $("addTokenImageConcurrency").value = "-1";
  $("addTokenVideoConcurrency").value = "-1";
  $("addRTRefreshHint").classList.add("hidden");
};

const openEditModal = id => {
  const token = allTokens.find(t => t.id === id);
  if (!token) return showToast("Token не существует", "error");
  $("editTokenId").value = token.id;
  $("editTokenAT").value = token.token || "";
  $("editTokenST").value = token.st || "";
  $("editTokenRT").value = token.rt || "";
  $("editTokenClientId").value = token.client_id || "";
  $("editTokenRemark").value = token.remark || "";
  $("editTokenImageEnabled").checked = token.image_enabled !== false;
  $("editTokenVideoEnabled").checked = token.video_enabled !== false;
  $("editTokenImageConcurrency").value = token.image_concurrency || "-1";
  $("editTokenVideoConcurrency").value = token.video_concurrency || "-1";
  $("editModal").classList.remove("hidden");
};

const closeEditModal = () => {
  $("editModal").classList.add("hidden");
  $("editTokenId").value = "";
  $("editTokenAT").value = "";
  $("editTokenST").value = "";
  $("editTokenRT").value = "";
  $("editTokenClientId").value = "";
  $("editTokenRemark").value = "";
  $("editTokenImageEnabled").checked = true;
  $("editTokenVideoEnabled").checked = true;
  $("editTokenImageConcurrency").value = "";
  $("editTokenVideoConcurrency").value = "";
  $("editRTRefreshHint").classList.add("hidden");
};

const submitEditToken = async () => {
  const id = parseInt($("editTokenId").value),
    at = $("editTokenAT").value.trim(),
    st = $("editTokenST").value.trim(),
    rt = $("editTokenRT").value.trim(),
    clientId = $("editTokenClientId").value.trim(),
    remark = $("editTokenRemark").value.trim(),
    imageEnabled = $("editTokenImageEnabled").checked,
    videoEnabled = $("editTokenVideoEnabled").checked,
    imageConcurrency = $("editTokenImageConcurrency").value
      ? parseInt($("editTokenImageConcurrency").value)
      : null,
    videoConcurrency = $("editTokenVideoConcurrency").value
      ? parseInt($("editTokenVideoConcurrency").value)
      : null;
  if (!id) return showToast("Token ID недействителен", "error");
  if (!at) return showToast("Введите Access Token", "error");
  const btn = $("editTokenBtn"),
    btnText = $("editTokenBtnText"),
    btnSpinner = $("editTokenBtnSpinner");
  btn.disabled = true;
  btnText.textContent = "Сохранение...";
  btnSpinner.classList.remove("hidden");
  try {
    const r = await apiRequest(`/api/tokens/${id}`, {
      method: "PUT",
      body: JSON.stringify({
        token: at,
        st: st || null,
        rt: rt || null,
        client_id: clientId || null,
        remark: remark || null,
        image_enabled: imageEnabled,
        video_enabled: videoEnabled,
        image_concurrency: imageConcurrency,
        video_concurrency: videoConcurrency
      })
    });
    if (!r) {
      btn.disabled = false;
      btnText.textContent = "Сохранить";
      btnSpinner.classList.add("hidden");
      return;
    }
    const d = await r.json();
    if (d.success) {
      closeEditModal();
      await refreshTokens();
      showToast("Token успешно обновлён", "success");
    } else {
      showToast(
        `Ошибка обновления: ${d.detail || d.message || "Неизвестная ошибка"}`,
        "error"
      );
    }
  } catch (e) {
    showToast(`Ошибка обновления: ${e.message}`, "error");
  } finally {
    btn.disabled = false;
    btnText.textContent = "Сохранить";
    btnSpinner.classList.add("hidden");
  }
};

const convertST2AT = async () => {
  const st = $("addTokenST").value.trim();
  if (!st) return showToast("Сначала введите Session Token", "error");
  try {
    showToast("Конвертация ST→AT...", "info");
    const r = await apiRequest("/api/tokens/st2at", {
      method: "POST",
      body: JSON.stringify({
        st
      })
    });
    if (!r) return;
    const d = await r.json();
    if (d.success && d.access_token) {
      $("addTokenAT").value = d.access_token;
      showToast("Конвертация успешна! AT автоматически заполнен", "success");
    } else {
      showToast(
        `Ошибка конвертации: ${d.message || d.detail || "Неизвестная ошибка"}`,
        "error"
      );
    }
  } catch (e) {
    showToast(`Ошибка конвертации: ${e.message}`, "error");
  }
};

const convertRT2AT = async () => {
  const rt = $("addTokenRT").value.trim();
  if (!rt) return showToast("Сначала введите Refresh Token", "error");
  const hint = $("addRTRefreshHint");
  hint.classList.add("hidden");
  try {
    showToast("Конвертация RT→AT...", "info");
    const r = await apiRequest("/api/tokens/rt2at", {
      method: "POST",
      body: JSON.stringify({
        rt
      })
    });
    if (!r) return;
    const d = await r.json();
    if (d.success && d.access_token) {
      $("addTokenAT").value = d.access_token;
      if (d.refresh_token) {
        $("addTokenRT").value = d.refresh_token;
        hint.classList.remove("hidden");
        showToast(
          "Конвертация успешна! AT автоматически заполнен, RT обновлён",
          "success"
        );
      } else {
        showToast("Конвертация успешна! AT автоматически заполнен", "success");
      }
    } else {
      showToast(
        `Ошибка конвертации: ${d.message || d.detail || "Неизвестная ошибка"}`,
        "error"
      );
    }
  } catch (e) {
    showToast(`Ошибка конвертации: ${e.message}`, "error");
  }
};

const convertEditST2AT = async () => {
  const st = $("editTokenST").value.trim();
  if (!st) return showToast("Сначала введите Session Token", "error");
  try {
    showToast("Конвертация ST→AT...", "info");
    const r = await apiRequest("/api/tokens/st2at", {
      method: "POST",
      body: JSON.stringify({
        st
      })
    });
    if (!r) return;
    const d = await r.json();
    if (d.success && d.access_token) {
      $("editTokenAT").value = d.access_token;
      showToast("Конвертация успешна! AT автоматически заполнен", "success");
    } else {
      showToast(
        `Ошибка конвертации: ${d.message || d.detail || "Неизвестная ошибка"}`,
        "error"
      );
    }
  } catch (e) {
    showToast(`Ошибка конвертации: ${e.message}`, "error");
  }
};

const convertEditRT2AT = async () => {
  const rt = $("editTokenRT").value.trim();
  if (!rt) return showToast("Сначала введите Refresh Token", "error");
  const hint = $("editRTRefreshHint");
  hint.classList.add("hidden");
  try {
    showToast("Конвертация RT→AT...", "info");
    const r = await apiRequest("/api/tokens/rt2at", {
      method: "POST",
      body: JSON.stringify({
        rt
      })
    });
    if (!r) return;
    const d = await r.json();
    if (d.success && d.access_token) {
      $("editTokenAT").value = d.access_token;
      if (d.refresh_token) {
        $("editTokenRT").value = d.refresh_token;
        hint.classList.remove("hidden");
        showToast(
          "Конвертация успешна! AT автоматически заполнен, RT обновлён",
          "success"
        );
      } else {
        showToast("Конвертация успешна! AT автоматически заполнен", "success");
      }
    } else {
      showToast(
        `Ошибка конвертации: ${d.message || d.detail || "Неизвестная ошибка"}`,
        "error"
      );
    }
  } catch (e) {
    showToast(`Ошибка конвертации: ${e.message}`, "error");
  }
};

const submitAddToken = async () => {
  const at = $("addTokenAT").value.trim(),
    st = $("addTokenST").value.trim(),
    rt = $("addTokenRT").value.trim(),
    clientId = $("addTokenClientId").value.trim(),
    remark = $("addTokenRemark").value.trim(),
    imageEnabled = $("addTokenImageEnabled").checked,
    videoEnabled = $("addTokenVideoEnabled").checked,
    imageConcurrency = parseInt($("addTokenImageConcurrency").value) || -1,
    videoConcurrency = parseInt($("addTokenVideoConcurrency").value) || -1;
  if (!at)
    return showToast(
      "Введите Access Token или используйте конвертацию ST/RT",
      "error"
    );
  const btn = $("addTokenBtn"),
    btnText = $("addTokenBtnText"),
    btnSpinner = $("addTokenBtnSpinner");
  btn.disabled = true;
  btnText.textContent = "Добавление...";
  btnSpinner.classList.remove("hidden");
  try {
    const r = await apiRequest("/api/tokens", {
      method: "POST",
      body: JSON.stringify({
        token: at,
        st: st || null,
        rt: rt || null,
        client_id: clientId || null,
        remark: remark || null,
        image_enabled: imageEnabled,
        video_enabled: videoEnabled,
        image_concurrency: imageConcurrency,
        video_concurrency: videoConcurrency
      })
    });
    if (!r) {
      btn.disabled = false;
      btnText.textContent = "Добавить";
      btnSpinner.classList.add("hidden");
      return;
    }
    if (r.status === 409) {
      const d = await r.json();
      const msg = d.detail || "Token уже существует";
      btn.disabled = false;
      btnText.textContent = "Добавить";
      btnSpinner.classList.add("hidden");
      if (confirm(`${msg}\n\nУдалить старый Token и добавить заново?`)) {
        const existingToken = allTokens.find(({ token }) => token === at);
        if (existingToken) {
          const deleted = await deleteToken(existingToken.id, true);
          if (deleted) {
            showToast("Повторное добавление...", "info");
            setTimeout(() => submitAddToken(), 500);
          } else {
            showToast("Ошибка удаления старого Token", "error");
          }
        }
      }
      return;
    }
    const d = await r.json();
    if (d.success) {
      closeAddModal();
      await refreshTokens();
      showToast("Token успешно добавлен", "success");
    } else {
      showToast(
        `Ошибка добавления: ${d.detail || d.message || "Неизвестная ошибка"}`,
        "error"
      );
    }
  } catch (e) {
    showToast(`Ошибка добавления: ${e.message}`, "error");
  } finally {
    btn.disabled = false;
    btnText.textContent = "Добавить";
    btnSpinner.classList.add("hidden");
  }
};

const testToken = async id => {
  try {
    showToast("Тестирование Token...", "info");
    const r = await apiRequest(`/api/tokens/${id}/test`, {
      method: "POST"
    });
    if (!r) return;
    const d = await r.json();
    if (d.success && d.status === "success") {
      let msg = `Token действителен! Пользователь: ${d.email || "Неизвестно"}`;
      if (d.sora2_supported) {
        const remaining = d.sora2_total_count - d.sora2_redeemed_count;
        msg += `\nSora2: Поддерживается (${remaining}/${d.sora2_total_count})`;
        if (d.sora2_remaining_count !== undefined) {
          msg += `\nДоступно: ${d.sora2_remaining_count}`;
        }
      }
      showToast(msg, "success");
      await refreshTokens();
    } else {
      showToast(
        `Token недействителен: ${d.message || "Неизвестная ошибка"}`,
        "error"
      );
    }
  } catch (e) {
    showToast(`Ошибка теста: ${e.message}`, "error");
  }
};

const toggleToken = async (id, isActive) => {
  const action = isActive ? "disable" : "enable";
  try {
    const r = await apiRequest(`/api/tokens/${id}/${action}`, {
      method: "POST"
    });
    if (!r) return;
    const d = await r.json();
    d.success
      ? (
          await refreshTokens(),
          showToast(isActive ? "Token отключён" : "Token включён", "success")
        )
      : showToast("Ошибка действия", "error");
  } catch (e) {
    showToast(`Ошибка действия: ${e.message}`, "error");
  }
};

const toggleTokenStatus = async (id, active) => {
  try {
    const r = await apiRequest(`/api/tokens/${id}/status`, {
      method: "PUT",
      body: JSON.stringify({
        is_active: active
      })
    });
    if (!r) return;
    const d = await r.json();
    d.success
      ? (await refreshTokens(), showToast("Статус успешно обновлён", "success"))
      : showToast("Ошибка обновления", "error");
  } catch (e) {
    showToast(`Ошибка обновления: ${e.message}`, "error");
  }
};

const deleteToken = async (id, skipConfirm = false) => {
  if (!skipConfirm && !confirm("Вы уверены, что хотите удалить этот Token?"))
    return;
  try {
    const r = await apiRequest(`/api/tokens/${id}`, {
      method: "DELETE"
    });
    if (!r) return;
    const d = await r.json();
    if (d.success) {
      await refreshTokens();
      if (!skipConfirm) showToast("Успешно удалено", "success");
      return true;
    } else {
      if (!skipConfirm) showToast("Ошибка удаления", "error");
      return false;
    }
  } catch (e) {
    if (!skipConfirm) showToast(`Ошибка удаления: ${e.message}`, "error");
    return false;
  }
};

const copySora2Code = async code => {
  if (!code) {
    showToast("Нет кода приглашения для копирования", "error");
    return;
  }
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(code);
      showToast(`Код приглашения скопирован: ${code}`, "success");
    } else {
      const textarea = document.createElement("textarea");
      textarea.value = code;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      const success = document.execCommand("copy");
      document.body.removeChild(textarea);
      if (success) {
        showToast(`Код приглашения скопирован: ${code}`, "success");
      } else {
        showToast("Ошибка копирования: браузер не поддерживается", "error");
      }
    }
  } catch (e) {
    showToast(`Ошибка копирования: ${e.message}`, "error");
  }
};

const openSora2Modal = id => {
  $("sora2TokenId").value = id;
  $("sora2InviteCode").value = "";
  $("sora2Modal").classList.remove("hidden");
};

const closeSora2Modal = () => {
  $("sora2Modal").classList.add("hidden");
  $("sora2TokenId").value = "";
  $("sora2InviteCode").value = "";
};

const openImportModal = () => {
  $("importModal").classList.remove("hidden");
  $("importFile").value = "";
};

const closeImportModal = () => {
  $("importModal").classList.add("hidden");
  $("importFile").value = "";
};

const exportTokens = () => {
  if (allTokens.length === 0) {
    showToast("Нет токенов для экспорта", "error");
    return;
  }
  const exportData = allTokens.map(t => ({
    email: t.email,
    access_token: t.token,
    session_token: t.st || null,
    refresh_token: t.rt || null,
    is_active: t.is_active,
    image_enabled: t.image_enabled !== false,
    video_enabled: t.video_enabled !== false,
    image_concurrency: t.image_concurrency || -1,
    video_concurrency: t.video_concurrency || -1
  }));
  const dataStr = JSON.stringify(exportData, null, 2);
  const dataBlob = new Blob([dataStr], {
    type: "application/json"
  });
  const url = URL.createObjectURL(dataBlob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `tokens_${new Date().toISOString().split("T")[0]}.json`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
  showToast(`Экспортировано ${allTokens.length} токенов`, "success");
};

const submitImportTokens = async () => {
  const fileInput = $("importFile");
  if (!fileInput.files || fileInput.files.length === 0) {
    showToast("Пожалуйста, выберите файл", "error");
    return;
  }
  const file = fileInput.files[0];
  if (!file.name.endsWith(".json")) {
    showToast("Пожалуйста, выберите JSON файл", "error");
    return;
  }
  try {
    const fileContent = await file.text();
    const importData = JSON.parse(fileContent);
    if (!Array.isArray(importData)) {
      showToast("Ошибка формата JSON: должен быть массив", "error");
      return;
    }
    if (importData.length === 0) {
      showToast("JSON файл пуст", "error");
      return;
    }
    const btn = $("importBtn"),
      btnText = $("importBtnText"),
      btnSpinner = $("importBtnSpinner");
    btn.disabled = true;
    btnText.textContent = "Импортирование...";
    btnSpinner.classList.remove("hidden");
    try {
      const r = await apiRequest("/api/tokens/import", {
        method: "POST",
        body: JSON.stringify({
          tokens: importData
        })
      });
      if (!r) {
        btn.disabled = false;
        btnText.textContent = "Импортировать";
        btnSpinner.classList.add("hidden");
        return;
      }
      const d = await r.json();
      if (d.success) {
        closeImportModal();
        await refreshTokens();
        const msg = `Импорт успешен! Добавлено: ${d.added ||
          0}, Обновлено: ${d.updated || 0}`;
        showToast(msg, "success");
      } else {
        showToast(
          `Ошибка импорта: ${d.detail || d.message || "Неизвестная ошибка"}`,
          "error"
        );
      }
    } catch (e) {
      showToast(`Ошибка импорта: ${e.message}`, "error");
    } finally {
      btn.disabled = false;
      btnText.textContent = "Импортировать";
      btnSpinner.classList.add("hidden");
    }
  } catch (e) {
    showToast(`Ошибка разбора файла: ${e.message}`, "error");
  }
};

const submitSora2Activate = async () => {
  const tokenId = parseInt($("sora2TokenId").value),
    inviteCode = $("sora2InviteCode").value.trim();
  if (!tokenId) return showToast("Token ID недействителен", "error");
  if (!inviteCode)
    return showToast("Пожалуйста, введите код приглашения", "error");
  if (inviteCode.length !== 6)
    return showToast("Код приглашения должен состоять из 6 символов", "error");
  const btn = $("sora2ActivateBtn"),
    btnText = $("sora2ActivateBtnText"),
    btnSpinner = $("sora2ActivateBtnSpinner");
  btn.disabled = true;
  btnText.textContent = "Активация...";
  btnSpinner.classList.remove("hidden");
  try {
    showToast("Активация Sora2...", "info");
    const r = await apiRequest(
      `/api/tokens/${tokenId}/sora2/activate?invite_code=${inviteCode}`,
      {
        method: "POST"
      }
    );
    if (!r) {
      btn.disabled = false;
      btnText.textContent = "Активировать";
      btnSpinner.classList.add("hidden");
      return;
    }
    const d = await r.json();
    if (d.success) {
      closeSora2Modal();
      await refreshTokens();
      if (d.already_accepted) {
        showToast("Sora2 уже активирован (ранее принят)", "success");
      } else {
        showToast(
          `Sora2 успешно активирован! Код приглашения: ${d.invite_code ||
            "Нет"}`,
          "success"
        );
      }
    } else {
      showToast(
        `Ошибка активации: ${d.message || "Неизвестная ошибка"}`,
        "error"
      );
    }
  } catch (e) {
    showToast(`Ошибка активации: ${e.message}`, "error");
  } finally {
    btn.disabled = false;
    btnText.textContent = "Активировать";
    btnSpinner.classList.add("hidden");
  }
};

const loadAdminConfig = async () => {
  try {
    const r = await apiRequest("/api/admin/config");
    if (!r) return;
    const d = await r.json();
    $("cfgErrorBan").value = d.error_ban_threshold || 3;
    $("cfgAdminUsername").value = d.admin_username || "admin";
    $("cfgCurrentAPIKey").value = d.api_key || "";
    $("cfgDebugEnabled").checked = d.debug_enabled || false;
  } catch (e) {
    console.error("Ошибка загрузки конфигурации:", e);
  }
};

const saveAdminConfig = async () => {
  try {
    const r = await apiRequest("/api/admin/config", {
      method: "POST",
      body: JSON.stringify({
        error_ban_threshold: parseInt($("cfgErrorBan").value) || 3
      })
    });
    if (!r) return;
    const d = await r.json();
    d.success
      ? showToast("Конфигурация успешно сохранена", "success")
      : showToast("Ошибка сохранения", "error");
  } catch (e) {
    showToast(`Ошибка сохранения: ${e.message}`, "error");
  }
};

const updateAdminPassword = async () => {
  const username = $("cfgAdminUsername").value.trim(),
    oldPwd = $("cfgOldPassword").value.trim(),
    newPwd = $("cfgNewPassword").value.trim();
  if (!oldPwd || !newPwd)
    return showToast(
      "Пожалуйста, введите старый пароль и новый пароль",
      "error"
    );
  if (newPwd.length < 4)
    return showToast(
      "Новый пароль должен содержать не менее 4 символов",
      "error"
    );
  try {
    const r = await apiRequest("/api/admin/password", {
      method: "POST",
      body: JSON.stringify({
        username: username || undefined,
        old_password: oldPwd,
        new_password: newPwd
      })
    });
    if (!r) return;
    const d = await r.json();
    if (d.success) {
      showToast("Пароль успешно изменен, пожалуйста, войдите снова", "success");
      setTimeout(() => {
        localStorage.removeItem("adminToken");
        location.href = "/login";
      }, 2000);
    } else {
      showToast(
        `Ошибка изменения: ${d.detail || "Неизвестная ошибка"}`,
        "error"
      );
    }
  } catch (e) {
    showToast(`Ошибка изменения: ${e.message}`, "error");
  }
};

const updateAPIKey = async () => {
  const newKey = $("cfgNewAPIKey").value.trim();
  if (!newKey) return showToast("Пожалуйста, введите новый API ключ", "error");
  if (newKey.length < 6)
    return showToast("API ключ должен содержать не менее 6 символов", "error");
  if (
    !confirm(
      "Вы уверены, что хотите обновить API ключ? После обновления необходимо уведомить всех клиентов об использовании нового ключа."
    )
  )
    return;
  try {
    const r = await apiRequest("/api/admin/apikey", {
      method: "POST",
      body: JSON.stringify({
        new_api_key: newKey
      })
    });
    if (!r) return;
    const d = await r.json();
    if (d.success) {
      showToast("API ключ успешно обновлен", "success");
      $("cfgCurrentAPIKey").value = newKey;
      $("cfgNewAPIKey").value = "";
    } else {
      showToast(
        `Ошибка обновления: ${d.detail || "Неизвестная ошибка"}`,
        "error"
      );
    }
  } catch (e) {
    showToast(`Ошибка обновления: ${e.message}`, "error");
  }
};

const toggleDebugMode = async () => {
  const enabled = $("cfgDebugEnabled").checked;
  try {
    const r = await apiRequest("/api/admin/debug", {
      method: "POST",
      body: JSON.stringify({
        enabled
      })
    });
    if (!r) return;
    const d = await r.json();
    if (d.success) {
      showToast(
        enabled ? "Режим отладки включен" : "Режим отладки выключен",
        "success"
      );
    } else {
      showToast(
        `Ошибка операции: ${d.detail || "Неизвестная ошибка"}`,
        "error"
      );
      $("cfgDebugEnabled").checked = !enabled;
    }
  } catch (e) {
    showToast(`Ошибка операции: ${e.message}`, "error");
    $("cfgDebugEnabled").checked = !enabled;
  }
};

const loadProxyConfig = async () => {
  try {
    const r = await apiRequest("/api/proxy/config");
    if (!r) return;
    const d = await r.json();
    $("cfgProxyEnabled").checked = d.proxy_enabled || false;
    $("cfgProxyUrl").value = d.proxy_url || "";
  } catch (e) {
    console.error("Ошибка загрузки настройки прокси:", e);
  }
};

const saveProxyConfig = async () => {
  try {
    const r = await apiRequest("/api/proxy/config", {
      method: "POST",
      body: JSON.stringify({
        proxy_enabled: $("cfgProxyEnabled").checked,
        proxy_url: $("cfgProxyUrl").value.trim()
      })
    });
    if (!r) return;
    const d = await r.json();
    d.success
      ? showToast("Настройка прокси успешно сохранена", "success")
      : showToast("Ошибка сохранения", "error");
  } catch (e) {
    showToast(`Ошибка сохранения: ${e.message}`, "error");
  }
};

const loadWatermarkFreeConfig = async () => {
  try {
    const r = await apiRequest("/api/watermark-free/config");
    if (!r) return;
    const d = await r.json();
    $("cfgWatermarkFreeEnabled").checked = d.watermark_free_enabled || false;
    $("cfgParseMethod").value = d.parse_method || "third_party";
    $("cfgCustomParseUrl").value = d.custom_parse_url || "";
    $("cfgCustomParseToken").value = d.custom_parse_token || "";
    toggleWatermarkFreeOptions();
    toggleCustomParseOptions();
  } catch (e) {
    console.error("Ошибка загрузки настройки режима без водяных знаков:", e);
  }
};

const saveWatermarkFreeConfig = async () => {
  try {
    const enabled = $("cfgWatermarkFreeEnabled").checked,
      parseMethod = $("cfgParseMethod").value,
      customUrl = $("cfgCustomParseUrl").value.trim(),
      customToken = $("cfgCustomParseToken").value.trim();
    if (enabled && parseMethod === "custom") {
      if (!customUrl)
        return showToast("Пожалуйста, введите адрес сервера разбора", "error");
      if (!customToken)
        return showToast("Пожалуйста, введите ключ доступа", "error");
    }
    const r = await apiRequest("/api/watermark-free/config", {
      method: "POST",
      body: JSON.stringify({
        watermark_free_enabled: enabled,
        parse_method: parseMethod,
        custom_parse_url: customUrl || null,
        custom_parse_token: customToken || null
      })
    });
    if (!r) return;
    const d = await r.json();
    d.success
      ? showToast(
          "Настройка режима без водяных знаков успешно сохранена",
          "success"
        )
      : showToast("Ошибка сохранения", "error");
  } catch (e) {
    showToast(`Ошибка сохранения: ${e.message}`, "error");
  }
};

const toggleWatermarkFreeOptions = () => {
  const enabled = $("cfgWatermarkFreeEnabled").checked;
  $("watermarkFreeOptions").style.display = enabled ? "block" : "none";
};

const toggleCustomParseOptions = () => {
  const method = $("cfgParseMethod").value;
  $("customParseOptions").style.display =
    method === "custom" ? "block" : "none";
};

const toggleCacheOptions = () => {
  const enabled = $("cfgCacheEnabled").checked;
  $("cacheOptions").style.display = enabled ? "block" : "none";
};

const loadCacheConfig = async () => {
  try {
    console.log("Начало загрузки настройки кэша...");
    const r = await apiRequest("/api/cache/config");
    if (!r) {
      console.error("Ошибка API запроса");
      return;
    }
    const d = await r.json();
    console.log("Данные настройки кэша:", d);
    if (d.success && d.config) {
      const enabled = d.config.enabled !== false;
      const timeout = d.config.timeout || 7200;
      const baseUrl = d.config.base_url || "";
      const effectiveUrl = d.config.effective_base_url || "";
      console.log("Установка кэша включен:", enabled);
      console.log("Установка времени ожидания:", timeout);
      console.log("Установка домена:", baseUrl);
      console.log("Действующий URL:", effectiveUrl);
      $("cfgCacheEnabled").checked = enabled;
      $("cfgCacheTimeout").value = timeout;
      $("cfgCacheBaseUrl").value = baseUrl;
      if (effectiveUrl) {
        $("cacheEffectiveUrlValue").textContent = effectiveUrl;
        $("cacheEffectiveUrl").classList.remove("hidden");
      } else {
        $("cacheEffectiveUrl").classList.add("hidden");
      }
      toggleCacheOptions();
      console.log("Настройка кэша успешно загружена");
    } else {
      console.error("Ошибка формата данных настройки кэша:", d);
    }
  } catch (e) {
    console.error("Ошибка загрузки настройки кэша:", e);
    showToast(`Ошибка загрузки настройки кэша: ${e.message}`, "error");
  }
};

const loadGenerationTimeout = async () => {
  try {
    console.log("Начало загрузки настройки таймаутов генерации...");
    const r = await apiRequest("/api/generation/timeout");
    if (!r) {
      console.error("Ошибка API запроса");
      return;
    }
    const d = await r.json();
    console.log("Данные настройки таймаутов генерации:", d);
    if (d.success && d.config) {
      const imageTimeout = d.config.image_timeout || 300;
      const videoTimeout = d.config.video_timeout || 1500;
      console.log("Установка таймаута изображения:", imageTimeout);
      console.log("Установка таймаута видео:", videoTimeout);
      $("cfgImageTimeout").value = imageTimeout;
      $("cfgVideoTimeout").value = videoTimeout;
      console.log("Настройка таймаутов генерации успешно загружена");
    } else {
      console.error("Ошибка формата данных настройки таймаутов генерации:", d);
    }
  } catch (e) {
    console.error("Ошибка загрузки настройки таймаутов генерации:", e);
    showToast(
      `Ошибка загрузки настройки таймаутов генерации: ${e.message}`,
      "error"
    );
  }
};

const saveCacheConfig = async () => {
  const enabled = $("cfgCacheEnabled").checked,
    timeout = parseInt($("cfgCacheTimeout").value) || 7200,
    baseUrl = $("cfgCacheBaseUrl").value.trim();
  console.log("Сохранение настройки кэша:", {
    enabled,
    timeout,
    baseUrl
  });
  if (timeout < 60 || timeout > 86400)
    return showToast(
      "Время хранения кэша должно быть в диапазоне 60-86400 секунд",
      "error"
    );
  if (
    baseUrl &&
    !baseUrl.startsWith("http://") &&
    !baseUrl.startsWith("https://")
  )
    return showToast("Домен должен начинаться с http:// или https://", "error");
  try {
    console.log("Сохранение статуса включения кэша...");
    const r0 = await apiRequest("/api/cache/enabled", {
      method: "POST",
      body: JSON.stringify({
        enabled
      })
    });
    if (!r0) {
      console.error("Ошибка запроса сохранения статуса включения кэша");
      return;
    }
    const d0 = await r0.json();
    console.log("Результат сохранения статуса включения кэша:", d0);
    if (!d0.success) {
      console.error("Ошибка сохранения статуса включения кэша:", d0);
      return showToast("Ошибка сохранения статуса включения кэша", "error");
    }
    console.log("Сохранение времени ожидания...");
    const r1 = await apiRequest("/api/cache/config", {
      method: "POST",
      body: JSON.stringify({
        timeout
      })
    });
    if (!r1) {
      console.error("Ошибка запроса сохранения времени ожидания");
      return;
    }
    const d1 = await r1.json();
    console.log("Результат сохранения времени ожидания:", d1);
    if (!d1.success) {
      console.error("Ошибка сохранения времени ожидания:", d1);
      return showToast("Ошибка сохранения времени ожидания", "error");
    }
    console.log("Сохранение домена...");
    const r2 = await apiRequest("/api/cache/base-url", {
      method: "POST",
      body: JSON.stringify({
        base_url: baseUrl
      })
    });
    if (!r2) {
      console.error("Ошибка запроса сохранения домена");
      return;
    }
    const d2 = await r2.json();
    console.log("Результат сохранения домена:", d2);
    if (d2.success) {
      showToast("Настройка кэша успешно сохранена", "success");
      console.log("Ожидание завершения записи файла конфигурации...");
      await new Promise(r => setTimeout(r, 200));
      console.log("Перезагрузка конфигурации...");
      await loadCacheConfig();
    } else {
      console.error("Ошибка сохранения домена:", d2);
      showToast("Ошибка сохранения домена", "error");
    }
  } catch (e) {
    console.error("Ошибка сохранения:", e);
    showToast(`Ошибка сохранения: ${e.message}`, "error");
  }
};

const saveGenerationTimeout = async () => {
  const imageTimeout = parseInt($("cfgImageTimeout").value) || 300,
    videoTimeout = parseInt($("cfgVideoTimeout").value) || 1500;
  console.log("Сохранение настройки таймаутов генерации:", {
    imageTimeout,
    videoTimeout
  });
  if (imageTimeout < 60 || imageTimeout > 3600)
    return showToast(
      "Время ожидания изображения должно быть в диапазоне 60-3600 секунд",
      "error"
    );
  if (videoTimeout < 60 || videoTimeout > 7200)
    return showToast(
      "Время ожидания видео должно быть в диапазоне 60-7200 секунд",
      "error"
    );
  try {
    const r = await apiRequest("/api/generation/timeout", {
      method: "POST",
      body: JSON.stringify({
        image_timeout: imageTimeout,
        video_timeout: videoTimeout
      })
    });
    if (!r) {
      console.error("Ошибка запроса сохранения");
      return;
    }
    const d = await r.json();
    console.log("Результат сохранения:", d);
    if (d.success) {
      showToast("Настройка таймаутов генерации успешно сохранена", "success");
      await new Promise(r => setTimeout(r, 200));
      await loadGenerationTimeout();
    } else {
      console.error("Ошибка сохранения:", d);
      showToast("Ошибка сохранения", "error");
    }
  } catch (e) {
    console.error("Ошибка сохранения:", e);
    showToast(`Ошибка сохранения: ${e.message}`, "error");
  }
};

const toggleATAutoRefresh = async () => {
  try {
    const enabled = $("atAutoRefreshToggle").checked;
    const r = await apiRequest("/api/token-refresh/enabled", {
      method: "POST",
      body: JSON.stringify({
        enabled
      })
    });
    if (!r) {
      $("atAutoRefreshToggle").checked = !enabled;
      return;
    }
    const d = await r.json();
    if (d.success) {
      showToast(
        enabled
          ? "Автоматическое обновление AT включено"
          : "Автоматическое обновление AT выключено",
        "success"
      );
    } else {
      showToast(
        `Ошибка операции: ${d.detail || "Неизвестная ошибка"}`,
        "error"
      );
      $("atAutoRefreshToggle").checked = !enabled;
    }
  } catch (e) {
    showToast(`Ошибка операции: ${e.message}`, "error");
    $("atAutoRefreshToggle").checked = !enabled;
  }
};

const loadATAutoRefreshConfig = async () => {
  try {
    const r = await apiRequest("/api/token-refresh/config");
    if (!r) return;
    const d = await r.json();
    if (d.success && d.config) {
      $("atAutoRefreshToggle").checked =
        d.config.at_auto_refresh_enabled || false;
    } else {
      console.error(
        "Ошибка формата данных конфигурации автоматического обновления AT:",
        d
      );
    }
  } catch (e) {
    console.error(
      "Ошибка загрузки конфигурации автоматического обновления AT:",
      e
    );
  }
};

const loadLogs = async () => {
  try {
    const r = await apiRequest("/api/logs?limit=100");
    if (!r) return;
    const logs = await r.json();
    const tb = $("logsTableBody");
    tb.innerHTML = logs
      .map(
        l =>
          `<tr><td class="py-2.5 px-3">${l.operation}</td><td class="py-2.5 px-3"><span class="text-xs ${l.token_email
            ? "text-blue-600"
            : "text-muted-foreground"}">${l.token_email ||
            "Неизвестно"}</span></td><td class="py-2.5 px-3"><span class="inline-flex items-center rounded px-2 py-0.5 text-xs ${l.status_code ===
          200
            ? "bg-green-50 text-green-700"
            : "bg-red-50 text-red-700"}">${l.status_code}</span></td><td class="py-2.5 px-3">${l.duration.toFixed(
            2
          )}</td><td class="py-2.5 px-3 text-xs text-muted-foreground">${l.created_at
            ? new Date(l.created_at).toLocaleString("ru-RU")
            : "-"}</td></tr>`
      )
      .join("");
  } catch (e) {
    console.error("Ошибка загрузки журнала:", e);
  }
};

const refreshLogs = async () => {
  await loadLogs();
};

const showToast = (m, t = "info") => {
  const d = document.createElement("div"),
    bc = {
      success: "bg-green-600",
      error: "bg-destructive",
      info: "bg-primary"
    };
  d.className = `fixed bottom-4 right-4 ${bc[t] ||
    bc.info} text-white px-4 py-2.5 rounded-lg shadow-lg text-sm font-medium z-50 animate-slide-up`;
  d.textContent = m;
  document.body.appendChild(d);
  setTimeout(() => {
    d.style.opacity = "0";
    d.style.transition = "opacity .3s";
    setTimeout(() => d.parentNode && document.body.removeChild(d), 300);
  }, 2000);
};

const logout = () => {
  if (!confirm("Вы уверены, что хотите выйти?")) return;
  localStorage.removeItem("adminToken");
  location.href = "/login";
};

const switchTab = t => {
  const cap = n => n.charAt(0).toUpperCase() + n.slice(1);
  ["tokens", "settings", "logs"].forEach(n => {
    const active = n === t;
    $(`panel${cap(n)}`).classList.toggle("hidden", !active);
    $(`tab${cap(n)}`).classList.toggle("border-primary", active);
    $(`tab${cap(n)}`).classList.toggle("text-primary", active);
    $(`tab${cap(n)}`).classList.toggle("border-transparent", !active);
    $(`tab${cap(n)}`).classList.toggle("text-muted-foreground", !active);
  });
  if (t === "settings") {
    loadAdminConfig();
    loadProxyConfig();
    loadWatermarkFreeConfig();
    loadCacheConfig();
    loadGenerationTimeout();
    loadATAutoRefreshConfig();
  } else if (t === "logs") {
    loadLogs();
  }
};

window.addEventListener("DOMContentLoaded", () => {
  checkAuth();
  refreshTokens();
  loadATAutoRefreshConfig();
});
