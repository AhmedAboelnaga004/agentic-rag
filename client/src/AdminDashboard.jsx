import { useMemo, useState } from "react";
import "./AdminDashboard.css";

const INITIAL_UNIVERSITIES = [
  {
    id: "cairo_uni",
    name: "Cairo University",
    contact_email: "it-admin@cairo.edu",
    status: "active",
    faculties_count: 4,
    active_semesters: 2,
    docs_ingested: 186,
    total_messages: 4231,
    est_cost_usd: 184.22,
  },
  {
    id: "alex_uni",
    name: "Alexandria University",
    contact_email: "lms@alex.edu",
    status: "active",
    faculties_count: 3,
    active_semesters: 1,
    docs_ingested: 97,
    total_messages: 1902,
    est_cost_usd: 86.4,
  },
  {
    id: "mans_uni",
    name: "Mansoura University",
    contact_email: "digital.learning@mans.edu",
    status: "inactive",
    faculties_count: 2,
    active_semesters: 0,
    docs_ingested: 41,
    total_messages: 612,
    est_cost_usd: 27.88,
  },
];

const INITIAL_FACULTIES = [
  { id: "eng_cairo", university_id: "cairo_uni", name: "Engineering", status: "active", courses_count: 14, docs_count: 78, chunks_count: 5401 },
  { id: "med_cairo", university_id: "cairo_uni", name: "Medicine", status: "active", courses_count: 10, docs_count: 52, chunks_count: 3324 },
  { id: "sci_cairo", university_id: "cairo_uni", name: "Science", status: "active", courses_count: 8, docs_count: 39, chunks_count: 2418 },
  { id: "eng_alex", university_id: "alex_uni", name: "Engineering", status: "active", courses_count: 11, docs_count: 58, chunks_count: 3602 },
  { id: "bus_alex", university_id: "alex_uni", name: "Business", status: "active", courses_count: 6, docs_count: 24, chunks_count: 1197 },
  { id: "agri_mans", university_id: "mans_uni", name: "Agriculture", status: "inactive", courses_count: 5, docs_count: 19, chunks_count: 704 },
];

const INITIAL_SEMESTERS = [
  { id: "cairo_2026_spring", university_id: "cairo_uni", label: "2026 Spring", starts_on: "2026-02-01", ends_on: "2026-06-20", status: "active", docs_count: 102, messages_count: 2820 },
  { id: "cairo_2025_fall", university_id: "cairo_uni", label: "2025 Fall", starts_on: "2025-09-10", ends_on: "2026-01-25", status: "active", docs_count: 84, messages_count: 1411 },
  { id: "alex_2026_spring", university_id: "alex_uni", label: "2026 Spring", starts_on: "2026-02-05", ends_on: "2026-06-25", status: "active", docs_count: 97, messages_count: 1902 },
  { id: "mans_2025_fall", university_id: "mans_uni", label: "2025 Fall", starts_on: "2025-09-15", ends_on: "2026-01-30", status: "inactive", docs_count: 41, messages_count: 612 },
];

const INITIAL_COURSES_ACTIVITY = [
  { course_code: "MATH101", course_name: "Calculus I", university_id: "cairo_uni", faculty_id: "eng_cairo", docs: 24, messages: 1102 },
  { course_code: "PHY201", course_name: "General Physics", university_id: "cairo_uni", faculty_id: "sci_cairo", docs: 19, messages: 840 },
  { course_code: "MECH301", course_name: "Thermodynamics", university_id: "alex_uni", faculty_id: "eng_alex", docs: 15, messages: 701 },
  { course_code: "ACC101", course_name: "Financial Accounting", university_id: "alex_uni", faculty_id: "bus_alex", docs: 13, messages: 494 },
  { course_code: "BIO221", course_name: "Medical Biology", university_id: "cairo_uni", faculty_id: "med_cairo", docs: 11, messages: 445 },
];

function fmtUsd(value) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value);
}

export default function AdminDashboard() {
  const [tab, setTab] = useState("overview");
  const [universities, setUniversities] = useState(INITIAL_UNIVERSITIES);
  const [faculties, setFaculties] = useState(INITIAL_FACULTIES);
  const [semesters, setSemesters] = useState(INITIAL_SEMESTERS);
  const [courses] = useState(INITIAL_COURSES_ACTIVITY);

  const [uniForm, setUniForm] = useState({ id: "", name: "", contact_email: "" });
  const [facultyForm, setFacultyForm] = useState({ id: "", name: "", university_id: "" });
  const [semesterForm, setSemesterForm] = useState({ id: "", label: "", university_id: "", starts_on: "", ends_on: "" });
  const [facultyFilterUni, setFacultyFilterUni] = useState("all");

  const dashboardMetrics = useMemo(() => {
    const totalDocs = universities.reduce((sum, item) => sum + item.docs_ingested, 0);
    const totalMsgs = universities.reduce((sum, item) => sum + item.total_messages, 0);
    const totalCost = universities.reduce((sum, item) => sum + item.est_cost_usd, 0);
    const activeUnis = universities.filter((item) => item.status === "active").length;
    const activeSemesters = semesters.filter((item) => item.status === "active").length;
    return { totalDocs, totalMsgs, totalCost, activeUnis, activeSemesters };
  }, [universities, semesters]);

  const filteredFaculties = useMemo(() => {
    if (facultyFilterUni === "all") return faculties;
    return faculties.filter((item) => item.university_id === facultyFilterUni);
  }, [faculties, facultyFilterUni]);

  const topUniversitiesByCost = useMemo(() => {
    return [...universities].sort((a, b) => b.est_cost_usd - a.est_cost_usd);
  }, [universities]);

  const highestCost = topUniversitiesByCost[0]?.est_cost_usd || 1;

  const recommendations = useMemo(() => {
    const data = [];
    const highCost = topUniversitiesByCost[0];
    if (highCost) {
      data.push(`Review ${highCost.name} usage weekly: it is your highest spend at ${fmtUsd(highCost.est_cost_usd)}.`);
    }
    const inactiveSemesters = semesters.filter((item) => item.status !== "active").length;
    if (inactiveSemesters > 0) {
      data.push(`You have ${inactiveSemesters} inactive semester(s); archive their stale documents to reduce retrieval noise.`);
    }
    const lowDocsFaculties = faculties.filter((item) => item.docs_count < 20).length;
    if (lowDocsFaculties > 0) {
      data.push(`${lowDocsFaculties} faculty/faculties have low content density (<20 docs); prioritize onboarding more core materials.`);
    }
    data.push("Track duplicate upload rejection rate per university to identify user training and UX issues.");
    data.push("Set monthly budget alerts by university and faculty to avoid unexpected LlamaParse/Gemini overages.");
    return data;
  }, [topUniversitiesByCost, semesters, faculties]);

  function getUniName(universityId) {
    return universities.find((item) => item.id === universityId)?.name || universityId;
  }

  function addUniversity() {
    if (!uniForm.id.trim() || !uniForm.name.trim()) return;
    setUniversities((prev) => [
      {
        id: uniForm.id.trim(),
        name: uniForm.name.trim(),
        contact_email: uniForm.contact_email.trim() || "-",
        status: "active",
        faculties_count: 0,
        active_semesters: 0,
        docs_ingested: 0,
        total_messages: 0,
        est_cost_usd: 0,
      },
      ...prev,
    ]);
    setUniForm({ id: "", name: "", contact_email: "" });
  }

  function addFaculty() {
    if (!facultyForm.id.trim() || !facultyForm.name.trim() || !facultyForm.university_id) return;
    setFaculties((prev) => [
      {
        id: facultyForm.id.trim(),
        name: facultyForm.name.trim(),
        university_id: facultyForm.university_id,
        status: "active",
        courses_count: 0,
        docs_count: 0,
        chunks_count: 0,
      },
      ...prev,
    ]);
    setUniversities((prev) => prev.map((item) => item.id === facultyForm.university_id ? { ...item, faculties_count: item.faculties_count + 1 } : item));
    setFacultyForm({ id: "", name: "", university_id: "" });
  }

  function addSemester() {
    if (!semesterForm.id.trim() || !semesterForm.label.trim() || !semesterForm.university_id) return;
    setSemesters((prev) => [
      {
        id: semesterForm.id.trim(),
        label: semesterForm.label.trim(),
        university_id: semesterForm.university_id,
        starts_on: semesterForm.starts_on || "2026-01-01",
        ends_on: semesterForm.ends_on || "2026-06-30",
        status: "active",
        docs_count: 0,
        messages_count: 0,
      },
      ...prev,
    ]);
    setUniversities((prev) => prev.map((item) => item.id === semesterForm.university_id ? { ...item, active_semesters: item.active_semesters + 1 } : item));
    setSemesterForm({ id: "", label: "", university_id: "", starts_on: "", ends_on: "" });
  }

  function toggleSemesterStatus(semesterId) {
    setSemesters((prev) => prev.map((item) => {
      if (item.id !== semesterId) return item;
      return { ...item, status: item.status === "active" ? "inactive" : "active" };
    }));
  }

  return (
    <div className="adminShell">
      <header className="adminHeader">
        <div>
          <h1>Admin Dashboard</h1>
          <p>Manage institutions, faculties, semesters, and monitor operational cost/usage insights.</p>
        </div>
        <div className="adminHeaderActions">
          <a href="#/" className="ghostButton">← Student App</a>
        </div>
      </header>

      <nav className="adminTabs">
        {[
          { id: "overview", label: "Overview" },
          { id: "universities", label: "Universities" },
          { id: "faculties", label: "Faculties" },
          { id: "semesters", label: "Semesters" },
        ].map((item) => (
          <button
            key={item.id}
            className={`adminTab ${tab === item.id ? "active" : ""}`}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {tab === "overview" && (
        <section className="adminSection">
          <div className="kpiGrid">
            <article className="kpiCard"><span>Total Universities</span><strong>{universities.length}</strong></article>
            <article className="kpiCard"><span>Active Universities</span><strong>{dashboardMetrics.activeUnis}</strong></article>
            <article className="kpiCard"><span>Active Semesters</span><strong>{dashboardMetrics.activeSemesters}</strong></article>
            <article className="kpiCard"><span>Total Documents</span><strong>{dashboardMetrics.totalDocs}</strong></article>
            <article className="kpiCard"><span>Total Messages</span><strong>{dashboardMetrics.totalMsgs}</strong></article>
            <article className="kpiCard"><span>Estimated API Cost</span><strong>{fmtUsd(dashboardMetrics.totalCost)}</strong></article>
          </div>

          <div className="splitGrid">
            <article className="panel">
              <h3>Cost Breakdown by University</h3>
              <table>
                <thead>
                  <tr>
                    <th>University</th>
                    <th>Cost</th>
                    <th>Share</th>
                  </tr>
                </thead>
                <tbody>
                  {topUniversitiesByCost.map((item) => {
                    const percent = Math.round((item.est_cost_usd / highestCost) * 100);
                    return (
                      <tr key={item.id}>
                        <td>{item.name}</td>
                        <td>{fmtUsd(item.est_cost_usd)}</td>
                        <td>
                          <div className="barWrap">
                            <div className="barFill" style={{ width: `${percent}%` }} />
                            <span>{percent}%</span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </article>

            <article className="panel">
              <h3>Top Courses by Activity</h3>
              <table>
                <thead>
                  <tr>
                    <th>Course</th>
                    <th>University</th>
                    <th>Docs</th>
                    <th>Messages</th>
                  </tr>
                </thead>
                <tbody>
                  {courses.map((item) => (
                    <tr key={item.course_code}>
                      <td>{item.course_code} · {item.course_name}</td>
                      <td>{getUniName(item.university_id)}</td>
                      <td>{item.docs}</td>
                      <td>{item.messages}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </article>
          </div>

          <article className="panel">
            <h3>Recommendations</h3>
            <ul className="recommendations">
              {recommendations.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </article>
        </section>
      )}

      {tab === "universities" && (
        <section className="adminSection">
          <article className="panel">
            <h3>Add Institution</h3>
            <div className="formGrid">
              <input placeholder="University ID (slug)" value={uniForm.id} onChange={(e) => setUniForm((prev) => ({ ...prev, id: e.target.value }))} />
              <input placeholder="University Name" value={uniForm.name} onChange={(e) => setUniForm((prev) => ({ ...prev, name: e.target.value }))} />
              <input placeholder="Contact Email" value={uniForm.contact_email} onChange={(e) => setUniForm((prev) => ({ ...prev, contact_email: e.target.value }))} />
              <button className="primaryButton" onClick={addUniversity}>Add Institution</button>
            </div>
          </article>

          <article className="panel">
            <h3>Institutions</h3>
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>ID</th>
                  <th>Faculties</th>
                  <th>Active Semesters</th>
                  <th>Documents</th>
                  <th>Messages</th>
                  <th>Cost</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {universities.map((item) => (
                  <tr key={item.id}>
                    <td>{item.name}</td>
                    <td>{item.id}</td>
                    <td>{item.faculties_count}</td>
                    <td>{item.active_semesters}</td>
                    <td>{item.docs_ingested}</td>
                    <td>{item.total_messages}</td>
                    <td>{fmtUsd(item.est_cost_usd)}</td>
                    <td><span className={`statusBadge ${item.status}`}>{item.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </article>
        </section>
      )}

      {tab === "faculties" && (
        <section className="adminSection">
          <article className="panel">
            <h3>Add Faculty</h3>
            <div className="formGrid">
              <input placeholder="Faculty ID" value={facultyForm.id} onChange={(e) => setFacultyForm((prev) => ({ ...prev, id: e.target.value }))} />
              <input placeholder="Faculty Name" value={facultyForm.name} onChange={(e) => setFacultyForm((prev) => ({ ...prev, name: e.target.value }))} />
              <select value={facultyForm.university_id} onChange={(e) => setFacultyForm((prev) => ({ ...prev, university_id: e.target.value }))}>
                <option value="">Select University</option>
                {universities.map((item) => (
                  <option key={item.id} value={item.id}>{item.name}</option>
                ))}
              </select>
              <button className="primaryButton" onClick={addFaculty}>Add Faculty</button>
            </div>
          </article>

          <article className="panel">
            <div className="panelTop">
              <h3>Faculties</h3>
              <select value={facultyFilterUni} onChange={(e) => setFacultyFilterUni(e.target.value)}>
                <option value="all">All Universities</option>
                {universities.map((item) => (
                  <option key={item.id} value={item.id}>{item.name}</option>
                ))}
              </select>
            </div>
            <table>
              <thead>
                <tr>
                  <th>Faculty</th>
                  <th>University</th>
                  <th>Courses</th>
                  <th>Docs</th>
                  <th>Chunks</th>
                  <th>Avg Chunks/Doc</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredFaculties.map((item) => {
                  const avg = item.docs_count ? (item.chunks_count / item.docs_count).toFixed(1) : "0.0";
                  return (
                    <tr key={item.id}>
                      <td>{item.name}</td>
                      <td>{getUniName(item.university_id)}</td>
                      <td>{item.courses_count}</td>
                      <td>{item.docs_count}</td>
                      <td>{item.chunks_count}</td>
                      <td>{avg}</td>
                      <td><span className={`statusBadge ${item.status}`}>{item.status}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </article>
        </section>
      )}

      {tab === "semesters" && (
        <section className="adminSection">
          <article className="panel">
            <h3>Add Semester</h3>
            <div className="formGrid">
              <input placeholder="Semester ID" value={semesterForm.id} onChange={(e) => setSemesterForm((prev) => ({ ...prev, id: e.target.value }))} />
              <input placeholder="Label (e.g. 2026 Spring)" value={semesterForm.label} onChange={(e) => setSemesterForm((prev) => ({ ...prev, label: e.target.value }))} />
              <select value={semesterForm.university_id} onChange={(e) => setSemesterForm((prev) => ({ ...prev, university_id: e.target.value }))}>
                <option value="">Select University</option>
                {universities.map((item) => (
                  <option key={item.id} value={item.id}>{item.name}</option>
                ))}
              </select>
              <input type="date" value={semesterForm.starts_on} onChange={(e) => setSemesterForm((prev) => ({ ...prev, starts_on: e.target.value }))} />
              <input type="date" value={semesterForm.ends_on} onChange={(e) => setSemesterForm((prev) => ({ ...prev, ends_on: e.target.value }))} />
              <button className="primaryButton" onClick={addSemester}>Add Semester</button>
            </div>
          </article>

          <article className="panel">
            <h3>Semesters</h3>
            <table>
              <thead>
                <tr>
                  <th>Semester</th>
                  <th>University</th>
                  <th>Start</th>
                  <th>End</th>
                  <th>Docs</th>
                  <th>Messages</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {semesters.map((item) => (
                  <tr key={item.id}>
                    <td>{item.label}</td>
                    <td>{getUniName(item.university_id)}</td>
                    <td>{item.starts_on}</td>
                    <td>{item.ends_on}</td>
                    <td>{item.docs_count}</td>
                    <td>{item.messages_count}</td>
                    <td><span className={`statusBadge ${item.status}`}>{item.status}</span></td>
                    <td>
                      <button className="ghostButton" onClick={() => toggleSemesterStatus(item.id)}>
                        {item.status === "active" ? "Deactivate" : "Activate"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </article>
        </section>
      )}
    </div>
  );
}
