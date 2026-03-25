import { useCallback, useMemo, useRef, useState } from 'react';
import './styles.css';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const REDIRECT_URL = (import.meta.env.VITE_REDIRECT_URL || '').trim();

function copyText(text) {
  return navigator.clipboard.writeText(text);
}

const ACCEPT_TYPES = '.pdf,.doc,.docx';
const ACCEPT_MIME = ['application/pdf',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];

/** Map a category string to a pill CSS modifier */
function pillClass(category = '') {
  const cat = category.toLowerCase();
  if (cat.includes('tech') || cat.includes('programming') || cat.includes('language'))
    return 'pill pill-tech';
  if (cat.includes('soft') || cat.includes('communication') || cat.includes('leadership'))
    return 'pill pill-soft';
  if (cat.includes('domain') || cat.includes('industry') || cat.includes('business'))
    return 'pill pill-domain';
  if (cat.includes('tool') || cat.includes('platform') || cat.includes('framework'))
    return 'pill pill-tool';
  return 'pill pill-default';
}

export default function App() {
  const canOpenRedirect = Boolean(REDIRECT_URL);
  /* ── shared state ── */
  const [tab, setTab] = useState('paste');   // 'paste' | 'upload'
  const [jd, setJd] = useState('');
  const [skills, setSkills] = useState([]);
  const [booleanString, setBooleanString] = useState('');
  const [status, setStatus] = useState('Paste a JD or upload a file to get started.');
  const [statusType, setStatusType] = useState('idle');
  const [isLoading, setIsLoading] = useState(false);
  const [copiedSkill, setCopiedSkill] = useState(null);
  const [strictness, setStrictness] = useState(3);   // 1 broad → 5 strict

  /* ── upload state ── */
  const [dragOver, setDragOver] = useState(false);
  const [uploadedFile, setUploadedFile] = useState(null); // File object
  const [textPreview, setTextPreview] = useState('');
  const fileInputRef = useRef(null);

  const STRICTNESS_LABELS = {
    1: { label: 'Very Broad', desc: 'Max reach — many synonyms, fewer AND blocks' },
    2: { label: 'Broad', desc: 'Wide net with some precision anchors' },
    3: { label: 'Balanced', desc: 'Equal recall and precision (default)' },
    4: { label: 'Strict', desc: 'Fewer synonyms, more AND blocks' },
    5: { label: 'Very Strict', desc: 'Exact matches only — max precision' },
  };

  const skillCountText = useMemo(() => {
    const count = skills.length;
    return `${count} skill${count === 1 ? '' : 's'}`;
  }, [skills]);

  function setMsg(text, type = 'idle') {
    setStatus(text);
    setStatusType(type);
  }

  /* ── apply API result ── */
  function applyResult(payload) {
    const extracted = Array.isArray(payload.skills) ? payload.skills : [];
    const query = typeof payload.boolean_string === 'string' ? payload.boolean_string.trim() : '';
    setSkills(extracted);
    setBooleanString(query);
    if (payload.extracted_text_preview) setTextPreview(payload.extracted_text_preview);
    setMsg(
      extracted.length
        ? `✓ Extracted ${extracted.length} skill${extracted.length === 1 ? '' : 's'} successfully.`
        : 'No clear skills identified.',
      extracted.length ? 'ok' : 'idle'
    );
  }

  /* ── paste mode extract ── */
  async function onExtract() {
    const value = jd.trim();
    if (!value) { setMsg('Please paste a job description first.', 'err'); return; }
    setIsLoading(true);
    setMsg('Analyzing job description with AI…', 'busy');
    setBooleanString(''); setSkills([]); setTextPreview('');

    try {
      const res = await fetch(`${API_BASE_URL}/api/extract`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jd: value, strictness }),
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(payload.detail || 'Request failed.');
      applyResult(payload);
    } catch (err) {
      setMsg(err.message || 'Unable to extract skills.', 'err');
    } finally {
      setIsLoading(false);
    }
  }

  /* ── file validation ── */
  function isValidFile(file) {
    if (!file) return false;
    const name = file.name.toLowerCase();
    return name.endsWith('.pdf') || name.endsWith('.doc') || name.endsWith('.docx');
  }

  function onSelectUploadFile(file) {
    if (!file) { setMsg('No file selected.', 'err'); return; }
    if (!isValidFile(file)) {
      setMsg('Only PDF, DOC, and DOCX files are supported.', 'err'); return;
    }
    setUploadedFile(file);
    setTextPreview('');
    setMsg(`File selected: "${file.name}". Click Generate Skills to continue.`, 'ok');
  }

  /* ── file upload extract ── */
  async function onUploadExtract() {
    if (!uploadedFile) { setMsg('Please upload a file first.', 'err'); return; }
    setIsLoading(true);
    setMsg(`Reading "${uploadedFile.name}"…`, 'busy');
    setBooleanString(''); setSkills([]); setTextPreview('');

    try {
      const form = new FormData();
      form.append('file', uploadedFile);
      form.append('strictness', String(strictness));
      const res = await fetch(`${API_BASE_URL}/api/extract-file`, { method: 'POST', body: form });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(payload.detail || 'Request failed.');
      applyResult(payload);
    } catch (err) {
      setMsg(err.message || 'Unable to process file.', 'err');
    } finally {
      setIsLoading(false);
    }
  }

  /* ── drag-and-drop ── */
  const onDrop = useCallback((e) => {
    e.preventDefault(); setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    onSelectUploadFile(file);
  }, []);

  const onDragOver = useCallback((e) => { e.preventDefault(); setDragOver(true); }, []);
  const onDragLeave = useCallback(() => setDragOver(false), []);

  /* ── file input change ── */
  function onFileInputChange(e) {
    const file = e.target.files?.[0];
    if (file) onSelectUploadFile(file);
    e.target.value = '';  // reset so same file can be re-selected
  }

  /* ── other actions ── */
  async function onCopyAll() {
    if (!skills.length) { setMsg('No skills to copy yet.', 'err'); return; }
    await copyText(skills.map((s) => s.name).join('\n'));
    setMsg(`Copied all ${skills.length} skills to clipboard.`, 'ok');
  }

  function onClear() {
    setJd(''); setSkills([]); setBooleanString(''); setUploadedFile(null); setTextPreview('');
    setMsg('Ready. Paste a new job description or upload a file.', 'idle');
  }

  async function handleCopySkill(skillName) {
    await copyText(skillName);
    setCopiedSkill(skillName);
    setMsg(`Copied: ${skillName}`, 'ok');
    setTimeout(() => setCopiedSkill(null), 1800);
  }

  async function handleCopyBoolean() {
    if (!booleanString) { setMsg('Boolean string not available yet.', 'err'); return; }
    await copyText(booleanString);
    setMsg('Copied Naukri boolean string to clipboard.', 'ok');
  }

  /* ─────────────────────────────────────────── */
  return (
    <main className="page">
      {/* Nav */}
      <nav className="topbar" aria-label="App navigation">
        <div className="topbar-brand">
          <div className="topbar-icon" aria-hidden="true">⚡</div>
          <span className="topbar-name">SkillExtract</span>
        </div>
        <span className="topbar-badge">AI Powered</span>
      </nav>

      {/* Hero */}
      <section className="hero" aria-labelledby="hero-heading">
        <div className="hero-content">
          <div className="hero-eyebrow" aria-hidden="true">🎯 &nbsp;Recruitment Intelligence</div>
          <h1 id="hero-heading">
            Extract Skills from<br />
            <span>any Job Description</span>
          </h1>
          <p className="hero-sub">
            Paste a JD or upload a PDF / Word file — AI identifies every technical,
            domain, and soft skill and generates a Naukri-ready boolean string.
          </p>
          <div className="hero-chips" aria-label="Key features">
            <span className="hero-chip">🧠 AI Skill Extraction</span>
            <span className="hero-chip">🔍 Boolean String Builder</span>
            <span className="hero-chip">📄 PDF &amp; Word Upload</span>
            <span className="hero-chip">🏷️ Auto Categorization</span>
          </div>
        </div>
      </section>

      {/* Grid */}
      <div className="layout">

        {/* ─ Input Panel ─ */}
        <article className="panel" aria-label="Job description input">
          <div className="panel-header">
            <div>
              <div className="panel-label">
                <div className="panel-dot" aria-hidden="true" />
                Input
              </div>
              <div className="panel-title">Job Description</div>
              <div className="panel-desc">Paste text or upload a PDF / Word document.</div>
            </div>
          </div>

          {/* Strictness slider — shared by both tabs */}
          <div className="strictness-control">
            <div className="strictness-header">
              <div className="strictness-title">
                <span className="strictness-icon">{strictness <= 2 ? '🏹' : strictness === 3 ? '⚖️' : '🎯'}</span>
                Boolean Strictness
              </div>
              <div className="strictness-badge" data-level={strictness}>
                {STRICTNESS_LABELS[strictness].label}
              </div>
            </div>
            <input
              id="strictness-slider"
              type="range"
              min="1"
              max="5"
              step="1"
              value={strictness}
              onChange={(e) => setStrictness(Number(e.target.value))}
              className="strictness-range"
              style={{ '--val': strictness }}
              aria-label={`Boolean strictness: ${STRICTNESS_LABELS[strictness].label}`}
              disabled={isLoading}
            />
            <div className="strictness-track-labels">
              <span>Broad</span>
              <span>Balanced</span>
              <span>Strict</span>
            </div>
            <p className="strictness-desc">{STRICTNESS_LABELS[strictness].desc}</p>
          </div>

          {/* Tab bar */}
          <div className="tab-bar" role="tablist" aria-label="Input method">
            <button
              id="tab-paste"
              role="tab"
              aria-selected={tab === 'paste'}
              className={`tab-btn ${tab === 'paste' ? 'active' : ''}`}
              onClick={() => setTab('paste')}
            >
              ✏️ Paste Text
            </button>
            <button
              id="tab-upload"
              role="tab"
              aria-selected={tab === 'upload'}
              className={`tab-btn ${tab === 'upload' ? 'active' : ''}`}
              onClick={() => setTab('upload')}
            >
              📄 Upload File
            </button>
          </div>

          {/* ── PASTE tab ── */}
          {tab === 'paste' && (
            <div className="tab-content">
              <div className="textarea-wrap">
                <textarea
                  id="jd-input"
                  value={jd}
                  onChange={(e) => setJd(e.target.value)}
                  placeholder={`Paste complete job description here…\n\ne.g. We are looking for a Senior React Developer with 5+ years...`}
                  aria-label="Job description input"
                  spellCheck="false"
                />
                {jd.length > 0 && (
                  <span className="char-count" aria-live="polite">{jd.length.toLocaleString()} chars</span>
                )}
              </div>

              <div className="actions">
                <button
                  id="extract-btn"
                  className="btn primary"
                  onClick={onExtract}
                  disabled={isLoading}
                  aria-busy={isLoading}
                >
                  {isLoading
                    ? <><span className="spinner" aria-hidden="true" /> Extracting…</>
                    : <>⚡ Extract Skills</>}
                </button>
                <button className="btn ghost-danger" onClick={onClear} disabled={isLoading}>✕ Clear</button>
                <button className="btn" onClick={() => window.open(REDIRECT_URL, '_blank', 'noopener,noreferrer')} disabled={isLoading || !canOpenRedirect}>↗ Naukri</button>
              </div>
            </div>
          )}

          {/* ── UPLOAD tab ── */}
          {tab === 'upload' && (
            <div className="tab-content">
              {/* Drop zone */}
              <div
                className={`drop-zone ${dragOver ? 'drag-over' : ''} ${uploadedFile && !isLoading ? 'has-file' : ''}`}
                onDrop={onDrop}
                onDragOver={onDragOver}
                onDragLeave={onDragLeave}
                onClick={() => !isLoading && fileInputRef.current?.click()}
                role="button"
                tabIndex={0}
                aria-label="Click or drag a PDF/Word file here"
                onKeyDown={(e) => e.key === 'Enter' && fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={ACCEPT_TYPES}
                  className="file-input-hidden"
                  onChange={onFileInputChange}
                  aria-hidden="true"
                />

                {isLoading ? (
                  <div className="drop-zone-body">
                    <div className="dz-spinner" aria-hidden="true" />
                    <p className="dz-label">Processing file…</p>
                  </div>
                ) : uploadedFile ? (
                  <div className="drop-zone-body">
                    <div className="dz-icon success">✓</div>
                    <p className="dz-filename">{uploadedFile.name}</p>
                    <p className="dz-hint">Click to replace file</p>
                  </div>
                ) : (
                  <div className="drop-zone-body">
                    <div className="dz-icon">📂</div>
                    <p className="dz-label">Drag &amp; drop your JD file here</p>
                    <p className="dz-hint">or click to browse — PDF, DOC, DOCX</p>
                    <div className="dz-formats">
                      <span className="format-chip">PDF</span>
                      <span className="format-chip">DOC</span>
                      <span className="format-chip">DOCX</span>
                    </div>
                  </div>
                )}
              </div>

              {/* Text preview */}
              {textPreview && (
                <div className="text-preview">
                  <div className="text-preview-label">📋 Extracted text preview</div>
                  <div className="text-preview-content">{textPreview}…</div>
                </div>
              )}

              <div className="actions" style={{ marginTop: '14px' }}>
                <button
                  className="btn primary"
                  onClick={onUploadExtract}
                  disabled={isLoading || !uploadedFile}
                  aria-busy={isLoading}
                >
                  {isLoading
                    ? <><span className="spinner" aria-hidden="true" /> Extracting…</>
                    : <>⚡ Generate Skills</>}
                </button>
                <button className="btn ghost-danger" onClick={onClear} disabled={isLoading}>✕ Clear</button>
                <button className="btn" onClick={() => window.open(REDIRECT_URL, '_blank', 'noopener,noreferrer')} disabled={isLoading || !canOpenRedirect}>↗ Naukri</button>
              </div>
            </div>
          )}

          {/* Status – shared */}
          <div className={`status-bar ${statusType}`} role="status" aria-live="polite">
            <span className="status-dot" aria-hidden="true" />
            <span>{status}</span>
          </div>
        </article>

        {/* ─ Results Panel ─ */}
        <article className="panel" aria-label="Extracted skills results">
          <div className="result-header">
            <span className="result-title">Extracted Skills</span>
            <div className="result-meta">
              {skills.length > 0 && (
                <span className="count-badge" aria-label={skillCountText}>{skillCountText}</span>
              )}
              <button id="copy-all-btn" className="btn" onClick={onCopyAll} disabled={!skills.length} title="Copy all skill names">
                ⎘ Copy All
              </button>
            </div>
          </div>

          {/* Boolean String */}
          <div className="boolean-section">
            <div className="section-label">Naukri Boolean String</div>
            <div className="boolean-box" aria-label="Boolean search string">
              <div className="boolean-box-header">
                <span className="boolean-box-tag">BOOLEAN QUERY</span>
                <button id="copy-boolean-btn" className="btn" onClick={handleCopyBoolean} disabled={!booleanString} title="Copy boolean string">
                  ⎘ Copy
                </button>
              </div>
              <textarea
                className="boolean-value"
                readOnly
                value={booleanString || 'Boolean search string will appear here after extraction…'}
                aria-label="Boolean string output"
              />
            </div>
          </div>

          <div className="divider" aria-hidden="true" />

          {/* Skills List */}
          {skills.length === 0 ? (
            <div className="empty-state" aria-label="No skills extracted yet">
              <div className="empty-icon" aria-hidden="true">🔍</div>
              <p>Skills extracted from the job description<br />will appear here.</p>
            </div>
          ) : (
            <ul className="skills-list" aria-label={`List of ${skills.length} extracted skills`}>
              {skills.map((skill, index) => (
                <li
                  key={`${skill.name}-${index}`}
                  className="skill-card"
                  style={{ animationDelay: `${index * 30}ms` }}
                >
                  <div className="skill-top">
                    <div>
                      <div className="skill-name">{skill.name}</div>
                      <span className={pillClass(skill.category)}>{skill.category || skill.type || 'General'}</span>
                    </div>
                    <button
                      className="btn"
                      onClick={() => handleCopySkill(skill.name)}
                      title={`Copy ${skill.name}`}
                      aria-label={`Copy ${skill.name}`}
                      style={{ flexShrink: 0 }}
                    >
                      {copiedSkill === skill.name ? '✓' : '⎘'}
                    </button>
                  </div>
                  {skill.evidence && (
                    <p className="skill-evidence">{skill.evidence}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </article>
      </div>

      {/* Footer */}
      <footer className="footer">
        <p>JD Skill Extractor &mdash; AI-powered recruitment intelligence</p>
      </footer>
    </main>
  );
}
