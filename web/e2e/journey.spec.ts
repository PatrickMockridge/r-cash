import { expect, test, type Page } from "@playwright/test";

// The v0.4 payment journey against a running devnet:
// create two wallets, faucet them, fund the sender's account, send a claimable
// transfer, claim it with the recipient, and check the recipient's purse.

const NODE = "http://localhost:40403";
const PASSWORD = "devnet-password";
const DRIP_SETTLE_MS = 10_000;

test.setTimeout(600_000);

async function createWallet(page: Page): Promise<{ address: string; publicKey: string }> {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Wallet" })).toBeVisible({ timeout: 60_000 });

  // A fresh browser context has no saved keystores, so the form opens in create mode.
  const passwords = page.locator('input[type="password"]');
  await passwords.first().fill(PASSWORD);
  await passwords.nth(1).fill(PASSWORD);
  await page.getByRole("button", { name: "Create wallet" }).click();

  await expect(page.getByRole("heading", { name: "Accounts" })).toBeVisible({ timeout: 120_000 });
  await page.getByRole("link", { name: "Receive" }).click();
  const publicKey = await page.getByLabel("Public key").inputValue();
  const address = await page.getByLabel("REV address").inputValue();
  expect(publicKey).toMatch(/^[0-9a-f]{130}$/);
  expect(address).toMatch(/^1111/);
  return { address, publicKey };
}

async function faucet(page: Page, address: string): Promise<void> {
  for (let attempt = 0; attempt < 5; attempt++) {
    const response = await page.request.post(`${NODE}/api/v1/faucet`, {
      data: { address },
    });
    if (response.ok()) return;
    const body = await response.text();
    if (!/rate|fringe/i.test(body)) {
      throw new Error(`faucet ${response.status()}: ${body}`);
    }
    await page.waitForTimeout(2_000);
  }
  throw new Error("faucet did not accept the drip");
}

test("send, claim and see the credit", async ({ browser }) => {
  const senderContext = await browser.newContext();
  const recipientContext = await browser.newContext();
  const sender = await senderContext.newPage();
  const recipient = await recipientContext.newPage();

  const from = await createWallet(sender);
  const to = await createWallet(recipient);

  await faucet(sender, from.address);
  await sender.waitForTimeout(1_500);
  await faucet(recipient, to.address);
  await sender.waitForTimeout(DRIP_SETTLE_MS);
  await recipient.waitForTimeout(DRIP_SETTLE_MS);

  // Fund the sender's account purse from its native REV.
  await sender.getByRole("link", { name: "Accounts" }).click();
  await sender.getByRole("button", { name: "Refresh" }).click();
  await expect(sender.getByRole("button", { name: "Deposit REV" })).toBeEnabled({
    timeout: 120_000,
  });
  await sender.getByLabel("Amount (REV)").fill("0.05");
  await sender.getByRole("button", { name: "Deposit REV" }).click();
  await expect(sender.getByText(/Deposited .* REV into the account/)).toBeVisible({
    timeout: 180_000,
  });

  // Send a claimable transfer to the recipient's public key.
  await sender.getByRole("link", { name: "Pay" }).click();
  await sender.getByLabel("Recipient public key").fill(to.publicKey);
  await sender.getByLabel("Asset", { exact: true }).fill("REV");
  await sender.getByLabel("Amount", { exact: true }).fill("0.01");
  await sender.getByRole("button", { name: "Generate claim secret" }).click();
  await sender.getByRole("button", { name: "Send" }).click();
  const linkInput = sender.getByLabel("Claim link");
  await expect(linkInput).toBeVisible({ timeout: 240_000 });
  const link = await linkInput.inputValue();
  expect(link).toContain("#/claim/rho:id:");
  expect(link).toMatch(/[0-9a-f]{64}$/);

  // Claim it in the recipient's browser context.
  await recipient.goto(link);
  await expect(recipient.getByRole("heading", { name: "Transfer" })).toBeVisible({
    timeout: 60_000,
  });
  const claim = recipient.getByRole("button", { name: "Claim into my account" });
  await expect(claim).toBeEnabled({ timeout: 120_000 });
  await claim.click();
  await expect(recipient.getByText(/Claimed .* into your account/)).toBeVisible({
    timeout: 240_000,
  });
  await expect(recipient.getByText("claimed", { exact: true })).toContainText("claimed");

  // The recipient's REV purse now holds the transfer.
  await recipient.getByRole("link", { name: "Accounts" }).click();
  await recipient.getByRole("button", { name: "Refresh" }).click();
  await expect(recipient.locator(".grid").first()).toContainText("REV purse", {
    timeout: 120_000,
  });
  await expect(recipient.locator(".grid").first()).toContainText("0.01", {
    timeout: 120_000,
  });

  await senderContext.close();
  await recipientContext.close();
});
