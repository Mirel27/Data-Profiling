#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const PptxGenJS = require('pptxgenjs');

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
        inQuotes = !inQuotes;
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
  const counts = {};
  for (const row of rows) {
    const v = row[key] || 'UNKNOWN';
    counts[v] = (counts[v] || 0) + 1;
  }
  return counts;
}

function addTitleSlide(ppt, title, subtitle) {
  const slide = ppt.addSlide();
  slide.background = { color: 'F3F7FB' };
  slide.addShape(ppt.ShapeType.rect, { x: 0, y: 0, w: 13.33, h: 1.0, fill: { color: '1F4E79' }, line: { color: '1F4E79' } });
  slide.addText(title, { x: 0.7, y: 1.6, w: 12.0, h: 1.1, fontSize: 34, bold: true, color: '1F4E79' });
  slide.addText(subtitle, { x: 0.7, y: 2.8, w: 11.8, h: 1.2, fontSize: 18, color: '2F3A45' });
  slide.addText('Data Champs | Feasibility Show & Tell', { x: 0.7, y: 6.8, w: 6.0, h: 0.4, fontSize: 12, color: '6E7781' });
}

function addSectionSlide(ppt, title, bullets) {
  const slide = ppt.addSlide();
  slide.background = { color: 'FFFFFF' };
  slide.addShape(ppt.ShapeType.roundRect, { x: 0.6, y: 0.5, w: 12.1, h: 0.8, fill: { color: '1F4E79' }, line: { color: '1F4E79' }, radius: 0.07 });
  slide.addText(title, { x: 0.9, y: 0.72, w: 11.4, h: 0.4, fontSize: 22, bold: true, color: 'FFFFFF' });

  const bulletRuns = bullets.map((b) => ({ text: b, options: { bullet: { indent: 16 }, breakLine: true } }));
  slide.addText(bulletRuns, { x: 0.9, y: 1.7, w: 11.7, h: 5.2, fontSize: 20, color: '1E2A35', valign: 'top' });
}

function addMetricsSlide(ppt, total, green, amber, red) {
  const slide = ppt.addSlide();
  slide.background = { color: 'FFFFFF' };
  slide.addText('Current Feasibility Snapshot', { x: 0.7, y: 0.5, w: 8.0, h: 0.6, fontSize: 28, bold: true, color: '1F4E79' });

  const cards = [
    { label: 'Total Data Points', value: String(total), color: '2F5597' },
    { label: 'GREEN', value: String(green), color: '2E8B57' },
    { label: 'AMBER', value: String(amber), color: 'D68910' },
    { label: 'RED', value: String(red), color: 'C0392B' }
  ];

  cards.forEach((card, idx) => {
    const x = 0.8 + idx * 3.1;
    slide.addShape(ppt.ShapeType.roundRect, {
      x,
      y: 1.6,
      w: 2.8,
      h: 2.0,
      fill: { color: card.color },
      line: { color: card.color },
      radius: 0.08
    });
    slide.addText(card.value, { x: x + 0.1, y: 2.0, w: 2.6, h: 0.7, fontSize: 40, bold: true, color: 'FFFFFF', align: 'center' });
    slide.addText(card.label, { x: x + 0.1, y: 2.9, w: 2.6, h: 0.4, fontSize: 14, color: 'FFFFFF', align: 'center' });
  });

  slide.addText('Result from mock_feasibility_sqlite.db with mock_cancer_data_dictionary_50.csv', {
    x: 0.8, y: 4.2, w: 12.0, h: 0.6, fontSize: 14, color: '495057'
  });

  slide.addText('Key insight: only 3/50 concepts currently map cleanly. This quantifies the gap and guides extraction priorities.', {
    x: 0.8, y: 5.0, w: 12.0, h: 1.0, fontSize: 18, color: '1E2A35'
  });
}

function addTopMatchesSlide(ppt, topRows) {
  const slide = ppt.addSlide();
  slide.addText('Top Feasible Matches', { x: 0.7, y: 0.5, w: 10.0, h: 0.6, fontSize: 28, bold: true, color: '1F4E79' });

  const rows = [['ID', 'Data Point', 'Mapped Table.Column', 'Score', 'RAG']];
  topRows.forEach((r) => {
    rows.push([
      r.request_id,
      r.data_point_name,
      `${r.table_name}.${r.column_name}`,
      r.feasibility_score,
      r.rag_score
    ]);
  });

  slide.addTable(rows, {
    x: 0.7,
    y: 1.4,
    w: 12.0,
    h: 3.5,
    border: { type: 'solid', color: 'D0D7DE', pt: 1 },
    fill: 'FFFFFF',
    fontSize: 13,
    color: '1E2A35'
  });

  slide.addText('These are immediate candidates for dashboards, cohorts, and downstream analytics.', {
    x: 0.7, y: 5.4, w: 12.0, h: 0.6, fontSize: 16, color: '2F3A45'
  });
}

function main() {
  const repoRoot = process.cwd();
  const csvPath = path.join(repoRoot, 'data/processed/feasibility_assessment.csv');
  const outPath = path.join(repoRoot, 'data/processed/show_tell_feasibility_assessment.pptx');

  if (!fs.existsSync(csvPath)) {
    throw new Error(`Input CSV not found: ${csvPath}`);
  }

  const rows = parseCsv(csvPath);
  const rag = countBy(rows, 'rag_score');

  const topRows = rows
    .filter((r) => r.table_name && r.table_name !== '-')
    .sort((a, b) => Number(b.feasibility_score || 0) - Number(a.feasibility_score || 0))
    .slice(0, 5);

  const ppt = new PptxGenJS();
  ppt.layout = 'LAYOUT_WIDE';
  ppt.author = 'Data Champs';
  ppt.company = 'Imperial College Healthcare NHS Trust';
  ppt.subject = 'Feasibility Assessment Show & Tell';
  ppt.title = 'Feasibility Assessment - Problem to Solution';

  addTitleSlide(
    ppt,
    'Efficient Feasibility Assessment Across 1000+ Raw Tables',
    'Show & Tell: From problem assessment to delivered solution'
  );

  addSectionSlide(ppt, '1. Problem Assessment', [
    'Research teams need fast answers: Is each requested data point available and usable?',
    'Raw environment can include 1000+ tables with varied naming and quality.',
    'Manual discovery is slow, inconsistent, and hard to govern at scale.',
    'Need: repeatable, auditable feasibility scoring with clear RAG outputs.'
  ]);

  addSectionSlide(ppt, '2. Constraints and Risks', [
    'Heterogeneous schemas across domains (cancer, pathology, secondary care).',
    'Data completeness differs significantly column-to-column.',
    'Access governance (RBAC) and policy restrictions must be respected.',
    'Scalability requirement: metadata-first approach to avoid expensive full scans.'
  ]);

  addSectionSlide(ppt, '3. Solution Implemented', [
    'Input data dictionary: mock_cancer_data_dictionary_50.csv (50 requested points).',
    'Target source: mock_feasibility_sqlite.db (100 mock raw tables).',
    'Automated matching: metadata similarity of requested concepts to schema columns.',
    'Feasibility score = 45% metadata match + 40% populated % + 15% distinctiveness.',
    'Output artifact: feasibility_assessment.csv for transparent review.'
  ]);

  addSectionSlide(ppt, '4. Execution Workflow', [
    'Step 1: Read data dictionary concepts and priorities.',
    'Step 2: Discover all table/column metadata from the SQLite database.',
    'Step 3: Match candidate columns per concept and sample quality statistics.',
    'Step 4: Compute weighted score and assign RAG recommendation.',
    'Step 5: Export CSV for analyst and stakeholder review.'
  ]);

  addMetricsSlide(
    ppt,
    rows.length,
    rag.GREEN || 0,
    rag.AMBER || 0,
    rag.RED || 0
  );

  addTopMatchesSlide(ppt, topRows);

  addSectionSlide(ppt, '6. What This Tells Us', [
    'Immediate value: objective baseline of what is feasible today.',
    'Only a small subset is currently GREEN/AMBER, exposing schema alignment gaps.',
    'Result can drive targeted mapping and model enrichment instead of broad rework.',
    'This approach scales to larger estates by keeping discovery metadata-first.'
  ]);

  addSectionSlide(ppt, '7. Next Steps', [
    'Improve dictionary-to-schema synonym mappings for low-match concepts.',
    'Add table-level domain hints to reduce false negatives.',
    'Introduce multi-candidate ranking per concept (top 3) for clinical validation.',
    'Automate recurring run and trend reporting across refresh cycles.'
  ]);

  const today = new Date().toISOString().slice(0, 10);
  addSectionSlide(ppt, '8. Outcome and Deliverables', [
    `Deliverable 1: CSV feasibility output generated (${today}).`,
    'Deliverable 2: Reusable scoring script for repeatable assessments.',
    'Deliverable 3: This show-and-tell deck for stakeholders.',
    'Decision support: prioritize extraction for GREEN/AMBER items first.'
  ]);

  ppt.writeFile({ fileName: outPath }).then(() => {
    console.log(`Created presentation: ${outPath}`);
  }).catch((err) => {
    console.error(err);
    process.exit(1);
  });
}

main();
