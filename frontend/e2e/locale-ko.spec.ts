/**
 * Korean-locale rendering test for the view components.
 *
 * Phase C lifted every hardcoded user-facing string in the 6 view
 * components (Dashboard, Incidents, RulesManager, DailyReport, CostMonitor,
 * Settings) into the `supervisor` next-intl namespace. This spec navigates
 * to the `/ko`-prefixed routes and asserts that the Korean copy from the
 * newly added keys actually renders — proving the namespace wiring works
 * end-to-end for the views, not just the chrome.
 */
import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis } from "./helpers";

test.describe("Phase C: Korean locale — view components", () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page);
    await mockAllApis(page);
  });

  test("/ko renders the Korean Dashboard copy", async ({ page }) => {
    await page.goto("/ko");
    // supervisor.dashboard.statEventsToday
    await expect(page.getByText("오늘 이벤트")).toBeVisible();
    // supervisor.dashboard.timelineTitle
    await expect(page.getByText("이벤트 타임라인").first()).toBeVisible();
    // supervisor.dashboard.feedTitle
    await expect(page.getByText("실시간 이벤트 피드")).toBeVisible();
    // supervisor.dashboard.topRulesTitle
    await expect(page.getByText("최다 트리거 규칙")).toBeVisible();
  });

  test("/ko/rules renders the Korean Rules Manager copy", async ({ page }) => {
    await page.goto("/ko/rules");
    // supervisor.rules.heading
    await expect(page.getByText("감사 규칙 관리")).toBeVisible();
    // supervisor.rules.createRule
    await expect(page.getByRole("button", { name: "규칙 생성" })).toBeVisible();
    // supervisor.rules.searchPlaceholder
    await expect(page.getByPlaceholder("이름 또는 패턴으로 규칙 검색...")).toBeVisible();
    // supervisor.rules.colName column header
    await expect(page.getByRole("columnheader", { name: "이름" })).toBeVisible();
  });

  test("/ko/costs renders the Korean Cost Monitor copy", async ({ page }) => {
    await page.goto("/ko/costs");
    // supervisor.costs.consumptionLabel
    await expect(page.getByText("당일 사용량")).toBeVisible();
    // supervisor.costs.trendTitle
    await expect(page.getByText("일일 비용 추이 (30일)")).toBeVisible();
    // supervisor.costs.breakdownTitle
    await expect(page.getByText("실행자별 분석")).toBeVisible();
  });

  test("/ko/incidents renders the Korean Incidents copy", async ({ page }) => {
    await page.goto("/ko/incidents");
    // supervisor.incidents.heading
    await expect(page.getByText("사건 타임라인").first()).toBeVisible();
    // supervisor.incidents.subtitle
    await expect(
      page.getByText("에이전트별로 분류된 차단 이벤트의 포렌식 뷰"),
    ).toBeVisible();
  });

  test("/ko/settings renders the Korean Settings copy", async ({ page }) => {
    await page.goto("/ko/settings");
    // supervisor.settings.platformsTitle
    await expect(page.getByText("에이전트 플랫폼")).toBeVisible();
    // supervisor.settings.notificationsTitle
    await expect(page.getByText("알림 채널")).toBeVisible();
    // supervisor.settings.save
    await expect(page.getByRole("button", { name: "설정 저장" })).toBeVisible();
  });
});
