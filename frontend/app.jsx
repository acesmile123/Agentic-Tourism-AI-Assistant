import { useState, useEffect, useRef, useCallback } from "react";

// Vite proxies /api locally; production Nginx uses the same prefix.
const API = import.meta.env.VITE_API_URL || "/api";

const escapeHtml = (text) => text
  .replace(/&/g, "&amp;")
  .replace(/</g, "&lt;")
  .replace(/>/g, "&gt;");

const fmt = (text) =>
  escapeHtml(text)
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/\n/g, "<br/>");

// ── Icons ─────────────────────────────────────────────────────────────────────
const IconMenu    = () => <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16"/></svg>;
const IconClose   = () => <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>;
const IconSun     = () => <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" clipRule="evenodd"/></svg>;
const IconMoon    = () => <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z"/></svg>;
const IconSend    = () => <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>;
const IconTrash   = () => <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>;
const IconChevron = ({ open }) => <svg className={`w-4 h-4 transition-transform duration-200 ${open ? "rotate-180" : ""}`} fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7"/></svg>;
const IconPlus    = () => <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4"/></svg>;

// ── Typing dots ───────────────────────────────────────────────────────────────
function TypingDots() {
  return (
    <div className="flex items-center gap-1.5 py-0.5">
      {[0, 150, 300].map((delay, i) => (
        <span key={i}
          className="w-2 h-2 rounded-full bg-emerald-400/60 animate-bounce"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </div>
  );
}

// ── Avatar ────────────────────────────────────────────────────────────────────
function Avatar({ role }) {
  const isUser = role === "user";
  return (
    <div className={`
      w-8 h-8 rounded-xl flex-shrink-0 flex items-center justify-center
      text-[11px] font-bold tracking-wide select-none shadow-sm
      ${isUser
        ? "bg-gradient-to-br from-emerald-400 to-teal-500 text-white"
        : "bg-gradient-to-br from-violet-500 to-indigo-600 text-white"
      }
    `}>
      {isUser ? "U" : "AI"}
    </div>
  );
}

// ── Message ───────────────────────────────────────────────────────────────────
function Message({ role, content, isStreaming }) {
  const isUser = role === "user";
  return (
    <div className={`
      flex gap-3 items-end mb-6
      ${isUser ? "flex-row-reverse" : "flex-row"}
      msg-enter
    `}>
      <Avatar role={role} />
      <div className={`flex flex-col gap-1 max-w-[74%] ${isUser ? "items-end" : "items-start"}`}>
        <span className={`text-[10px] font-semibold uppercase tracking-widest
          ${isUser ? "text-emerald-500/70 dark:text-emerald-400/60" : "text-violet-500/70 dark:text-violet-400/60"}`}>
          {isUser ? "Bạn" : "Trợ lý AI"}
        </span>
        <div className={`
          px-4 py-3 rounded-2xl text-sm leading-relaxed
          ${isUser
            ? "bg-gradient-to-br from-emerald-500 to-teal-600 text-white rounded-br-sm shadow-md shadow-emerald-500/15"
            : "bg-white dark:bg-slate-800/90 text-gray-800 dark:text-slate-100 rounded-bl-sm shadow-md shadow-black/5 dark:shadow-black/20 border border-gray-100/80 dark:border-slate-700/50"
          }
        `}
          dangerouslySetInnerHTML={{
            __html: fmt(content) + (isStreaming ? '<span class="streaming-cursor">▋</span>' : "")
          }}
        />
      </div>
    </div>
  );
}

// ── Session item ──────────────────────────────────────────────────────────────
function SessionItem({ session, active, onLoad, onDelete }) {
  return (
    <div
      onClick={() => onLoad(session.session_id, session.title)}
      className={`group flex items-center gap-2 rounded-xl px-3 py-2.5 cursor-pointer transition-all
        ${active
          ? "bg-emerald-500/10 dark:bg-emerald-500/15 border border-emerald-400/25"
          : "hover:bg-gray-50 dark:hover:bg-slate-800/60 border border-transparent"
        }`}
    >
      <div className="flex-1 min-w-0">
        <p className={`text-xs font-medium truncate
          ${active ? "text-emerald-600 dark:text-emerald-400" : "text-gray-700 dark:text-slate-300"}`}>
          {active && <span className="mr-1">▶</span>}{session.title}
        </p>
        <p className="text-[10px] text-gray-400 dark:text-slate-500 mt-0.5">
          {session.updated_at?.slice(0, 16)}
        </p>
      </div>
      <button
        onClick={(e) => { e.stopPropagation(); onDelete(session.session_id); }}
        className="opacity-0 group-hover:opacity-100 p-1 rounded-md text-gray-400 hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-all"
      >
        <IconTrash />
      </button>
    </div>
  );
}

// ── Collapsible ───────────────────────────────────────────────────────────────
function Collapsible({ label, children }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-sm text-gray-700 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-800/60 transition-colors"
      >
        {label}<IconChevron open={open} />
      </button>
      {open && <div className="mt-1 space-y-0.5">{children}</div>}
    </div>
  );
}

// ── Slide panel ───────────────────────────────────────────────────────────────
function Panel({ open, onClose, title, side = "right", children }) {
  useEffect(() => {
    const fn = (e) => e.key === "Escape" && onClose();
    if (open) window.addEventListener("keydown", fn);
    return () => window.removeEventListener("keydown", fn);
  }, [open, onClose]);

  return (
    <div className={`fixed inset-0 z-50 ${open ? "" : "pointer-events-none"}`}>
      <div
        onClick={onClose}
        className={`absolute inset-0 bg-black/20 dark:bg-black/40 backdrop-blur-[2px] transition-opacity duration-300
          ${open ? "opacity-100" : "opacity-0"}`}
      />
      <aside
        role="dialog" aria-modal="true"
        className={`
          absolute top-0 bottom-0 ${side === "left" ? "left-0" : "right-0"} w-80
          bg-white dark:bg-[#0f1923] shadow-2xl flex flex-col
          border-r dark:border-r-0 border-gray-100 dark:border-slate-800
          transform transition-transform duration-300 ease-in-out
          ${open ? "translate-x-0" : side === "left" ? "-translate-x-full" : "translate-x-full"}
        `}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100 dark:border-slate-800">
          <span className="text-sm font-semibold text-gray-800 dark:text-slate-200">{title}</span>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 dark:hover:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-800 transition-colors"
          >
            <IconClose />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">{children}</div>
      </aside>
    </div>
  );
}

// ── FAQ ───────────────────────────────────────────────────────────────────────
const FAQS = [
  { id: 1, q: "Đây là trang web gì?",          a: "Hệ thống trợ lý du lịch thông minh ứng dụng AI chuyên sâu cho các tỉnh thành Việt Nam, sử dụng RAG để đảm bảo thông tin chính xác." },
  { id: 2, q: "Tôi có thể hỏi những gì?",       a: "Địa điểm tham quan, ẩm thực, di chuyển, lưu trú, chi phí và lịch trình cho: Hà Nội, Đà Nẵng, TP.HCM, Phú Quốc, Hội An, Huế, Hạ Long, Ninh Bình và nhiều nơi khác." },
  { id: 3, q: "Chúng tôi là ai?",               a: "Nhóm sinh viên CS thực hiện đồ án về RAG & LLM ứng dụng cho ngành du lịch Việt Nam." },
  { id: 4, q: "Thông tin có chính xác không?",  a: "Hệ thống dùng RAG để truy xuất từ nguồn uy tín, giảm thiểu lỗi hallucination. Tuy nhiên vẫn nên kiểm chứng thông tin quan trọng." },
  { id: 5, q: "Có cần đăng nhập không?",        a: "Không. Dùng ngay lập tức, quyền riêng tư được đảm bảo tuyệt đối." },
];

// ── Welcome suggestions ───────────────────────────────────────────────────────
const SUGGESTIONS = [
  {
    icon: "🗺️",
    title: "Lên lịch trình",
    description: "Đà Nẵng 3 ngày 2 đêm",
    query: "Lập lịch trình Đà Nẵng 3 ngày 2 đêm cho 2 người, gồm các địa điểm nổi bật.",
    tone: "emerald",
  },
  {
    icon: "🍜",
    title: "Khám phá ẩm thực",
    description: "Món ngon Hà Nội",
    query: "Du lịch Hà Nội nên thử những món ăn đặc trưng nào?",
    tone: "orange",
  },
  {
    icon: "💰",
    title: "Dự trù ngân sách",
    description: "5 triệu đi Đà Nẵng",
    query: "Ngân sách 5 triệu đồng có đủ cho 2 người đi Đà Nẵng 3 ngày không? Hãy ước tính chi tiết.",
    tone: "violet",
  },
  {
    icon: "🌤️",
    title: "Kiểm tra thời tiết",
    description: "Đà Lạt cuối tuần này",
    query: "Dự báo thời tiết Đà Lạt cuối tuần này và tôi nên chuẩn bị gì?",
    tone: "sky",
  },
];

// ═════════════════════════════════════════════════════════════════════════════
// Main App
// ═════════════════════════════════════════════════════════════════════════════
export default function App() {
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem("theme") ||
        (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    } catch { return "light"; }
  });

  const [sessions, setSessions]         = useState([]);
  const [currentId, setCurrentId]       = useState(null);
  const [currentTitle, setCurrentTitle] = useState("Phiên chat mới");
  const [messages, setMessages]         = useState([]);
  const [query, setQuery]               = useState("");
  const [loading, setLoading]           = useState(false);
  const [isStreaming, setIsStreaming]   = useState(false);
  const [activities, setActivities]     = useState([]);
  const [sidebarOpen, setSidebarOpen]   = useState(false);
  const [faqOpen, setFaqOpen]           = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [selectedFaq, setSelectedFaq]   = useState(null);

  const messagesEndRef = useRef(null);
  const textareaRef    = useRef(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    try { localStorage.setItem("theme", theme); } catch {}
  }, [theme]);

  const scrollToBottom = () =>
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  useEffect(() => { scrollToBottom(); }, [messages, activities]);

  const fetchSessions = useCallback(async () => {
    try { setSessions(await (await fetch(`${API}/sessions`)).json()); } catch {}
  }, []);
  useEffect(() => { fetchSessions(); }, [fetchSessions]);

  const newSession = useCallback(async () => {
    try {
      const data = await (await fetch(`${API}/sessions`, { method: "POST" })).json();
      setCurrentId(data.session_id);
      setCurrentTitle("Phiên chat mới");
      setMessages([]);
      await fetchSessions();
    } catch {}
  }, [fetchSessions]);
  useEffect(() => { newSession(); }, []);

  const loadSession = async (sid, title) => {
    setCurrentId(sid); setCurrentTitle(title);
    try {
      const msgs = await (await fetch(`${API}/sessions/${sid}/messages`)).json();
      setMessages(msgs.length ? msgs : []);
    } catch {}
    setSidebarOpen(false);
    await fetchSessions();
  };

  const deleteSession = async (sid) => {
    await fetch(`${API}/sessions/${sid}`, { method: "DELETE" });
    sid === currentId ? await newSession() : await fetchSessions();
  };

  const doSend = async (text) => {
    if (!text.trim() || loading) return;
    const userText = text.trim();
    setQuery("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    setMessages(prev => [
      ...prev,
      { role: "user", content: userText },
      { role: "assistant", content: "" },
    ]);
    setLoading(true);
    setIsStreaming(false);
    setActivities([{ id: "starting", label: "Đang kết nối với agent", status: "running" }]);

    try {
      const res     = await fetch(`${API}/chat`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ session_id: currentId, query: userText }),
      });
      if (!res.ok) {
        let detail = `Server trả về lỗi ${res.status}`;
        try {
          const body = await res.json();
          detail = body.detail || detail;
        } catch {}
        throw new Error(detail);
      }
      if (!res.body) throw new Error("Server không hỗ trợ streaming");
      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n"); buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const p = JSON.parse(line.slice(6));
          if (p.event === "activity" && p.activity) {
            setActivities(prev => {
              const next = prev.filter(item => item.id !== "starting");
              const index = next.findIndex(item => item.id === p.activity.id);
              if (index === -1) return [...next, p.activity];
              next[index] = p.activity;
              return [...next];
            });
            continue;
          }
          if (p.error) {
            setActivities([]);
            setMessages(prev => {
              const c = [...prev];
              c[c.length - 1] = { role: "assistant", content: "❌ " + p.error };
              return c;
            });
            break;
          }
          if (!p.done) {
            setIsStreaming(true);
            setMessages(prev => {
              const c = [...prev];
              c[c.length - 1] = {
                role: "assistant",
                content: c[c.length - 1].content + p.token,
              };
              return c;
            });
          } else {
            setIsStreaming(false);
            setActivities([]);
            if (p.title) setCurrentTitle(p.title);
            await fetchSessions();
          }
        }
      }
    } catch (error) {
      setIsStreaming(false);
      setActivities([]);
      setMessages(prev => {
        const c = [...prev];
        c[c.length - 1] = {
          role: "assistant",
          content: `❌ ${error?.message || "Không kết nối được với server."}`,
        };
        return c;
      });
    }
    setLoading(false);
  };

  const sendMessage  = () => doSend(query);
  const handleKey    = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } };
  const autoResize   = (e) => { e.target.style.height = "auto"; e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px"; };
  const isEmpty      = messages.length === 0;

  return (
    <div className="min-h-screen bg-[#f6f8fb] dark:bg-[#0b1520] flex flex-col transition-colors duration-300">

      {/* ── Header ── */}
      <header className="sticky top-0 z-10 bg-white/85 dark:bg-[#0b1520]/85 backdrop-blur-xl border-b border-gray-200/60 dark:border-slate-800/60">
        <div className="max-w-3xl mx-auto px-4 h-20 flex items-center justify-between gap-3">

          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2.5 rounded-xl text-gray-400 hover:text-gray-700 dark:hover:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-800/70 transition-colors flex-shrink-0"
          >
            <IconMenu />
          </button>

          {/* Title block — bigger */}
          <div className="flex-1 text-center min-w-0 px-2">
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white tracking-tight leading-none">
              🗺️ Du lịch Việt Nam
            </h1>
            <p className="text-xs text-gray-400 dark:text-slate-500 mt-1.5 truncate font-medium">
              {isEmpty ? "Trợ lý du lịch thông minh" : currentTitle}
            </p>
          </div>

          <button
            onClick={() => setTheme(t => t === "dark" ? "light" : "dark")}
            className="p-2.5 rounded-xl text-gray-400 hover:text-gray-700 dark:hover:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-800/70 transition-colors flex-shrink-0"
          >
            {theme === "dark" ? <IconSun /> : <IconMoon />}
          </button>
        </div>
      </header>

      {/* ── Messages / Welcome ── */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-4 pt-8 pb-44">

          {/* Welcome screen khi chưa có tin nhắn */}
          {isEmpty && (
            <div className="flex flex-col items-center text-center pt-5 sm:pt-10 pb-6 welcome-enter">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center text-3xl mb-5 shadow-lg shadow-emerald-500/20 ring-8 ring-emerald-500/5">
                🗺️
              </div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-600 dark:text-emerald-400 mb-2">
                Trợ lý du lịch Việt Nam
              </p>
              <h2 className="text-2xl sm:text-3xl font-bold text-gray-800 dark:text-white mb-3 tracking-tight">
                👋 Xin chào! Bạn muốn khám phá đâu hôm nay?
              </h2>
              <p className="text-sm text-gray-500 dark:text-slate-400 max-w-xl leading-relaxed mb-5">
                Lên lịch trình, khám phá địa điểm và dự trù chi phí cho chuyến đi Việt Nam.
              </p>
              <div className="flex flex-wrap justify-center gap-2 mb-8 max-w-xl">
                {["Tri thức du lịch", "Thời tiết", "Bản đồ", "Ngân sách", "Thông tin mới"].map(item => (
                  <span key={item} className="capability-pill">{item}</span>
                ))}
              </div>

              {/* Suggestions reflect tools the agent can actually use. */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-2xl">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion.title}
                    onClick={() => doSend(suggestion.query)}
                    className="suggestion-card group px-4 py-4 rounded-2xl text-left
                      bg-white dark:bg-slate-800/80
                      border border-gray-200 dark:border-slate-700/60
                      text-gray-700 dark:text-slate-300
                      hover:border-emerald-400/60 dark:hover:border-emerald-500/50
                      hover:bg-emerald-50/60 dark:hover:bg-emerald-900/10
                      hover:text-emerald-700 dark:hover:text-emerald-400
                      transition-all shadow-sm hover:shadow-md hover:-translate-y-0.5
                      active:translate-y-0"
                  >
                    <span className={`suggestion-icon suggestion-${suggestion.tone}`}>{suggestion.icon}</span>
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold text-gray-800 dark:text-slate-100 group-hover:text-emerald-700 dark:group-hover:text-emerald-400">
                        {suggestion.title}
                      </span>
                      <span className="block text-xs text-gray-400 dark:text-slate-500 mt-1">
                        “{suggestion.description}”
                      </span>
                    </span>
                    <span className="suggestion-arrow" aria-hidden="true">→</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Messages */}
          {messages.map((msg, i) => (msg.role === "assistant" && !msg.content ? null : (
            <Message
              key={i}
              role={msg.role}
              content={msg.content}
              isStreaming={isStreaming && i === messages.length - 1 && msg.role === "assistant"}
            />
          )))}

          {/* High-level activity only; never chain-of-thought. */}
          {loading && (
            <div className="flex gap-3 items-end mb-6 msg-enter">
              <Avatar role="assistant" />
              <div className="flex flex-col gap-1 items-start">
                <span className="text-[10px] font-semibold uppercase tracking-widest text-violet-500/70 dark:text-violet-400/60">
                  Trợ lý AI
                </span>
                <AgentActivity activities={activities} />
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </main>

      {/* ── Composer ── */}
      <div className="fixed bottom-0 left-0 right-0 z-10 pointer-events-none"
        style={{ background: "linear-gradient(to top, var(--composer-bg) 55%, transparent)" }}>
        <div className="max-w-3xl mx-auto px-4 pb-5 pt-12 pointer-events-auto">
          <div className="flex gap-2 items-end bg-white dark:bg-slate-800/95 border border-gray-200/80 dark:border-slate-700/60 rounded-2xl shadow-xl px-4 py-3 focus-within:border-emerald-400/70 dark:focus-within:border-emerald-500/60 transition-all">
            <textarea
              ref={textareaRef}
              value={query}
              onChange={(e) => { setQuery(e.target.value); autoResize(e); }}
              onKeyDown={handleKey}
              rows={1}
              disabled={loading}
              placeholder="Nhập câu hỏi... (Enter gửi, Shift+Enter xuống dòng)"
              className="flex-1 resize-none bg-transparent text-sm text-gray-800 dark:text-slate-100 placeholder:text-gray-400 dark:placeholder:text-slate-500 focus:outline-none max-h-28 disabled:opacity-50 leading-relaxed"
            />
            <button
              onClick={sendMessage}
              disabled={loading || !query.trim()}
              className="flex-shrink-0 w-9 h-9 rounded-xl bg-emerald-500 hover:bg-emerald-400 active:scale-95 disabled:opacity-35 disabled:cursor-not-allowed text-white flex items-center justify-center transition-all shadow-md shadow-emerald-500/20"
            >
              <IconSend />
            </button>
          </div>
          <p className="text-center text-[10px] text-gray-400 dark:text-slate-600 mt-2 select-none">
            ⚠️ Thông tin có thể không chính xác. Hãy kiểm chứng trước khi quyết định.
          </p>
        </div>
      </div>

      {/* ── Sidebar ── */}
      <Panel open={sidebarOpen} onClose={() => setSidebarOpen(false)} title="Menu" side="left">
        <div className="p-4 space-y-1.5">
          <button
            onClick={() => { newSession(); setSidebarOpen(false); }}
            className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-semibold text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 border border-emerald-200/60 dark:border-emerald-800/40 transition-colors mb-3"
          >
            <IconPlus /> Phiên chat mới
          </button>

          <Collapsible label="📋 Lịch sử hội thoại">
            <div className="space-y-0.5 mt-1">
              {sessions.length === 0
                ? <p className="px-3 py-2 text-xs text-gray-400 dark:text-slate-500">Chưa có phiên nào</p>
                : sessions.map(s => (
                    <SessionItem key={s.session_id} session={s}
                      active={s.session_id === currentId}
                      onLoad={loadSession} onDelete={deleteSession} />
                  ))
              }
            </div>
          </Collapsible>

          <button
            onClick={() => { setFaqOpen(true); setSidebarOpen(false); }}
            className="w-full text-left px-3 py-2.5 rounded-xl text-sm text-gray-700 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-800/60 transition-colors"
          >
            ❓ FAQs
          </button>
          <button
            onClick={() => { setFeedbackOpen(true); setSidebarOpen(false); }}
            className="w-full text-left px-3 py-2.5 rounded-xl text-sm text-gray-700 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-800/60 transition-colors"
          >
            💬 Báo lỗi / Góp ý
          </button>
        </div>
      </Panel>

      {/* ── FAQ panel ── */}
      <Panel open={faqOpen} onClose={() => setFaqOpen(false)} title="❓ Câu hỏi thường gặp" side="right">
        <div className="p-4 space-y-2">
          {FAQS.map(faq => (
            <div key={faq.id} className="rounded-xl border border-gray-100 dark:border-slate-800 overflow-hidden">
              <button
                onClick={() => setSelectedFaq(selectedFaq?.id === faq.id ? null : faq)}
                className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 dark:bg-slate-800/50 text-left hover:bg-gray-100 dark:hover:bg-slate-800 transition-colors"
              >
                <span className="text-sm font-medium text-gray-700 dark:text-slate-300 pr-4">{faq.q}</span>
                <IconChevron open={selectedFaq?.id === faq.id} />
              </button>
              {selectedFaq?.id === faq.id && (
                <div className="px-4 py-3 text-sm text-gray-600 dark:text-slate-400 leading-relaxed bg-white dark:bg-slate-900 border-t border-gray-100 dark:border-slate-800">
                  {faq.a}
                </div>
              )}
            </div>
          ))}
        </div>
      </Panel>

      {/* ── Feedback panel ── */}
      <Panel open={feedbackOpen} onClose={() => setFeedbackOpen(false)} title="💬 Báo lỗi / Góp ý" side="right">
        <div className="p-5">
          <form
            className="space-y-4"
            onSubmit={(e) => { e.preventDefault(); alert("Cảm ơn bạn đã gửi góp ý!"); setFeedbackOpen(false); }}
          >
            <div>
              <label className="block text-xs font-medium text-gray-500 dark:text-slate-400 mb-1.5">Nội dung</label>
              <textarea rows={5} required placeholder="Mô tả chi tiết vấn đề hoặc góp ý..."
                className="w-full px-3 py-2.5 text-sm text-gray-800 dark:text-slate-200 bg-gray-50 dark:bg-slate-800/80 border border-gray-200 dark:border-slate-700 rounded-xl focus:outline-none focus:border-emerald-400 dark:focus:border-emerald-500 resize-none transition-colors placeholder:text-gray-400 dark:placeholder:text-slate-600"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 dark:text-slate-400 mb-1.5">Email liên hệ</label>
              <input type="email" required placeholder="your@email.com"
                className="w-full px-3 py-2.5 text-sm text-gray-800 dark:text-slate-200 bg-gray-50 dark:bg-slate-800/80 border border-gray-200 dark:border-slate-700 rounded-xl focus:outline-none focus:border-emerald-400 dark:focus:border-emerald-500 transition-colors placeholder:text-gray-400 dark:placeholder:text-slate-600"
              />
            </div>
            <button type="submit"
              className="w-full py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 active:scale-[0.98] text-white text-sm font-semibold transition-all shadow-md shadow-emerald-500/20">
              Gửi góp ý
            </button>
            <p className="text-xs text-gray-400 dark:text-slate-500 text-center">Phản hồi trong vòng 24–48 giờ.</p>
          </form>
        </div>
      </Panel>
    </div>
  );
}

function AgentActivity({ activities }) {
  const visible = activities.length
    ? activities
    : [{ id: "starting", label: "Đang bắt đầu xử lý", status: "running" }];

  return (
    <div className="activity-card msg-enter" aria-live="polite" aria-label="Tiến trình xử lý của trợ lý">
      <div className="activity-heading">
        <span className="activity-sparkle">✦</span>
        Agent đang thực hiện
      </div>
      <div className="activity-list">
        {visible.map((activity) => (
          <div key={activity.id} className={`activity-row activity-${activity.status}`}>
            <span className="activity-state" aria-hidden="true">
              {activity.status === "completed" ? "✓" : activity.status === "failed" ? "!" : ""}
            </span>
            <span>{activity.label}</span>
          </div>
        ))}
      </div>
      <p className="activity-note">Chỉ hiển thị trạng thái công cụ, không hiển thị suy luận nội bộ.</p>
    </div>
  );
}
