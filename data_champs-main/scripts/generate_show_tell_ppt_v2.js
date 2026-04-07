#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const PptxGenJS = require('pptxgenjs');

const BRAND = {
  navy: '0B2545',
  teal: '0E7490',
  sky: 'E6F4F8',
  slate: '1F2937',
  green: '2E8B57',
  amber: 'D68910',
  red: 'C0392B',
  white: 'FFFFFF',
  gray: '6B7280'
};

function parseCsv(filePath) {
  const text = fs.readFileSync(filePath, 'utf8').trim();
  const lines = text.split(/\r?\n/);
  const headers = lines[0].split(',');
  const rows = [];

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    const values = [];
    let current = '';
    let inQuotes = false;

    for (let j = 0; j < line.length; j++) {
      const ch = line[j];
      if (ch === '"') {
        if (inQuotes && line[j + 1] === '"') {
          current += '"';
          j++;
        } else {
          inQuotes = !inQuotes;
        }
      } else if (ch === ',' && !inQuotes) {
        values.push(current);
        current = '';
      } else {
        current += ch;
      }
    }
    values.push(current);

    const row = {};
    headers.forEach((h, idx) => {
      row[h] = (values[idx] || '').trim();
    });
    rows.push(row);
  }
  return rows;
}

function countBy(rows, key) {
  const out = {};
  rows.forEach((r) => {
    const k = r[key] || 'UNKNOWN';
    out[k] = (out[k] || 0) + 1;
  });
  return out;
}

function addBrandHeader(slide, title) {
  slide.background = { color: BRAND.white };
  slide.addShape('rect', {
    x: 0,
    y: 0,
    w: 13.33,
    h: 0.85,
    fill: { color: BRAND.navy },
    line: { color: BRAND.navy }
  });
  slide.addText(title, {
    x: 0.9,
    y: 0.22,
    w: 9.8,
    h: 0.3,
    fontSize: 16,
    bold: true,
    color: BRAND.white
  });

  // Team badge used as logo substitute when no image logo exists.
  slide.addShape('ellipse', {
    x: 11.65,
    y: 0.11,
    w: 1.45,
    h: 0.62,
    fill: { color: BRAND.teal },
    line: { color: BRAND.teal }
  });
  slide.addText('DC', {
    x: 12.03,
    y: 0.24,
    w: 0.7,
    h: 0.25,
    fontSize: 16,
    bold: true,
    color: BRAND.white,
    align: 'center'
  });
  slide.addText('Data Champs', {
    x: 11.2,
    y: 6.95,
    w: 2.0,
    h: 0.2,
    fontSize: 10,
    color: BRAND.gray,
    align: 'right'
  });
}

function addNotes(slide, notes) {
  slide.addNotes(notes.join('\n'));
}

function addTitleSlide(ppt) {
  const slide = ppt.addSlide();
  slide.background = { color: BRAND.sky };
  addBrandHeader(slide, 'Feasibility Show & Tell');

  slide.addText('Efficient Feasibility Assessment Across 1000+ Raw Tables', {
    x: 0.9,
    y: 1.7,
    w: 11.8,
    h: 1.0,
    fontSize: 34,
    bold: true,
    color: BRAND.navy
  });
  slide.addText('From problem assessment to implemented solution and governance outcomes', {
    x: 0.9,
    y: 2.9,
    w: 11.0,
    h: 0.7,
    fontSize: 18,
    color: BRAND.slate
  });
  slide.addText('Data source: mock_feasibility_sqlite.db | Dictionary: mock_cancer_data_dictionary_50.csv', {
    x: 0.9,
    y: 4.0,
    w: 12.0,
    h: 0.4,
    fontSize: 13,
    color: BRAND.gray
  });

  addNotes(slide, [
    'Open by framing the challenge: fast, trustworthy feasibility at scale.',
    'This deck shows problem, method, results, RBAC context, and concrete next steps.'
  ]);
}

function addBulletsSlide(ppt, title, bullets, notes) {
  const slide = ppt.addSlide();
  addBrandHeader(slide, title);

  slide.addShape('roundRect', {
    x: 0.8,
    y: 1.15,
    w: 11.9,
    h: 5.6,
    fill: { color: 'F8FAFC' },
    line: { color: 'D5DFEA' },
    radius: 0.07
  });

  const runs = bullets.map((b) => ({ text: b, options: { bullet: { indent: 16 }, breakLine: true } }));
  slide.addText(runs, {
    x: 1.1,
    y: 1.55,
    w: 11.3,
    h: 4.9,
    fontSize: 20,
    color: BRAND.slate,
    valign: 'top'
  });

  addNotes(slide, notes);
}

function addFeasibilityMetricsSlide(ppt, total, ragCounts) {
  const slide = ppt.addSlide();
  addBrandHeader(slide, 'Feasibility Results Snapshot');

  const cards = [
    { label: 'TOTAL', value: String(total), color: BRAND.navy },
    { label: 'GREEN', value: String(ragCounts.GREEN || 0), color: BRAND.green },
    { label: 'AMBER', value: String(ragCounts.AMBER || 0), color: BRAND.amber },
    { label: 'RED', value: String(ragCounts.RED || 0), color: BRAND.red }
  ];

  cards.forEach((c, i) => {
    const x = 0.95 + i * 3.06;
    slide.addShape('roundRect', {
      x,
      y: 1.6,
      w: 2.78,
      h: 2.2,
      fill: { color: c.color },
      line: { color: c.color },
      radius: 0.08
    });
    slide.addText(c.value, {
      x: x + 0.1,
      y: 2.1,
      w: 2.58,
      h: 0.7,
      fontSize: 40,
      bold: true,
      color: BRAND.white,
      align: 'center'
    });
    slide.addText(c.label, {
      x: x + 0.1,
      y: 3.0,
      w: 2.58,
      h: 0.3,
      fontSize: 14,
      bold: true,
      color: BRAND.white,
      align: 'center'
    });
  });

  slide.addText('Interpretation: high red rate indicates mapping coverage gaps, not failure of the assessment process.', {
    x: 0.95,
    y: 4.45,
    w: 12.0,
    h: 0.6,
    fontSize: 16,
    color: BRAND.slate
  });

  addNotes(slide, [
    'Emphasize that this baseline is actionable: we now know exactly where to focus remediation.',
    'GREEN and AMBER concepts should move first into downstream data products.'
  ]);
}

function addTopFeasibilityTableSlide(ppt, rows) {
  const slide = ppt.addSlide();
  addBrandHeader(slide, 'Top Feasible Concepts');

  const data = [['ID', 'Concept', 'Mapped Column', 'Score', 'RAG']];
  rows.forEach((r) => {
    data.push([
      r.request_id,
      r.data_point_name,
      `${r.table_name}.${r.column_name}`,
      r.feasibility_score,
      r.rag_score
    ]);
  });

  slide.addTable(data, {
    x: 0.8,
    y: 1.4,
    w: 12.0,
    h: 3.8,
    border: { pt: 1, color: 'C7D2E0', type: 'solid' },
    fontSize: 12,
    color: BRAND.slate,
    fill: BRAND.white
  });

  slide.addText('These are immediate candidates for extraction and early value realization.', {
    x: 0.8,
    y: 5.5,
    w: 12.0,
    h: 0.5,
    fontSize: 16,
    color: BRAND.slate
  });

  addNotes(slide, [
    'Walk through one GREEN and one AMBER example to build confidence in scoring logic.',
    'Invite domain experts to validate semantic correctness of each mapping.'
  ]);
}

function addRbacSummarySlide(ppt, rbacRows) {
  const slide = ppt.addSlide();
  addBrandHeader(slide, 'RBAC Report Summary');

  const accessCounts = countBy(rbacRows, 'access_status');
  const total = rbacRows.length;

  slide.addText('Access Profile from rbac_table_report.csv', {
    x: 0.9,
    y: 1.2,
    w: 8.0,
    h: 0.4,
    fontSize: 20,
    bold: true,
    color: BRAND.navy
  });

  const cardDefs = [
    { key: 'FULL_ACCESS', color: BRAND.green },
    { key: 'ANON_ONLY', color: BRAND.amber },
    { key: 'NO_ACCESS', color: BRAND.red },
    { key: 'BLOCKED', color: BRAND.navy }
  ];

  cardDefs.forEach((c, i) => {
    const x = 0.95 + i * 3.06;
    const value = accessCounts[c.key] || 0;
    slide.addShape('roundRect', {
      x,
      y: 2.0,
      w: 2.78,
      h: 1.7,
      fill: { color: c.color },
      line: { color: c.color },
      radius: 0.08
    });
    slide.addText(String(value), {
      x: x + 0.1,
      y: 2.35,
      w: 2.58,
      h: 0.5,
      fontSize: 30,
      bold: true,
      color: BRAND.white,
      align: 'center'
    });
    slide.addText(c.key, {
      x: x + 0.1,
      y: 3.0,
      w: 2.58,
      h: 0.3,
      fontSize: 12,
      color: BRAND.white,
      align: 'center'
    });
  });

  slide.addText(`RBAC rows analyzed: ${total}`, {
    x: 0.95,
    y: 4.1,
    w: 5.0,
    h: 0.3,
    fontSize: 14,
    color: BRAND.gray
  });

  const suggestion = rbacRows[0] ? rbacRows[0].suggestion : 'No RBAC suggestions available.';
  slide.addText(`Sample governance guidance: ${suggestion}`, {
    x: 0.95,
    y: 4.6,
    w: 12.0,
    h: 1.1,
    fontSize: 15,
    color: BRAND.slate
  });

  addNotes(slide, [
    'RBAC is integrated into delivery planning: feasibility without access is not operationally feasible.',
    'Call out anonymized access as a useful bridge for early analytics and governance-safe prototyping.'
  ]);
}

function addRbacTableSlide(ppt, rbacRows) {
  const slide = ppt.addSlide();
  addBrandHeader(slide, 'RBAC Details (Sample)');

  const data = [['Model', 'Table', 'Rows', 'Pop %', 'Access', 'Top Values (Masked)']];
  rbacRows.slice(0, 6).forEach((r) => {
    data.push([
      r.model_name,
      r.table_name,
      r.row_count,
      r.populated_pct,
      r.access_status,
      (r.top_5_values || '').slice(0, 70)
    ]);
  });

  slide.addTable(data, {
    x: 0.8,
    y: 1.35,
    w: 12.0,
    h: 4.4,
    border: { pt: 1, color: 'C7D2E0', type: 'solid' },
    fontSize: 10,
    color: BRAND.slate,
    fill: BRAND.white
  });

  slide.addText('Included to demonstrate how access constraints shape usable output and handoff decisions.', {
    x: 0.8,
    y: 6.0,
    w: 12.0,
    h: 0.5,
    fontSize: 14,
    color: BRAND.slate
  });

  addNotes(slide, [
    'Use this as evidence that the solution is governance-aware and practical in restricted settings.',
    'If needed, replace with a role-specific RBAC report in future runs.'
  ]);
}

function main() {
  const root = process.cwd();
  const feasPath = path.join(root, 'data/processed/feasibility_assessment.csv');
  const rbacPath = path.join(root, 'data/processed/rbac_table_report.csv');
  const outPath = path.join(root, 'data/processed/show_tell_feasibility_assessment_v2_team_brand.pptx');

  if (!fs.existsSync(feasPath)) {
    throw new Error(`Missing feasibility input: ${feasPath}`);
  }
  if (!fs.existsSync(rbacPath)) {
    throw new Error(`Missing RBAC input: ${rbacPath}`);
  }

  const feasRows = parseCsv(feasPath);
  const rbacRows = parseCsv(rbacPath);
  const rag = countBy(feasRows, 'rag_score');

  const topFeasible = feasRows
    .filter((r) => r.table_name && r.table_name !== '-')
    .sort((a, b) => Number(b.feasibility_score || 0) - Number(a.feasibility_score || 0))
    .slice(0, 5);

  const ppt = new PptxGenJS();
  ppt.layout = 'LAYOUT_WIDE';
  ppt.author = 'Data Champs Team';
  ppt.company = 'Imperial College Healthcare NHS Trust';
  ppt.subject = 'Feasibility and RBAC Show & Tell';
  ppt.title = 'Feasibility Assessment V2 - Team Branded';

  addTitleSlide(ppt);
  addBulletsSlide(
    ppt,
    '1. Problem Assessment',
    [
      'Teams need rapid yes/no/maybe answers for requested clinical data points.',
      'The raw data landscape can span 1000+ tables and evolving schemas.',
      'Manual assessment creates delay, inconsistency, and governance risk.',
      'We need repeatable scoring plus policy-aware output.'
    ],
    [
      'Set context in business terms: speed, trust, and governance.',
      'State the objective: reduce feasibility assessment from weeks to hours.'
    ]
  );

  addBulletsSlide(
    ppt,
    '2. Solution Provided',
    [
      'Automated metadata-first matching against a curated 50-point data dictionary.',
      'Quality metrics sampled per candidate: populated percentage and distinctiveness.',
      'Weighted feasibility score and RAG classification for prioritization.',
      'CSV output generated for immediate analyst and stakeholder use.'
    ],
    [
      'Describe this as a pragmatic first pass that is transparent and auditable.',
      'Highlight why metadata-first is efficient for high-table-count environments.'
    ]
  );

  addFeasibilityMetricsSlide(ppt, feasRows.length, rag);
  addTopFeasibilityTableSlide(ppt, topFeasible);
  addRbacSummarySlide(ppt, rbacRows);
  addRbacTableSlide(ppt, rbacRows);

  addBulletsSlide(
    ppt,
    '3. Recommendations and Next Steps',
    [
      'Prioritize GREEN and AMBER concepts for first extraction releases.',
      'Expand synonym maps and domain hints to improve low-match concept coverage.',
      'Run this pipeline on a schedule and track trend lines over refresh cycles.',
      'Integrate feasibility and RBAC outputs into intake governance workflow.'
    ],
    [
      'Close with a clear call to action: approve phase-2 mapping refinement.',
      'Offer a quick pilot using the top 3 feasible concepts to demonstrate value.'
    ]
  );

  ppt.writeFile({ fileName: outPath })
    .then(() => console.log(`Created presentation: ${outPath}`))
    .catch((err) => {
      console.error(err);
      process.exit(1);
    });
}

main();
