import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './JDResultsPage.css';
import { API_BASE } from '../utils/api';

/* Grade config */
const GRADE_CONFIG = {
  'Strong Match': { color: '#16A34A', bg: '#F0FDF4', border: '#BBF7D0', ring: '#22C55E', label: 'Strong Match', icon: '🟢' },
  'Good Match':   { color: '#0073cb', bg: '#EFF6FF', border: '#BFDBFE', ring: '#0073cb', label: 'Good Match',   icon: '🔵' },
  'Moderate Match': { color: '#D97706', bg: '#FFFBEB', border: '#FDE68A', ring: '#F59E0B', label: 'Moderate Match', icon: '🟡' },
  'Weak Match':   { color: '#DC2626', bg: '#FEF2F2', border: '#FECACA', ring: '#EF4444', label: 'Weak Match',   icon: '🔴' },
};

function scoreToGrade(score) {
  if (score <= 35) return 'Weak Match';
  if (score <= 55) return 'Moderate Match';
  if (score <= 75) return 'Good Match';
  return 'Strong Match';
}

function getGradeConfig(grade) {
  return GRADE_CONFIG[grade] || { color: '#0073cb', bg: '#e6f2fb', border: '#0073cb', ring: '#0073cb', label: grade || 'Match', icon: '🔵' };
}

/* Circular score ring */
function ScoreRing({ score, color, ring }) {
  const radius = 23;
  const circumference = 2 * Math.PI * radius;
  const filled = (score / 100) * circumference;
  const dash = `${filled} ${circumference - filled}`;

  return (
    <div className="score-ring-wrap">
      <svg width="58" height="58" viewBox="0 0 58 58">
        <circle cx="29" cy="29" r={radius} fill="none" stroke="#E2E8F0" strokeWidth="5" />
        <circle
          cx="29" cy="29" r={radius}
          fill="none"
          stroke={ring}
          strokeWidth="5"
          strokeDasharray={dash}
          strokeLinecap="round"
          transform="rotate(-90 29 29)"
          style={{ transition: 'stroke-dasharray 1s ease' }}
        />
      </svg>
      <div className="score-ring-label" style={{ color }}>
        <span className="score-ring-pct">{score}%</span>
      </div>
    </div>
  );
}

function CandidateCard({ result, index }) {
  const cfg = getGradeConfig(result.grade);
  const aicte = result.aicte_eligibility || {};
  const recStatus = aicte.primary_recommended_status || "Evaluated";
  const researchAreas = Array.isArray(result.research_areas) ? result.research_areas : [];

  return (
    <div
      className="candidate-card"
      id={`candidate-${index + 1}`}
      style={{ '--card-border': cfg.border, '--card-ring': cfg.ring }}
    >
      <div className="card-score-col">
        <ScoreRing score={result.overall_score || 0} color={cfg.color} ring={cfg.ring} />
        <span className="aicte-status-tag">{recStatus}</span>
      </div>

      <div className="card-info-col">
        <div className="card-top-row">
          <div>
            <span className="candidate-sr">#{result.sr_no || index + 1}</span>
            <h3 className="candidate-name">{result.candidate_name || result.filename?.replace(/\.[^/.]+$/, "")}</h3>
          </div>
          <span
            className="grade-badge"
            style={{ background: cfg.bg, color: cfg.color, borderColor: cfg.border }}
          >
            {cfg.icon} {cfg.label}
          </span>
        </div>

        <p className="candidate-applied-post">
          <strong>Applied Post:</strong> {result.applied_post || 'Not Mentioned'}
        </p>

        {researchAreas.length > 0 && (
          <div className="card-research-areas">
            <span className="card-research-label">Research Areas:</span>
            <div className="research-tags">
              {researchAreas.map((area, i) => (
                <span key={i} className="research-tag">{area}</span>
              ))}
            </div>
          </div>
        )}

        <p className="candidate-summary">{result.summary}</p>
      </div>
    </div>
  );
}

function JDResultsPage({ matchData, onReset }) {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('table'); // 'table' or 'cards'
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [showToast, setShowToast] = useState(true);

  useEffect(() => {
    // Auto hide notification toast after 7s
    const timer = setTimeout(() => setShowToast(false), 7000);
    return () => clearTimeout(timer);
  }, []);

  if (!matchData) {
    navigate('/jd-matcher', { replace: true });
    return null;
  }

  const { results = [], report_download_url, csv_download_url } = matchData;

  const mappedResults = results.map((r, i) => ({
    ...r,
    sr_no: r.sr_no || i + 1,
    grade: scoreToGrade(r.overall_score || 0)
  }));

  const sorted = [...mappedResults].sort((a, b) => (b.overall_score || 0) - (a.overall_score || 0));

  const handleDownloadReport = () => {
    if (!report_download_url) return;
    const url = report_download_url.startsWith('http') ? report_download_url : `${API_BASE}${report_download_url}`;
    window.open(url, '_blank');
  };

  const handleDownloadCsv = () => {
    const url = csv_download_url ? (csv_download_url.startsWith('http') ? csv_download_url : `${API_BASE}${csv_download_url}`) : `${API_BASE}/download-csv-report`;
    window.open(url, '_blank');
  };

  const handleNewMatch = () => {
    onReset?.();
    navigate('/jd-matcher');
  };

  return (
    <div className="jd-results-page">
      {/* Toast Notification */}
      {/* {showToast && (
        <div className="completion-toast-notification">
          <div className="toast-icon">✨</div>
          <div className="toast-body">
            <strong>Work Done! Analysis of Resumes Completed.</strong>
            <p>Extracted exact academic details & AICTE eligibility for {mappedResults.length} candidates.</p>
          </div>
          <button className="toast-close" onClick={() => setShowToast(false)}>×</button>
        </div>
      )} */}

      {/* ---- Top bar ---- */}
      <div className="jdr-topbar">
        <div className="jdr-topbar-left">
          <div className="jdr-icon-wrap">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 10v6M2 10l10-5 10 5-10 5z" />
              <path d="M6 12v5c3 3 9 3 12 0v-5" />
            </svg>
          </div>
          <div>
            <h2 className="jdr-main-title">Faculty Recruitment Screening Results</h2>
            <p className="jdr-main-sub">{mappedResults.length} candidate resumes extracted and evaluated against AICTE Norms</p>
          </div>
        </div>

        <div className="jdr-topbar-actions">
          <button className="primary-btn jdr-download-csv-btn" onClick={handleDownloadCsv}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
            </svg>
            Download CSV
          </button>
          
          <button className="outline-btn jdr-download-pdf-btn" onClick={handleDownloadReport}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            Download PDF
          </button>

          <button className="outline-btn jdr-new-btn" onClick={handleNewMatch}>
            New Batch
          </button>
        </div>
      </div>

      {/* ---- View Switcher ---- */}
      <div className="view-toggle-row">
        <div className="view-toggle-tabs">
          <button
            className={`view-tab ${activeTab === 'table' ? 'active' : ''}`}
            onClick={() => setActiveTab('table')}
          >
            📊 Tabulated Data View (12 Fields + AICTE Norms)
          </button>
          <button
            className={`view-tab ${activeTab === 'cards' ? 'active' : ''}`}
            onClick={() => setActiveTab('cards')}
          >
            📇 Candidate Detail Cards
          </button>
        </div>
      </div>

      {/* ---- Tab 1: Tabulated Matrix View ---- */}
      {activeTab === 'table' && (
        <div className="table-container-card glass-card">
          <div className="table-responsive-wrapper">
            <table className="faculty-summary-table">
              <thead>
                <tr>
                  <th>Sr. No.</th>
                  <th>Candidate Name</th>
                  <th>Contact Number</th>
                  <th>Email ID</th>
                  <th>Qualification (UG/PG/Ph.D. & Univ)</th>
                  <th>Publications</th>
                  <th>Research Areas</th>
                  <th>Patents</th>
                  <th>Grants / Funding</th>
                  <th>Experience (Teaching & Industry)</th>
                  <th>Previous Employers</th>
                  <th>AICTE Eligibility Norms</th>
                  <th>Score</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((r, idx) => {
                  const qual = r.qualification || {};
                  const qualText = typeof qual === 'object' ? (qual.formatted_string || `UG: ${qual.ug?.degree || '—'} | PG: ${qual.pg?.degree || '—'} | Ph.D: ${qual.phd?.status || '—'}`) : String(qual);
                  const expText = r.experience_data?.details || 'N/A';
                  const aicte = r.aicte_eligibility || {};
                  const empText = Array.isArray(r.previous_employers) ? r.previous_employers.join(', ') : (r.previous_employers || '—');

                  return (
                    <tr key={r.filename || idx} className="candidate-table-row">
                      <td className="center-cell font-bold">{idx + 1}</td>
                      <td className="cand-name-cell">
                        <strong>{r.candidate_name}</strong>
                        <span className="sub-file">{r.filename}</span>
                      </td>
                      {/* <td>{r.applied_post || 'Faculty'}</td> */}
                      <td>{r.contact_number || 'Not Mentioned'}</td>
                      <td>{r.email_id || 'Not Mentioned'}</td>
                      <td className="qual-cell">{qualText}</td>
                      <td className="center-cell highlight-cell">{r.total_publications ?? 0}</td>
                      <td className="research-areas-cell">
                        {Array.isArray(r.research_areas) && r.research_areas.length > 0 ? (
                          <div className="research-tags">
                            {r.research_areas.map((area, i) => (
                              <span key={i} className="research-tag">{area}</span>
                            ))}
                          </div>
                        ) : '—'}
                      </td>
                      <td>{r.patents || 'Nil'}</td>
                      <td>{r.grants_funding || 'Nil'}</td>
                      <td>{expText}</td>
                      <td>{empText || 'None listed'}</td>
                      <td className="aicte-cell">
                        <span className={`aicte-badge ${aicte.primary_recommended_status?.includes('Eligible') ? 'eligible' : 'not-eligible'}`}>
                          {aicte.primary_recommended_status || 'Evaluated'}
                        </span>
                      </td>
                      <td className="center-cell score-cell">
                        <span className="score-badge">{r.overall_score || 0}%</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ---- Tab 2: Detail Cards View ---- */}
      {activeTab === 'cards' && (
        <div className="jdr-cards">
          {sorted.map((result, i) => (
            <CandidateCard key={result.filename || i} result={result} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}

export default JDResultsPage;
