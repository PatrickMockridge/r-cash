import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

// The UI journey runs against the local devnet. It creates a fresh wallet, funds it from
// the faucet, opens a vault, borrows NGN, and converts NGN to KES. Oracle prices are
// refreshed from the CLI immediately before each freshness-gated action because the
// devnet's freshness window is 50 fast blocks.
const REPO = process.env.RCASH_REPO ?? "/home/patrick/Rholphin";
const NODE = process.env.RCASH_NODE ?? "http://localhost:40403";

async function refreshOracle(currencies: string[]): Promise<void> {
  const status = await (await fetch(`${NODE}/api/v1/status`)).json();
  const height = String(status.latestBlockNumber);
  const prices: Record<string, string> = {
    REV: "0.05",
    NGN: "0.00066666",
    KES: "0.0076923",
  };
  for (const currency of currencies) {
    for (let index = 0; index < 2; index += 1) {
      execFileSync(
        "cargo",
        [
          "run",
          "-q",
          "-p",
          "rcash-cli",
          "--",
          "oracle",
          "submit",
          "--currency",
          currency,
          "--price",
          prices[currency]!,
          "--height",
          height,
          "--index",
          String(index),
          "--key",
          `reporter${index + 1}`,
        ],
        { cwd: REPO, stdio: "ignore" },
      );
    }
  }
}

test("create a wallet, mint NGN and convert it to KES", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Wallet" })).toBeVisible();

  await page.getByRole("button", { name: "Create", exact: true }).click();
  await page.getByLabel("Password", { exact: true }).fill("e2e-password");
  await page.getByLabel("Confirm password").fill("e2e-password");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Create wallet" }).click();
  await download;

  await expect(page.getByRole("heading", { name: "Accounts" })).toBeVisible();
  const address = (await page.locator(".panel .mono").first().textContent())?.trim() ?? "";
  expect(address).toMatch(/^1111/);

  await page.getByRole("button", { name: "Faucet" }).click();
  // The faucet funds the native REV vault, which pays phlo. The Account itself starts
  // empty, so the signed balance read succeeds with a zero REV row once the faucet lands.
  await expect(async () => {
    await page.getByRole("button", { name: "Refresh" }).click();
    await expect(page.locator("tr", { hasText: "REV" })).toBeVisible({ timeout: 5_000 });
  }).toPass({ timeout: 60_000 });

  // Fund the Account with 0.2 REV, then open and collateralise an NGN vault.
  await page.getByRole("link", { name: "Mint" }).click();
  await page.getByLabel("REV to deposit").fill("0.2");
  await page.getByRole("button", { name: "Deposit REV" }).click();
  await expect(page.getByText("REV deposited into the Account.")).toBeVisible();

  await page.getByRole("button", { name: "Open vault" }).click();
  await expect(page.getByText("Vault opened.")).toBeVisible();
  await page.getByLabel(/Amount/).fill("0.2");
  await page.getByRole("button", { name: "Deposit collateral" }).click();
  await expect(page.getByText("Collateral deposited.")).toBeVisible();

  await refreshOracle(["REV", "NGN"]);
  await page.getByLabel(/Amount/).fill("0.1");
  await page.getByRole("button", { name: "Borrow" }).click();
  await expect(page.getByText("Borrowed.")).toBeVisible();

  // Convert 0.05 NGN to KES.
  await page.getByRole("link", { name: "Convert" }).click();
  await page.getByLabel("Amount").fill("0.05");
  await refreshOracle(["NGN", "KES"]);
  await page.getByRole("button", { name: "Convert", exact: true }).click();
  await expect(page.getByText("Converted")).toBeVisible({ timeout: 60_000 });
});
