import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const artifactToolRoot = process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES;
if (!artifactToolRoot) throw new Error("CODEX_PRIMARY_RUNTIME_NODE_MODULES is required");
const { Presentation, PresentationFile } = await import(
  pathToFileURL(path.join(artifactToolRoot, "@oai", "artifact-tool", "dist", "artifact_tool.mjs")).href
);

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(ROOT, "brand", "Lightyear-Deck-Template.pptx");
const PREVIEW = path.join(ROOT, "build", "brand-deck");
const ASSETS = path.join(ROOT, "brand", "assets");
const LOGO_SVG = await fs.readFile(path.join(ASSETS, "lightyear-horizontal.svg"), "utf8");
const REVERSED_LOGO_SVG = await fs.readFile(path.join(ASSETS, "lightyear-horizontal-reversed.svg"), "utf8");
const ICON_SVG = await fs.readFile(path.join(ASSETS, "lightyear-icon.svg"), "utf8");

const C = {
  navy: "#15184D",
  violet: "#7D57EA",
  violetDark: "#6942D6",
  bronze: "#A7702C",
  paper: "#FEFEFE",
  lavender: "#EFEBFB",
  lavenderStrong: "#D8CCF8",
  muted: "#676985",
  line: "#DDD7F2",
  green: "#267653",
};

const deck = Presentation.create({ slideSize: { width: 1280, height: 720 } });

function shape(slide, name, position, fill, geometry = "rect", line = "none") {
  return slide.shapes.add({
    geometry,
    name,
    position,
    fill,
    line: { style: "solid", fill: line, width: line === "none" ? 0 : 1 },
  });
}

function text(slide, name, value, position, fontSize, color, options = {}) {
  const item = shape(slide, name, position, "none", "textbox");
  item.text = value;
  item.text.style = {
    fontFamily: options.fontFamily ?? "Arial",
    fontSize,
    color,
    bold: options.bold ?? false,
    alignment: options.alignment ?? "left",
    verticalAlignment: options.verticalAlignment ?? "top",
  };
  return item;
}

function logo(slide, reversed = false, position = { left: 72, top: 44, width: 250, height: 64 }) {
  slide.images.add({
    svg: reversed ? REVERSED_LOGO_SVG : LOGO_SVG,
    alt: "LIGHTYEAR",
    fit: "contain",
    position,
  });
}

function rule(slide, x, y, width, color = C.bronze, thickness = 3) {
  shape(slide, `rule-${x}-${y}`, { left: x, top: y, width, height: thickness }, color);
}

function notes(slide, body) {
  slide.speakerNotes.textFrame.setText(`${body}\n\n[Sources]\n- User-supplied LIGHTYEAR Brand Kit v1.0, Logo System, September 1, 2026.\n[/Sources]`);
  slide.speakerNotes.setVisible(false);
}

// 1 — title
{
  const slide = deck.slides.add();
  slide.background.fill = C.navy;
  logo(slide, true, { left: 72, top: 54, width: 300, height: 80 });
  rule(slide, 78, 176, 92, C.bronze, 4);
  text(slide, "title", "Where context becomes\ntrusted action.", { left: 76, top: 214, width: 880, height: 170 }, 58, C.paper, { bold: true });
  text(slide, "subtitle", "A presentation system for evidence-led modernization decisions.", { left: 80, top: 420, width: 760, height: 72 }, 23, C.lavenderStrong);
  text(slide, "version", "LIGHTYEAR BRAND SYSTEM · VERSION 1.0", { left: 80, top: 616, width: 520, height: 30 }, 13, C.lavenderStrong, { bold: true });
  slide.images.add({ svg: ICON_SVG, alt: "LIGHTYEAR icon", fit: "contain", position: { left: 950, top: 390, width: 250, height: 190 } });
  notes(slide, "Use this opening for executive, investor, or customer presentations. Keep the title short and outcome-led.");
}

// 2 — section opener
{
  const slide = deck.slides.add();
  slide.background.fill = C.paper;
  logo(slide);
  text(slide, "eyebrow", "SECTION OPENER", { left: 76, top: 180, width: 260, height: 28 }, 14, C.bronze, { bold: true });
  text(slide, "title", "A system built for\nreviewable decisions.", { left: 76, top: 228, width: 760, height: 150 }, 52, C.navy, { bold: true });
  text(slide, "body", "Use generous whitespace, a single clear claim, and one signal of emphasis.", { left: 80, top: 418, width: 650, height: 66 }, 22, C.muted);
  shape(slide, "violet-field", { left: 954, top: 0, width: 326, height: 720 }, C.lavender);
  slide.images.add({ svg: ICON_SVG, alt: "LIGHTYEAR icon", fit: "contain", position: { left: 995, top: 235, width: 240, height: 180 } });
  rule(slide, 954, 0, 8, C.violet, 720);
  notes(slide, "Use this layout to establish a new narrative section without adding an agenda slide.");
}

// 3 — narrative principles
{
  const slide = deck.slides.add();
  slide.background.fill = C.paper;
  logo(slide);
  text(slide, "title", "Modernization decisions need evidence, not confidence theater.", { left: 76, top: 142, width: 1040, height: 100 }, 40, C.navy, { bold: true });
  const cols = [
    ["01", "Context", "Keep every workload, dependency, policy, and evidence class in one navigable frame."],
    ["02", "Proof", "Separate asserted mappings, deterministic results, and authorized live observations."],
    ["03", "Action", "Turn evidence into the next bounded decision, owner, gate, or proof run."],
  ];
  cols.forEach(([number, heading, body], index) => {
    const left = 76 + index * 382;
    if (index) shape(slide, `divider-${index}`, { left: left - 34, top: 292, width: 1, height: 240 }, C.line);
    text(slide, `number-${index}`, number, { left, top: 286, width: 90, height: 54 }, 38, C.violet, { bold: true });
    text(slide, `heading-${index}`, heading, { left, top: 352, width: 290, height: 44 }, 26, C.navy, { bold: true });
    text(slide, `body-${index}`, body, { left, top: 412, width: 302, height: 126 }, 19, C.muted);
  });
  rule(slide, 76, 596, 1128, C.bronze, 3);
  text(slide, "footer", "One system. One source of truth. Clear claim boundaries.", { left: 76, top: 615, width: 830, height: 36 }, 18, C.navy, { bold: true });
  notes(slide, "Use this three-part narrative structure for principles, operating model, or strategic pillars.");
}

// 4 — evidence architecture
{
  const slide = deck.slides.add();
  slide.background.fill = C.paper;
  logo(slide);
  text(slide, "title", "Every decision remains attached to its evidence chain.", { left: 76, top: 142, width: 980, height: 82 }, 40, C.navy, { bold: true });
  const items = [
    { x: 86, title: "Sources", body: "Code · schemas · runtime", fill: C.lavender },
    { x: 466, title: "Knowledge Graph", body: "Context · claims · relationships", fill: C.violet, inverse: true },
    { x: 846, title: "Trusted Action", body: "Decision · gate · proof run", fill: C.lavender },
  ];
  items.forEach((item, index) => {
    shape(slide, `stage-${index}`, { left: item.x, top: 310, width: 300, height: 164 }, item.fill, "roundRect", item.inverse ? C.violet : C.line);
    text(slide, `stage-title-${index}`, item.title, { left: item.x + 24, top: 340, width: 252, height: 42 }, 25, item.inverse ? C.paper : C.navy, { bold: true, alignment: "center" });
    text(slide, `stage-body-${index}`, item.body, { left: item.x + 24, top: 402, width: 252, height: 48 }, 16, item.inverse ? C.lavender : C.muted, { alignment: "center" });
    if (index < 2) {
      shape(slide, `connector-${index}`, { left: item.x + 305, top: 389, width: 62, height: 4 }, C.bronze);
      shape(slide, `arrow-${index}`, { left: item.x + 357, top: 380, width: 18, height: 22 }, C.bronze, "triangle");
    }
  });
  text(slide, "caption", "The graph is the connective tissue—not a decorative visualization.", { left: 76, top: 558, width: 900, height: 42 }, 21, C.navy, { bold: true });
  text(slide, "support", "Claims can be traced backward to source and forward to the next controlled action.", { left: 76, top: 606, width: 980, height: 34 }, 17, C.muted);
  notes(slide, "Use this layout to explain a three-stage architecture, operating flow, or decision chain.");
}

// 5 — proof metrics
{
  const slide = deck.slides.add();
  slide.background.fill = C.paper;
  logo(slide);
  text(slide, "title", "The documentation system is governed at portfolio scale.", { left: 76, top: 142, width: 1040, height: 82 }, 40, C.navy, { bold: true });
  const metrics = [
    ["47", "milestones", "A customer-readable brief for every governed milestone."],
    ["141", "artifacts", "Markdown, Word, and PDF generated from one catalog."],
    ["1", "source of truth", "Content hashes detect drift across every published format."],
  ];
  metrics.forEach(([value, label, body], index) => {
    const left = 76 + index * 382;
    text(slide, `metric-${index}`, value, { left, top: 282, width: 300, height: 88 }, 62, C.violet, { bold: true });
    text(slide, `metric-label-${index}`, label.toUpperCase(), { left, top: 378, width: 300, height: 26 }, 14, C.bronze, { bold: true });
    text(slide, `metric-body-${index}`, body, { left, top: 430, width: 310, height: 90 }, 18, C.muted);
    if (index < 2) shape(slide, `metric-divider-${index}`, { left: left + 338, top: 286, width: 1, height: 230 }, C.line);
  });
  shape(slide, "bottom-band", { left: 0, top: 620, width: 1280, height: 100 }, C.navy);
  text(slide, "bottom-copy", "Evidence stays useful because brand, content, and integrity move together.", { left: 76, top: 650, width: 1020, height: 36 }, 22, C.paper, { bold: true });
  notes(slide, "Use large metrics only when the numbers are meaningful and source-backed. The values shown come from the repository milestone manifest.");
}

// 6 — close
{
  const slide = deck.slides.add();
  slide.background.fill = C.navy;
  logo(slide, true, { left: 72, top: 54, width: 300, height: 80 });
  text(slide, "title", "Make the next decision reviewable.", { left: 76, top: 236, width: 980, height: 92 }, 52, C.paper, { bold: true });
  text(slide, "subtitle", "Bring context, evidence, and action into one trusted operating frame.", { left: 80, top: 366, width: 790, height: 70 }, 24, C.lavenderStrong);
  rule(slide, 80, 488, 116, C.bronze, 4);
  text(slide, "tagline", "WHERE CONTEXT BECOMES TRUSTED ACTION.", { left: 80, top: 536, width: 720, height: 34 }, 16, C.lavenderStrong, { bold: true });
  slide.images.add({ svg: ICON_SVG, alt: "LIGHTYEAR icon", fit: "contain", position: { left: 972, top: 408, width: 220, height: 165 } });
  notes(slide, "Close by resolving the opening: the audience should understand the concrete decision or proof run that comes next.");
}

await fs.mkdir(PREVIEW, { recursive: true });
for (const [index, slide] of deck.slides.items.entries()) {
  const stem = `slide-${String(index + 1).padStart(2, "0")}`;
  const png = await deck.export({ slide, format: "png", scale: 1.5 });
  await fs.writeFile(path.join(PREVIEW, `${stem}.png`), new Uint8Array(await png.arrayBuffer()));
  const layout = await slide.export({ format: "layout" });
  await fs.writeFile(path.join(PREVIEW, `${stem}.layout.json`), await layout.text());
}
const montage = await deck.export({ format: "webp", montage: true, scale: 1 });
await fs.writeFile(path.join(PREVIEW, "deck-montage.webp"), new Uint8Array(await montage.arrayBuffer()));
const pptx = await PresentationFile.exportPptx(deck);
await pptx.save(OUT);
await fs.rm(`${OUT}.inspect.ndjson`, { force: true });
console.log(JSON.stringify({ output: OUT, slides: deck.slides.items.length }));
