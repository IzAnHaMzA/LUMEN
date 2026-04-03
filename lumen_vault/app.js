"use strict";

const LS_KEYS = {
  currentStudent: "lumen_vault_current_student",
  bookmarks: "lumen_vault_bookmarks",
  solved: "lumen_vault_solved",
  notes: "lumen_vault_notes",
  aiMode: "lumen_vault_ai_mode",
  aiChats: "lumen_vault_ai_chats",
  aiActiveChatId: "lumen_vault_ai_active_chat_id",
  generalChats: "lumen_vault_general_chats",
  quizHistory: "lumen_vault_quiz_history",
};

const MCQ_SOURCE_LABELS = {
  papers: "Question Papers",
  materials: "Uploaded Material",
};

const state = {
  data: null,
  currentStudent: null,
  filteredSubjects: [],
  activeSubjectKey: "",
  bookmarks: new Set(),
  solved: new Set(),
  notes: {},
  aiChats: [],
  aiActiveChatId: "",
  aiMode: "study",
  aiPending: false,
  aiBackend: "Syllabus-grounded",
  generalChats: [],
  generalPending: false,
  generalBackend: "general",
  materialsBySubject: {},
  materialsSubjectKey: "",
  materialsLoading: false,
  mcqSubjectKey: "",
  mcqSourceMode: "papers",
  mcqQuiz: null,
  mcqLoading: false,
  quizHistory: [],
};

const el = {};

function defaultStudentState() {
  return {
    activeSubjectKey: "",
    bookmarks: new Set(),
    solved: new Set(),
    notes: {},
    aiChats: [],
    aiActiveChatId: "",
    aiMode: "study",
    aiPending: false,
    generalChats: [],
    generalPending: false,
    materialsBySubject: {},
    materialsSubjectKey: "",
    materialsLoading: false,
    mcqSubjectKey: "",
    mcqSourceMode: "papers",
    mcqQuiz: null,
    mcqLoading: false,
    quizHistory: [],
  };
}

function qs(id) {
  return document.getElementById(id);
}

function studentStorageSuffix() {
  return state.currentStudent && state.currentStudent.key ? `::${state.currentStudent.key}` : "";
}

function storageKey(base) {
  return `${base}${studentStorageSuffix()}`;
}

function normalizeStudentKey(name, id) {
  return `${String(name || "").trim()}::${String(id || "").trim()}`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function restoreStudentSession() {
  try {
    state.currentStudent = JSON.parse(localStorage.getItem(LS_KEYS.currentStudent) || "null");
  } catch (_) {
    state.currentStudent = null;
  }
}

function updateStudentUi() {
  document.body.classList.toggle("logged-out", !state.currentStudent);
  el.studentBadge.textContent = state.currentStudent
    ? `Student: ${state.currentStudent.name} (${state.currentStudent.id})`
    : "Student: --";
}

function resetStudentScopedState() {
  Object.assign(state, defaultStudentState());
}

function setLoginStatus(text) {
  el.loginStatus.textContent = text;
}

function renderStudentWorkspace() {
  ensureChatState();
  const active = getActiveChat();
  state.activeSubjectKey = active.subjectKey || state.activeSubjectKey;
  state.filteredSubjects = state.data ? state.data.subjects.slice() : [];
  fillMeta();
  fillFilterOptions();
  applyFilters();
  renderAiMode();
  renderAiThreads();
  renderAiSubjectCard();
  renderAiPromptChips();
  renderAiMessages();
  renderGeneralMessages();
  renderMaterialsView();
  renderMcqView();
  renderHistory();
  refreshAiSubjectMaterials(getSelectedAiSubjectKey());
}

function handleLoginSubmit(event) {
  event.preventDefault();
  const name = (el.studentName.value || "").trim();
  const id = (el.studentId.value || "").trim();
  if (!name || !id) {
    setLoginStatus("Enter both student name and student ID.");
    return;
  }
  state.currentStudent = {
    name,
    id,
    key: normalizeStudentKey(name, id),
  };
  localStorage.setItem(LS_KEYS.currentStudent, JSON.stringify(state.currentStudent));
  updateStudentUi();
  loadStorage();
  renderStudentWorkspace();
  setLoginStatus("Workspace ready.");
  switchView("dashboard");
}

function handleLogout() {
  state.currentStudent = null;
  localStorage.removeItem(LS_KEYS.currentStudent);
  resetStudentScopedState();
  updateStudentUi();
  el.studentName.value = "";
  el.studentId.value = "";
  setLoginStatus("Signed out. Enter student details to open a personal workspace.");
}

function pathUrl(path) {
  return encodeURI(path);
}

function keyForSubject(subject) {
  return `${subject.program_code}|${subject.paper_code}|${subject.subject}`;
}

function escapeHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function sessionSortScore(session) {
  const text = String(session || "").toLowerCase();
  const yearMatch = text.match(/(20\d{2})/);
  const year = yearMatch ? Number(yearMatch[1]) : 0;
  let season = 0;
  if (text.includes("winter")) season = 2;
  else if (text.includes("summer")) season = 1;
  return year * 10 + season;
}

function sortedPaperFilesForCode(code) {
  const entry = state.data && state.data.papers_by_code ? state.data.papers_by_code[code] : null;
  const files = entry && Array.isArray(entry.files) ? entry.files.slice() : [];
  files.sort((a, b) => sessionSortScore(b.session) - sessionSortScore(a.session));
  return files;
}

function latestPaperForSubject(subject) {
  if (!subject) return null;
  const files = sortedPaperFilesForCode(subject.paper_code);
  return files.length ? files[0] : null;
}

function formatDateTime(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString();
}

function truncate(text, max = 42) {
  const value = String(text || "").trim();
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1)}...`;
}

function normalizeMcqSourceMode(mode) {
  return mode === "materials" ? "materials" : "papers";
}

function mcqSourceLabel(mode) {
  return MCQ_SOURCE_LABELS[normalizeMcqSourceMode(mode)] || "Question Papers";
}

function buildWelcomeMessage() {
  return {
    role: "assistant",
    content:
      "Welcome to Lumen Vault AI.\n\nSelect a subject from Library, then ask for study notes, theory answers, step-wise explanations, answer papers, or type commands like 'make mcq from my uploaded material' and 'make mcq from question paper'.",
    meta: {
      backend: state.aiBackend,
      subject: {},
      snippets: [],
    },
  };
}

function buildGeneralWelcomeMessage() {
  return {
    role: "assistant",
    content: "Welcome to General Chat.\n\nAsk anything here and I will reply as a normal general assistant.",
    meta: {
      backend: state.generalBackend,
    },
  };
}

function createChatThread(subjectKey = "") {
  return {
    id: `chat-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    title: "New Chat",
    subjectKey,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    messages: [buildWelcomeMessage()],
  };
}

function hydrateChatThread(thread) {
  const safe = thread && typeof thread === "object" ? thread : {};
  const messages = Array.isArray(safe.messages) && safe.messages.length ? safe.messages : [buildWelcomeMessage()];
  return {
    id: safe.id || `chat-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    title: safe.title || "New Chat",
    subjectKey: safe.subjectKey || "",
    createdAt: safe.createdAt || new Date().toISOString(),
    updatedAt: safe.updatedAt || new Date().toISOString(),
    messages,
  };
}

function ensureChatState() {
  state.aiChats = state.aiChats.map(hydrateChatThread);
  if (!state.aiChats.length) {
    const thread = createChatThread();
    state.aiChats = [thread];
    state.aiActiveChatId = thread.id;
  }
  if (!state.aiActiveChatId || !state.aiChats.some((thread) => thread.id === state.aiActiveChatId)) {
    state.aiActiveChatId = state.aiChats[0].id;
  }
}

function getActiveChat() {
  ensureChatState();
  return state.aiChats.find((thread) => thread.id === state.aiActiveChatId) || state.aiChats[0];
}

function getActiveChatMessages() {
  const thread = getActiveChat();
  return thread ? thread.messages : [];
}

function getSelectedAiSubjectKey() {
  const thread = getActiveChat();
  return thread ? thread.subjectKey || "" : "";
}

function trimChats() {
  if (state.aiChats.length > 12) {
    state.aiChats = state.aiChats.slice(0, 12);
  }
}

function trimActiveChatMessages() {
  const thread = getActiveChat();
  if (!thread) return;
  if (thread.messages.length > 24) {
    thread.messages = [thread.messages[0], ...thread.messages.slice(-23)];
  }
}

function setActiveChatSubject(subjectKey) {
  const thread = getActiveChat();
  if (!thread) return;
  thread.subjectKey = subjectKey || "";
  thread.updatedAt = new Date().toISOString();
}

function updateActiveChatTitle(seed) {
  const thread = getActiveChat();
  if (!thread) return;
  const subject = findSubjectByKey(thread.subjectKey);
  if (subject && thread.messages.filter((message) => message.role === "user").length <= 1) {
    thread.title = `${subject.paper_code} - ${subject.subject}`;
  } else if (seed) {
    thread.title = truncate(seed, 34);
  }
  thread.updatedAt = new Date().toISOString();
}

function pushActiveChatMessage(message) {
  const thread = getActiveChat();
  if (!thread) return;
  thread.messages.push(message);
  thread.updatedAt = new Date().toISOString();
  if (message.role === "user") {
    updateActiveChatTitle(message.content);
  }
  trimActiveChatMessages();
}

function clearCurrentChat() {
  const thread = getActiveChat();
  if (!thread) return;
  thread.messages = [buildWelcomeMessage()];
  thread.title = "New Chat";
  thread.updatedAt = new Date().toISOString();
}

function getGeneralMessages() {
  if (!Array.isArray(state.generalChats) || !state.generalChats.length) {
    state.generalChats = [buildGeneralWelcomeMessage()];
  }
  return state.generalChats;
}

function pushGeneralMessage(message) {
  getGeneralMessages().push(message);
}

function clearGeneralChat() {
  state.generalChats = [buildGeneralWelcomeMessage()];
}

function createAndActivateChat(subjectKey = "") {
  const thread = createChatThread(subjectKey);
  state.aiChats.unshift(thread);
  trimChats();
  state.aiActiveChatId = thread.id;
  state.activeSubjectKey = subjectKey || state.activeSubjectKey;
  return thread;
}

function switchActiveChat(id) {
  if (!state.aiChats.some((thread) => thread.id === id)) return;
  state.aiActiveChatId = id;
  const thread = getActiveChat();
  state.activeSubjectKey = thread.subjectKey || state.activeSubjectKey;
  saveStorage();
  renderAiThreads();
  renderAiSubjectCard();
  renderAiPromptChips();
  renderAiMessages();
  refreshAiSubjectMaterials(thread.subjectKey || "");
}

function loadStorage() {
  if (!state.currentStudent) {
    resetStudentScopedState();
    return;
  }
  try {
    state.bookmarks = new Set(JSON.parse(localStorage.getItem(storageKey(LS_KEYS.bookmarks)) || "[]"));
    state.solved = new Set(JSON.parse(localStorage.getItem(storageKey(LS_KEYS.solved)) || "[]"));
    state.notes = JSON.parse(localStorage.getItem(storageKey(LS_KEYS.notes)) || "{}");
    state.aiMode = localStorage.getItem(storageKey(LS_KEYS.aiMode)) || "study";
    state.aiChats = JSON.parse(localStorage.getItem(storageKey(LS_KEYS.aiChats)) || "[]");
    state.aiActiveChatId = localStorage.getItem(storageKey(LS_KEYS.aiActiveChatId)) || "";
    state.generalChats = JSON.parse(localStorage.getItem(storageKey(LS_KEYS.generalChats)) || "[]");
    state.quizHistory = JSON.parse(localStorage.getItem(storageKey(LS_KEYS.quizHistory)) || "[]");
    state.activeSubjectKey = "";
    state.materialsBySubject = {};
    state.materialsSubjectKey = "";
    state.mcqSubjectKey = "";
    state.mcqQuiz = null;
  } catch (_) {
    resetStudentScopedState();
  }
  ensureChatState();
}

function saveStorage() {
  if (!state.currentStudent) return;
  localStorage.setItem(storageKey(LS_KEYS.bookmarks), JSON.stringify(Array.from(state.bookmarks)));
  localStorage.setItem(storageKey(LS_KEYS.solved), JSON.stringify(Array.from(state.solved)));
  localStorage.setItem(storageKey(LS_KEYS.notes), JSON.stringify(state.notes));
  localStorage.setItem(storageKey(LS_KEYS.aiMode), state.aiMode || "study");
  localStorage.setItem(storageKey(LS_KEYS.aiChats), JSON.stringify(state.aiChats));
  localStorage.setItem(storageKey(LS_KEYS.aiActiveChatId), state.aiActiveChatId || "");
  localStorage.setItem(storageKey(LS_KEYS.generalChats), JSON.stringify(state.generalChats));
  localStorage.setItem(storageKey(LS_KEYS.quizHistory), JSON.stringify(state.quizHistory));
}

async function init() {
  cacheEls();
  restoreStudentSession();
  updateStudentUi();
  loadStorage();
  wireEvents();
  const res = await fetch("./data/library_index.json");
  state.data = await res.json();
  if (state.currentStudent) {
    renderStudentWorkspace();
  } else {
    state.filteredSubjects = state.data.subjects.slice();
    fillMeta();
    setLoginStatus("Enter your student name and ID to open a personal workspace.");
  }
  await loadHealth();
}

function cacheEls() {
  el.loginGate = qs("loginGate");
  el.loginForm = qs("loginForm");
  el.studentName = qs("studentName");
  el.studentId = qs("studentId");
  el.loginStatus = qs("loginStatus");
  el.studentBadge = qs("studentBadge");
  el.logoutBtn = qs("logoutBtn");
  el.globalSearch = qs("globalSearch");
  el.filterProgram = qs("filterProgram");
  el.filterSemester = qs("filterSemester");
  el.filterCode = qs("filterCode");
  el.filterSubject = qs("filterSubject");
  el.filterSession = qs("filterSession");
  el.clearFilters = qs("clearFilters");
  el.kpiCards = qs("kpiCards");
  el.matrixTable = qs("matrixTable");
  el.subjectsTable = qs("subjectsTable");
  el.papersTable = qs("papersTable");
  el.subjectDetail = qs("subjectDetail");
  el.syllabusList = qs("syllabusList");
  el.bookmarksList = qs("bookmarksList");
  el.solvedList = qs("solvedList");
  el.notesList = qs("notesList");
  el.metaPrograms = qs("metaPrograms");
  el.metaSubjects = qs("metaSubjects");
  el.metaPapers = qs("metaPapers");
  el.metaBackend = qs("metaBackend");
  el.jumpToAi = qs("jumpToAi");
  el.jumpToLibrary = qs("jumpToLibrary");
  el.aiModeGroup = qs("aiModeGroup");
  el.aiSubjectCard = qs("aiSubjectCard");
  el.aiPromptChips = qs("aiPromptChips");
  el.aiPrompt = qs("aiPrompt");
  el.aiSend = qs("aiSend");
  el.aiClear = qs("aiClear");
  el.aiMessages = qs("aiMessages");
  el.aiStatus = qs("aiStatus");
  el.aiNewChat = qs("aiNewChat");
  el.chatThreadList = qs("chatThreadList");
  el.generalMessages = qs("generalMessages");
  el.generalStatus = qs("generalStatus");
  el.generalPrompt = qs("generalPrompt");
  el.generalSend = qs("generalSend");
  el.generalClear = qs("generalClear");
  el.materialsSubjectCard = qs("materialsSubjectCard");
  el.materialUploadForm = qs("materialUploadForm");
  el.materialType = qs("materialType");
  el.materialFile = qs("materialFile");
  el.materialsStatus = qs("materialsStatus");
  el.materialsList = qs("materialsList");
  el.mcqSubjectCard = qs("mcqSubjectCard");
  el.mcqCount = qs("mcqCount");
  el.mcqStartPapers = qs("mcqStartPapers");
  el.mcqStartMaterials = qs("mcqStartMaterials");
  el.mcqStatus = qs("mcqStatus");
  el.mcqQuizBox = qs("mcqQuizBox");
  el.historySummary = qs("historySummary");
  el.historyList = qs("historyList");
}

function wireEvents() {
  el.loginForm.addEventListener("submit", handleLoginSubmit);
  el.logoutBtn.addEventListener("click", handleLogout);
  document.querySelectorAll(".menu-item").forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.dataset.view));
  });

  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  [el.globalSearch, el.filterProgram, el.filterSemester, el.filterCode, el.filterSubject, el.filterSession].forEach((node) => {
    node.addEventListener("input", applyFilters);
  });

  el.clearFilters.addEventListener("click", () => {
    el.globalSearch.value = "";
    el.filterProgram.value = "";
    el.filterSemester.value = "";
    el.filterCode.value = "";
    el.filterSubject.value = "";
    el.filterSession.value = "";
    applyFilters();
  });

  el.jumpToAi.addEventListener("click", () => switchView("ai"));
  el.jumpToLibrary.addEventListener("click", () => switchView("library"));
  el.subjectsTable.addEventListener("click", handleSubjectsTableClick);
  el.papersTable.addEventListener("click", handlePapersTableClick);
  el.subjectDetail.addEventListener("click", handleDetailClick);
  el.syllabusList.addEventListener("click", handleSyllabusListClick);
  el.aiModeGroup.addEventListener("click", handleAiModeClick);
  el.aiPromptChips.addEventListener("click", handleAiPromptChipClick);
  el.aiSubjectCard.addEventListener("click", handleAiSubjectCardClick);
  el.aiSend.addEventListener("click", sendAiPrompt);
  el.aiClear.addEventListener("click", handleClearChat);
  el.aiNewChat.addEventListener("click", handleNewChat);
  el.generalSend.addEventListener("click", sendGeneralPrompt);
  el.generalClear.addEventListener("click", handleClearGeneralChat);
  el.chatThreadList.addEventListener("click", handleChatThreadClick);
  el.aiPrompt.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      sendAiPrompt();
    }
  });
  el.generalPrompt.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      sendGeneralPrompt();
    }
  });
  el.materialUploadForm.addEventListener("submit", handleMaterialUpload);
  el.materialsSubjectCard.addEventListener("click", handleMaterialsListClick);
  el.materialsList.addEventListener("click", handleMaterialsListClick);
  el.mcqStartPapers.addEventListener("click", () => generateMcqQuiz("papers"));
  el.mcqStartMaterials.addEventListener("click", () => generateMcqQuiz("materials"));
  el.mcqQuizBox.addEventListener("click", handleMcqQuizClick);
  el.historyList.addEventListener("click", handleHistoryClick);
}

async function loadHealth() {
  try {
    const res = await fetch("./api/health");
    if (!res.ok) return;
    const data = await res.json();
    state.aiBackend = data.backend || state.aiBackend;
    el.metaBackend.textContent = `AI: ${state.aiBackend}`;
    if (!state.aiPending) {
      setAiStatus(`Backend ready: ${state.aiBackend}`);
    }
  } catch (_) {
    setAiStatus("Backend ready: retrieval mode");
  }
}

function switchView(view) {
  document.querySelectorAll(".menu-item").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  document.body.classList.toggle("general-view", view === "general");
  document.querySelectorAll(".view").forEach((node) => {
    node.classList.toggle("active", node.id === `view-${view}`);
  });
  if (view === "ai") {
    renderAiThreads();
    renderAiSubjectCard();
    renderAiPromptChips();
    renderAiMessages();
  }
  if (view === "general") {
    renderGeneralMessages();
  }
  if (view === "materials") {
    renderMaterialsView();
  }
  if (view === "mcq") {
    renderMcqView();
  }
  if (view === "history") {
    renderHistory();
  }
}

function switchTab(tabId) {
  document.querySelectorAll(".tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tabId);
  });
  document.querySelectorAll(".tab-view").forEach((node) => {
    node.classList.toggle("active", node.id === tabId);
  });
}

function fillMeta() {
  const meta = state.data.meta;
  el.metaPrograms.textContent = `Programs: ${meta.programs_total}`;
  el.metaSubjects.textContent = `Subjects: ${meta.subjects_total}`;
  el.metaPapers.textContent = `Papers: ${meta.papers_total}`;
  el.metaBackend.textContent = `AI: ${state.aiBackend}`;
}

function fillFilterOptions() {
  el.filterProgram.innerHTML = `<option value="">All Programs</option>`;
  el.filterSemester.innerHTML = `<option value="">All Semesters</option>`;
  el.filterSession.innerHTML = `<option value="">All Sessions</option>`;
  const programs = Array.from(new Set(state.data.subjects.map((subject) => subject.program_name))).sort();
  programs.forEach((program) => {
    const option = document.createElement("option");
    option.value = program;
    option.textContent = program;
    el.filterProgram.appendChild(option);
  });

  const semesters = Array.from(new Set(state.data.subjects.map((subject) => subject.semester))).sort();
  semesters.forEach((semester) => {
    const option = document.createElement("option");
    option.value = semester;
    option.textContent = semester;
    el.filterSemester.appendChild(option);
  });

  state.data.sessions.forEach((session) => {
    const option = document.createElement("option");
    option.value = session;
    option.textContent = session;
    el.filterSession.appendChild(option);
  });
}

function applyFilters() {
  if (!state.data) return;
  const q = (el.globalSearch.value || "").trim().toLowerCase();
  const program = el.filterProgram.value;
  const semester = el.filterSemester.value;
  const code = (el.filterCode.value || "").trim();
  const subjectText = (el.filterSubject.value || "").trim().toLowerCase();
  const session = el.filterSession.value;

  state.filteredSubjects = state.data.subjects.filter((subject) => {
    if (program && subject.program_name !== program) return false;
    if (semester && subject.semester !== semester) return false;
    if (code && !subject.paper_code.includes(code)) return false;
    if (subjectText && !subject.subject.toLowerCase().includes(subjectText)) return false;
    if (session && !(subject.available_sessions || []).includes(session)) return false;
    if (q) {
      const blob = `${subject.paper_code} ${subject.subject} ${subject.program_name} ${subject.semester}`.toLowerCase();
      if (!blob.includes(q)) return false;
    }
    return true;
  });

  renderKPIs();
  renderMatrix();
  renderSubjectsTable();
  renderPapersTable();
  renderSyllabusCards();
  renderSaved();
  renderAiThreads();
  renderAiSubjectCard();
  renderAiPromptChips();
  if (state.activeSubjectKey) {
    renderSubjectDetail(findSubjectByKey(state.activeSubjectKey));
  }
  renderMaterialsView();
  renderMcqView();
  renderHistory();
}

function renderKPIs() {
  const uniquePrograms = new Set(state.filteredSubjects.map((subject) => subject.program_name)).size;
  const uniqueCodes = new Set(state.filteredSubjects.map((subject) => subject.paper_code)).size;
  let linkedPapers = 0;
  state.filteredSubjects.forEach((subject) => {
    linkedPapers += (subject.available_sessions || []).length;
  });

  const cards = [
    ["Visible Subjects", state.filteredSubjects.length],
    ["Visible Codes", uniqueCodes],
    ["Programs In View", uniquePrograms],
    ["Session Links", linkedPapers],
  ];

  el.kpiCards.innerHTML = cards
    .map(
      ([label, value]) => `
      <article class="card">
        <h3>${escapeHtml(label)}</h3>
        <div class="value">${escapeHtml(value)}</div>
      </article>`
    )
    .join("");
}

function renderMatrix() {
  const sessions = state.data.sessions;
  const rows = [];
  const seen = new Set();
  for (const subject of state.filteredSubjects) {
    if (seen.has(subject.paper_code)) continue;
    seen.add(subject.paper_code);
    rows.push(subject);
  }
  const capped = rows.slice(0, 180);
  const head = "<tr><th>Paper Code</th><th>Subject</th>" + sessions.map((session) => `<th>${escapeHtml(session)}</th>`).join("") + "</tr>";
  const body = capped
    .map((row) => {
      const set = new Set(row.available_sessions || []);
      const cols = sessions
        .map((session) => `<td>${set.has(session) ? '<span class="badge ok">Available</span>' : '<span class="badge no">--</span>'}</td>`)
        .join("");
      return `<tr><td>${escapeHtml(row.paper_code)}</td><td>${escapeHtml(row.subject)}</td>${cols}</tr>`;
    })
    .join("");
  el.matrixTable.innerHTML = head + body;
}

function renderSubjectsTable() {
  const head = `
    <tr>
      <th>Program</th>
      <th>Sem</th>
      <th>Paper Code</th>
      <th>Subject</th>
      <th>Question Papers</th>
      <th>Actions</th>
    </tr>`;

  const body = state.filteredSubjects
    .slice(0, 900)
    .map((subject) => {
      const key = keyForSubject(subject);
      const papers = sortedPaperFilesForCode(subject.paper_code);
      const bookmarked = state.bookmarks.has(key) ? "Unbookmark" : "Bookmark";
      const papersCell =
        papers.length === 0
          ? `<span class="badge no">No papers</span>`
          : papers
              .slice(0, 4)
              .map(
                (paper) =>
                  `<a href="${pathUrl(paper.path)}" target="_blank" rel="noopener" class="badge ok" style="text-decoration:none;margin-right:6px;margin-bottom:4px;">${escapeHtml(paper.session)}</a>`
              )
              .join("") +
            (papers.length > 4 ? ` <span class="badge">+${papers.length - 4} more</span>` : "");

      return `
      <tr>
        <td>${escapeHtml(subject.program_code)}</td>
        <td>${escapeHtml(subject.semester)}</td>
        <td>${escapeHtml(subject.paper_code)}</td>
        <td>${escapeHtml(subject.subject)}</td>
        <td>${papersCell}</td>
        <td class="row-actions">
          <button data-act="view" data-key="${escapeHtml(key)}">View</button>
          <button data-act="ask-ai" data-key="${escapeHtml(key)}">Ask AI</button>
          <button data-act="open-mcq" data-key="${escapeHtml(key)}">MCQ</button>
          <button data-act="materials" data-key="${escapeHtml(key)}">Materials</button>
          <button data-act="bookmark" data-key="${escapeHtml(key)}">${escapeHtml(bookmarked)}</button>
        </td>
      </tr>`;
    })
    .join("");

  el.subjectsTable.innerHTML = head + body;
}

function renderPapersTable() {
  const uniqueCodes = Array.from(new Set(state.filteredSubjects.map((subject) => subject.paper_code)));
  const rows = uniqueCodes
    .map((code) => {
      const paper = state.data.papers_by_code[code];
      if (!paper) return null;
      const sorted = sortedPaperFilesForCode(code);
      return { code, count: paper.count, sessions: sorted.map((item) => item.session).join(", ") };
    })
    .filter(Boolean)
    .sort((a, b) => a.code.localeCompare(b.code));

  const head = "<tr><th>Paper Code</th><th>Available Files</th><th>Sessions</th><th>Actions</th></tr>";
  const body = rows
    .slice(0, 900)
    .map(
      (row) => `
      <tr>
        <td>${escapeHtml(row.code)}</td>
        <td><span class="badge ok">${escapeHtml(row.count)}</span></td>
        <td>${escapeHtml(row.sessions || "--")}</td>
        <td class="row-actions">
          <button data-act="open-first" data-code="${escapeHtml(row.code)}">Open Latest</button>
          <button data-act="ask-ai" data-code="${escapeHtml(row.code)}">Ask AI</button>
          <button data-act="open-mcq" data-code="${escapeHtml(row.code)}">MCQ</button>
          <button data-act="materials" data-code="${escapeHtml(row.code)}">Materials</button>
          <button data-act="mark-solved" data-code="${escapeHtml(row.code)}">Mark Solved</button>
        </td>
      </tr>`
    )
    .join("");

  el.papersTable.innerHTML = head + body;
}

function renderSyllabusCards() {
  const rows = state.filteredSubjects.slice(0, 220);
  el.syllabusList.innerHTML = rows
    .map((subject) => {
      const key = keyForSubject(subject);
      const papers = sortedPaperFilesForCode(subject.paper_code);
      return `
      <article class="mini-card">
        <h4>${escapeHtml(subject.paper_code)} - ${escapeHtml(subject.subject)}</h4>
        <div>${escapeHtml(subject.program_code)} | ${escapeHtml(subject.semester)}</div>
        <div style="margin-top:6px;">
          ${
            papers.length
              ? papers
                  .slice(0, 3)
                  .map(
                    (paper) =>
                      `<a href="${pathUrl(paper.path)}" target="_blank" rel="noopener" class="badge ok" style="text-decoration:none;margin-right:6px;">${escapeHtml(paper.session)}</a>`
                  )
                  .join("")
              : `<span class="badge no">No papers</span>`
          }
        </div>
        <div class="row-actions" style="margin-top:8px;">
          <a href="${pathUrl(subject.syllabus_path)}" target="_blank" rel="noopener">Open Syllabus</a>
          <button data-act="ask-ai" data-key="${escapeHtml(key)}">Ask AI</button>
          <button data-act="open-mcq" data-key="${escapeHtml(key)}">MCQ</button>
          <button data-act="materials" data-key="${escapeHtml(key)}">Materials</button>
          <button data-act="note" data-key="${escapeHtml(key)}">Add Note</button>
          <button data-act="bookmark" data-key="${escapeHtml(key)}">${state.bookmarks.has(key) ? "Unbookmark" : "Bookmark"}</button>
        </div>
      </article>`;
    })
    .join("");
}

function findSubjectByKey(key) {
  if (!state.data || !key) return null;
  return state.data.subjects.find((subject) => keyForSubject(subject) === key) || null;
}

function findSubjectsByCode(code) {
  if (!state.data || !code) return [];
  return state.data.subjects.filter((subject) => subject.paper_code === code);
}

function findPreferredSubjectByCode(code) {
  const matches = findSubjectsByCode(code);
  if (!matches.length) return null;
  const filtered = matches.find((subject) => state.filteredSubjects.some((item) => keyForSubject(item) === keyForSubject(subject)));
  return filtered || matches[0];
}

function knownMaterialsForSubject(subjectKey) {
  return state.materialsBySubject[subjectKey] || [];
}

function renderSubjectDetail(subject) {
  if (!subject) {
    el.subjectDetail.textContent = "Pick a row from Subject Library to view details.";
    return;
  }

  state.activeSubjectKey = keyForSubject(subject);
  const papers = sortedPaperFilesForCode(subject.paper_code);
  const note = state.notes[state.activeSubjectKey] || "";
  const materialsCount = knownMaterialsForSubject(state.activeSubjectKey).length;
  const papersHtml =
    papers.length === 0
      ? "<p>No previous papers available for this code in current dataset.</p>"
      : papers
          .map((paper) => {
            const solvedKey = `${subject.paper_code}|${paper.session}`;
            return `
            <li>
              <strong>${escapeHtml(paper.session)}</strong>
              <div class="row-actions" style="margin-top:6px;">
                <a href="${pathUrl(paper.path)}" target="_blank" rel="noopener">Open PDF</a>
                <a href="${pathUrl(paper.path)}" download>Download</a>
                <button data-act="mark-solved" data-code="${escapeHtml(subject.paper_code)}" data-session="${escapeHtml(paper.session)}">
                  ${state.solved.has(solvedKey) ? "Solved" : "Mark Solved"}
                </button>
              </div>
            </li>`;
          })
          .join("");

  el.subjectDetail.innerHTML = `
    <div class="subject-title">${escapeHtml(subject.paper_code)} - ${escapeHtml(subject.subject)}</div>
    <div><strong>Program:</strong> ${escapeHtml(subject.program_name)}</div>
    <div><strong>Semester:</strong> ${escapeHtml(subject.semester)}</div>
    <div><strong>Uploaded materials:</strong> ${escapeHtml(materialsCount || 0)}</div>
    <div class="row-actions" style="margin-top:10px;">
      <a href="${pathUrl(subject.syllabus_path)}" target="_blank" rel="noopener">Open Syllabus</a>
      <button data-act="ask-ai" data-key="${escapeHtml(state.activeSubjectKey)}">Ask AI</button>
      <button data-act="open-mcq" data-key="${escapeHtml(state.activeSubjectKey)}">MCQ Test</button>
      <button data-act="materials" data-key="${escapeHtml(state.activeSubjectKey)}">Materials</button>
      <button data-act="bookmark" data-key="${escapeHtml(state.activeSubjectKey)}">${state.bookmarks.has(state.activeSubjectKey) ? "Unbookmark" : "Bookmark"}</button>
      <button data-act="save-note" data-key="${escapeHtml(state.activeSubjectKey)}">Save Note</button>
    </div>
    <div style="margin-top:10px;">
      <textarea id="subjectNoteBox" style="width:100%;min-height:92px;border:1px solid #dcc8a0;border-radius:10px;padding:8px;background:#fffdf8;">${escapeHtml(note)}</textarea>
    </div>
    <h4 style="margin:12px 0 8px;">Available Question Papers</h4>
    <ul>${papersHtml}</ul>
  `;
}

function downloadAllForCode(code) {
  const files = sortedPaperFilesForCode(code);
  if (!files.length) {
    alert("No downloaded question papers found for this code.");
    return;
  }
  files.forEach((file) => {
    const link = document.createElement("a");
    link.href = pathUrl(file.path);
    link.download = file.name || "";
    link.style.display = "none";
    document.body.appendChild(link);
    link.click();
    link.remove();
  });
}

function handleSubjectsTableClick(event) {
  const target = event.target;
  const act = target.dataset.act;
  if (!act) return;
  const key = target.dataset.key;
  const subject = findSubjectByKey(key);

  if (act === "view" && subject) {
    renderSubjectDetail(subject);
    switchView("papers");
    return;
  }
  if (act === "bookmark" && key) {
    toggleBookmark(key);
    return;
  }
  if (act === "ask-ai" && subject) {
    openAiForSubject(subject, `Explain the important exam topics for ${subject.paper_code} - ${subject.subject}.`);
    return;
  }
  if (act === "open-mcq" && subject) {
    openMcqForSubject(subject);
    return;
  }
  if (act === "materials" && subject) {
    openMaterialsForSubject(subject);
  }
}

function handlePapersTableClick(event) {
  const target = event.target;
  const act = target.dataset.act;
  if (!act) return;
  const code = target.dataset.code;
  if (!code) return;

  const latest = sortedPaperFilesForCode(code)[0];
  const subject = findPreferredSubjectByCode(code);
  if (act === "open-first") {
    if (latest) {
      window.open(pathUrl(latest.path), "_blank", "noopener");
    }
    return;
  }
  if (act === "mark-solved") {
    if (!latest) return;
    state.solved.add(`${code}|${latest.session}`);
    saveStorage();
    renderSaved();
    renderPapersTable();
    return;
  }
  if (act === "ask-ai" && subject) {
    openAiForSubject(subject, `Based on the linked papers, what should I study first in ${subject.paper_code} - ${subject.subject}?`);
    return;
  }
  if (act === "open-mcq" && subject) {
    openMcqForSubject(subject);
    return;
  }
  if (act === "materials" && subject) {
    openMaterialsForSubject(subject);
  }
}

function handleDetailClick(event) {
  const target = event.target;
  const act = target.dataset.act;
  if (!act) return;

  if (act === "bookmark") {
    toggleBookmark(target.dataset.key);
    return;
  }
  if (act === "mark-solved") {
    state.solved.add(`${target.dataset.code}|${target.dataset.session}`);
    saveStorage();
    renderSaved();
    if (state.activeSubjectKey) renderSubjectDetail(findSubjectByKey(state.activeSubjectKey));
    return;
  }
  if (act === "save-note") {
    const key = target.dataset.key;
    const note = qs("subjectNoteBox") ? qs("subjectNoteBox").value.trim() : "";
    if (note) state.notes[key] = note;
    else delete state.notes[key];
    saveStorage();
    renderSaved();
    alert("Note saved.");
    return;
  }
  if (act === "ask-ai") {
    const subject = findSubjectByKey(target.dataset.key);
    if (subject) openAiForSubject(subject, `Generate a theory answer for ${subject.paper_code} - ${subject.subject}.`);
    return;
  }
  if (act === "open-mcq") {
    const subject = findSubjectByKey(target.dataset.key);
    if (subject) openMcqForSubject(subject);
    return;
  }
  if (act === "materials") {
    const subject = findSubjectByKey(target.dataset.key);
    if (subject) openMaterialsForSubject(subject);
  }
}

function handleSyllabusListClick(event) {
  const target = event.target;
  const act = target.dataset.act;
  if (!act) return;

  if (act === "bookmark") {
    toggleBookmark(target.dataset.key);
    return;
  }
  if (act === "note") {
    const key = target.dataset.key;
    const current = state.notes[key] || "";
    const note = prompt("Add note", current);
    if (note === null) return;
    if (note.trim()) state.notes[key] = note.trim();
    else delete state.notes[key];
    saveStorage();
    renderSaved();
    return;
  }
  if (act === "ask-ai") {
    const subject = findSubjectByKey(target.dataset.key);
    if (subject) openAiForSubject(subject, `Summarize ${subject.paper_code} - ${subject.subject} for quick revision.`);
    return;
  }
  if (act === "open-mcq") {
    const subject = findSubjectByKey(target.dataset.key);
    if (subject) openMcqForSubject(subject);
    return;
  }
  if (act === "materials") {
    const subject = findSubjectByKey(target.dataset.key);
    if (subject) openMaterialsForSubject(subject);
    return;
  }
  if (act === "bookmark") {
    toggleBookmark(target.dataset.key);
  }
}

function toggleBookmark(key) {
  if (state.bookmarks.has(key)) state.bookmarks.delete(key);
  else state.bookmarks.add(key);
  saveStorage();
  renderSaved();
  renderSubjectsTable();
  renderSyllabusCards();
  if (state.activeSubjectKey) {
    const subject = findSubjectByKey(state.activeSubjectKey);
    if (subject) renderSubjectDetail(subject);
  }
}

function renderSaved() {
  const bookmarks = Array.from(state.bookmarks)
    .map((key) => findSubjectByKey(key))
    .filter(Boolean);

  el.bookmarksList.innerHTML =
    bookmarks.length === 0
      ? "<li>Nothing bookmarked yet.</li>"
      : bookmarks
          .slice(0, 120)
          .map((subject) => `<li>${escapeHtml(subject.paper_code)} - ${escapeHtml(subject.subject)} <small>(${escapeHtml(subject.program_code)})</small></li>`)
          .join("");

  const solved = Array.from(state.solved);
  el.solvedList.innerHTML =
    solved.length === 0
      ? "<li>No solved papers marked yet.</li>"
      : solved.slice(0, 180).map((item) => `<li>${escapeHtml(item)}</li>`).join("");

  const notesEntries = Object.entries(state.notes);
  el.notesList.innerHTML =
    notesEntries.length === 0
      ? "<li>No notes yet.</li>"
      : notesEntries
          .slice(0, 120)
          .map(([key, value]) => `<li><strong>${escapeHtml(key.split("|")[1] || "Subject")}</strong>: ${escapeHtml(value.slice(0, 90))}</li>`)
          .join("");
}

function getSelectedAiSubject() {
  return findSubjectByKey(getSelectedAiSubjectKey());
}

function refreshAiSubjectMaterials(subjectKey, force = false) {
  if (!subjectKey) return Promise.resolve([]);
  return fetchMaterialsForSubject(subjectKey, force)
    .then((materials) => {
      if (getSelectedAiSubjectKey() === subjectKey) {
        renderAiSubjectCard();
        renderAiPromptChips();
      }
      return materials;
    })
    .catch(() => []);
}

function renderAiMode() {
  document.querySelectorAll(".mode-pill").forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === state.aiMode);
  });
}

function handleAiModeClick(event) {
  const target = event.target.closest("[data-mode]");
  if (!target) return;
  const previousMode = state.aiMode;
  state.aiMode = target.dataset.mode || "study";
  saveStorage();
  renderAiMode();
  renderAiPromptChips();
  if (state.aiMode === "paper" && previousMode !== "paper" && getSelectedAiSubject()) {
    generateAnswerPaperFromLatest();
  }
}

function renderAiThreads() {
  ensureChatState();
  el.chatThreadList.innerHTML = state.aiChats
    .map((thread) => {
      const subject = findSubjectByKey(thread.subjectKey);
      const subtitle = subject ? `${subject.paper_code} | ${subject.semester}` : "General";
      return `
        <button class="thread-item ${thread.id === state.aiActiveChatId ? "active" : ""}" data-chat-id="${escapeHtml(thread.id)}">
          <span class="thread-title">${escapeHtml(thread.title || "New Chat")}</span>
          <span class="thread-subtitle">${escapeHtml(subtitle)}</span>
        </button>`;
    })
    .join("");
}

function handleNewChat() {
  createAndActivateChat(getSelectedAiSubjectKey());
  saveStorage();
  renderAiThreads();
  renderAiSubjectCard();
  renderAiPromptChips();
  renderAiMessages();
  switchView("ai");
  el.aiPrompt.focus();
}

function handleClearChat() {
  clearCurrentChat();
  saveStorage();
  setAiStatus(`Backend ready: ${state.aiBackend}`);
  renderAiThreads();
  renderAiMessages();
}

function handleChatThreadClick(event) {
  const target = event.target.closest("[data-chat-id]");
  if (!target) return;
  switchActiveChat(target.dataset.chatId);
}

function openAiForSubject(subject, presetPrompt) {
  const nextSubjectKey = keyForSubject(subject);
  const current = getActiveChat();
  const hasConversation = current.messages.some((message) => message.role === "user");

  if (!current.subjectKey && !hasConversation) {
    current.subjectKey = nextSubjectKey;
    current.title = `${subject.paper_code} - ${subject.subject}`;
  } else if (hasConversation && current.subjectKey !== nextSubjectKey) {
    createAndActivateChat(nextSubjectKey);
  } else {
    setActiveChatSubject(nextSubjectKey);
  }

  state.activeSubjectKey = nextSubjectKey;
  saveStorage();
  renderAiThreads();
  renderAiSubjectCard();
  renderAiPromptChips();
  refreshAiSubjectMaterials(nextSubjectKey);
  switchView("ai");
  if (presetPrompt) {
    el.aiPrompt.value = presetPrompt;
  }
  el.aiPrompt.focus();
}

function renderAiSubjectCard() {
  const subject = getSelectedAiSubject();
  if (!subject) {
    el.aiSubjectCard.innerHTML = `
      <div class="subject-title">No subject selected</div>
      <div>Choose a subject from Library or mention a paper code inside your question.</div>
    `;
    return;
  }

  const sortedFiles = sortedPaperFilesForCode(subject.paper_code);
  const latestPaper = sortedFiles.length ? sortedFiles[0] : null;
  const orderedSessions = sortedFiles.map((item) => item.session);
  const materialsCount = knownMaterialsForSubject(keyForSubject(subject)).length;

  el.aiSubjectCard.innerHTML = `
    <div class="subject-title">${escapeHtml(subject.paper_code)} - ${escapeHtml(subject.subject)}</div>
    <div><strong>Program:</strong> ${escapeHtml(subject.program_name)}</div>
    <div><strong>Semester:</strong> ${escapeHtml(subject.semester)}</div>
    <div><strong>Paper sessions:</strong> ${escapeHtml(orderedSessions.join(", ") || "No linked papers yet")}</div>
    <div><strong>Latest linked paper:</strong> ${escapeHtml((latestPaper && latestPaper.session) || "No linked papers yet")}</div>
    <div><strong>Uploaded materials:</strong> ${escapeHtml(materialsCount || 0)}</div>
    <div class="row-actions" style="margin-top:10px;">
      <a href="${pathUrl(subject.syllabus_path)}" target="_blank" rel="noopener">Open Syllabus</a>
      ${latestPaper ? `<a href="${pathUrl(latestPaper.path)}" target="_blank" rel="noopener">Open Latest Paper</a>` : ""}
      ${latestPaper ? `<button data-ai-act="generate-answer-paper">Generate Answer Paper</button>` : ""}
      <button data-ai-act="generate-mcq-papers">MCQ From Question Papers</button>
      <button data-ai-act="generate-mcq-materials">MCQ From Uploaded Material</button>
      <button data-ai-act="open-materials">Materials</button>
      <button data-ai-act="clear-subject">Clear Subject</button>
    </div>
  `;
}

function handleAiSubjectCardClick(event) {
  const target = event.target;
  const act = target.dataset.aiAct;
  if (!act) return;
  if (act === "clear-subject") {
    setActiveChatSubject("");
    saveStorage();
    renderAiThreads();
    renderAiSubjectCard();
    renderAiPromptChips();
    return;
  }
  if (act === "generate-answer-paper") {
    generateAnswerPaperFromLatest();
    return;
  }
  if (act === "generate-mcq-papers") {
    const subject = getSelectedAiSubject();
    if (subject) {
      openMcqForSubject(subject, "papers");
      generateMcqQuiz("papers");
    }
    return;
  }
  if (act === "generate-mcq-materials") {
    const subject = getSelectedAiSubject();
    if (subject) {
      openMcqForSubject(subject, "materials");
      generateMcqQuiz("materials");
    }
    return;
  }
  if (act === "open-materials") {
    const subject = getSelectedAiSubject();
    if (subject) openMaterialsForSubject(subject);
  }
}

function currentPromptSuggestions() {
  const subject = getSelectedAiSubject();
  if (!subject) {
    return [
      "Explain paper code 311302 in simple study language.",
      "Generate a theory answer on a diploma subject topic.",
      "Create a step-wise answer for a mathematics question.",
      "Make mcq from question paper.",
    ];
  }

  const materials = knownMaterialsForSubject(keyForSubject(subject));
  if (materials.length) {
    const primary = materials[0] || {};
    const materialName = truncate(primary.original_name || primary.name || "my uploaded PDF", 40);
    return [
      `Summarize the important topics from my uploaded PDF ${materialName} for ${subject.paper_code} - ${subject.subject}.`,
      `Generate a 10-mark theory answer using my uploaded PDF ${materialName} for ${subject.paper_code} - ${subject.subject}.`,
      `Explain the important concepts from my uploaded PDF ${materialName} for ${subject.subject}.`,
      `Make mcq from my uploaded material ${materialName} for ${subject.paper_code} - ${subject.subject}.`,
    ];
  }

  return [
    `Summarize the important units in ${subject.paper_code} - ${subject.subject}.`,
    `Generate a 10-mark theory answer for ${subject.paper_code} - ${subject.subject}.`,
    `Give me a step-wise approach for solving questions in ${subject.subject}.`,
    `Make mcq from question paper for ${subject.paper_code} - ${subject.subject}.`,
  ];
}

function renderAiPromptChips() {
  const prompts = currentPromptSuggestions();
  el.aiPromptChips.innerHTML = prompts
    .map((prompt) => `<button class="chip" data-prompt="${escapeHtml(prompt)}">${escapeHtml(prompt)}</button>`)
    .join("");
}

function handleAiPromptChipClick(event) {
  const target = event.target.closest("[data-prompt]");
  if (!target) return;
  el.aiPrompt.value = target.dataset.prompt || "";
  el.aiPrompt.focus();
}

function setAiStatus(text) {
  el.aiStatus.textContent = text;
}

function setGeneralStatus(text) {
  el.generalStatus.textContent = text;
}

function summarizeMeta(meta) {
  if (!meta) return "";
  const pills = [];
  if (meta.backend) pills.push(`<span class="meta-pill">Backend: ${escapeHtml(meta.backend)}</span>`);
  if (meta.subject && meta.subject.paper_code) pills.push(`<span class="meta-pill">${escapeHtml(meta.subject.paper_code)} - ${escapeHtml(meta.subject.subject)}</span>`);
  if (meta.subject && meta.subject.semester) pills.push(`<span class="meta-pill">${escapeHtml(meta.subject.semester)}</span>`);
  if (meta.paper && meta.paper.session) pills.push(`<span class="meta-pill">Paper: ${escapeHtml(meta.paper.session)}</span>`);
  if (meta.materials && meta.materials.length) pills.push(`<span class="meta-pill">Materials: ${escapeHtml(meta.materials.length)}</span>`);
  if (meta.sourceLabel) pills.push(`<span class="meta-pill">MCQ Source: ${escapeHtml(meta.sourceLabel)}</span>`);
  return pills.join("");
}

function renderAiMessages() {
  const messages = getActiveChatMessages();
  if (!messages.length && !state.aiPending) {
    el.aiMessages.innerHTML = `<div class="placeholder">Start a chat to build subject-grounded answers here.</div>`;
    return;
  }

  const markup = messages
    .map((message) => {
      const isUser = message.role === "user";
      const metaHtml = !isUser && message.meta ? `<div class="message-meta">${summarizeMeta(message.meta)}</div>` : "";
      const contextHtml =
        !isUser && message.meta && message.meta.snippets && message.meta.snippets.length
          ? `
          <details class="context-box">
            <summary>Grounding used</summary>
            <ul class="context-list">
              ${message.meta.snippets.map((snippet) => `<li>${escapeHtml(snippet)}</li>`).join("")}
            </ul>
          </details>`
          : "";
      const paperQuestionsHtml =
        !isUser && message.meta && message.meta.paper_questions && message.meta.paper_questions.length
          ? `
          <details class="context-box">
            <summary>Paper questions read</summary>
            <ol class="context-list">
              ${message.meta.paper_questions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
            </ol>
          </details>`
          : "";

      return `
        <article class="message ${isUser ? "user" : "assistant"}">
          <div class="message-head">
            <div class="message-role ${isUser ? "user-role" : ""}">${isUser ? "You" : "Lumen Vault AI"}</div>
          </div>
          <div class="message-body">${escapeHtml(message.content)}</div>
          ${metaHtml}
          ${contextHtml}
          ${paperQuestionsHtml}
        </article>`;
    })
    .join("");

  const pendingHtml = state.aiPending
    ? `
      <article class="message assistant pending">
        <div class="message-head">
          <div class="message-role">Lumen Vault AI</div>
        </div>
        <div class="message-body">Thinking through the subject and preparing the answer...</div>
      </article>`
    : "";

  el.aiMessages.innerHTML = markup + pendingHtml;
  el.aiMessages.scrollTop = el.aiMessages.scrollHeight;
}

function renderGeneralMessages() {
  const messages = getGeneralMessages();
  const markup = messages
    .map((message) => {
      const isUser = message.role === "user";
      const metaHtml = !isUser && message.meta ? `<div class="message-meta">${summarizeMeta(message.meta)}</div>` : "";
      return `
        <article class="message ${isUser ? "user" : "assistant"} general-message">
          <div class="message-head">
            <div class="message-role ${isUser ? "user-role" : ""}">${isUser ? "You" : "General Chat"}</div>
          </div>
          <div class="message-body">${escapeHtml(message.content)}</div>
          ${metaHtml}
        </article>`;
    })
    .join("");

  const pendingHtml = state.generalPending
    ? `
      <article class="message assistant pending general-message">
        <div class="message-head">
          <div class="message-role">General Chat</div>
        </div>
        <div class="message-body">Thinking about your general question...</div>
      </article>`
    : "";

  el.generalMessages.innerHTML = markup + pendingHtml;
  el.generalMessages.scrollTop = el.generalMessages.scrollHeight;
}

function applyMcqResponse(data, explicitSourceMode = "") {
  const subjectKey = data && data.subject && data.subject.key ? data.subject.key : state.mcqSubjectKey;
  const sourceMode = normalizeMcqSourceMode((data && data.source_mode) || explicitSourceMode || state.mcqSourceMode);
  const sourceRefs = Array.isArray(data && data.source_refs)
    ? data.source_refs
    : Array.isArray(data && data.source_sessions)
      ? data.source_sessions
      : [];

  state.mcqSourceMode = sourceMode;
  state.mcqSubjectKey = subjectKey || state.mcqSubjectKey;
  state.activeSubjectKey = state.mcqSubjectKey;
  state.mcqQuiz = {
    subjectKey: state.mcqSubjectKey,
    questions: (data.questions || []).map((item) => ({
      prompt: item.prompt,
      options: item.options || [],
      answer_index: Number(item.answer_index),
      explanation: item.explanation || "",
      selectedIndex: null,
    })),
    currentIndex: 0,
    sourceMode,
    sourceLabel: data.source_label || mcqSourceLabel(sourceMode),
    sourceRefs,
    sourceSessions: Array.isArray(data && data.source_sessions) ? data.source_sessions : [],
    sourceLines: data.source_lines || [],
    backend: data.backend || state.aiBackend,
    completed: false,
    score: 0,
    savedToHistory: false,
  };
}

async function sendAiPrompt() {
  if (state.aiPending) return;
  const prompt = (el.aiPrompt.value || "").trim();
  if (!prompt) {
    if (state.aiMode === "paper" && getSelectedAiSubject()) {
      generateAnswerPaperFromLatest();
    }
    return;
  }

  const history = getActiveChatMessages().slice(-8).map((message) => ({
    role: message.role,
    content: message.content,
  }));

  pushActiveChatMessage({ role: "user", content: prompt });
  el.aiPrompt.value = "";
  state.aiPending = true;
  saveStorage();
  renderAiThreads();
  renderAiMessages();
  setAiStatus("Generating answer...");

  try {
    const response = await fetch("./api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: prompt,
        mode: state.aiMode,
        subject_key: getSelectedAiSubjectKey(),
        history,
      }),
    });

    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || "Failed to get AI response.");
    }

    if (data.subject && data.subject.key) {
      setActiveChatSubject(data.subject.key);
      if (Array.isArray(data.materials)) {
        state.materialsBySubject[data.subject.key] = data.materials;
      }
    }

    pushActiveChatMessage({
      role: "assistant",
      content: data.answer || "No answer returned.",
      meta: {
        backend: data.backend || state.aiBackend,
        subject: data.subject || {},
        snippets: data.snippets || [],
        materials: data.materials || [],
        sourceLabel: data.source_label || "",
      },
    });
    state.aiBackend = data.backend || state.aiBackend;
    el.metaBackend.textContent = `AI: ${state.aiBackend}`;
    if (data.action === "open_mcq" && Array.isArray(data.questions) && data.questions.length) {
      applyMcqResponse(data);
      setMcqStatus(data.fallback_note || `MCQ test ready from ${data.source_label || mcqSourceLabel(data.source_mode)}.`);
      switchView("mcq");
      setAiStatus(`MCQ test sent to MCQ Lab: ${data.source_label || mcqSourceLabel(data.source_mode)}`);
    } else {
      setAiStatus(`Answer ready: ${state.aiBackend}`);
    }
  } catch (error) {
    pushActiveChatMessage({
      role: "assistant",
      content: `I hit an error while generating the answer.\n\n${error.message || String(error)}`,
      meta: {
        backend: state.aiBackend,
        subject: getSelectedAiSubject() || {},
        snippets: [],
      },
    });
    setAiStatus("The request failed. Please try again.");
  } finally {
    state.aiPending = false;
    saveStorage();
    renderAiThreads();
    renderAiSubjectCard();
    renderAiPromptChips();
    renderAiMessages();
  }
}

function handleClearGeneralChat() {
  clearGeneralChat();
  saveStorage();
  setGeneralStatus(`Backend ready: ${state.generalBackend}`);
  renderGeneralMessages();
}

async function sendGeneralPrompt() {
  if (state.generalPending) return;
  const prompt = (el.generalPrompt.value || "").trim();
  if (!prompt) return;

  const history = getGeneralMessages().slice(-8).map((message) => ({
    role: message.role,
    content: message.content,
  }));

  pushGeneralMessage({ role: "user", content: prompt });
  el.generalPrompt.value = "";
  state.generalPending = true;
  saveStorage();
  renderGeneralMessages();
  setGeneralStatus("Generating answer...");

  try {
    const response = await fetch("./api/chat/general", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: prompt,
        history,
      }),
    });

    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || "Failed to get general response.");
    }

    pushGeneralMessage({
      role: "assistant",
      content: data.answer || "No answer returned.",
      meta: {
        backend: data.backend || state.generalBackend,
      },
    });
    state.generalBackend = data.backend || state.generalBackend;
    setGeneralStatus(`Answer ready: ${state.generalBackend}`);
  } catch (error) {
    pushGeneralMessage({
      role: "assistant",
      content: `I hit an error while generating the answer.\n\n${error.message || String(error)}`,
      meta: {
        backend: state.generalBackend,
      },
    });
    setGeneralStatus("The request failed. Please try again.");
  } finally {
    state.generalPending = false;
    saveStorage();
    renderGeneralMessages();
  }
}

async function generateAnswerPaperFromLatest() {
  if (state.aiPending) return;
  const subject = getSelectedAiSubject();
  if (!subject) {
    setAiStatus("Select a subject first, then generate the answer paper.");
    switchView("library");
    return;
  }

  const latestPaper = latestPaperForSubject(subject);
  if (!latestPaper) {
    setAiStatus("No linked question paper was found for this subject.");
    return;
  }

  state.aiMode = "paper";
  saveStorage();
  renderAiMode();
  renderAiPromptChips();
  switchView("ai");

  const history = getActiveChatMessages().slice(-8).map((message) => ({
    role: message.role,
    content: message.content,
  }));

  pushActiveChatMessage({
    role: "user",
    content: `Generate the answer paper from the latest linked paper: ${latestPaper.session} for ${subject.paper_code} - ${subject.subject}.`,
  });
  state.aiPending = true;
  saveStorage();
  renderAiThreads();
  renderAiMessages();
  setAiStatus(`Reading ${latestPaper.session} and generating the answer paper...`);

  try {
    const response = await fetch("./api/answer-paper", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        subject_key: getSelectedAiSubjectKey(),
        paper_path: latestPaper.path,
        history,
      }),
    });

    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || "Failed to generate answer paper.");
    }

    if (data.subject && data.subject.key && Array.isArray(data.materials)) {
      state.materialsBySubject[data.subject.key] = data.materials;
    }

    pushActiveChatMessage({
      role: "assistant",
      content: data.answer || "No answer paper returned.",
      meta: {
        backend: data.backend || state.aiBackend,
        subject: data.subject || {},
        paper: data.paper || {},
        paper_questions: data.questions || [],
        snippets: data.snippets || [],
        materials: data.materials || [],
      },
    });
    state.aiBackend = data.backend || state.aiBackend;
    el.metaBackend.textContent = `AI: ${state.aiBackend}`;
    setAiStatus(`Answer paper ready: ${latestPaper.session}`);
  } catch (error) {
    pushActiveChatMessage({
      role: "assistant",
      content: `I hit an error while generating the answer paper.\n\n${error.message || String(error)}`,
      meta: {
        backend: state.aiBackend,
        subject: subject || {},
        paper: latestPaper || {},
        paper_questions: [],
        snippets: [],
      },
    });
    setAiStatus("The answer-paper request failed. Please try again.");
  } finally {
    state.aiPending = false;
    saveStorage();
    renderAiThreads();
    renderAiMessages();
  }
}

function getSelectedMaterialsSubject() {
  return findSubjectByKey(state.materialsSubjectKey || state.activeSubjectKey || getSelectedAiSubjectKey());
}

function setMaterialsStatus(text) {
  el.materialsStatus.textContent = text;
}

async function fetchMaterialsForSubject(subjectKey, force = false) {
  if (!subjectKey) return [];
  if (!force && state.materialsBySubject[subjectKey]) {
    return state.materialsBySubject[subjectKey];
  }

  const response = await fetch(`./api/materials?subject_key=${encodeURIComponent(subjectKey)}`);
  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(data.error || "Failed to load subject materials.");
  }
  state.materialsBySubject[subjectKey] = data.materials || [];
  return state.materialsBySubject[subjectKey];
}

function openMaterialsForSubject(subject) {
  const key = keyForSubject(subject);
  state.materialsSubjectKey = key;
  state.activeSubjectKey = key;
  switchView("materials");
  renderMaterialsView();
  fetchMaterialsForSubject(key)
    .then(() => {
      renderMaterialsView();
    })
    .catch((error) => {
      setMaterialsStatus(error.message || "Failed to load materials.");
    });
}

function renderMaterialsView() {
  const subject = getSelectedMaterialsSubject();
  if (!subject) {
    el.materialsSubjectCard.innerHTML = `
      <div class="subject-title">No subject selected</div>
      <div>Choose a subject from Library, Papers, Syllabus, or AI Studio to add material.</div>
    `;
    el.materialsList.innerHTML = `<div class="placeholder">Subject-wise uploads will appear here.</div>`;
    return;
  }

  state.materialsSubjectKey = keyForSubject(subject);
  const materials = knownMaterialsForSubject(state.materialsSubjectKey);
  el.materialsSubjectCard.innerHTML = `
    <div class="subject-title">${escapeHtml(subject.paper_code)} - ${escapeHtml(subject.subject)}</div>
    <div><strong>Program:</strong> ${escapeHtml(subject.program_name)}</div>
    <div><strong>Semester:</strong> ${escapeHtml(subject.semester)}</div>
    <div><strong>Question papers available:</strong> ${escapeHtml(sortedPaperFilesForCode(subject.paper_code).length)}</div>
    <div><strong>Uploaded PDFs:</strong> ${escapeHtml(materials.length)}</div>
    <div class="row-actions" style="margin-top:10px;">
      <button data-material-open="ai">Open In AI</button>
      <button data-material-open="mcq-papers">MCQ From Question Papers</button>
      <button data-material-open="mcq-materials">MCQ From Uploaded Material</button>
    </div>
  `;

  if (state.materialsLoading) {
    el.materialsList.innerHTML = `<div class="placeholder">Uploading and indexing the PDF...</div>`;
    return;
  }

  if (!materials.length) {
    el.materialsList.innerHTML = `<div class="placeholder">No uploaded PDFs for this subject yet.</div>`;
    return;
  }

  el.materialsList.innerHTML = materials
    .map(
      (item) => `
      <article class="mini-card">
        <h4>${escapeHtml(item.original_name || item.name)}</h4>
        <div>${escapeHtml(item.material_label || item.material_type || "Material")}</div>
        <div style="margin-top:6px;">Uploaded: ${escapeHtml(formatDateTime(item.uploaded_at))}</div>
        <div style="margin-top:6px;">Pages: ${escapeHtml(item.pages || 0)}</div>
        <div class="row-actions" style="margin-top:8px;">
          <a href="${pathUrl(item.path)}" target="_blank" rel="noopener">Open PDF</a>
        </div>
      </article>`
    )
    .join("");
}

function handleMaterialsListClick(event) {
  const target = event.target.closest("[data-material-open]");
  if (!target) return;
  const subject = getSelectedMaterialsSubject();
  if (!subject) return;
  if (target.dataset.materialOpen === "ai") {
    openAiForSubject(subject, `Use my uploaded material and linked papers to explain ${subject.paper_code} - ${subject.subject}.`);
    return;
  }
  if (target.dataset.materialOpen === "mcq-papers") {
    openMcqForSubject(subject, "papers");
    generateMcqQuiz("papers");
    return;
  }
  if (target.dataset.materialOpen === "mcq-materials") {
    openMcqForSubject(subject, "materials");
    generateMcqQuiz("materials");
  }
}

async function handleMaterialUpload(event) {
  event.preventDefault();
  const subject = getSelectedMaterialsSubject();
  if (!subject) {
    setMaterialsStatus("Choose a subject first, then upload the PDF.");
    return;
  }
  const file = el.materialFile.files && el.materialFile.files[0];
  if (!file) {
    setMaterialsStatus("Select a PDF file first.");
    return;
  }

  const formData = new FormData();
  formData.append("subject_key", keyForSubject(subject));
  formData.append("material_type", el.materialType.value || "study");
  formData.append("file", file);

  state.materialsLoading = true;
  renderMaterialsView();
  setMaterialsStatus("Uploading text PDF and attaching it to the subject...");

  try {
    const response = await fetch("./api/materials/upload", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || "Upload failed.");
    }
    state.materialsBySubject[keyForSubject(subject)] = data.materials || [];
    el.materialFile.value = "";
    setMaterialsStatus("PDF uploaded and indexed successfully.");
    renderMaterialsView();
    renderAiSubjectCard();
    renderSubjectDetail(subject);
  } catch (error) {
    setMaterialsStatus(error.message || "Upload failed.");
  } finally {
    state.materialsLoading = false;
    renderMaterialsView();
  }
}

function getSelectedMcqSubject() {
  return findSubjectByKey(state.mcqSubjectKey || state.activeSubjectKey || getSelectedAiSubjectKey() || state.materialsSubjectKey);
}

function setMcqStatus(text) {
  el.mcqStatus.textContent = text;
}

function openMcqForSubject(subject, sourceMode = state.mcqSourceMode) {
  const key = keyForSubject(subject);
  state.mcqSubjectKey = key;
  state.mcqSourceMode = normalizeMcqSourceMode(sourceMode);
  state.activeSubjectKey = key;
  switchView("mcq");
  renderMcqView();
}

function renderMcqSubjectCard() {
  const subject = getSelectedMcqSubject();
  if (!subject) {
    el.mcqSubjectCard.innerHTML = `
      <div class="subject-title">No subject selected</div>
      <div>Choose a subject with question papers to generate an MCQ test.</div>
    `;
    return;
  }

  state.mcqSubjectKey = keyForSubject(subject);
  const sortedFiles = sortedPaperFilesForCode(subject.paper_code);
  const materialsCount = knownMaterialsForSubject(state.mcqSubjectKey).length;
  el.mcqSubjectCard.innerHTML = `
    <div class="subject-title">${escapeHtml(subject.paper_code)} - ${escapeHtml(subject.subject)}</div>
    <div><strong>Program:</strong> ${escapeHtml(subject.program_name)}</div>
    <div><strong>Semester:</strong> ${escapeHtml(subject.semester)}</div>
    <div><strong>Available paper sessions:</strong> ${escapeHtml(sortedFiles.map((item) => item.session).join(", ") || "No linked papers yet")}</div>
    <div><strong>Uploaded materials:</strong> ${escapeHtml(materialsCount)}</div>
    <div><strong>Current MCQ source:</strong> ${escapeHtml(mcqSourceLabel(state.mcqSourceMode))}</div>
    <div class="row-actions" style="margin-top:10px;">
      <button data-mcq-open="ai">Open In AI</button>
      <button data-mcq-open="materials">Materials</button>
      <button data-mcq-open="generate-papers">Use Question Papers</button>
      <button data-mcq-open="generate-materials">Use Uploaded Material</button>
    </div>
  `;
}

function renderMcqView() {
  renderMcqSubjectCard();
  const subject = getSelectedMcqSubject();
  el.mcqSubjectCard.querySelectorAll("[data-mcq-open]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!subject) return;
      if (button.dataset.mcqOpen === "ai") {
        openAiForSubject(subject, `Help me prepare ${subject.paper_code} - ${subject.subject} from past papers.`);
      } else if (button.dataset.mcqOpen === "materials") {
        openMaterialsForSubject(subject);
      } else if (button.dataset.mcqOpen === "generate-papers") {
        state.mcqSourceMode = "papers";
        generateMcqQuiz("papers");
      } else if (button.dataset.mcqOpen === "generate-materials") {
        state.mcqSourceMode = "materials";
        generateMcqQuiz("materials");
      }
    });
  });

  if (state.mcqLoading) {
    el.mcqQuizBox.innerHTML = `<div class="placeholder">Generating MCQs from ${escapeHtml(mcqSourceLabel(state.mcqSourceMode)).toLowerCase()}...</div>`;
    return;
  }

  const quiz = state.mcqQuiz;
  if (!quiz || quiz.subjectKey !== (subject ? keyForSubject(subject) : "")) {
    el.mcqQuizBox.innerHTML = `<div class="placeholder">Generate an MCQ test to begin. Answers will be marked green or red and saved in history after completion.</div>`;
    return;
  }

  if (quiz.completed) {
    const percentage = Math.round((quiz.score / quiz.questions.length) * 100);
    const review = quiz.questions
      .map((question, index) => {
        const chosen = question.selectedIndex;
        const correct = question.answer_index;
        return `
          <article class="mini-card">
            <h4>Q${index + 1}. ${escapeHtml(question.prompt)}</h4>
            <div><strong>Your answer:</strong> ${escapeHtml(question.options[chosen] || "Not answered")}</div>
            <div><strong>Correct answer:</strong> ${escapeHtml(question.options[correct] || "")}</div>
            ${question.explanation ? `<div style="margin-top:6px;"><strong>Why:</strong> ${escapeHtml(question.explanation)}</div>` : ""}
          </article>`;
      })
      .join("");

    el.mcqQuizBox.innerHTML = `
      <div class="mcq-summary">
        <div class="summary-score">${escapeHtml(`${quiz.score} / ${quiz.questions.length}`)}</div>
        <div class="summary-percent">${escapeHtml(`${percentage}%`)}</div>
        <div><strong>Source used:</strong> ${escapeHtml(quiz.sourceLabel || mcqSourceLabel(quiz.sourceMode))}</div>
        <div><strong>Source refs:</strong> ${escapeHtml((quiz.sourceRefs || quiz.sourceSessions || []).join(", ") || mcqSourceLabel(quiz.sourceMode))}</div>
        <div class="row-actions" style="margin-top:10px;">
          <button data-mcq-act="retry">Generate Another Test</button>
          <button data-mcq-act="history">Open History</button>
        </div>
      </div>
      <div class="mcq-review-list">${review}</div>
    `;
    return;
  }

  const question = quiz.questions[quiz.currentIndex];
  const answered = typeof question.selectedIndex === "number";
  const currentScore = quiz.questions.filter((item) => typeof item.selectedIndex === "number" && item.selectedIndex === item.answer_index).length;

  el.mcqQuizBox.innerHTML = `
    <div class="mcq-progress">
      <div>Question ${escapeHtml(quiz.currentIndex + 1)} of ${escapeHtml(quiz.questions.length)}</div>
      <div>Current score: ${escapeHtml(currentScore)}</div>
    </div>
    <div class="question">${escapeHtml(question.prompt)}</div>
    <div class="opts mcq-options">
      ${question.options
        .map((option, index) => {
          let cls = "mcq-option";
          if (answered && index === question.answer_index) cls += " correct";
          if (answered && index === question.selectedIndex && index !== question.answer_index) cls += " wrong";
          if (index === question.selectedIndex) cls += " selected";
          return `<button class="${cls}" data-mcq-choice="${index}" ${answered ? "disabled" : ""}>${escapeHtml(option)}</button>`;
        })
        .join("")}
    </div>
    ${
      answered
        ? `
      <div class="mcq-feedback ${question.selectedIndex === question.answer_index ? "good" : "bad"}">
        ${
          question.selectedIndex === question.answer_index
            ? "Correct answer selected."
            : `Wrong answer. Correct answer: ${escapeHtml(question.options[question.answer_index])}`
        }
      </div>
      ${question.explanation ? `<div class="mcq-explanation">${escapeHtml(question.explanation)}</div>` : ""}
      <div class="row-actions" style="margin-top:12px;">
        <button data-mcq-act="next">${quiz.currentIndex === quiz.questions.length - 1 ? "Finish Test" : "Next Question"}</button>
      </div>`
        : ""
    }
  `;
}

async function generateMcqQuiz(sourceMode = state.mcqSourceMode) {
  sourceMode = normalizeMcqSourceMode(sourceMode);

  const subject = getSelectedMcqSubject();
  if (!subject) {
    setMcqStatus("Choose a subject first.");
    return;
  }
  const hasPapers = Boolean(latestPaperForSubject(subject));
  const hasMaterials = knownMaterialsForSubject(keyForSubject(subject)).length > 0;
  if (!hasPapers && !hasMaterials) {
    setMcqStatus("This subject does not have linked question papers or uploaded material yet.");
    return;
  }

  state.mcqLoading = true;
  state.mcqSubjectKey = keyForSubject(subject);
  state.mcqSourceMode = sourceMode;
  state.activeSubjectKey = state.mcqSubjectKey;
  if (sourceMode === "materials" && !hasMaterials && hasPapers) {
    setMcqStatus("No uploaded material found for this subject, so Lumen Vault is falling back to question papers.");
  } else {
    setMcqStatus(`Generating MCQs from ${mcqSourceLabel(sourceMode).toLowerCase()}...`);
  }
  renderMcqView();

  try {
    const response = await fetch("./api/mcq", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        subject_key: state.mcqSubjectKey,
        count: Number(el.mcqCount.value || 8),
        source_mode: sourceMode,
      }),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || "Failed to generate MCQs.");
    }

    if (Array.isArray(data.materials)) {
      state.materialsBySubject[state.mcqSubjectKey] = data.materials;
    }

    applyMcqResponse(data, sourceMode);
    setMcqStatus(data.fallback_note || `MCQ test ready from ${data.source_label || mcqSourceLabel(sourceMode)}.`);
  } catch (error) {
    state.mcqQuiz = null;
    setMcqStatus(error.message || "MCQ generation failed.");
  } finally {
    state.mcqLoading = false;
    renderMcqView();
  }
}

function handleMcqQuizClick(event) {
  const choice = event.target.closest("[data-mcq-choice]");
  if (choice) {
    const quiz = state.mcqQuiz;
    if (!quiz || quiz.completed) return;
    const question = quiz.questions[quiz.currentIndex];
    if (typeof question.selectedIndex === "number") return;
    question.selectedIndex = Number(choice.dataset.mcqChoice);
    renderMcqView();
    return;
  }

  const action = event.target.closest("[data-mcq-act]");
  if (!action) return;
  const act = action.dataset.mcqAct;
  if (act === "next") {
    const quiz = state.mcqQuiz;
    if (!quiz) return;
    if (quiz.currentIndex >= quiz.questions.length - 1) {
      finishMcqQuiz();
    } else {
      quiz.currentIndex += 1;
      renderMcqView();
    }
    return;
  }
  if (act === "retry") {
    generateMcqQuiz(state.mcqQuiz && state.mcqQuiz.sourceMode ? state.mcqQuiz.sourceMode : state.mcqSourceMode);
    return;
  }
  if (act === "history") {
    switchView("history");
  }
}

function finishMcqQuiz() {
  const quiz = state.mcqQuiz;
  if (!quiz || quiz.completed) return;
  quiz.score = quiz.questions.filter((item) => item.selectedIndex === item.answer_index).length;
  quiz.completed = true;
  if (!quiz.savedToHistory) {
    const subject = getSelectedMcqSubject();
    const percentage = Math.round((quiz.score / quiz.questions.length) * 100);
    state.quizHistory.unshift({
      id: `attempt-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      subjectKey: subject ? keyForSubject(subject) : quiz.subjectKey,
      paperCode: subject ? subject.paper_code : "",
      subject: subject ? subject.subject : "",
      programName: subject ? subject.program_name : "",
      semester: subject ? subject.semester : "",
      score: quiz.score,
      total: quiz.questions.length,
      percentage,
      completedAt: new Date().toISOString(),
      sourceMode: quiz.sourceMode || state.mcqSourceMode,
      sourceLabel: quiz.sourceLabel || mcqSourceLabel(quiz.sourceMode || state.mcqSourceMode),
      sourceRefs: quiz.sourceRefs || quiz.sourceSessions || [],
      sourceSessions: quiz.sourceSessions || [],
      backend: quiz.backend || state.aiBackend,
    });
    if (state.quizHistory.length > 120) {
      state.quizHistory = state.quizHistory.slice(0, 120);
    }
    quiz.savedToHistory = true;
    saveStorage();
    renderHistory();
  }
  setMcqStatus(`Test completed: ${quiz.score}/${quiz.questions.length}`);
  renderMcqView();
}

function renderHistory() {
  if (!state.quizHistory.length) {
    el.historySummary.textContent = "No quiz attempts saved yet.";
    el.historyList.innerHTML = `<div class="placeholder">Complete an MCQ test and the result will appear here.</div>`;
    return;
  }

  const average = Math.round(state.quizHistory.reduce((sum, item) => sum + Number(item.percentage || 0), 0) / state.quizHistory.length);
  el.historySummary.textContent = `Attempts saved: ${state.quizHistory.length} | Average percentage: ${average}%`;
  el.historyList.innerHTML = state.quizHistory
    .map(
      (entry) => `
      <article class="mini-card">
        <h4>${escapeHtml(entry.paperCode)} - ${escapeHtml(entry.subject)}</h4>
        <div>${escapeHtml(entry.programName)}</div>
        <div style="margin-top:6px;">Score: ${escapeHtml(entry.score)} / ${escapeHtml(entry.total)} | ${escapeHtml(entry.percentage)}%</div>
        <div style="margin-top:6px;">${escapeHtml(formatDateTime(entry.completedAt))}</div>
        <div style="margin-top:6px;">Source used: ${escapeHtml(entry.sourceLabel || mcqSourceLabel(entry.sourceMode || "papers"))}</div>
        <div style="margin-top:6px;">Source refs: ${escapeHtml((entry.sourceRefs || entry.sourceSessions || []).join(", ") || mcqSourceLabel(entry.sourceMode || "papers"))}</div>
        <div class="row-actions" style="margin-top:8px;">
          <button data-history-act="retry-mcq" data-key="${escapeHtml(entry.subjectKey)}" data-source="${escapeHtml(entry.sourceMode || "papers")}">Retry MCQ</button>
          <button data-history-act="open-ai" data-key="${escapeHtml(entry.subjectKey)}">Open AI</button>
        </div>
      </article>`
    )
    .join("");
}

function handleHistoryClick(event) {
  const target = event.target.closest("[data-history-act]");
  if (!target) return;
  const subject = findSubjectByKey(target.dataset.key);
  if (!subject) return;

  if (target.dataset.historyAct === "retry-mcq") {
    const sourceMode = normalizeMcqSourceMode(target.dataset.source || "papers");
    openMcqForSubject(subject, sourceMode);
    generateMcqQuiz(sourceMode);
    return;
  }
  if (target.dataset.historyAct === "open-ai") {
    openAiForSubject(subject, `Help me improve in ${subject.paper_code} - ${subject.subject} based on my past papers.`);
  }
}

init().catch((err) => {
  console.error(err);
  document.body.innerHTML = `<pre style="padding:16px;">Failed to load Lumen Vault.\n${escapeHtml(String(err))}</pre>`;
});
