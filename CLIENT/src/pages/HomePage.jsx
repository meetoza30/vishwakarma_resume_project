import { useNavigate } from 'react-router-dom';
import './HomePage.css';

function HomePage() {
  const navigate = useNavigate();

  return (
    <div className="home-page">
      <div className="home-headline">
        <h2 className="home-title">Faculty Recruitment & Academic Resume Intelligence</h2>
        <p className="home-sub">Select a tool to screen resumes against AICTE Norms or format candidate CVs for Vishwakarma Group.</p>
      </div>

      <div className="feature-cards">
        {/* Feature 1: Academic & Faculty Resume Analyzer */}
        <div className="feature-card glass-card" onClick={() => navigate('/jd-matcher')} id="feature-jd-matcher">
          <div className="feature-icon-wrap feature-icon-blue">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 10v6M2 10l10-5 10 5-10 5z" />
              <path d="M6 12v5c3 3 9 3 12 0v-5" />
            </svg>
          </div>
          <div className="feature-content">
            <h3 className="feature-title">AICTE Faculty Screening & Resume Analyzer</h3>
            <p className="feature-desc">Batch evaluation of 10 resumes at a time against AICTE eligibility norms (Asst Prof, Assoc Prof, Professor), Scopus post-PhD publications, patents, grants & scoring.</p>
          </div>
          <div className="feature-cta">
            <span>Analyze Resumes</span>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </div>
        </div>

        {/* Feature 2: Vishwakarma Format CV Parser */}
        {/* <div className="feature-card glass-card" onClick={() => navigate('/upload')} id="feature-resume-parser">
          <div className="feature-icon-wrap feature-icon-blue">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10 9 9 9 8 9" />
            </svg>
          </div>
          <div className="feature-content">
            <h3 className="feature-title">Vishwakarma Format Resume Parser</h3>
            <p className="feature-desc">Extract candidate data and generate standardized Vishwakarma Group candidate profile PDFs.</p>
          </div>
          <div className="feature-cta">
            <span>Single Parse</span>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </div>
        </div> */}
      </div>
    </div>
  );
}

export default HomePage;
