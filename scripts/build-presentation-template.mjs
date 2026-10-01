// Mini LLM – powered by AI-Implements · C. Lins
// Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
// Dieser Code darf frei verwendet, verändert und erweitert werden.
// Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const moduleSpecifier = process.env.ARTIFACT_TOOL_MODULE || "@oai/artifact-tool";
const { Presentation, PresentationFile } = await import(
  moduleSpecifier.startsWith("/") ? pathToFileURL(moduleSpecifier).href : moduleSpecifier
);

const outputPath = process.argv[2];
if (!outputPath) {
  throw new Error("Ausgabepfad für die PPTX-Vorlage fehlt.");
}

const deck = Presentation.create({
  slideSize: { width: 1280, height: 720 },
});

const palette = {
  canvas: "#F7F9FC",
  paper: "#FFFFFF",
  navy: "#102A43",
  blue: "#377CF6",
  blueSoft: "#EAF1FF",
  text: "#18324A",
  muted: "#66788A",
  line: "#CFD9E4",
};

function addText(slide, name, text, position, fontSize, options = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    name,
    position,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = text;
  shape.text.style = {
    fontSize,
    fontFamily: "Aptos",
    color: options.color || palette.text,
    bold: options.bold || false,
    alignment: options.alignment || "left",
    verticalAlignment: options.verticalAlignment || "middle",
  };
  return shape;
}

function addFrame(slide, slideNumber, options = {}) {
  const paper = options.paper || palette.paper;
  const accent = options.accent || palette.blue;
  const brandColor = options.brandColor || palette.blue;
  const numberColor = options.numberColor || palette.muted;
  slide.background.fill = palette.canvas;
  slide.shapes.add({
    geometry: "roundRect",
    name: "minimal-frame",
    position: { left: 28, top: 28, width: 1224, height: 664 },
    fill: paper,
    line: { style: "solid", fill: palette.line, width: 1.2 },
    borderRadius: "rounded-xl",
  });
  slide.shapes.add({
    geometry: "rect",
    name: "accent-line",
    position: { left: 28, top: 28, width: 10, height: 664 },
    fill: accent,
    line: { style: "solid", fill: accent, width: 0 },
  });
  addText(
    slide,
    "brand-label",
    "MINI LLM",
    { left: 72, top: 54, width: 180, height: 28 },
    13,
    { color: brandColor, bold: true },
  );
  addText(
    slide,
    "slide-number",
    String(slideNumber).padStart(2, "0"),
    { left: 1134, top: 644, width: 66, height: 24 },
    13,
    { color: numberColor, alignment: "right" },
  );
}

function addBullet(slide, index, left, top, width, options = {}) {
  slide.shapes.add({
    geometry: "roundRect",
    name: `bullet-dot-${index}`,
    position: { left, top: top + 17, width: 11, height: 11 },
    fill: palette.blue,
    line: { style: "solid", fill: palette.blue, width: 0 },
    borderRadius: "rounded-full",
  });
  addText(
    slide,
    `bullet-${index}`,
    `Inhalt ${index}`,
    { left: left + 28, top, width: width - 28, height: 66 },
    options.fontSize || 21,
    { color: palette.text, bold: options.bold || false },
  );
}

function addSlideHeader(slide, number) {
  addText(
    slide,
    "slide-kicker",
    "KERNAUSSAGE",
    { left: 72, top: 94, width: 300, height: 24 },
    13,
    { color: palette.blue, bold: true },
  );
  addText(
    slide,
    "slide-title",
    "Eine klare Aussage pro Folie",
    { left: 72, top: 120, width: 1080, height: 82 },
    38,
    { color: palette.navy, bold: true },
  );
  addText(
    slide,
    "slide-index",
    String(number).padStart(2, "0"),
    { left: 1144, top: 95, width: 56, height: 24 },
    13,
    { color: palette.muted, alignment: "right" },
  );
}

const titleSlide = deck.slides.add();
addFrame(titleSlide, 1);
titleSlide.shapes.add({
  geometry: "rect",
  name: "title-accent",
  position: { left: 72, top: 175, width: 72, height: 7 },
  fill: palette.blue,
  line: { style: "solid", fill: palette.blue, width: 0 },
});
addText(
  titleSlide,
  "deck-kicker",
  "PRÄSENTATION",
  { left: 72, top: 116, width: 360, height: 32 },
  15,
  { color: palette.blue, bold: true },
);
addText(
  titleSlide,
  "deck-title",
  "Titel der Präsentation",
  { left: 72, top: 196, width: 1035, height: 248 },
  54,
  { color: palette.navy, bold: true },
);
addText(
  titleSlide,
  "deck-subtitle",
  "Klarer Untertitel oder Anlass",
  { left: 72, top: 464, width: 940, height: 72 },
  25,
  { color: palette.muted },
);
addText(
  titleSlide,
  "deck-date",
  "Erstellt mit Mini LLM",
  { left: 900, top: 592, width: 280, height: 32 },
  16,
  { color: palette.muted, alignment: "right" },
);
addText(
  titleSlide,
  "deck-author-label",
  "ERSTELLT VON",
  { left: 72, top: 570, width: 150, height: 24 },
  11,
  { color: palette.blue, bold: true },
);
addText(
  titleSlide,
  "deck-author",
  "BEISPIEL GMBH",
  { left: 72, top: 592, width: 520, height: 32 },
  18,
  { color: palette.navy, bold: true },
);

for (let slideNumber = 2; slideNumber <= 6; slideNumber += 1) {
  const slide = deck.slides.add();
  addFrame(slide, slideNumber);
  addSlideHeader(slide, slideNumber - 1);
  const highlighted = slideNumber === 3 || slideNumber === 5;
  if (highlighted) {
    slide.shapes.add({
      geometry: "roundRect",
      name: "lead-frame",
      position: { left: 72, top: 216, width: 1110, height: 94 },
      fill: palette.blueSoft,
      line: { style: "solid", fill: "#D8E5FF", width: 1 },
      borderRadius: "rounded-xl",
    });
    addBullet(slide, 1, 96, 230, 1042, { fontSize: 23, bold: true });
    for (let index = 2; index <= 5; index += 1) {
      addBullet(slide, index, 88, 333 + ((index - 2) * 78), 1060);
    }
  } else {
    for (let index = 1; index <= 5; index += 1) {
      addBullet(slide, index, 88, 222 + ((index - 1) * 80), 1060);
    }
  }
}

for (let slideNumber = 7; slideNumber <= 11; slideNumber += 1) {
  const slide = deck.slides.add();
  addFrame(slide, slideNumber);
  addSlideHeader(slide, slideNumber - 1);
  for (let index = 1; index <= 5; index += 1) {
    addBullet(slide, index, 88, 222 + ((index - 1) * 82), 520);
  }
  slide.shapes.add({
    geometry: "roundRect",
    name: "chart-frame",
    position: { left: 655, top: 222, width: 530, height: 354 },
    fill: "#F5F8FC",
    line: { style: "solid", fill: palette.line, width: 1 },
    borderRadius: "rounded-xl",
  });
  addText(
    slide,
    "chart-title",
    "Zahlen im Überblick",
    { left: 686, top: 243, width: 450, height: 34 },
    18,
    { color: palette.navy, bold: true },
  );
  for (let index = 1; index <= 5; index += 1) {
    const rowTop = 293 + ((index - 1) * 52);
    addText(
      slide,
      `chart-label-${index}`,
      `Wert ${index}`,
      { left: 686, top: rowTop - 6, width: 155, height: 40 },
      14,
      { color: palette.muted },
    );
    slide.shapes.add({
      geometry: "roundRect",
      name: `chart-track-${index}`,
      position: { left: 846, top: rowTop + 4, width: 210, height: 18 },
      fill: "#DEE7F1",
      line: { style: "solid", fill: "#DEE7F1", width: 0 },
      borderRadius: "rounded-full",
    });
    slide.shapes.add({
      geometry: "roundRect",
      name: `chart-bar-${index}`,
      position: { left: 846, top: rowTop + 4, width: 140, height: 18 },
      fill: palette.blue,
      line: { style: "solid", fill: palette.blue, width: 0 },
      borderRadius: "rounded-full",
    });
    addText(
      slide,
      `chart-value-${index}`,
      `${index * 10}%`,
      { left: 1068, top: rowTop, width: 88, height: 28 },
      15,
      { color: palette.navy, bold: true, alignment: "right" },
    );
  }
  addText(
    slide,
    "metric-big-value",
    "42 %",
    { left: 700, top: 326, width: 430, height: 104 },
    64,
    { color: palette.blue, bold: true, alignment: "center" },
  );
  addText(
    slide,
    "metric-big-label",
    "Zentrale Kennzahl",
    { left: 700, top: 428, width: 430, height: 76 },
    20,
    { color: palette.muted, alignment: "center" },
  );
}

const endSlide = deck.slides.add();
addFrame(endSlide, 12, {
  paper: palette.navy,
  accent: "#6EA1FF",
  brandColor: "#91B4FF",
  numberColor: "#AFC0D1",
});
addText(
  endSlide,
  "closing-kicker",
  "ABSCHLUSS",
  { left: 72, top: 142, width: 360, height: 32 },
  15,
  { color: "#91B4FF", bold: true },
);
addText(
  endSlide,
  "closing-title",
  "Die zentrale Erkenntnis",
  { left: 72, top: 190, width: 1040, height: 142 },
  48,
  { color: "#FFFFFF", bold: true },
);
addText(
  endSlide,
  "closing-metric",
  "NÄCHSTER SCHRITT",
  { left: 72, top: 354, width: 900, height: 58 },
  30,
  { color: "#6EA1FF", bold: true },
);
addText(
  endSlide,
  "closing-body",
  "Ein prägnanter Abschluss oder der nächste Schritt.",
  { left: 72, top: 432, width: 980, height: 110 },
  25,
  { color: "#D6E0EA" },
);

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const pptx = await PresentationFile.exportPptx(deck);
await pptx.save(outputPath);
