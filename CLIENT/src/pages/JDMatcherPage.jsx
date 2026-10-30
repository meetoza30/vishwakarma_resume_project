import { useRef, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './JDMatcherPage.css';
import { API_BASE } from '../utils/api';

function playCompletionChime() {
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const now = ctx.currentTime;

    const osc1 = ctx.createOscillator();
    const osc2 = ctx.createOscillator();
    const gain = ctx.createGain();

    osc1.type = 'sine';
    osc1.frequency.setValueAtTime(587.33, now); // D5
    osc1.frequency.exponentialRampToValueAtTime(880, now + 0.15); // A5

    osc2.type = 'triangle';
    osc2.frequency.setValueAtTime(880, now + 0.15);
    osc2.frequency.exponentialRampToValueAtTime(1174.66, now + 0.35); // D6

    gain.gain.setValueAtTime(0.12, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.55);

    osc1.connect(gain);
    osc2.connect(gain);
    gain.connect(ctx.destination);

    osc1.start(now);
    osc2.start(now + 0.15);
    osc1.stop(now + 0.35);
    osc2.stop(now + 0.55);
  } catch (e) {
    // AudioContext blocked or unsupported
  }
}

function JDMatcherPage({ onMatchComplete }) {
  const navigate = useNavigate();

  const [targetPosition, setTargetPosition] = useState('');
  const [resumeFiles, setResumeFiles] = useState([]);
  const [isDragging, setIsDragging] = useState(false);
  const resumeInputRef = useRef(null);

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [completionData, setCompletionData] = useState(null);
  const [notifPermission, setNotifPermission] = useState(() => (window.Notification ? Notification.permission : 'unsupported'));

  // Proactively check browser desktop notification permission on mount
  useEffect(() => {
    if (window.Notification) {
      setNotifPermission(Notification.permission);
      if (Notification.permission === 'default') {
        Notification.requestPermission().then(perm => setNotifPermission(perm)).catch(() => {});
      }
    }
  }, []);

  const requestAndTestNotification = async () => {
    playCompletionChime();
    if (window.Notification) {
      if (Notification.permission !== 'granted') {
        const perm = await Notification.requestPermission();
        setNotifPermission(perm);
        if (perm === 'granted') {
          new Notification('Vishwakarma Screening Portal', {
            body: '✅ Notifications are enabled! You will be alerted when resume processing completes.',
            icon: '/favicon.ico',
          });
        }
      } else {
        new Notification('Vishwakarma Screening Portal', {
          body: '🔔 Test Notification: Batch screening alerts are active and working!',
          icon: '/favicon.ico',
        });
      }
    }
  };

  /* ---- RESUME FILE HANDLERS ---- */
  const addResumes = (files) => {
    const validFiles = Array.from(files).filter(f => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf') || f.name.toLowerCase().endsWith('.docx') || f.name.toLowerCase().endsWith('.doc') || f.type.includes('word'));
    if (validFiles.length !== files.length) setError('Only PDF and DOCX files accepted. Other formats were skipped.');
    setResumeFiles(prev => {
      const names = new Set(prev.map(f => f.name));
      return [...prev, ...validFiles.filter(f => !names.has(f.name))];
    });
  };

  const handleDragOver = (e) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = (e) => { e.preventDefault(); setIsDragging(false); };
  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files.length) addResumes(e.dataTransfer.files);
  };

  const removeResume = (name) => setResumeFiles(prev => prev.filter(f => f.name !== name));

  /* ---- SUBMIT ---- */
  const handleSubmit = async () => {
    setError(null);

    // Request notification permission if still default
    if (window.Notification && Notification.permission === 'default') {
      try { await Notification.requestPermission(); } catch (e) {}
    }

    // Validation
    if (!targetPosition) return setError('Please select a faculty position.');
    if (resumeFiles.length === 0) return setError('Please upload at least one resume (up to 10 resumes at a time).');

    const formData = new FormData();
    formData.append('target_position', targetPosition);
    resumeFiles.forEach(f => formData.append('resume_files', f));

    setIsLoading(true);

    try {
      const res = await fetch(`${API_BASE}/match-bulk`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Server error ${res.status}`);
      }

      const data = await res.json();
      onMatchComplete(data);

      // 1. Play pleasant audio completion sound
      playCompletionChime();

      // 2. Trigger OS Desktop Notification
      if (window.Notification && Notification.permission === 'granted') {
        new Notification('Vishwakarma Faculty Resume Analysis Complete', {
          body: `Successfully evaluated ${resumeFiles.length} candidate resume(s) against AICTE Norms!`,
          icon: '/favicon.ico',
        });
      }

      // 3. Show interactive In-App Completion Popup Modal
      setIsLoading(false);
      setCompletionData({
        count: resumeFiles.length,
        results: data.results || [],
        topCandidate: (data.results || []).reduce((prev, curr) => ((curr.overall_score || 0) > (prev?.overall_score || 0) ? curr : prev), data.results?.[0] || null),
      });
      console.log(data.results)

    } catch (err) {
      setIsLoading(false);
      setError(err.message || 'Something went wrong. Please try again.');
    }
  };

  /* ---- RENDER ---- */
  if (isLoading) {
    return (
      <div className="jd-matcher-page-container">
        <div className="jdm-header-top">
          <div className="jdm-header-left">
            <div className="jdm-icon-wrap">
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 10v6M2 10l10-5 10 5-10 5z" />
                <path d="M6 12v5c3 3 9 3 12 0v-5" />
              </svg>
            </div>
            <div>
              <h2 className="jdm-title">Faculty Resume & AICTE Eligibility Analyzer</h2>
              <p className="jdm-subtitle">Batch analysis of up to 10 resumes against the selected AICTE position norms</p>
            </div>
          </div>
          {/* ---- Submit ---- */}
          <div className="jdm-footer">
            <button
              id="jdm-submit-btn"
              className="primary-btn jdm-submit-btn"
              onClick={handleSubmit}
              disabled={isLoading}
            >
              Analyzing...
            </button>
            <button className="outline-btn" onClick={() => navigate('/')}>Back</button>
          </div>
        </div>

        <div className="jdm-section glass-card jd-loading-state">
          <div className="jd-scanner-icon">
            <svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="jd-scan-svg">
              <path d="M22 10v6M2 10l10-5 10 5-10 5z" />
              <path d="M6 12v5c3 3 9 3 12 0v-5" />
            </svg>
            <div className="jd-scan-ring" />
          </div>
          <h3 className="jd-loading-title">Extracting Details & Evaluating AICTE Norms…</h3>
          <p className="jd-loading-sub">
            Analyzing {resumeFiles.length} candidate resume{resumeFiles.length > 1 ? 's' : ''} for qualifications, Scopus papers, patents, grants & AICTE compliance.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="jd-matcher-page-container">
      {/* Header top */}
      <div className="jdm-header-top">
        <div className="jdm-header-left">
          <div className="jdm-icon-wrap">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
          </div>
          <div>
            <h2 className="jdm-title">Resume analyzer</h2>
            <p className="jdm-subtitle">Select a faculty position, then upload resumes for evaluation</p>
          </div>
        </div>
        {/* ---- Submit ---- */}
        <div className="jdm-footer">
          <button
            type="button"
            className="outline-btn jdm-notif-toggle-btn"
            onClick={requestAndTestNotification}
            title="Click to test sound chime and desktop alert"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
              <path d="M13.73 21a2 2 0 0 1-3.46 0" />
            </svg>
            {notifPermission === 'granted' ? 'Alerts Active (Test)' : 'Enable Alerts'}
          </button>

          <button
            id="jdm-submit-btn"
            className="primary-btn jdm-submit-btn"
            onClick={handleSubmit}
            disabled={isLoading}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            Run analysis
          </button>
          <button className="outline-btn" onClick={() => navigate('/')}>Back</button>
        </div>
      </div>

      {error && (
        <div className="jdm-error" role="alert">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          {error}
        </div>
      )}

      <div className="jdm-sections-row">
        {/* ---- Section 1: Select stored faculty criteria ---- */}
        <section className="jdm-section glass-card">
          <div className="jdm-section-label">
            <span className="jdm-step">1</span>
            <h3 className="jdm-section-title">Select Position</h3>
          </div>
          <p className="jdm-subtitle">The selected role determines which stored AICTE norms are applied.</p>
          <div className="jdm-role-options" role="group" aria-label="Faculty position">
            {['Assistant Professor', 'Associate Professor', 'Professor'].map(role => (
              <button
                key={role}
                type="button"
                className={`jdm-role-button ${targetPosition === role ? 'active' : ''}`}
                aria-pressed={targetPosition === role}
                onClick={() => setTargetPosition(role)}
              >
                {role}
              </button>
            ))}
          </div>
        </section>

        {/* ---- Section 2: Resume Upload ---- */}
        <section className="jdm-section glass-card">
          <div className="jdm-section-label">
            <span className="jdm-step">2</span>
            <h3 className="jdm-section-title">Upload Resumes</h3>
          </div>

          <div
            id="resume-dropzone"
            className={`jdm-dropzone ${isDragging ? 'dragging' : ''}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => resumeInputRef.current?.click()}
          >
            <div className="jdm-dz-icon">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
              </svg>
            </div>
            <p className="jdm-dz-main"><span className="jdm-dz-highlight">Click to upload</span> or drag & drop</p>
            <p className="jdm-dz-sub">Multiple PDF & DOCX resumes supported</p>
          </div>
          <input
            ref={resumeInputRef}
            type="file"
            name="resume_files"
            accept=".pdf,.docx,.doc"
            multiple
            onChange={e => addResumes(e.target.files)}
            style={{ display: 'none' }}
          />

          {/* File list */}
          {resumeFiles.length > 0 && (
            <div className="jdm-file-list">
              <div className="jdm-file-list-header">
                <span>{resumeFiles.length} resume{resumeFiles.length > 1 ? 's' : ''} selected</span>
                <button className="jdm-clear-all" onClick={() => setResumeFiles([])}>Clear all</button>
              </div>
              {resumeFiles.map(f => (
                <div key={f.name} className="jdm-file-row">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" />
                  </svg>
                  <span className="jdm-file-name">{f.name}</span>
                  <span className="jdm-file-size">{(f.size / 1024).toFixed(0)} KB</span>
                  <button className="jdm-remove-file" onClick={() => removeResume(f.name)} aria-label={`Remove ${f.name}`}>×</button>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      {/* ---- In-App Animated Completion Modal ---- */}
      {completionData && (
        <div className="jdm-modal-overlay">
          <div className="jdm-modal-card">
            <h3 className="jdm-modal-title">Faculty Screening Complete!</h3>
            <p className="jdm-modal-sub">
              Successfully evaluated <strong>{completionData.count}</strong> candidate resume{completionData.count > 1 ? 's' : ''} against AICTE Norms & Faculty Requirements.
            </p>

            {completionData.topCandidate && (
              <div className="jdm-modal-highlight">
                <div className="jdm-modal-hl-header">
                  <span className="jdm-modal-hl-pill">Top Recommended Candidate</span>
                  <span className="jdm-modal-hl-score">{completionData.topCandidate.overall_score || 0}% Match</span>
                </div>
                <div className="jdm-modal-hl-name">
                  {completionData.topCandidate.candidate_name || completionData.topCandidate.filename}
                </div>
                <div className="jdm-modal-hl-post">
                  {completionData.topCandidate.applied_post || "Faculty Post"} · <span className="jdm-modal-hl-grade">{completionData.topCandidate.grade || "Strong Match"}</span>
                </div>
                {completionData.topCandidate.summary && (
                  <p className="jdm-modal-hl-summary">{completionData.topCandidate.summary}</p>
                )}
              </div>
            )}

            <div className="jdm-modal-actions">
              <button
                className="primary-btn jdm-modal-view-btn"
                onClick={() => navigate('/jd-results')}
              >
                View Full Results & Analytics Dashboard →
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

export default JDMatcherPage;
