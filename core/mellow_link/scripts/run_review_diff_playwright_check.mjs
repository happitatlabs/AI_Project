import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

function parseArgs(argv) {
  const output = {
    baseUrl: "http://127.0.0.1:8000",
    token: "",
    projects: [],
    outputDir: "",
    surfaceMode: "internal",
  };
  for (let index = 2; index < argv.length; index += 1) {
    const current = argv[index];
    if (current === "--base-url") {
      output.baseUrl = argv[++index];
      continue;
    }
    if (current === "--token") {
      output.token = argv[++index];
      continue;
    }
    if (current === "--project") {
      output.projects.push(argv[++index]);
      continue;
    }
    if (current === "--output-dir") {
      output.outputDir = argv[++index];
      continue;
    }
    if (current === "--surface-mode") {
      output.surfaceMode = argv[++index];
    }
  }
  if (!output.token) {
    throw new Error("--token is required");
  }
  if (!output.projects.length) {
    throw new Error("at least one --project is required");
  }
  if (!output.outputDir) {
    output.outputDir = path.resolve("mellow_link", "docs", "validation_runs", "screenshots");
  }
  return output;
}

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function dateTag() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

async function inspectProject(page, baseUrl, projectId, outputDir, surfaceMode) {
  await page.goto(`${baseUrl}/projects/${projectId}/result?surface_mode=${encodeURIComponent(surfaceMode)}`, { waitUntil: "networkidle", timeout: 120000 });
  await page.waitForSelector("#resultView:not(.hidden)", { timeout: 120000 });

  const result = await page.evaluate(() => {
    const section = document.getElementById("reviewDiffSection");
    const internalSurface = document.getElementById("internalSurface");
    const externalSurface = document.getElementById("externalSurface");
    const externalCards = document.getElementById("externalSummaryCardsBox");
    const externalSections = document.getElementById("externalSectionsBox");
    const structural = document.getElementById("reviewDiffStructuralBox");
    const evidence = document.getElementById("reviewDiffEvidenceBox");
    const decision = document.getElementById("reviewDiffDecisionBox");
    const markdown = document.getElementById("reviewDiffMarkdownBox");
    const error = document.getElementById("errorState");
    return {
      hasReviewSection: Boolean(section),
      reviewSectionHidden: section ? section.classList.contains("hidden") : true,
      internalSurfaceHidden: internalSurface ? internalSurface.classList.contains("hidden") : true,
      externalSurfaceHidden: externalSurface ? externalSurface.classList.contains("hidden") : true,
      externalCardsText: externalCards ? externalCards.innerText.trim() : "",
      externalSectionsText: externalSections ? externalSections.innerText.trim() : "",
      structuralText: structural ? structural.innerText.trim() : "",
      evidenceText: evidence ? evidence.innerText.trim() : "",
      decisionText: decision ? decision.innerText.trim() : "",
      markdownText: markdown ? markdown.innerText.trim() : "",
      errorVisible: error ? !error.classList.contains("hidden") : false,
      errorText: error ? error.innerText.trim() : "",
    };
  });

  const screenshotPath = path.join(outputDir, `${dateTag()}-${projectId}-${surfaceMode}-review-diff.png`);
  await page.screenshot({ path: screenshotPath, fullPage: true });
  let expandedScreenshotPath = "";
  let curatedSecondaryScreenshotPath = "";
  let expandedResult = { markdownText: "" };

  if (surfaceMode === "internal") {
    const patternSection = page.locator("#reviewDiffPatternSection");
    const codeDiffSection = page.locator("#codeDiffSection");
    const codeDiffButton = page.locator("#showCodeDiffBtn");
    if (await patternSection.count()) {
      await patternSection.evaluate((node) => {
        node.open = true;
      });
      await page.waitForTimeout(150);
    }
    if (await codeDiffSection.count()) {
      const sectionHidden = await codeDiffSection.evaluate((node) => node.classList.contains("hidden"));
      const buttonVisible = (await codeDiffButton.count()) ? await codeDiffButton.isVisible() : false;
      if (!sectionHidden && buttonVisible) {
        await codeDiffButton.scrollIntoViewIfNeeded();
        await codeDiffButton.click();
        await page.waitForTimeout(200);
        curatedSecondaryScreenshotPath = path.join(outputDir, `${dateTag()}-${projectId}-internal-structure-pattern-expanded.png`);
        await page.screenshot({ path: curatedSecondaryScreenshotPath, fullPage: true });
      }
    }
    const details = page.locator("#reviewDiffSection details");
    const detailsCount = await details.count();
    if (detailsCount) {
      for (let index = 0; index < detailsCount; index += 1) {
        await details.nth(index).evaluate((node) => {
          node.open = true;
        });
      }
      await page.waitForTimeout(150);
      expandedResult = await page.evaluate(() => {
        const markdown = document.getElementById("reviewDiffMarkdownBox");
        return {
          markdownText: markdown ? markdown.innerText.trim() : "",
        };
      });
      expandedScreenshotPath = path.join(outputDir, `${dateTag()}-${projectId}-${surfaceMode}-review-diff-expanded.png`);
      await page.screenshot({ path: expandedScreenshotPath, fullPage: true });
    }
  } else {
    const externalSections = page.locator("#externalSectionsBox");
    if (await externalSections.count()) {
      await externalSections.scrollIntoViewIfNeeded();
      await page.waitForTimeout(200);
      curatedSecondaryScreenshotPath = path.join(outputDir, `${dateTag()}-${projectId}-external-explanation-centered.png`);
      await page.screenshot({ path: curatedSecondaryScreenshotPath });
    }
  }

  return {
    project_id: projectId,
    surface_mode: surfaceMode,
    screenshot_path: screenshotPath,
    expanded_screenshot_path: expandedScreenshotPath,
    curated_secondary_screenshot_path: curatedSecondaryScreenshotPath,
    has_review_section: result.hasReviewSection,
    review_section_hidden: result.reviewSectionHidden,
    internal_surface_hidden: result.internalSurfaceHidden,
    external_surface_hidden: result.externalSurfaceHidden,
    external_cards_text_length: result.externalCardsText.length,
    external_sections_text_length: result.externalSectionsText.length,
    structural_text_length: result.structuralText.length,
    evidence_text_length: result.evidenceText.length,
    decision_text_length: result.decisionText.length,
    markdown_text_length: expandedResult.markdownText.length,
    error_visible: result.errorVisible,
    error_text: result.errorText,
  };
}

async function main() {
  const args = parseArgs(process.argv);
  ensureDir(args.outputDir);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1600, height: 1200 },
    deviceScaleFactor: 1,
  });
  await context.addInitScript((token) => {
    window.localStorage.setItem("authToken", token);
  }, args.token);

  const page = await context.newPage();
  const rows = [];
  for (const projectId of args.projects) {
    rows.push(await inspectProject(page, args.baseUrl, projectId, args.outputDir, args.surfaceMode));
  }

  await context.close();
  await browser.close();
  process.stdout.write(`${JSON.stringify(rows, null, 2)}\n`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
