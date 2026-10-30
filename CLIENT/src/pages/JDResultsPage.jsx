import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import './JDResultsPage.css';
import { API_BASE } from '../utils/api';

const GRADE_CONFIG = {
  'Strong Match': { color: '#16A34A', bg: '#F0FDF4', border: '#BBF7D0', ring: '#22C55E', icon: '🟢' },
  'Good Match': { color: '#0073cb', bg: '#EFF6FF', border: '#BFDBFE', ring: '#0073cb', icon: '🔵' },
  'Moderate Match': { color: '#D97706', bg: '#FFFBEB', border: '#FDE68A', ring: '#F59E0B', icon: '🟡' },
  'Weak Match': { color: '#DC2626', bg: '#FEF2F2', border: '#FECACA', ring: '#EF4444', icon: '🔴' },
};

function scoreToGrade(score) {
  if (score <= 35) return 'Weak Match';
  if (score <= 55) return 'Moderate Match';
  if (score <= 75) return 'Good Match';
  return 'Strong Match';
}

function getAICTEEligibleRole(result) {
  if (result.aicte_eligibility_role) return result.aicte_eligibility_role;
  const eligibility = result.aicte_eligibility || {};
  const recommended = eligibility.primary_recommended_status || '';
  const prefix = 'Eligible - ';
  if (recommended.toLowerCase().startsWith(prefix.toLowerCase())) {
    return recommended.slice(prefix.length).trim();
  }
  return [
    ['professor', 'Professor'],
    ['associate_professor', 'Associate Professor'],
    ['assistant_professor', 'Assistant Professor'],
  ].find(([key]) => eligibility[key]?.eligible === true)?.[1]
    || (recommended || Object.keys(eligibility).length ? 'Not Eligible' : 'Not Evaluated');
}

function ScoreRing({ score, color, ring }) {
  const radius = 23;
  const circumference = 2 * Math.PI * radius;
  const dash = `${(score / 100) * circumference} ${circumference - (score / 100) * circumference}`;
  return (
    <div className="score-ring-wrap">
      <svg width="58" height="58" viewBox="0 0 58 58">
        <circle cx="29" cy="29" r={radius} fill="none" stroke="#E2E8F0" strokeWidth="5" />
        <circle cx="29" cy="29" r={radius} fill="none" stroke={ring} strokeWidth="5" strokeDasharray={dash} strokeLinecap="round" transform="rotate(-90 29 29)" />
      </svg>
      <div className="score-ring-label" style={{ color }}><span className="score-ring-pct">{score}%</span></div>
    </div>
  );
}

function CandidateCard({ result, index }) {
  const grade = result.grade || scoreToGrade(result.overall_score || 0);
  const config = GRADE_CONFIG[grade] || GRADE_CONFIG['Good Match'];
  const areas = Array.isArray(result.research_areas) ? result.research_areas : [];
  return (
    <div className="candidate-card" id={`candidate-${index + 1}`} style={{ '--card-border': config.border, '--card-ring': config.ring }}>
      <div className="card-score-col">
        <ScoreRing score={result.overall_score || 0} color={config.color} ring={config.ring} />
        <span className="aicte-status-tag">{getAICTEEligibleRole(result)}</span>
      </div>
      <div className="card-info-col">
        <div className="card-top-row">
          <div><span className="candidate-sr">#{result.sr_no || index + 1}</span><h3 className="candidate-name">{result.candidate_name || result.filename?.replace(/\.[^/.]+$/, '')}</h3></div>
          <span className="grade-badge" style={{ background: config.bg, color: config.color, borderColor: config.border }}>{config.icon} {grade}</span>
        </div>
        <p className="candidate-applied-post"><strong>Applied Post:</strong> {result.target_position || result.applied_post || 'Not Mentioned'}</p>
        {!!areas.length && <div className="card-research-areas"><span className="card-research-label">Research Areas:</span><div className="research-tags">{areas.map((area, i) => <span key={i} className="research-tag">{area}</span>)}</div></div>}
        <p className="candidate-summary">{result.summary}</p>
      </div>
    </div>
  );
}

function JDResultsPage({ matchData, onReset }) {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('table');
  const [showToast, setShowToast] = useState(true);
  useEffect(() => {
    const timer = setTimeout(() => setShowToast(false), 7000);
    return () => clearTimeout(timer);
  }, []);

  if (!matchData) {
    navigate('/jd-matcher', { replace: true });
    return null;
  }

  const { results = [], report_download_url, excel_download_url } = matchData;
  const mappedResults = results.map((result, index) => ({
    ...result,
    sr_no: result.sr_no || index + 1,
    grade: scoreToGrade(result.overall_score || 0),
  }));
  const sorted = [...mappedResults].sort((a, b) => (b.overall_score || 0) - (a.overall_score || 0));
  const selectedRole = matchData.target_position || sorted[0]?.target_position || '';
  const download = (path, fallback) => {
    const url = path ? (path.startsWith('http') ? path : `${API_BASE}${path}`) : `${API_BASE}${fallback}`;
    window.open(url, '_blank');
  };
  const handleNewMatch = () => { onReset?.(); navigate('/jd-matcher'); };
  const scorePillars = [
    ['Research & Publications', 'research_publications'],
    ['Experience & Norms', 'experience_position_norms'],
    ['Patents & Grants', 'patents_grants'],
    ['Leadership Roles', 'leadership_roles'],
    ['Professional Development', 'professional_dev'],
    ['Education', 'education'],
  ];

  return (
    <div className="jd-results-page">
      <div className="jdr-topbar">
        <div className="jdr-topbar-left"><div className="jdr-icon-wrap"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 10v6M2 10l10-5 10 5-10 5z" /><path d="M6 12v5c3 3 9 3 12 0v-5" /></svg></div><div><h2 className="jdr-main-title">Faculty Recruitment Screening Results</h2><p className="jdr-main-sub">{mappedResults.length} candidate resumes extracted and evaluated against AICTE Norms</p></div></div>
        <div className="jdr-topbar-actions">
          <button className="primary-btn jdr-download-csv-btn" onClick={() => download(excel_download_url, '/download-excel-report')}>Download Excel</button>
          <button className="outline-btn jdr-download-pdf-btn" onClick={() => download(report_download_url, '/download-report')}>Download PDF</button>
          <button className="outline-btn jdr-new-btn" onClick={handleNewMatch}>New Batch</button>
        </div>
      </div>

      <div className="view-toggle-row"><div className="view-toggle-tabs">
        <button className={`view-tab ${activeTab === 'table' ? 'active' : ''}`} onClick={() => setActiveTab('table')}>📊 Tabulated Data View (Excel Report)</button>
        <button className={`view-tab ${activeTab === 'cards' ? 'active' : ''}`} onClick={() => setActiveTab('cards')}>📇 Candidate Detail Cards</button>
      </div></div>

      {activeTab === 'table' && <div className="table-container-card glass-card"><div className="table-responsive-wrapper"><table className="faculty-summary-table">
        <thead><tr>
          <th>Sr. No.</th><th>Timing</th><th>Name of Candidate</th><th>Applied for Post</th><th>Contact No.</th><th>Email ID</th><th>Overall Score</th><th>Score Breakdown</th><th>Qualification (UG/PG/Ph.D.)</th><th>Research Areas</th><th>Scopus Publications after Ph.D.</th><th>Patent (Filed/Published/Granted)</th><th>Grants/Funding Received</th><th>Experience (Teaching / Industry)</th><th>Previous Employers</th><th>Eligibility as per AICTE Norms</th>
        </tr></thead>
        <tbody>{sorted.map((result, index) => {
          const failed = result.success === false;
          const qualification = result.qualification || {};
          const qualificationText = typeof qualification === 'object' ? (qualification.formatted_string || '') : String(qualification || '');
          const breakdown = result.breakdown || {};
          const scoreText = scorePillars.map(([label, key]) => {
            const score = breakdown[key]?.score;
            return `${label}: ${score == null ? 'Not Scored' : `${score}/100`}`;
          }).join('\n');
          const researchAreas = Array.isArray(result.research_areas) ? result.research_areas.join(', ') : (result.research_areas || '');
          const employers = Array.isArray(result.previous_employers) ? result.previous_employers.filter(Boolean).map(name => `• ${name}`).join('\n') : (result.previous_employers || '');
          return <tr key={result.filename || index} className="candidate-table-row">
            <td className="center-cell font-bold">{index + 1}</td><td></td>
            <td>{failed ? `Error: ${result.error || 'Candidate processing failed'}` : (result.candidate_name || result.filename)}</td>
            <td>{failed ? '' : (result.target_position || selectedRole)}</td><td>{failed ? '' : (result.contact_number || '')}</td><td>{failed ? '' : (result.email_id || '')}</td>
            <td className="center-cell score-cell">{failed ? '' : (result.overall_score || 0)}</td><td className="report-breakdown-cell">{failed ? '' : scoreText}</td>
            <td className="qual-cell">{failed ? '' : qualificationText}</td><td>{failed ? '' : researchAreas}</td><td>{failed ? '' : (result.scopus_post_phd_publications ?? '')}</td>
            <td>{failed ? '' : (result.patents || '')}</td><td>{failed ? '' : (result.grants_funding || '')}</td><td>{failed ? '' : (result.experience_data?.details || '')}</td>
            <td>{failed ? '' : employers}</td><td>{failed ? '' : getAICTEEligibleRole(result)}</td>
          </tr>;
        })}</tbody>
      </table></div></div>}

      {activeTab === 'cards' && <div className="jdr-cards">{sorted.map((result, index) => <CandidateCard key={result.filename || index} result={result} index={index} />)}</div>}
    </div>
  );
}

export default JDResultsPage;
