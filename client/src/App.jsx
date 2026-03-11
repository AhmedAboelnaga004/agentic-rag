import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import "./App.css";

const DOC_TYPES = ["Lecture", "Textbook", "Assignment", "Notes", "Exam", "Other"];

/**
 * Normalise LLM math output so remark-math + KaTeX can render it correctly.
 *
 * Root cause: Gemini returns LaTeX inside JSON. The JSON layer encodes every
 * backslash as \\ so "\frac" in LaTeX becomes "\\frac" in the JSON string.
 * When JavaScript parses the JSON it keeps it as "\\frac" (two chars: \ + \).
 * KaTeX then sees a literal backslash followed by "frac" — not a command.
 *
 * Fix: replace every \\ that precedes a letter or common LaTeX symbol with a
 * single \, but only when we are inside a $...$ or $$...$$ span so we never
 * corrupt URLs or code blocks that legitimately contain \\.
 *
 * Additionally wraps bare LaTeX lines (no $ but contains \cmd) in $$ $$.
 */
function fixLatex(text) {
  // Step 1 — fix double-backslashes inside $ ... $ and $$ ... $$ spans.
  // Strategy: split on math delimiters, fix only the math segments.
  const parts = text.split(/(\$\$[\s\S]*?\$\$|\$[^\n$]*?\$)/g);
  const fixed = parts.map((part, i) => {
    // Odd-indexed parts are the captured math spans
    if ((i % 2) === 1) {
      // Replace \\cmd → \cmd inside math
      return part.replace(/\\\\([a-zA-Z'`"{}[\]()^_|])/g, "\\$1");
    }
    return part;
  });
  let result = fixed.join("");

  // Step 2 — wrap bare LaTeX lines that have no $ delimiters at all.
  // Catches cases where the LLM forgot to add $ around a standalone equation.
  const LATEX_CMD = /\\[a-zA-Z]+/;
  const HAS_DOLLAR = /\$/;
  let inCodeFence = false;
  const processed = result.split("\n").map((line) => {
    if (line.trimStart().startsWith("```")) {
      inCodeFence = !inCodeFence;
      return line;
    }
    if (inCodeFence) return line;
    const trimmed = line.trim();
    if (trimmed.length > 0 && LATEX_CMD.test(trimmed) && !HAS_DOLLAR.test(trimmed)) {
      return `$$${trimmed}$$`;
    }
    return line;
  });

  return processed.join("\n");
}

const EMPTY_CONTEXT = {
  university_id: "",
  faculty_id: "",
  semester: "",
  course_id: "",
  course_code: "",
  course_name: "",
};

function App() {
  // ── Course context ──────────────────────────────────────────────────────
  // courseContext holds the form inputs; activeCourse is locked in once "Start"
  // is clicked. All chat and upload requests use activeCourse.
  const [courseContext, setCourseContext] = useState(EMPTY_CONTEXT);
  const [activeCourse, setActiveCourse] = useState(null);

  // ── Chat ────────────────────────────────────────────────────────────────
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);

  // ── Upload ──────────────────────────────────────────────────────────────
  const [selectedFile, setSelectedFile] = useState(null);
  const [docTitle, setDocTitle] = useState("");
  const [docType, setDocType] = useState(DOC_TYPES[0]);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState(null);

  const endOfMessagesRef = useRef(null);

  useEffect(() => {
    endOfMessagesRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // ── Handlers ────────────────────────────────────────────────────────────

  const updateCtx = (field) => (e) =>
    setCourseContext((prev) => ({ ...prev, [field]: e.target.value }));

  const startSession = () => {
    const { university_id, faculty_id, semester, course_id, course_code, course_name } =
      courseContext;
    if (!university_id || !faculty_id || !semester || !course_id || !course_code || !course_name) {
      alert("Please fill in all course context fields before starting.");
      return;
    }
    setActiveCourse({ ...courseContext });
    setMessages([]);
  };

  const changeCourse = () => {
    setActiveCourse(null);
    setMessages([]);
    setUploadStatus(null);
  };

  const sendMessage = async () => {
    const trimmed = input.trim();
    if (!trimmed || loading || !activeCourse) return;

    setLoading(true);
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: trimmed }]);

    try {
      const response = await fetch("http://localhost:8000/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmed,
          university_id: activeCourse.university_id,
          course_id: activeCourse.course_id,
          course_name: activeCourse.course_name,
        }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data?.detail || "Chat request failed");
      setMessages((prev) => [...prev, { role: "ai", text: data.answer }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "ai", text: err?.message ?? "Chat request failed" },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const uploadDocument = async () => {
    if (!selectedFile || !activeCourse) return;
    if (!docTitle.trim()) {
      alert("Please enter a document title.");
      return;
    }

    setUploading(true);
    setUploadStatus(null);

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("university_id", activeCourse.university_id);
      formData.append("faculty_id", activeCourse.faculty_id);
      formData.append("semester", activeCourse.semester);
      formData.append("course_id", activeCourse.course_id);
      formData.append("course_code", activeCourse.course_code);
      formData.append("course_name", activeCourse.course_name);
      formData.append("doc_title", docTitle.trim());
      formData.append("doc_type", docType);

      const response = await fetch("http://localhost:8000/api/ingest", {
        method: "POST",
        body: formData,
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data?.detail || "Upload failed");

      setUploadStatus(`✓ "${docTitle}" uploaded and ingested successfully.`);
      setSelectedFile(null);
      setDocTitle("");
    } catch (err) {
      setUploadStatus(`✗ ${err?.message ?? "Upload failed"}`);
    } finally {
      setUploading(false);
    }
  };

  const onComposerKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // ── Course context setup screen ─────────────────────────────────────────
  if (!activeCourse) {
    return (
      <div className="appShell">
        <header className="appHeader">
          <div className="appHeaderInner">
            <div className="appTitle">Agentic Study Assistant</div>
            <div className="appSubtitle">Enter your course context to begin.</div>
          </div>
        </header>
        <main className="appMain">
          <section className="contextPanel">
            <h2 className="contextTitle">Course Context</h2>
            <div className="contextGrid">
              <label>
                University ID
                <input value={courseContext.university_id} onChange={updateCtx("university_id")} placeholder="e.g. CAIRO_UNI" />
              </label>
              <label>
                Faculty ID
                <input value={courseContext.faculty_id} onChange={updateCtx("faculty_id")} placeholder="e.g. ENGINEERING" />
              </label>
              <label>
                Semester
                <input value={courseContext.semester} onChange={updateCtx("semester")} placeholder="e.g. 2025-SPRING" />
              </label>
              <label>
                Course ID
                <input value={courseContext.course_id} onChange={updateCtx("course_id")} placeholder="e.g. MATH101" />
              </label>
              <label>
                Course Code
                <input value={courseContext.course_code} onChange={updateCtx("course_code")} placeholder="e.g. MATH101" />
              </label>
              <label>
                Course Name
                <input value={courseContext.course_name} onChange={updateCtx("course_name")} placeholder="e.g. Calculus 1" />
              </label>
            </div>
            <button className="primaryButton" onClick={startSession}>
              Start Session
            </button>
          </section>
        </main>
      </div>
    );
  }

  // ── Main app (course locked) ────────────────────────────────────────────
  return (
    <div className="appShell">
      <header className="appHeader">
        <div className="appHeaderInner">
          <div className="appTitle">
            {activeCourse.course_name}
            <span className="courseTag">{activeCourse.course_code}</span>
          </div>
          <div className="appSubtitle">
            {activeCourse.faculty_id} · {activeCourse.semester} ·{" "}
            <button className="linkButton" onClick={changeCourse}>
              Change course
            </button>
          </div>
        </div>
      </header>

      <main className="appMain">
        <section className="uploadPanel">
          <div className="uploadRow">
            <label className="uploadButton" htmlFor="pdf-upload">
              Choose PDF
            </label>
            <input
              id="pdf-upload"
              className="uploadInput"
              type="file"
              accept="application/pdf,.pdf"
              onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
            />
            <input
              className="docTitleInput"
              type="text"
              placeholder="Document title…"
              value={docTitle}
              onChange={(e) => setDocTitle(e.target.value)}
            />
            <select
              className="docTypeSelect"
              value={docType}
              onChange={(e) => setDocType(e.target.value)}
            >
              {DOC_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <button
              className="primaryButton"
              onClick={uploadDocument}
              disabled={!selectedFile || uploading}
            >
              {uploading ? "Uploading…" : "Upload"}
            </button>
            <div className="uploadMeta">
              {selectedFile ? selectedFile.name : "No file selected"}
            </div>
          </div>
          {uploadStatus && <div className="uploadStatus">{uploadStatus}</div>}
        </section>

        <section className="chatPanel">
          <div className="messages">
            {messages.length === 0 && (
              <div className="emptyState">
                Upload a PDF for <strong>{activeCourse.course_name}</strong>, then ask a question below.
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} className={m.role === "user" ? "messageRow isUser" : "messageRow isAi"}>
                <div className="messageBubble">
                  {m.role === "ai" ? (
                    <ReactMarkdown
                      remarkPlugins={[remarkMath]}
                      rehypePlugins={[rehypeKatex]}
                    >
                      {fixLatex(m.text)}
                    </ReactMarkdown>
                  ) : m.text}
                </div>
              </div>
            ))}

            {loading && (
              <div className="messageRow isAi">
                <div className="messageBubble isTyping">Thinking…</div>
              </div>
            )}
            <div ref={endOfMessagesRef} />
          </div>

          <div className="composer">
            <div className="composerInner">
              <textarea
                className="composerInput"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onComposerKeyDown}
                placeholder={`Ask about ${activeCourse.course_name}…`}
                rows={1}
              />
              <button
                className="sendButton"
                onClick={sendMessage}
                disabled={loading || !input.trim()}
              >
                Send
              </button>
            </div>
            <div className="composerHint">Enter to send · Shift+Enter for a new line</div>
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
