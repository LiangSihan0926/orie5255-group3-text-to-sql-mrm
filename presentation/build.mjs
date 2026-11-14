import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const root = process.cwd();
const skill = process.env.SLIDE_SKILL_DIR;
const python = process.env.SLIDE_RUNTIME_PYTHON;
const stage = path.resolve(process.env.SLIDE_STAGE ?? ".build/slides");
const finalPath = path.resolve(process.env.SLIDE_OUTPUT ?? "deliverables/Group_3_Topic_2_Presentation.pptx");
const { finalizePresentation } = await import(pathToFileURL(path.join(skill, "container_tools/artifact_tool_utils.mjs")).href);

const evidence = JSON.parse(await fs.readFile(path.join(root, "evidence/validation_results.json"), "utf8"));
const pilot = evidence.pilot;
const replay = evidence.t4_archive_replay;
const expected = evidence.t4_fixtures.expected;
const fixtures = evidence.t4_fixtures.candidates;
const [correctTotal, correctLoans] = evidence.references.numeric_reference.T4[0];
const runtime = pilot.numeric_candidates;
const number = (value) => value.toLocaleString("en-US");
const mean = (value) => value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const ppt = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const W = 1136;
const X = 72;
const C = {
  paper: "#F8FAF9", dark: "#122B38", ink: "#15303D", muted: "#435C65",
  teal: "#10665B", pale: "#DFEEE9", white: "#FFFFFF", alt: "#F0F5F3",
  line: "#C5D6D4", red: "#9B4134", lightText: "#BBD9D4",
};
const font = "Arial";

function text(slide, name, value, left, top, width, height, options = {}) {
  const box = slide.shapes.add({
    name, geometry: "textbox", position: { left, top, width, height },
    fill: "none", line: { fill: "none", width: 0 },
  });
  box.text = value;
  box.text.style = {
    typeface: font, fontSize: options.size ?? 26, bold: options.bold ?? false,
    color: options.color ?? C.ink, insets: 0, alignment: options.align ?? "left",
    verticalAlignment: "middle", wrap: "wrap",
  };
  return box;
}

function page(title, subtitle) {
  const slide = ppt.slides.add();
  slide.background.fill = C.paper;
  text(slide, "slide-title", title, X, 56, W, 65, { size: 49, bold: true });
  if (subtitle) text(slide, "slide-subtitle", subtitle, X, 131, W, 58, { size: 26, color: C.muted });
  return slide;
}

function note(slide, time, body, sources) {
  slide.speakerNotes.text = [time, ...body, "Sources", ...sources].join("\n\n");
}

function table(slide, rows, widths, top, heights, options = {}) {
  const width = widths.reduce((a, b) => a + b, 0);
  const obj = slide.tables.add({
    rows: rows.length, columns: widths.length, left: options.left ?? X, top, width,
    height: heights.reduce((a, b) => a + b, 0), columnWidths: widths, values: rows,
  });
  obj.styleOptions = { headerRow: false, bandedRows: false };
  obj.borders.assign({ style: "solid", fill: C.line, width: 0.75 });
  rows.forEach((row, i) => {
    obj.rows[i].height = heights[i];
    row.forEach((_, j) => {
      const cell = obj.getCell(i, j);
      cell.fill = i === 0 ? C.dark : i % 2 === 0 ? C.alt : C.white;
      cell.text.style = {
        typeface: font, fontSize: i === 0 ? (options.headerSize ?? 21) : (options.size ?? 24),
        bold: i === 0 || j === 0, color: i === 0 ? C.white : C.ink,
        alignment: j > 0 && options.alignNumeric ? "center" : "left",
        verticalAlignment: "middle",
      };
    });
  });
  return obj;
}

function footer(slide, content, top = 634) {
  text(slide, "evidence-caption", content, X, top, W, 42, { size: 19, color: C.muted });
}

const archiveSource = "text2sql_bird.zip · four non-mock OpenAI run CSVs and test_suite_results.csv; offline validation regenerated evidence/validation_results.json.";
const bird = "Li et al. (2023), BIRD. https://bird-bench.github.io/";
const wretblad = "Wretblad et al. (2024), Table 1 and Figure 1. https://aclanthology.org/2024.acl-short.34/";

{
  const slide = ppt.slides.add();
  slide.background.fill = C.dark;
  text(slide, "course", "ORIE 5255 CAPSTONE   /   TOPIC 2", X, 70, W, 36, { size: 20, bold: true, color: C.lightText });
  text(slide, "title", "Validating a Text-to-SQL agent\nfor bank portfolio analytics", X, 170, W, 184, { size: 68, bold: true, color: C.white });
  text(slide, "research-question", "Which financially wrong answers survive successful SQL execution?", X, 392, W, 69, { size: 30, color: C.lightText });
  text(slide, "authors", "Group 3 · Sihan Liang and Minxi Lin", X, 601, W, 42, { size: 23, color: C.white });
  note(slide, "00:00–01:00 · Sihan", [
    "Imagine a bank risk analyst who asks for a loan total and gets back a number and SQL. The query executes, but the answer may refer to a different population. That can change the segment the analyst investigates.",
    "We validate a one-question-at-a-time assistant for historical, read-only aggregates. The analyst makes the investigation decision. The assistant can provide the amount, definition, date basis and SQL, ask a question, or defer. The proposed use excludes lending, pricing, collections and reporting decisions.",
    "We use the BIRD financial database and a small diagnostic study. Our decision concerns this exact workflow and current evidence.",
  ], ["Cornell ORIE 5255 Capstone assignment, Topic 2.", bird]);
}

{
  const slide = page("19 questions on one frozen snapshot", "The team wrote these cases and spot-checked two official BIRD references.");
  table(slide, [
    ["Cases", "Expected action", "Reference"],
    ["3 routine", "Answer", "Counts, sums, averages"],
    ["10 traps", "Answer with stated scope", "Join, timing, weighting and units"],
    ["3 ambiguous", "Ask a specific question", "Different defensible values"],
    ["3 policy", "Deny restricted part", "Grade the allowed aggregate separately"],
  ], [208, 352, 576], 221, [52, 61, 61, 61, 61]);
  footer(slide, "456 records = 19 cases × 2 model labels × 2 prompts × 2 repair settings × 3 repeats", 575);
  note(slide, "01:00–02:10 · Sihan", [
    "The approved dataset has eight tables, 682 loans and 1,056,320 transactions. We designed the 19 questions to cover basic results and high-risk mistakes. Counts and money are independently recomputed in Python from base columns, without using the stored reference query.",
    "We reproduced 16 numerical or permitted-component references and all three sets of ambiguity alternatives. This confirms the arithmetic under the stated definition. The two-person blinded definition review is a separate, pending step.",
    "The baseline supplies schema and source column descriptions. The dictionary adds business definitions and corrections. Repair on enables generic result checks and up to two rewrites. Repeats measure stability on the same questions.",
  ], [archiveSource, bird]);
}

{
  const slide = page("Where the agent can stop", "Proposed control boundary. The pilot implemented N1–N4 in one model call.");
  const lanes = [
    ["N1   Route", "N2   Load context", "N3   Resolve metric", "N4   Draft / repair"],
    ["N5   Check action", "N6   Authorize", "N7   Read-only query", "N8   Reconcile"],
  ];
  lanes.forEach((lane, row) => {
    lane.forEach((label, col) => {
      const left = X + 286 * col;
      text(slide, `node-${row}-${col}`, label, left, 211 + row * 99, 252, 50,
        { size: 23, bold: true, color: row === 0 ? C.ink : C.teal });
      if (col < 3) text(slide, `arrow-${row}-${col}`, "→", left + 244, 211 + row * 99, 36, 50,
        { size: 26, color: C.muted, align: "center" });
    });
  });
  text(slide, "workflow-continuation", "N4 → N5", X + 3, 263, 300, 42, { size: 19, color: C.muted });
  text(slide, "output", "N8 → N9   Answer, clarify, refuse or defer", X, 397, W, 57, { size: 31, bold: true });
  text(slide, "retry", "Recoverable fault → N4   Up to two rewrites under the same metric definition", X, 494, W, 45,
    { size: 23, color: C.muted });
  text(slide, "stop", "Unresolved intent or failed authority → N9   Hold, clarify or refuse", X, 548, W, 45,
    { size: 23, color: C.muted });
  note(slide, "02:10–03:25 · Sihan", [
    "At intake the role and purpose determine whether the request can proceed. The approved context includes the snapshot, schema, codes and metric dictionary. Resolve cohort, grain, date, unit and measure before drafting. A missing material field ends the run with a question.",
    "N5 checks action and syntax. N6 checks authority and financial meaning before the database. N7 only reads permitted aggregates with a deadline and row cap. N8 checks the result against the approved contract, and N9 renders it or holds it.",
    "Only eligible recoverable faults can enter N4 again. The gate for a mixed request starts with an independently authorized aggregate. Denied actions and unknown permissions stop. The pilot had weaker checks and no separate stage traces for N1–N4.",
  ], ["Report §3, Figure 1 and appendix matrices.", "Cornell ORIE 5255 Class 8 and Class 9 slides."]);
}

{
  const slide = page("T4 · A successful execution, a wrong total", "Sum approved amounts for loans on accounts with at least one card withdrawal.");
  text(slide, "archived-result", "111,981,565,824", X, 220, 585, 86, { size: 62, bold: true, color: C.red });
  text(slide, "independent-result", number(correctTotal), 720, 220, 480, 86, { size: 62, bold: true, color: C.teal });
  text(slide, "archive-label", "Runtime-clean answer", X, 313, 565, 43, { size: 24, color: C.muted });
  text(slide, "correct-label", `Independent total across ${correctLoans} loans`, 720, 313, 490, 43, { size: 24, color: C.muted });
  text(slide, "trace", "Missing column → rewrite substitutes card holding → faulty join multiplies loans", X, 437, W, 79,
    { size: 29, bold: true });
  footer(slide, "Source units. GPT-4o mini, dictionary + repair, repeat 2.", 587);
  note(slide, "03:25–04:50 · Sihan", [
    "T4's eligibility event is a withdrawal. Once an account qualifies, count each of its loans once. The model received a missing-column error. The saved rewrite used card holding as a proxy for withdrawal and used a join condition that compared a field with itself.",
    "The final amount ran and passed the archived generic checks. The independent scan starts with withdrawal events, creates an eligible account set and sums loans once. It finds 148 qualifying loans. A simple direct event join with the right event type still inflates the result to 124,697,580 across 965 joined rows.",
    "The trace gives one concrete material misstatement. We have the final SQL and first error message. We cannot reconstruct the first candidate or claim an analyst saw it.",
  ], [archiveSource, "Report §4 and evidence/reference_comparison.csv."]);
}

{
  const slide = page("Clean execution is a weak release test", "Strict automatic passes on 10 traps × 3 repeats per configuration.");
  const cells = [["Prompt / repair", "GPT-4.1", "GPT-4o mini"]];
  for (const [prompt, label, repair] of [
    ["baseline", "Baseline", "off"], ["dict", "Dictionary", "off"],
    ["baseline", "Baseline", "on"], ["dict", "Dictionary", "on"],
  ]) {
    const values = ["gpt-4.1", "gpt-4o-mini"].map((model) =>
      pilot.cells.find((r) => r.model === model && r.prompt === prompt && r.repair === repair && r.group === "T"),
    );
    cells.push([`${label} / ${repair}`, ...values.map((r) => `${r.strict_pass}/${r.total}`)]);
  }
  table(slide, cells, [301, 170, 180], 221, [58, 58, 58, 58, 58], { alignNumeric: true });
  text(slide, "mismatch-ratio", `${runtime.key_result_mismatch_among_runtime_clean} / ${runtime.action_answer_and_runtime_clean}`, 780, 243, 423, 95,
    { size: 65, bold: true, color: C.red });
  text(slide, "mismatch-description", "Runtime-clean routine or trap answers that differ from the archive’s key result", 780, 353, 411, 119,
    { size: 26, color: C.muted });
  footer(slide, "18 records require definition review. The mismatch count is a screening statistic.", 571);
  note(slide, "04:50–06:10 · Sihan", [
    "Dictionary results improved under both model labels in these cases. GPT-4.1 gets nine baseline and 18 dictionary passes; GPT-4o mini gets zero baseline and five or nine with the dictionary. These settings are bundled, so we cannot isolate an effect of repair or check quality.",
    "There were 312 routine/trap runs. Of 227 runtime-clean answer candidates, 84 mismatched the archived key-result rule. Some are alternate definitions or grader disagreements. Materiality requires independent business adjudication.",
    "Only six of 72 ambiguity cases passed the action check. The 36 repair-enabled policy action passes included 24 with no SQL, and just seven of 12 with SQL matched the permitted result. The T6 positive repair returned 247 scheduled contracts after two all-zero flags. Minxi will cover reference risk and the controls.",
  ], [archiveSource, "Report §§4–6; evidence/pilot_cells.csv."]);
}

{
  const slide = page("The benchmark reference can be wrong", "Q132 asks for the average approved loan amount of male borrowers.");
  const i = evidence.references.illustrations;
  table(slide, [
    ["Interpretation", "Observations", "Mean (source units)"],
    ["All male account links", number(i.Q132_all_authorized_links.rows), mean(i.Q132_all_authorized_links.average)],
    ["Male account owners", number(i.Q132_account_owners_only.rows), mean(i.Q132_account_owners_only.average)],
  ], [500, 263, 373], 224, [56, 68, 68], { alignNumeric: true });
  text(slide, "source-result", "Wretblad et al. identified 52 noisy items out of 106 in their release.", X, 467, W, 53, { size: 28, bold: true });
  text(slide, "second-spot-check", "Q169 explicitly uses male owners. Independently recomputed growth is 25.30%.", X, 531, W, 63,
    { size: 24, color: C.muted });
  note(slide, "06:10–07:10 · Minxi", [
    "The Wretblad result is from their release. It includes 22 erroneous SQL references. We independently spot-check two official items in the archive, separate from the model experiment. In Q132 the archived reference includes authorized clients as well as owners. That changes the mean when borrower means owner.",
    "Our archive version differs from the district-join example in their Figure 1. For Q169, a growth comparison, the archived query specifies owners. We computed each year from raw rows and compared the contract to the archived SQL.",
    "Our own benchmark has the same vulnerability. T7's weights and T8's loss definition need review. Agreement under a fixed definition is evidence, and selecting the definition is a separate business step.",
  ], [wretblad, bird, "Report §7; evidence/validation_results.json."]);
}

{
  const slide = page("Control 1 · Preserve intent across repair", "T4 contract fixes the qualifying event, loan grain, amount and unit.");
  const counts = (key) => [
    replay.filter((r) => r[key] && r.matched_key_result).length,
    replay.filter((r) => r[key] && !r.matched_key_result).length,
  ];
  const base = counts("base_release_proxy");
  const gate = counts("gated_release_proxy");
  table(slide, [
    ["T4 final candidate", "Runtime checks", "+ Template gate"],
    ["Matching answer", ...[base[0], gate[0]].map(String)],
    ["Mismatched answer", ...[base[1], gate[1]].map(String)],
    ["Held", ...[replay.length - base[0] - base[1], replay.length - gate[0] - gate[1]].map(String)],
  ], [440, 348, 348], 220, [59, 63, 63, 63], { alignNumeric: true });
  text(slide, "gate-tradeoff", "The same gate deferred two correct SQL forms in the synthetic test.", X, 514, W, 51,
    { size: 27, bold: true, color: C.teal });
  footer(slide, "Retrospective replay of 12 saved repair-enabled T4 records.", 603);
  note(slide, "07:10–08:20 · Minxi", [
    "Resolve the contract before drafting. A repair can change the syntax but cannot silently turn a withdrawal cohort into a cardholder cohort. The implemented demonstration recognizes two vetted SQL shapes for T4. It fingerprints saved text without running it.",
    "The same 12 final candidates are evaluated with and without the gate. Runtime checks alone would hold one, allow six matches and allow five mismatches. The added gate would retain the six matches and hold all five mismatches.",
    "The retrospective replay does not give a new model performance estimate. The synthetic test includes equivalent forms the gate defers. A narrow registry with typed compilation is an appropriate extension; an incorrect initial interpretation still needs clarification or independent review.",
  ], ["evidence/t4_archive_replay.csv and validation/controls.py.", "Pourreza & Rafiei, DIN-SQL. https://arxiv.org/abs/2304.11015"]);
}

{
  const slide = page("Control 2 · Change a record, predict the effect", "A has a 100-unit loan and a qualifying withdrawal. B has a 200-unit loan.");
  const names = {
    transaction_fanout: "Direct event join", constant_answer: "Constant answer",
    dedup_by_amount: "Deduplicate amount",
  };
  const display = (m) => [m.base, m.extra_event_A, m.first_event_B, m.same_amount_C].map(String);
  table(slide, [
    ["Candidate", "Base", "Another event on A", "First event on B", "Same amount on C"],
    ["Expected total", ...display(expected)],
    ...fixtures.filter((r) => names[r.candidate]).map((r) => [names[r.candidate], ...display(r.amounts)]),
  ], [306, 126, 237, 222, 245], 218, [60, 60, 60, 60, 60],
  { alignNumeric: true, headerSize: 20, size: 23 });
  footer(slide, "All four correct forms pass. Three of five faulty forms match the base alone.", 572);
  note(slide, "08:20–09:35 · Minxi", [
    "One correct number is weak evidence about the calculation. In the base scenario only A qualifies, so the answer is 100. Adding another event on A does not create a loan. Giving B its first withdrawal should increase the total by 200.",
    "The direct join and constant both pass the base but fail the event variants. Distinct amount also passes those variants, so add a different eligible loan with the same amount as A; that amount must count separately.",
    "We tested nine constructed candidates. All four correct forms pass all fixtures. The five incorrect forms include two additional errors that already fail the base. These are metric-specific deterministic checks for template validation, with remaining gaps around untested cases and shared source assumptions.",
  ], ["validation/controls.py; evidence/validation_results.json.", "Zhong et al. (2020). https://aclanthology.org/2020.emnlp-main.29/", "Chen et al. (2018). https://doi.org/10.1145/3143561"]);
}

{
  const slide = page("Monitor the system and review the outcomes", "Operational signals explain execution. Independent samples assess financial correctness.");
  table(slide, [
    ["Evidence", "Example trigger", "Owner response"],
    ["Live · Schema / policy version", "Unknown version", "Data owner holds route"],
    ["Live · Attempts / resource limits", "More than two rewrites", "App owner stops candidate"],
    ["Reviewed · Financial result", "One material wrong release", "Risk owner pauses metric"],
    ["Reviewed · Data access", "One restricted disclosure", "Security suspends access"],
  ], [397, 341, 398], 223, [53, 66, 66, 66, 66], { size: 22 });
  footer(slide, "Review every shadow result; revalidate changes to model, schema, definitions or access.", 587);
  note(slide, "09:35–10:50 · Minxi", [
    "A live trace should identify the snapshot, catalog, prompt, model, authority, attempt count, timing and exit reason. These metrics diagnose behavior, not business correctness. Use a separate review to recompute the answer, inspect materiality and record what the analyst would do.",
    "Any unknown version holds the route. Two rewrites is the maximum, with bounded read-only execution. One material wrong release or restricted disclosure pauses the affected route. The risk or security owner investigates, and an independent validator challenges the fix before restart.",
    "A future shadow trial would use 100% human review. With separate approval to expand, sample every alert, each changed metric and a routine stratified weekly sample. Track coverage and reviewer time alongside incidents.",
  ], ["Report §§10–11; Appendix C.", "NIST AI 600-1. https://doi.org/10.6028/NIST.AI.600-1"]);
}

{
  const slide = ppt.slides.add();
  slide.background.fill = C.dark;
  text(slide, "decision", "Reject automatic release", X, 93, W, 103, { size: 66, bold: true, color: C.white });
  text(slide, "decision-scope", "For internal portfolio-risk triage on the evaluated configuration", X, 214, W, 64,
    { size: 28, color: C.lightText });
  text(slide, "trial-title", "Evidence required before considering a shadow trial", X, 332, W, 61,
    { size: 31, bold: true, color: C.white });
  text(slide, "trial-conditions", "Vetted metric templates and verified access control\nFresh blinded holdout with zero severe releases or disclosures\nIndependent review of every shadow result and tracked review time",
    X, 418, W, 152, { size: 26, color: C.lightText });
  note(slide, "10:50–12:00 · Minxi", [
    "Reject automatic use for the defined workflow. A material T4 candidate survived clean execution, clarification and policy utility were weak, and the two controls were tested only in bounded offline examples.",
    "A future shadow trial is a distinct decision. Require signed business definitions, verified scoped access, vetted compilation, fresh blinded holdout and explicit fail-safe behavior. Proposed trial gates include zero severe releases and disclosures, at least 90% correct fully disclosed answers among answerable shadow cases, and no more than ten analyst minutes on average over 30 answerable requests.",
    "An analyst must be able to hold every output before it influences investigation. The repo provides the original evidence and reproducible check; independent human signatures and operational access tests are outstanding. We welcome questions.",
  ], ["Report §12 and docs/evaluation_protocol.md.", "NIST AI RMF. https://doi.org/10.6028/NIST.AI.100-1", "SR 26-2 footnote 3 excludes generative and agentic AI. https://www.federalreserve.gov/supervisionreg/srletters/sr2602.htm"]);
}

{
  const slide = page("Discussion · Evidence and limits", "Use as a reference for questions after the 12-minute presentation.");
  table(slide, [
    ["Question", "Evidence"],
    ["Why 19 and 106?", "19 team-written cases test the agent. Two of 106 official items check benchmark references."],
    ["What did we verify independently?", "All numerical results and ambiguity alternatives under explicit definitions."],
    ["How do we count success?", "Correct per answerable request. Material wrong releases per eligible request and per release."],
    ["What still needs review?", "Blinded business labels, verified access controls, held-out results and reviewer sign-off."],
  ], [390, 746], 213, [56, 79, 79, 79, 79], { size: 22 });
  note(slide, "Backup · Q&A", [
    "If asked about false positives, compare two correct forms deferred by the template gate with four correct forms passing all fixtures. If asked about the 84 mismatches, distinguish comparator differences from material confirmed errors. If asked what a refusal pass means, discuss the 24/36 without SQL and the five numeric misses.",
    "For reproducibility, run python3 -B -m validation.run from the repository. The data checksum is pinned and model calls are unnecessary.",
  ], ["README.md, docs/evaluation_protocol.md and report Appendix D."]);
}

await fs.mkdir(stage, { recursive: true });
await fs.mkdir(path.dirname(finalPath), { recursive: true });
const candidatePath = path.join(stage, "candidate.pptx");
await (await PresentationFile.exportPptx(ppt)).save(candidatePath);
const nativeTables = [2, 5, 6, 7, 8, 9, 11];
const result = await finalizePresentation({
  workspaceDir: root,
  candidatePath,
  finalPath,
  pythonExecutable: python,
  integrityValidatorPath: path.join(skill, "container_tools/inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(skill, "container_tools/inspect_presentation_layout_geometry.py"),
  layoutArgs: [
    "--expected-slide-size-emu", "12192000,6858000", "--validate-heading-fit",
    ...nativeTables.flatMap((index) => ["--require-native-table-slide", String(index)]),
  ],
  explicitTotalSlideCount: 11,
  requiredNativeTableOwnerSlides: nativeTables,
  fontPolicy: { basis: "design", families: [font] },
  verifyArtifactToolImport: true,
  receiptPath: path.join(stage, "validation.json"),
});
console.log(result.finalPath ?? finalPath);
